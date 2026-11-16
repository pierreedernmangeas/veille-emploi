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
    f = c.worksheet("15/11 07h30 matin")
    lignes = f.get_all_values()
    assert lignes[0] == COLONNES_VEILLE
    assert [l[COLONNES_VEILLE.index("Poste")] for l in lignes[1:]] == ["Buyer", "Acheteur", "Planner"]
    d = dict(zip(lignes[0], lignes[1]))
    assert d["Offre"] == "Ouvrir" and d["CV"] == "CV" and d["Lettre"] == "Lettre"
    assert [w.title for w in c.worksheets()][:2] == ["À postuler", "15/11 07h30 matin"]  # juste après le suivi global
    v.onglet_veille("matin", [(_o("Autre", 8), DOCS)], datetime(2026, 11, 15, 7, 30))     # deux veilles dans la même minute
    assert "15/11 07h30 matin (2)" in [w.title for w in c.worksheets()]


def test_onglets_de_veille_limites():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    for k in range(ONGLETS_VEILLE_MAX + 4):
        v.onglet_veille("midi", [(_o(f"P{k}", 8), {})], datetime(2026, 11, 1 + k, 13, 0))
    noms = [w.title for w in s.gc.open_by_key("sheet1").worksheets()]
    veilles = [n for n in noms if n.endswith("midi")]
    assert len(veilles) == ONGLETS_VEILLE_MAX and veilles[0] == "25/11 13h00 midi" and "01/11 13h00 midi" not in noms


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


def test_ajout_n_ecrase_jamais_une_ligne():
    """Une ligne vide au milieu (veille interrompue, ligne effacée à la main) ne doit pas faire écraser les lignes suivantes."""
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    f = s.gc.open_by_key("sheet1").worksheet("À postuler")
    v.a_postuler_ajouter([v.ligne_a_postuler(_o("A", 8), DOCS)])
    f.lignes.append([""] * len(COLONNES_A_POSTULER))
    f.lignes.append(v.ligne_a_postuler(_o("X", 8), DOCS))
    v.a_postuler_ajouter([v.ligne_a_postuler(_o("B", 8), DOCS)])
    v.a_postuler_ajouter([v.ligne_a_postuler(_o("C", 8), DOCS)])
    postes = [l[COLONNES_A_POSTULER.index("Poste")] for l in f.get_all_values()[1:] if any(l)]
    assert postes == ["A", "X", "B", "C"]


def test_heure_de_paris_dans_le_nom_et_la_ligne():
    s = faux_services()
    v = Veille(s.gc, "sheet1")
    nom = v.nom_onglet_veille("matin", datetime(2026, 11, 16, 14, 3))
    assert nom == "16/11 14h03 matin"
    ligne = v.ligne_a_postuler(_o("A", 8), DOCS, nom)
    import veille.sheet as SH
    assert ligne[0] == SH._maintenant() and SH._maintenant_dt().utcoffset() is not None


def test_reconstruction_retrouve_les_offres_perdues():
    from veille.sheet import COLONNES_TOUTES
    s = faux_services()
    c = s.gc.open_by_key("sheet1")
    v = Veille(s.gc, "sheet1")
    # « À postuler » n'a gardé qu'une ligne de la veille du 15/11 (UTC 19:21), statut modifié à la main
    v.a_postuler_ajouter([v.ligne_a_postuler(_o("Survivante", 6), {}, "15/11 19h21")])
    f = c.worksheet("À postuler")
    f.lignes[1][0] = "2026-11-15 19:21"
    v.statut_maj("Démo|Survivante", Statut="Pas intéressé")
    v.onglet_veille("x", [(_o("Survivante", 6), {})], nom="15/11 19h21")
    toutes = c.worksheet("Toutes les offres")
    def t(titre, note, quand, ent="GL"):
        d = {"Vue le": quand, "Note": note, "Catégorie": "CDI France", "Poste": titre, "Entreprise": ent, "Lieu": "Lyon", "Contrat": "CDI",
             "Publiée": "2026-11-15", "Sources": "LinkedIn", "Lien de l'offre": f"https://ex/{titre}", "Verdict": "", "Clé": f"{ent}|{titre}"}
        return [d[k] for k in COLONNES_TOUTES]
    toutes.append_rows([t("Planif", "8", "2026-11-15 19:21"), t("Survivante", "6", "2026-11-15 19:22", "Démo"), t("Ancienne", "7", "2026-11-14 18:11"),
                        t("Trop basse", "5", "2026-11-14 18:12")])
    base = [dict(cle="GL|Planif", etat="documents", note=8, cv="https://drive/cvP", lm="https://drive/lmP", dossier="https://drive/dP", brouillon_id=None),
            dict(cle="GL|Ancienne", etat="envoyee", note=7, cv="https://drive/cvA", lm="https://drive/lmA", dossier="https://drive/dA", brouillon_id="d1"),
            dict(cle="Démo|Survivante", etat="liste", note=6, cv=None, lm=None, dossier=None, brouillon_id=None),
            dict(cle="GL|Trop basse", etat="gardee", note=5, cv=None, lm=None, dossier=None, brouillon_id=None)]
    v.reconstruire(base)
    lignes = c.worksheet("À postuler").get_all_values()
    d = {l[COLONNES_A_POSTULER.index("Clé")]: dict(zip(lignes[0], l)) for l in lignes[1:]}
    assert set(d) == {"GL|Planif", "GL|Ancienne", "Démo|Survivante"}                      # « gardee » (< 6) reste hors du suivi
    assert d["GL|Planif"]["CV"] == "CV" and d["GL|Planif"]["Lettre"] == "Lettre" and d["GL|Planif"]["Offre"] == "Ouvrir"
    assert d["GL|Planif"]["Vue le"] == "2026-11-15 20:21" and d["GL|Planif"]["Veille"] == "15/11 20h21"   # UTC -> heure de Paris
    assert d["GL|Ancienne"]["Statut"] == "Envoyée" and d["Démo|Survivante"]["Statut"] == "Pas intéressé"
    noms = [w.title for w in c.worksheets()]
    assert "15/11 19h21" not in noms and noms[1:3] == ["15/11 20h21", "14/11 19h11"]
    onglet = c.worksheet("15/11 20h21").get_all_values()
    assert [l[1] for l in onglet[1:]] == ["Planif", "Survivante"]
