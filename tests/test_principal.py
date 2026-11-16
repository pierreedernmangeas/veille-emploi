import re
from datetime import datetime, timezone

import pytest

from tests.faux_google import faux_services
from veille import principal as PR, production
from veille.modele import Offre
from veille.sources import Contexte  # noqa: F401

CFG = {"seuil_documents": 5, "seuil_liste": 4, "max_documents": 40,
       "jours_premier_passage": 7, "relance_jours": 7, "heures": {"matin": "06:47", "midi": "13:17", "soir": "18:37"},
       "sites_carrieres": {"complet": ["matin"], "leger": ["midi", "soir"]}, "gemini": {"modele": "x", "max_appels": 60}}
DESC = ("Nous recrutons un Acheteur junior (H/F) en CDI à Lyon. Rattaché au responsable achats, vous suivez les commandes fournisseurs, "
        "relancez les retards de livraison, analysez les écarts de prix, participez aux appels d'offres et mettez à jour les indicateurs "
        "de performance fournisseurs. Profil : Bac+5 école de commerce, spécialisation achats ou supply chain, première expérience en "
        "stage, jeune diplômé bienvenu, anglais professionnel, Excel. Contrat : CDI. Candidature par mail à recrutement@demo-indus.fr")


class Coupure(BaseException):
    """Arrêt brutal (délai du job GitHub, machine coupée) : rien ne l'attrape."""


def test_doit_tourner_ete_hiver():
    assert PR.doit_tourner("matin", datetime(2027, 1, 15, 5, 47, tzinfo=timezone.utc), CFG)
    assert not PR.doit_tourner("matin", datetime(2027, 1, 15, 4, 47, tzinfo=timezone.utc), CFG)
    assert PR.doit_tourner("matin", datetime(2026, 7, 15, 4, 47, tzinfo=timezone.utc), CFG)
    assert not PR.doit_tourner("midi", datetime(2026, 7, 15, 4, 47, tzinfo=timezone.utc), CFG)


class Source:
    NOM = "Factice"

    def __init__(self, offres):
        self.offres = offres

    def collecter(self, ctx):
        return list(self.offres)


def _offres():
    a = Offre("Indeed", "Acheteur junior (H/F)", "Démo Industrie", lieu="Lyon", pays="France", url="https://ex.fr/1", description=DESC, contrat_brut="CDI")
    b = Offre("LinkedIn", "Acheteur Junior H/F", "Démo Industrie SAS", lieu="Lyon, France", pays="France", url="https://www.linkedin.com/jobs/view/9/",
              description=DESC, contrat_brut="CDI")
    c = Offre("Indeed", "Magasinier cariste", "Entrepôt X", lieu="Lille", pays="France", url="https://ex.fr/3", description=DESC.replace("Acheteur", "Magasinier"))
    return [a, b, c]


def _deps(s, moteur, modules, tmp_path):
    rech = s.drive.ajouter("Recherche emploi", "root", mime=s.drive.FOLDER)
    return PR.Dependances(services=s, moteur=moteur, modules=modules, ids={"recherche_emploi": rech, "veille": "sheet1"}, secrets={},
                          base_chemin=str(tmp_path / "veille.sqlite"), travail=str(tmp_path / "docs"))


def _dossiers(s):
    veille = [f["id"] for f in s.drive.fichiers.values() if f["name"] == "Veille"]
    return [f for f in s.drive.fichiers.values() if f.get("parents") and f["parents"][0] in veille]


def test_veille_essai_bout_en_bout(moteur_local, tmp_path):
    s = faux_services()
    res = PR.veille("matin", deps=_deps(s, moteur_local, [Source(_offres())], tmp_path), cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    lignes = s.gc.open_by_key("sheet1").worksheet("À postuler").get_all_values()
    assert len(lignes) == 2, lignes                                        # en-tête + 1 offre (doublon fusionné, hors cible écarté)
    assert len(_dossiers(s)) == 1 and len(s.gmail.brouillons) == 1
    envois = [a for a in s.gmail.appels if a[0] == "messages.send"]
    assert len(envois) == 1                                                # le récap seul, à soi-même
    assert res["nouvelles"] == 2 and res["documents"] == 1


def test_reprise_apres_plantage(moteur_local, tmp_path, monkeypatch):
    s = faux_services()
    autre = Offre("Indeed", "Acheteur junior (H/F)", "Autre Groupe", lieu="Lyon", pays="France", url="https://ex.fr/7", description=DESC.split(" Candidature par mail")[0] + " Postulez sur notre site carrières.",
                  contrat_brut="CDI")
    deps = _deps(s, moteur_local, [Source(_offres()[:1] + [autre])], tmp_path)
    vrai, n = production.produire, []

    def produire_puis_planter(*a, **k):
        if n:
            raise Coupure("délai GitHub dépassé")
        n.append(1)
        return vrai(*a, **k)
    monkeypatch.setattr(PR.P, "produire", produire_puis_planter)
    with pytest.raises(Coupure):
        PR.veille("matin", deps=deps, cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    monkeypatch.setattr(PR.P, "produire", vrai)
    PR.veille("matin", deps=deps, cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    noms = sorted(f["name"] for f in _dossiers(s))
    assert len(noms) == 2 and len(set(noms)) == 2                          # une seule fois chaque offre
    assert len(s.gmail.brouillons) == 1                                    # une seule offre donne une adresse
    lignes = s.gc.open_by_key("sheet1").worksheet("À postuler").get_all_values()
    assert len(lignes) == 3


def test_journaux_sans_donnees_perso(moteur_local, tmp_path):
    s = faux_services()
    sortie = []
    PR.veille("matin", deps=_deps(s, moteur_local, [Source(_offres())], tmp_path), cfg=CFG, rech={"entreprises": []}, journal=lambda *a: sortie.append(" ".join(map(str, a))))
    texte = "\n".join(sortie)
    assert sortie and "@" not in texte and not re.search(r"\+33|\b0[67](\s?\d{2}){4}\b", texte)
    assert "Démo" not in texte and "Acheteur" not in texte


def test_compte_attendu_vient_du_secret():
    assert PR.compte_attendu({"compte": "moi@exemple.fr"}) == "moi@exemple.fr"
    with pytest.raises(RuntimeError) as e:
        PR.compte_attendu({})
    assert "VEILLE_IDS" in str(e.value) and "@" not in str(e.value)


def test_aucune_adresse_perso_dans_le_depot():
    import subprocess
    from tests.conftest import RACINE
    fichiers = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True, text=True).stdout.split()
    trouves = [f for f in fichiers if not f.startswith("docs/superpowers/")
               and re.search(r"[\w.]+@gmail\.com|\+33\s?\d", open(f"{RACINE}/{f}", encoding="utf8", errors="ignore").read())]
    assert trouves == []


def test_garde_selon_l_horaire_declenche():
    hiver_retard = datetime(2027, 1, 15, 5, 25, tzinfo=timezone.utc)                # horaire d'été déclenché en hiver avec 38 min de retard
    assert not PR.doit_tourner_cron("47 4 * * *", "matin", hiver_retard, CFG)
    assert PR.doit_tourner_cron("47 5 * * *", "matin", datetime(2027, 1, 15, 7, 10, tzinfo=timezone.utc), CFG)   # bon horaire, 83 min de retard
    assert PR.doit_tourner_cron("47 4 * * *", "matin", datetime(2026, 7, 15, 4, 50, tzinfo=timezone.utc), CFG)
    assert not PR.doit_tourner_cron("47 5 * * *", "matin", datetime(2026, 7, 15, 5, 50, tzinfo=timezone.utc), CFG)


def test_offre_en_erreur_n_arrete_pas_la_veille(moteur_local, tmp_path, monkeypatch):
    s = faux_services()
    deps = _deps(s, moteur_local, [Source(_offres())], tmp_path)
    appels = []

    def casse(*a, **k):
        appels.append(1)
        raise ValueError("moteur : cas imprévu")
    monkeypatch.setattr(PR.P, "produire", casse)
    for _ in range(4):
        res = PR.veille("matin", deps=deps, cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    assert len(appels) == 3                                                    # 3 essais, puis l'offre est laissée de côté
    assert any("ValueError" in e for e in res["erreurs"]) or len(appels) == 3
    assert len([a for a in s.gmail.appels if a[0] == "messages.send"]) == 4  # un récap à chaque veille


def test_brouillon_sauve_avant_le_sheet(moteur_local, tmp_path, monkeypatch):
    s = faux_services()
    deps = _deps(s, moteur_local, [Source(_offres())], tmp_path)
    deps.local = False                                                         # base envoyée sur le Drive factice comme en production
    vrai = PR.Veille.a_postuler_ajouter

    def coupe(self, lignes):
        raise Coupure("coupure juste après le brouillon")
    monkeypatch.setattr(PR.Veille, "a_postuler_ajouter", coupe)
    with pytest.raises(Coupure):
        PR.veille("matin", deps=deps, cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    monkeypatch.setattr(PR.Veille, "a_postuler_ajouter", vrai)
    PR.veille("matin", deps=deps, cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    assert len(s.gmail.brouillons) == 1 and len(_dossiers(s)) == 1


def test_source_vide_signalee(moteur_local, tmp_path):
    s = faux_services()
    vide = Source([])
    vide.NOM = "Sites d'emploi"
    res = PR.veille("matin", deps=_deps(s, moteur_local, [Source(_offres()), vide], tmp_path), cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    assert any("Sites d'emploi" in e and "0 offre" in e for e in res["erreurs"])
    src = s.gc.open_by_key("sheet1").worksheet("Sources").get_all_values()
    assert any(l[2] == "Sites d'emploi" and "0 offre" in l[5] for l in src[1:])


def test_echec_sans_details_dans_le_journal(monkeypatch, capsys):
    def boum(*a, **k):
        raise RuntimeError("détail privé du moteur")
    monkeypatch.setattr(PR, "veille", boum)
    assert PR.main(["--moment", "matin", "--forcer"]) == 1
    out = capsys.readouterr()
    assert "détail privé" not in out.out + out.err and "RuntimeError" in out.out


def test_aucun_fait_du_cv_dans_le_depot():
    """Mots tirés du moteur privé (contact, nom, école, employeur du stage) : aucun ne doit apparaître dans les fichiers publiés."""
    import json
    import os
    import subprocess
    from tests.conftest import OFFRE_CV, RACINE
    banque = os.path.join(OFFRE_CV, "cv_bank.json")
    if not os.path.exists(banque):
        pytest.skip("moteur privé absent de cette machine")
    b = json.load(open(banque, encoding="utf8"))["base"]["fr"]
    nom = re.search(r'NOM = "([^"]+)"', open(os.path.join(OFFRE_CV, "mails.py"), encoding="utf8").read()).group(1)
    ecole = re.search(r"\b[A-Z]{4,}\b", b["neoma"]["title"] + " " + json.dumps(b["neoma"], ensure_ascii=False))
    mots = list(b["contact"][:3]) + [b["ip"]["org"].split(",")[0], nom, nom.split()[-1].capitalize()] + ([ecole.group(0)] if ecole else [])
    fichiers = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True, text=True).stdout.split()
    trouves = {f: m for f in fichiers if not f.startswith("docs/superpowers/")
               for m in mots if m and m in open(f"{RACINE}/{f}", encoding="utf8", errors="ignore").read()}
    assert trouves == {}


def test_secret_mal_colle_nomme_sans_contenu(monkeypatch, capsys):
    monkeypatch.setenv("VEILLE_IDS", "{“compte”: “moi@exemple.fr”}")         # guillemets typographiques (copier-coller)
    monkeypatch.setenv("GOOGLE_TOKEN", '{"client_id": "x"}')
    assert PR.main(["--moment", "matin", "--forcer"]) == 1
    out = capsys.readouterr().out
    assert "VEILLE_IDS" in out and "moi@exemple" not in out and "guillemets" in out


def test_jeton_google_incomplet_nomme(monkeypatch, capsys):
    monkeypatch.setenv("VEILLE_IDS", '{"compte": "moi@exemple.fr"}')
    monkeypatch.setenv("GOOGLE_TOKEN", '{"client_id": "x", "client_secret": "y"}')
    assert PR.main(["--moment", "matin", "--forcer"]) == 1
    out = capsys.readouterr().out
    assert "GOOGLE_TOKEN" in out and "refresh_token" in out and '"y"' not in out


def test_echec_indique_l_endroit_dans_le_code_public(monkeypatch, capsys):
    def boum(*a, **k):
        int("pas un nombre : détail privé")
    monkeypatch.setattr(PR, "veille", boum)
    assert PR.main(["--moment", "matin", "--forcer"]) == 1
    out = capsys.readouterr().out
    assert "ValueError" in out and "test_principal.py" in out and "détail privé" not in out


def test_onglet_de_la_veille_cree(moteur_local, tmp_path):
    s = faux_services()
    PR.veille("midi", deps=_deps(s, moteur_local, [Source(_offres())], tmp_path), cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    c = s.gc.open_by_key("sheet1")
    onglets = [w for w in c.worksheets() if w.title.endswith(" midi")]
    assert len(onglets) == 1 and c.worksheets()[1] is onglets[0]
    lignes = onglets[0].get_all_values()
    assert len(lignes) == 2 and "Acheteur" in lignes[1][1]
    suivi = c.worksheet("À postuler").get_all_values()
    assert suivi[1][1] == onglets[0].title                                  # colonne « Veille » du suivi global


def test_reconstruction_une_seule_fois(moteur_local, tmp_path, monkeypatch):
    s = faux_services()
    appels = []
    vrai = PR.Veille.reconstruire

    def compte(self, lignes):
        appels.append(len(lignes))
        return vrai(self, lignes)
    monkeypatch.setattr(PR.Veille, "reconstruire", compte)
    deps = _deps(s, moteur_local, [Source(_offres())], tmp_path)
    PR.veille("matin", deps=deps, cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    PR.veille("midi", deps=deps, cfg=CFG, rech={"entreprises": []}, journal=lambda *a: None)
    assert len(appels) == 1
