import os, subprocess, sys, tarfile
import pytest
from tests.faux_google import faux_services
from veille import google_acces as G
from veille import moteur_prive

OFFRE_CV = "/home/user/offre_cv"
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_compte_inattendu_arrete():
    s = faux_services("quelquun.dautre@exemple.fr")
    with pytest.raises(G.CompteInattendu) as e:
        G.verifier_compte(s, "moi@exemple.fr")
    assert "@" not in str(e.value)


def test_compte_attendu_passe():
    G.verifier_compte(faux_services(), "moi@exemple.fr")


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    sortie = tmp_path_factory.mktemp("arch") / "moteur.tar.gz"
    subprocess.run([sys.executable, os.path.join(RACINE, "outils", "emballer_moteur.py"), OFFRE_CV, str(sortie)], check=True)
    return sortie


def test_archive_sans_fichier_inattendu(archive):
    noms = set(tarfile.open(archive).getnames())
    attendus = {f + ".py" for f in ["offre_auto", "missions", "cible", "cible_radar", "adapt", "pdf_rapide", "analyse_offre", "cv_engine", "lm_compose", "radar_commun", "mails", "intitule", "qualite", "coller"]}
    attendus |= {f + ".json" for f in ["missions", "cv_bank", "keywords", "cours_bank", "lm_bank"]}
    attendus |= {f"fonts/Serif-{x}.ttf" for x in ["Regular", "Bold", "Italic", "BoldItalic"]}
    if os.path.exists(os.path.join(OFFRE_CV, "cerveau.py")):
        attendus.add("cerveau.py")
    assert noms == attendus


def test_installer_moteur(archive, tmp_path):
    s = faux_services()
    rech = s.drive.ajouter("Recherche emploi", "root", mime=s.drive.FOLDER)
    conf = s.drive.ajouter("Veille_config", rech, mime=s.drive.FOLDER)
    colab = s.drive.ajouter("Offres_Colab", rech, mime=s.drive.FOLDER)
    s.drive.ajouter("moteur.tar.gz", conf, archive.read_bytes())
    s.drive.ajouter("missions.json", colab, open(os.path.join(OFFRE_CV, "missions.json"), "rb").read())
    m = moteur_prive.installer(s, str(tmp_path / "moteur"), ids={"recherche_emploi": rech})
    assert hasattr(m.OA, "analyse_directe")
    assert m.rc.is_vie.__module__ == "cible_radar"
    assert m.C.metier("Acheteur junior")[0] == "coeur"


def test_moteur_absent_message_clair(tmp_path):
    s = faux_services()
    rech = s.drive.ajouter("Recherche emploi", "root", mime=s.drive.FOLDER)
    with pytest.raises(moteur_prive.MoteurAbsent):
        moteur_prive.installer(s, str(tmp_path / "m"), ids={"recherche_emploi": rech})
