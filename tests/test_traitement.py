from veille.modele import Offre
from veille import traitement as T

DESC_ACHAT = ("Nous recherchons un(e) Assistant(e) Achat en CDI pour notre siège de Saint-Ouen. Rattaché(e) au responsable achats, vous "
              "participez au suivi des commandes fournisseurs, à la relance des retards de livraison, à la mise à jour des données "
              "fournisseurs dans l'ERP et à la préparation des consultations. Vous analysez les écarts de prix et suivez les litiges "
              "avec la comptabilité. Profil : formation Bac+3 à Bac+5 en achats ou supply chain, première expérience en stage ou "
              "alternance appréciée, jeune diplômé accepté. Maîtrise d'Excel, anglais professionnel. Contrat : CDI, temps plein.")


def _o(titre, desc=DESC_ACHAT, lieu="Saint-Ouen, France", contrat="", ent="Maison Démo", url=None):
    return Offre("Indeed", titre, ent, lieu=lieu, pays="France", url=url or f"https://ex.fr/{abs(hash(titre + ent))}", description=desc, contrat_brut=contrat)


def test_vie_en_france_pas_vie(moteur_local):
    gardees, rejets = T.trier([_o("Assistant Achat - CDI", contrat="V.I.E")], moteur_local)
    assert len(gardees) == 1, rejets
    assert gardees[0]["categorie"] == "CDI France"


def test_hors_cible_rejete(moteur_local):
    gardees, rejets = T.trier([_o("Magasinier - Approvisionneur")], moteur_local)
    assert gardees == [] and sum(rejets.values()) == 1


def test_sim_echelle_fixe(moteur_local):
    seule, _ = T.trier([_o("Acheteur junior")], moteur_local)
    autres = [_o(f"Acheteur junior {i}", desc=DESC_ACHAT.replace("Excel", f"Excel et l'outil {i}") + " Logistique transport douane." * (i % 4), ent=f"Ent {i}")
              for i in range(49)]
    lot, _ = T.trier([_o("Acheteur junior")] + autres, moteur_local)
    meme = next(r for r in lot if r["company"] == "Maison Démo")
    assert meme["sim"] == seule[0]["sim"] and meme["note"] == seule[0]["note"]


def test_vie_monde_garde(moteur_local):
    desc = ("Volontariat International en Entreprise (V.I.E) de 18 mois à Singapour au sein de l'équipe achats. Vous participez au sourcing, "
            "au suivi des fournisseurs asiatiques, à l'analyse des prix et à la préparation des appels d'offres. Profil : jeune diplômé d'école "
            "de commerce, anglais courant, première expérience en achats ou supply chain en stage. Mission V.I.E de 18 mois, départ janvier 2027.")
    gardees, rejets = T.trier([Offre("Mon V.I.E", "VIE - Acheteur junior", "Groupe Démo", lieu="Singapour", pays="Singapour",
                                     url="https://mon-vie-via.businessfrance.fr/offres/1", description=desc, contrat_brut="V.I.E")], moteur_local)
    assert len(gardees) == 1, rejets
    assert gardees[0]["categorie"] == "V.I.E"


def test_doublon_proche_meme_poste_deux_noms_entreprise(moteur_local):
    """Le même poste publié sous « Le Bon Marché » et « GROUPE BON MARCHÉ : Le Bon Marché Rive Gauche… » : un seul dossier."""
    a = _o("Assistant Achat - CDI", ent="Le Bon Marché", lieu="Paris, France")
    b = _o("Assistant achat (F/H) - CDI", ent="GROUPE BON MARCHÉ : Le Bon Marché Rive Gauche, La Grande Epicerie de Paris", lieu="Paris, Île-de-France, France")
    c = _o("Assistant Achat - CDI", ent="Groupe SOS", lieu="Metz, France")
    d = _o("Assistant Achat - CDI", ent="Groupe SOS Seniors", lieu="Issy, France")
    gardees, rejets = T.trier([a, b, c, d], moteur_local)
    noms = sorted(g["company"] for g in gardees)
    assert len(gardees) == 2, noms
    assert rejets.get("doublon (même poste, même entreprise)") == 2


def test_pas_doublon_entreprises_differentes(moteur_local):
    gardees, _ = T.trier([_o("Acheteur junior", ent="Groupe Atlantic"), _o("Acheteur junior", ent="Groupe Seb")], moteur_local)
    assert len(gardees) == 2
