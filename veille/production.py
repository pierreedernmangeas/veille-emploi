# -*- coding: utf-8 -*-
"""Production d'une candidature : analyse du moteur privé, rédaction Gemini contrôlée, CV + lettre en PDF,
dossier Drive « Recherche emploi/Veille/<date> <entreprise> - <poste> » avec le CV, la lettre et Annonce_et_analyse.txt."""
import os
import re
import tempfile
from datetime import date

from veille import google_acces as G
from veille import redaction_ia as RI


def _nom_dossier(ent: str, poste: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", " ", f"{date.today().isoformat()} {ent} - {poste}").strip()[:120]


def produire(o: dict, m, s, racine_id: str, ia: dict | None, travail: str | None = None) -> dict:
    """o : offre au format radar_commun, déjà notée par traitement.trier. ia : {cle, cfg, compteur} ou None (moteur v12 seul)."""
    OA, AD = m.OA, m.OA.AD
    desc = (o.get("desc") or "").strip()
    if len(desc) < 300:
        return dict(err="annonce non lue en entier : CV non créé")
    contrat = o.get("contrat_n") or o.get("contract") or ""
    contrat = contrat if contrat in ("CDI", "CDD", "V.I.E") else ""
    lieu = str(o.get("location") or "")
    cand = o.get("candidats")
    try:
        cand = int(cand) if cand not in (None, "") else None
    except (TypeError, ValueError):
        cand = None
    travail = travail or tempfile.mkdtemp(prefix="veille_docs_")
    r = OA.analyse_directe(desc, AD.LMC.strip_hf(str(o.get("title") or "")), str(o.get("company") or "").strip() or "Entreprise",
                           lieu.split(",")[0].strip(), str(o.get("country") or ""), cand, contrat, "", travail)
    if r.get("erreur"):
        return dict(err=r["erreur"])
    r["lien"] = o.get("url") or ""
    OA.finir_analyse(r)
    notes = RI.rediger(r, ia["cle"], ia["cfg"], ia["compteur"]) if ia else list(RI.REPLI)
    OA.fabriquer(r)
    r["a_relire"] = list(r.get("a_relire") or []) + notes
    poste = AD.poste_lm(r["titre"])
    dossier_id = G.dossier(s.drive, ["Veille", _nom_dossier(r["ent"], poste)], racine_id)
    txt = os.path.join(r["wd"], "Annonce_et_analyse.txt")
    with open(txt, "w", encoding="utf8") as f:
        f.write(OA.texte_analyse(r))
    cv = G.televerser(s.drive, r["cv_pdf"], dossier_id, "application/pdf")
    lm = G.televerser(s.drive, r["lm_pdf"], dossier_id, "application/pdf")
    G.televerser(s.drive, txt, dossier_id, "text/plain")
    mail, objet = OA.consigne_mail(desc)
    return dict(cv=cv, lm=lm, dossier=G.lien_dossier(s.drive, dossier_id), dossier_id=dossier_id, cv_local=r["cv_pdf"], lm_local=r["lm_pdf"],
                mail=mail, objet=objet, poste=poste, ent=r["ent"], note=r["note"]["total"], lang=r["spec"]["lang"], alertes=r["a_relire"],
                forts=r.get("forts") or [], manques=r.get("faibles") or [])
