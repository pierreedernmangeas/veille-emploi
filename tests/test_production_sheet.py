import json
import os

import pytest

from tests.conftest import OFFRE_CV
from tests.faux_google import faux_services
from veille import historique, production as P
from veille.base import Base
from veille.modele import Offre, cle
from veille.sheet import COLONNES_A_POSTULER, Veille

REEL = os.path.join(OFFRE_CV, "tests", "reel", "suivi_offres.json")


def _telespazio():
    if not os.path.exists(REEL):
        pytest.skip("offres réelles absentes de cette machine")
    v = json.load(open(REEL, encoding="utf8"))["values"]
    x = next(r for r in v[1:] if "elespazio" in r[1])
    return dict(source="LinkedIn", title=x[2], company=x[1], location=x[3], country="France", desc=x[17], contract=x[4], url="https://www.linkedin.com/jobs/view/1/",
                note=8.5, categorie="CDD France", posted=None, candidats=None)


def test_produire_offre_reelle(moteur_local, tmp_path):
    s = faux_services()
    racine = s.drive.ajouter("Recherche emploi", "root", mime=s.drive.FOLDER)
    res = P.produire(_telespazio(), moteur_local, s, racine, ia=None, travail=str(tmp_path))
    assert res["poste"] == "Acheteur junior"
    noms = sorted(f["name"] for f in s.drive.fichiers.values() if f.get("parents") == [res["dossier_id"]])
    assert len(noms) == 3 and "Annonce_et_analyse.txt" in noms and sum(n.endswith(".pdf") for n in noms) == 2
    assert res["cv"] and res["lm"] and res["dossier"].startswith("https://drive.google.com/")
    assert res["alertes"] and "IA indisponible" in " ".join(res["alertes"])          # sans clé : moteur v12, signalé


def test_ligne_sheet_colonnes():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    o = dict(title="Acheteur junior", company="Démo", location="Lyon", country="France", url="https://ex/1", note=8.0, categorie="CDI France",
             contrat_n="CDI", posted=None, candidats=12, forts=["Achats"], manques=["SAP"], cle="demo|acheteur junior")
    docs = dict(cv="https://d/cv", lm="https://d/lm", dossier="https://d/dos", mail="rh@demo.fr", brouillon="https://mail/1")
    v.a_postuler_ajouter([v.ligne_a_postuler(o, docs)])
    lignes = s.gc.open_by_key("sheet1").worksheet("À postuler").get_all_values()
    assert lignes[0] == COLONNES_A_POSTULER
    d = dict(zip(lignes[0], lignes[1]))
    assert d["Poste"] == "Acheteur junior" and d["Candidature"] == "Mail (brouillon prêt)" and d["Statut"] == "À envoyer" and d["Clé"] == "demo|acheteur junior"
    assert d["CV"] == "CV" and d["Offre"] == "Ouvrir"                 # liens courts et cliquables
    v.statut_maj("demo|acheteur junior", Statut="Envoyée", **{"Date d'envoi": "2026-11-13"})
    st = v.statuts_lire()
    assert st[0]["Statut"] == "Envoyée" and st[0]["Date d'envoi"] == "2026-11-13"


def test_texte_jamais_formule():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    o = dict(title="=HYPERLINK(\"x\")", company="+Démo", url="https://ex/1", note=7, cle="k")
    v.a_postuler_ajouter([v.ligne_a_postuler(o, {})])
    f = s.gc.open_by_key("sheet1").worksheet("À postuler")
    d = dict(zip(f.get_all_values()[0], f.lignes[1]))                # valeurs saisies : apostrophe devant, jamais une formule
    assert d["Poste"].startswith("'=") and d["Entreprise"].startswith("'+")


def test_historique_importe_deja_vues(tmp_path):
    s = faux_services()
    c = s.gc.open_by_key("suivi")
    f = c.add_worksheet("Offres")
    f.append_rows([["Date", "Entreprise", "Poste", "Lien de l'offre"], ["2026-11-10", "Telespazio", "Acheteur.euse - Junior (F/H)", "https://www.linkedin.com/jobs/view/42/?trk=x"]])
    c2 = s.gc.open_by_key("cand")
    c2.add_worksheet("Feuille 1").append_rows([["Date", "Company", "Job title", "URL"], ["2026-10-01", "Bosch", "Junior Buyer", ""]])
    base = Base(str(tmp_path / "v.sqlite"))
    n = historique.importer(s, base, {"suivi_offres": "suivi", "candidatures": "cand"})
    assert n == 2
    assert base.connue(Offre("Indeed", "Acheteur.euse - Junior (F/H)", "Telespazio"))
    assert base.connue(Offre("LinkedIn", "Autre titre", "Autre", url="https://www.linkedin.com/jobs/view/42/"))
    assert base.connue(Offre("LinkedIn", "Junior Buyer", "Bosch"))


def test_entreprises_lire_et_memoriser_adresse():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    v.entreprises_initialiser([{"nom": "Démo", "url": "https://www.demo.fr/carrieres"}])
    assert v.entreprises_lire() == [("Démo", "https://www.demo.fr/carrieres")]
    v.entreprises_maj([{"entreprise": "Démo", "methode": "navigateur -> workday", "offres": 3, "erreur": ""}], {"Démo": "https://demo.wd3.myworkdayjobs.com/Ext"})
    assert v.entreprises_lire() == [("Démo", "https://demo.wd3.myworkdayjobs.com/Ext")]


def test_onglet_sans_en_tete_repare():
    """Onglet « Entreprises » rempli sans ligne d'en-tête (veille interrompue) : l'en-tête est réinséré, rien n'est perdu."""
    s = faux_services()
    c = s.gc.open_by_key("sheet1")
    f = c.add_worksheet("Entreprises")
    f.append_rows([["Airbus", "https://ag.wd3.myworkdayjobs.com/Airbus", "", "", "", "https://ag.wd3.myworkdayjobs.com/Airbus", ""]])
    v = Veille(s.gc, "sheet1")
    assert v.entreprises_lire() == [("Airbus", "https://ag.wd3.myworkdayjobs.com/Airbus")]
    assert c.worksheet("À postuler").get_all_values()[0][0] == "Vue le"
