from veille.base import Base
from veille.modele import Offre, cle
from tests.faux_google import faux_services


def _o(src, titre="Acheteur Junior H/F", ent="Telespazio", url=""):
    return Offre(src, titre, ent, url=url, description="x" * (10 if src == "Indeed" else 400))


def test_meme_offre_4_sources_une_ligne(tmp_path):
    b = Base(str(tmp_path / "v.sqlite"))
    lot = [_o("LinkedIn", url="https://www.linkedin.com/jobs/view/4123456789"), _o("LinkedIn", url="https://fr.linkedin.com/jobs/view/4123456789/?trk=a"),
           _o("Indeed", "Acheteur junior (F/H) - CDD", "TELESPAZIO SAS"), _o("Site carrières", "Acheteur Junior", "Telespazio France")]
    r = b.fusionner_lot(lot)
    assert len(r) == 1 and set(r[0].sources) == {"LinkedIn", "Indeed", "Site carrières"}


def test_revue_au_passage_suivant_pas_nouvelle(tmp_path):
    b = Base(str(tmp_path / "v.sqlite"))
    o = _o("LinkedIn")
    assert b.nouvelles([o]) == [o]
    b.ajouter(o, "à postuler")
    assert b.nouvelles([_o("Indeed", "Acheteur junior - CDI", "Telespazio")]) == []


def test_url_differente_meme_poste_reconnue_par_url(tmp_path):
    b = Base(str(tmp_path / "v.sqlite"))
    b.ajouter(_o("LinkedIn", "Buyer", "AB InBev", url="https://www.linkedin.com/jobs/view/4999999999"), "vue")
    assert b.connue(_o("LinkedIn", "Junior Category Buyer", "Anheuser-Busch", url="https://be.linkedin.com/jobs/view/x-4999999999"))


def test_importer_cles_historique(tmp_path):
    b = Base(str(tmp_path / "v.sqlite"))
    o = _o("LinkedIn")
    b.importer_cles([cle(o)], [])
    assert b.connue(o)


def test_marquer_et_lire(tmp_path):
    b = Base(str(tmp_path / "v.sqlite"))
    o = _o("LinkedIn"); b.ajouter(o, "à postuler")
    b.marquer(cle(o), brouillon_id="d1", note=8.5)
    assert b.ligne(cle(o))["brouillon_id"] == "d1" and b.ligne(cle(o))["note"] == 8.5


def test_aller_retour_drive(tmp_path):
    s = faux_services()
    conf = s.drive.ajouter("Veille_config", "root", mime=s.drive.FOLDER)
    b = Base.ouvrir_depuis_drive(s, conf, str(tmp_path / "a.sqlite"))
    b.ajouter(_o("LinkedIn"), "vue"); b.sauver_vers_drive(s, conf)
    b2 = Base.ouvrir_depuis_drive(s, conf, str(tmp_path / "b.sqlite"))
    assert b2.connue(_o("LinkedIn"))


def test_offre_fusionnee_ne_revient_pas_sous_une_autre_variante(tmp_path):
    b = Base(str(tmp_path / "v.sqlite"))
    apify = Offre("LinkedIn", "Acheteur Junior", "Démo", url="https://www.linkedin.com/jobs/view/77/")
    alerte = Offre("LinkedIn", "Acheteur junior - achats indirects", "Démo", url="https://www.linkedin.com/jobs/view/77/")
    site = Offre("Site carrières", "Acheteur Junior", "Démo", url="https://carrieres.demo.fr/1")
    for o in Base.fusionner_lot([apify, alerte, site]):
        b.ajouter(o, "documents")
    assert b.connue(Offre("LinkedIn", "Acheteur junior - achats indirects", "Démo", url="https://www.linkedin.com/jobs/view/99/"))   # clé variante
    assert b.connue(Offre("LinkedIn", "Autre titre", "Autre", url="https://www.linkedin.com/jobs/view/77/"))                          # URL LinkedIn
