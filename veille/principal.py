# -*- coding: utf-8 -*-
"""Une veille complète : collecte (toutes les sources en parallèle) → nouvelles offres → tri et note → CV + lettre pour les
meilleures (Gemini contrôlé, sinon moteur v12) → brouillons Gmail si l'annonce donne une adresse → suivi des candidatures →
Sheet « Veille emploi » → récap envoyé à soi-même. La base est sauvée sur Drive après chaque offre produite (reprise sûre).

Usage : python -m veille.principal --moment matin|midi|soir [--essai] [--forcer]
Les journaux ne contiennent que des compteurs et des noms de sources (dépôt public, journaux GitHub visibles)."""
import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from veille import candidatures as CA
from veille import config, historique, recap
from veille import google_acces as G
from veille import production as P
from veille.base import Base
from veille.modele import cle, maintenant, vers_rc
from veille.sheet import Veille
from veille.sources import Contexte, tout_collecter
from veille.traitement import trier

SECRETS = ["APIFY_TOKEN", "GEMINI_API_KEY", "FT_CLIENT_ID", "FT_CLIENT_SECRET", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "VIE_API_KEY"]
MARGE = timedelta(minutes=30)
ESSAIS_MAX = 3                                  # une offre qui fait planter la production est retentée 3 fois, puis laissée de côté
ATTENDUES = {"LinkedIn (JobSpy)", "Sites d'emploi", "Sites carrières", "V.I.E"}     # 0 offre sans erreur = anomalie probable                   # recouvrement entre deux veilles : rien ne passe entre les mailles


@dataclass
class Dependances:
    services: object
    moteur: object
    modules: list
    ids: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)
    base_chemin: str | None = None
    travail: str | None = None
    local: bool = False                         # essai : base et documents restent sur la machine


def doit_tourner(moment: str, maintenant_utc: datetime, cfg: dict) -> bool:
    """Deux horaires UTC par moment (heure d'été / d'hiver) : seul celui qui tombe à l'heure de Paris prévue (± 40 min) tourne."""
    h, m = (int(x) for x in cfg["heures"][moment].split(":"))
    paris = maintenant_utc.astimezone(ZoneInfo("Europe/Paris"))
    return abs((paris - paris.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds()) <= 40 * 60


def doit_tourner_cron(cron: str, moment: str, maintenant_utc: datetime, cfg: dict) -> bool:
    """L'horaire UTC déclenché (« 47 4 * * * ») + le décalage de Paris du jour doit tomber sur l'heure prévue du moment.
    Indépendant du retard de GitHub : l'horaire d'été ne tourne jamais en hiver, et un horaire en retard n'est jamais sauté."""
    mn, h = (int(x) for x in cron.split()[:2])
    decalage = int(maintenant_utc.astimezone(ZoneInfo("Europe/Paris")).utcoffset().total_seconds() // 60)
    hh, mm = (int(x) for x in cfg["heures"][moment].split(":"))
    return (h * 60 + mn + decalage) % 1440 == hh * 60 + mm


def modules_sources() -> list:
    from veille.sources import alertes_mail, api_officielles, linkedin_apify, linkedin_jobspy, sites_carrieres, sites_emploi, vie
    return [linkedin_apify, linkedin_jobspy, alertes_mail, sites_emploi, api_officielles, vie, sites_carrieres]


def compte_attendu(ids: dict) -> str:
    """Le compte Google attendu est dans le secret VEILLE_IDS (clé « compte »), jamais dans le dépôt public."""
    if not ids.get("compte"):
        raise RuntimeError("Le secret VEILLE_IDS doit contenir la clé « compte » (ton adresse Gmail pro) : voir docs/MISE_EN_PLACE.md.")
    return ids["compte"]


def dependances_reelles() -> Dependances:
    from veille import moteur_prive
    ids = json.loads(os.environ.get("VEILLE_IDS") or "{}")
    s = G.services(os.environ["GOOGLE_TOKEN"])
    G.verifier_compte(s, compte_attendu(ids))
    return Dependances(services=s, moteur=moteur_prive.installer(s, ids=ids), modules=modules_sources(), ids=ids,
                       secrets={k: os.environ.get(k, "") for k in SECRETS})


def dependances_essai(sortie: str) -> Dependances:
    """Sources réelles, Google factice (rien n'est écrit ni envoyé), moteur privé pris sur cette machine."""
    import subprocess
    import tarfile
    from tests.faux_google import faux_services
    from veille import moteur_prive
    source = os.environ.get("VEILLE_MOTEUR_SOURCE", "/home/user/offre_cv")
    d = os.path.join(sortie, "moteur")
    os.makedirs(d, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(config.ICI, "outils", "emballer_moteur.py"), source, os.path.join(d, "moteur.tar.gz")], check=True, capture_output=True)
    with tarfile.open(os.path.join(d, "moteur.tar.gz")) as t:
        t.extractall(d, filter="data")
    s = faux_services()
    rech = s.drive.ajouter("Recherche emploi", "root", mime=s.drive.FOLDER)
    return Dependances(services=s, moteur=moteur_prive.charger(d), modules=[m for m in modules_sources() if m.NOM != "Alertes mail"],
                       ids={"recherche_emploi": rech, "veille": "essai"}, secrets={k: os.environ.get(k, "") for k in SECRETS},
                       base_chemin=os.path.join(sortie, "veille.sqlite"), travail=os.path.join(sortie, "documents"), local=True)


def _sheet_id(s, racine: str, ids: dict) -> str:
    if ids.get("veille"):
        return ids["veille"]
    f = G.trouver(s.drive, "Veille emploi", racine)
    return f["id"] if f else s.gc.create("Veille emploi", folder_id=racine).id


def veille(moment: str, essai: bool = False, deps: Dependances | None = None, cfg: dict | None = None, rech: dict | None = None, journal=print) -> dict:
    t0 = datetime.now(timezone.utc)
    cfg = cfg or config.charger()
    rech = rech if rech is not None else config.recherches()
    if deps is None:
        deps = dependances_essai(os.path.join(config.ICI, "sortie_essai")) if essai else dependances_reelles()
    s = deps.services
    try:
        return _veille(moment, deps, cfg, rech, journal, t0)
    except Exception as e:
        try:                                    # le détail part dans le récap (à soi seul), jamais dans le journal public
            recap.envoyer(s.gmail, s.email, dict(moment=moment, nouvelles=0, gardees=0, documents=0, brouillons=0, relances=0, top=[],
                                                 erreurs=[f"Veille interrompue : {type(e).__name__}: {str(e)[:300]}"]))
        except Exception:
            pass
        raise


def _veille(moment, deps, cfg, rech, journal, t0) -> dict:
    s, m = deps.services, deps.moteur
    racine = deps.ids.get("recherche_emploi") or G.dossier(s.drive, ["Recherche emploi"])
    conf = G.dossier(s.drive, ["Veille_config"], racine)
    base = Base(deps.base_chemin) if deps.local else Base.ouvrir_depuis_drive(s, conf, deps.base_chemin)

    def sauver():
        if not deps.local:
            base.sauver_vers_drive(s, conf)

    v = Veille(s.gc, _sheet_id(s, racine, deps.ids))
    derniere = base.meta("derniere_veille")
    premier = derniere is None
    if premier:
        journal("Premier passage : historique importé,", historique.importer(s, base, deps.ids), "lignes")
        depuis = maintenant() - timedelta(days=cfg.get("jours_premier_passage", 7))
    else:
        depuis = datetime.fromisoformat(derniere) - MARGE
    v.entreprises_initialiser(rech.get("entreprises", []))
    ctx = Contexte(cfg=cfg, rech=rech, depuis=depuis, moment=moment, services=s, secrets=deps.secrets, moteur=m,
                   entreprises=[{"nom": n, "url": u} for n, u in v.entreprises_lire()])

    # 1) collecte
    offres, sante = tout_collecter(ctx, deps.modules)
    for x in sante:
        lus = ctx.budget.get("alertes_mails_lus", 0) if x.source == "Alertes mail" else 0
        if x.n == 0 and not x.erreur and (x.source in ATTENDUES or lus):
            x.erreur = f"0 offre ({lus} mails lus) : format changé ?" if lus else "0 offre : format changé ou blocage ?"
    for x in sorted(sante, key=lambda x: x.source):
        journal(f"{x.source} : {x.n} offres en {x.duree_s:.0f} s" + (" (erreur)" if x.erreur else ""))
    lot = Base.fusionner_lot(offres)
    nouv = base.nouvelles(lot)
    journal(f"Collecte : {len(offres)} offres, {len(lot)} uniques, {len(nouv)} nouvelles")

    # 2) tri et note
    par_cle = {cle(o): o for o in nouv}
    rows = [dict(vers_rc(o), cle=k) for k, o in par_cle.items()]
    gardees, rejets = trier(rows, m, max_age_days=cfg.get("jours_premier_passage", 7) if premier else None)
    gardees_cles = {o["cle"] for o in gardees}
    for k, o in par_cle.items():
        if k not in gardees_cles:
            base.ajouter(o, "rejetee")
    journal(f"Tri : {len(gardees)} gardées, {sum(rejets.values())} écartées")

    # 3) CV + lettres pour les meilleures, puis lignes du Sheet. Une erreur sur une offre n'arrête pas les autres : l'offre est
    #    retentée aux veilles suivantes, ESSAIS_MAX fois au plus. La base est sauvée sur Drive dès qu'un brouillon existe.
    ia = {"cle": deps.secrets.get("GEMINI_API_KEY", ""), "cfg": cfg, "compteur": {}}
    n_docs, n_brouillons, top, erreurs_offres = 0, 0, [], []
    for o in gardees:
        note = o.get("note") or 0
        if note < cfg.get("seuil_liste", 6):
            base.ajouter(par_cle[o["cle"]], "gardee")
            continue
        try:
            docs = {}
            if note >= cfg.get("seuil_documents", 7) and n_docs < cfg.get("max_documents", 40):
                docs = P.produire(o, m, s, racine, ia, travail=deps.travail)
                if docs.get("err"):
                    docs = {}
                else:
                    n_docs += 1
            base.ajouter(par_cle[o["cle"]], "documents" if docs else "liste")
            if docs:
                base.marquer(o["cle"], note=note, dossier=docs["dossier"], cv=docs["cv"], lm=docs["lm"])
                sauver()
                try:                            # une adresse refusée par Gmail ne doit pas faire perdre la ligne du Sheet
                    b = CA.preparer_brouillon(s.gmail, dict(cle=o["cle"], mail=docs["mail"], objet=docs["objet"], poste=docs["poste"], ent=docs["ent"],
                                                            lien=o.get("url", ""), lang=docs["lang"], cv_local=docs["cv_local"], lm_local=docs["lm_local"]), base)
                except Exception as e:
                    erreurs_offres.append("brouillon " + type(e).__name__)
                    b = None
                if b:
                    sauver()                    # le brouillon est connu de la base sur Drive avant toute autre écriture
                    docs["brouillon"] = b[1]
                    n_brouillons += 1
            else:
                base.marquer(o["cle"], note=note)
            v.a_postuler_ajouter([v.ligne_a_postuler(o, docs)])
            top.append(o)
            sauver()
        except Exception as e:
            erreurs_offres.append(type(e).__name__)
            if base.connue(par_cle[o["cle"]]):  # documents déjà enregistrés : ne pas les refaire
                sauver()
                continue
            n = int(base.meta("essais:" + o["cle"]) or 0) + 1
            base.meta("essais:" + o["cle"], str(n))
            if n >= ESSAIS_MAX:
                base.ajouter(par_cle[o["cle"]], "echec")
            sauver()
    v.toutes_ajouter([v.ligne_toutes(o) for o in gardees])

    # 4) suivi des candidatures, santé des sources, entreprises
    suivi = CA.suivre(s.gmail, v, base, date.today(), cfg.get("relance_jours", 7))
    v.sources_ecrire(sante, moment)
    v.entreprises_maj(ctx.budget.get("sites_carrieres", []), ctx.budget.get("entreprises_detectees", {}))
    base.meta("derniere_veille", t0.isoformat(timespec="seconds"))
    sauver()

    # 5) récap, à soi seul
    resume = dict(moment=moment, nouvelles=len(nouv), gardees=len(gardees), documents=n_docs, brouillons=n_brouillons, relances=suivi["relances"], top=top[:10],
                  erreurs=[f"{x.source} : {x.erreur[:120]}" for x in sante if x.erreur] + list(ctx.budget.get("notes_sources", []))[:10]
                  + ([f"Production : {len(erreurs_offres)} offre(s) en erreur ({', '.join(sorted(set(erreurs_offres)))}), retentées à la prochaine veille"]
                     if erreurs_offres else []) + ([f"Suivi Gmail : {suivi['erreurs']} fil(s) illisible(s)"] if suivi.get("erreurs") else []),
                  lien_sheet=getattr(v.classeur, "url", ""), appels_ia=ia["compteur"].get("appels", 0))
    recap.envoyer(s.gmail, s.email, resume)
    journal(f"Fini : {n_docs} CV + lettres, {n_brouillons} brouillons, {suivi['envoyees']} envois vus, {suivi['relances']} relances, "
            f"{ia['compteur'].get('appels', 0)} appels IA, {(datetime.now(timezone.utc) - t0).total_seconds() / 60:.0f} min")
    return {k: v_ for k, v_ in resume.items() if k != "top"}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description="Veille emploi")
    a.add_argument("--moment", choices=["matin", "midi", "soir"], required=True)
    a.add_argument("--essai", action="store_true", help="sources réelles, Google factice, sortie dans sortie_essai/")
    a.add_argument("--forcer", action="store_true", help="tourne même hors de l'heure prévue")
    a.add_argument("--cron", default="", help="horaire GitHub déclenché (garde été / hiver)")
    x = a.parse_args(argv)
    maintenant_utc = datetime.now(timezone.utc)
    if not (x.forcer or x.essai):
        ok = doit_tourner_cron(x.cron, x.moment, maintenant_utc, config.charger()) if x.cron else doit_tourner(x.moment, maintenant_utc, config.charger())
        if not ok:
            print(f"Pas l'heure de la veille « {x.moment} » à Paris (horaire d'été / d'hiver) : rien à faire.")
            return 0
    try:
        veille(x.moment, essai=x.essai)
    except Exception as e:                      # dépôt public : jamais de trace (code du moteur privé, données) dans le journal
        print(f"Veille interrompue : {type(e).__name__}. Le détail est dans le mail récap et l'onglet Sources.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
