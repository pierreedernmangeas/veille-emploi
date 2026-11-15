"""Mise en page du Sheet « Veille emploi » : un onglet par veille, liens courts, suivi global propre, ancien format repris."""
from datetime import datetime

from tests.faux_google import FauxClasseur, faux_services
from veille.sheet import COLONNES_A_POSTULER, COLONNES_VEILLE, ONGLETS_VEILLE_MAX, Veille


def _o(titre, note, ent="Démo"):
    return dict(title=titre, company=ent, location="Lyon", country="France", url=f"https://ex/{titre}", note=note, categorie="CDI France",
                contrat_n="CDI", cle=f"{ent}|{titre}")


DOCS = dict(cv="https://drive/cv", lm="https://drive/lm", dossier="https://drive/dos")


def test_onglet_par_veille_trie_par_note_et_liens_courts():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    v.onglet_veille("matin", [(_o("Acheteur", 7.5), DOCS), (_o("Buyer", 9), DOCS), (_o("Planner", 6), {})], datetime(2026, 11, 15, 7, 30))
    c = s.gc.open_by_key("sheet1")
    f = c.worksheet("15/11 matin")
    lignes = f.get_all_values()
    assert lignes[0] == COLONNES_VEILLE
    assert [l[COLONNES_VEILLE.index("Poste")] for l in lignes[1:]] == ["Buyer", "Acheteur", "Planner"]
    d = dict(zip(lignes[0], lignes[1]))
    assert d["Offre"] == "Ouvrir" and d["CV"] == "CV" and d["Lettre"] == "Lettre"
    assert [w.title for w in c.worksheets()][:2] == ["À postuler", "15/11 matin"]        # juste après le suivi global
    v.onglet_veille("matin", [(_o("Autre", 8), DOCS)], datetime(2026, 11, 15, 9, 0))      # relance manuelle le même matin
    assert "15/11 matin (2)" in [w.title for w in c.worksheets()]


def test_onglets_de_veille_limites():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    for k in range(ONGLETS_VEILLE_MAX + 4):
        v.onglet_veille("midi", [(_o(f"P{k}", 8), {})], datetime(2026, 11, 1 + k, 13, 0))
    noms = [w.title for w in s.gc.open_by_key("sheet1").worksheets()]
    veilles = [n for n in noms if n.endswith("midi")]
    assert len(veilles) == ONGLETS_VEILLE_MAX and veilles[0] == "25/11 midi" and "01/11 midi" not in noms


def test_statut_maj_garde_les_liens():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    o = _o("Acheteur", 8)
    v.a_postuler_ajouter([v.ligne_a_postuler(o, DOCS)])
    v.statut_maj(o["cle"], Statut="Envoyée", **{"Date d'envoi": "2026-11-15"})
    f = s.gc.open_by_key("sheet1").worksheet("À postuler")
    brut = dict(zip(COLONNES_A_POSTULER, f.lignes[1]))
    assert brut["CV"].startswith("=HYPERLINK(") and brut["Statut"] == "Envoyée" and brut["Date d'envoi"] == "2026-11-15"


def test_ancien_format_repris_et_onglets_recrees():
    s = faux_services()
    c = s.gc.open_by_key("sheet1")
    c.add_worksheet("Feuille 1")
    ancien = c.add_worksheet("À postuler")
    ancien.append_rows([["Vue le", "Note", "Catégorie", "Poste", "Entreprise", "Lieu", "Contrat", "Publiée", "Candidats", "Mode", "Lien de l'offre", "CV",
                         "Lettre", "Dossier", "Brouillon", "Statut", "Date d'envoi", "Relance", "Points forts", "Manques", "Clé"],
                        ["2026-11-13 15:16", "9", "CDI France", "Acheteur", "GH", "Le Havre", "CDI", "2026-11-12", "", "Site / LinkedIn", "https://ex/1",
                         "https://drive/cv1", "https://drive/lm1", "https://drive/d1", "", "Envoyée", "2026-11-14", "", "• fort", "• manque", "gh|acheteur"],
                        ["2026-11-14 13:06", "8", "CDI France", "Buyer", "W", "Munich", "CDI", "2026-11-13", "", "Site / LinkedIn", "https://ex/2",
                         "https://drive/cv2", "", "", "", "À envoyer", "", "", "", "", "w|buyer"]])
    v = Veille(s.gc, "sheet1")
    noms = [w.title for w in c.worksheets()]
    assert "Feuille 1" not in noms
    lignes = c.worksheet("À postuler").get_all_values()
    assert lignes[0] == COLONNES_A_POSTULER
    d = {l[COLONNES_A_POSTULER.index("Clé")]: dict(zip(lignes[0], l)) for l in lignes[1:]}
    assert d["gh|acheteur"]["Statut"] == "Envoyée" and d["gh|acheteur"]["CV"] == "CV" and d["gh|acheteur"]["Offre"] == "Ouvrir"
    assert d["gh|acheteur"]["Veille"] == "13/11 15h16" and d["w|buyer"]["Lettre"] == ""
    assert "13/11 15h16" in noms and "14/11 13h06" in noms                                  # veilles passées recréées en onglets
    assert v.statuts_lire()[0]["Clé"] in ("gh|acheteur", "w|buyer")


def test_separateur_selon_la_langue_du_sheet():
    s = faux_services()
    c = s.gc.open_by_key("sheet1")
    c.locale = "en_US"
    FauxClasseur.SEP = ","
    try:
        v = Veille(s.gc, "sheet1")
        v.a_postuler_ajouter([v.ligne_a_postuler(_o("Acheteur", 8), DOCS)])
        d = dict(zip(*c.worksheet("À postuler").get_all_values()[:2]))
        assert d["CV"] == "CV"
    finally:
        FauxClasseur.SEP = ";"
