import os
import subprocess
import sys
import tarfile

import pytest

OFFRE_CV = os.environ.get("VEILLE_MOTEUR_SOURCE", "/home/user/offre_cv")
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def moteur_local(tmp_path_factory):
    """Le vrai moteur privé, emballé puis chargé comme en production. Absent du dépôt public : test sauté s'il n'est pas sur la machine."""
    if not os.path.exists(os.path.join(OFFRE_CV, "offre_auto.py")):
        pytest.skip("moteur privé absent de cette machine")
    from veille import moteur_prive
    d = tmp_path_factory.mktemp("moteur")
    subprocess.run([sys.executable, os.path.join(RACINE, "outils", "emballer_moteur.py"), OFFRE_CV, str(d / "moteur.tar.gz")], check=True, capture_output=True)
    with tarfile.open(d / "moteur.tar.gz") as t:
        t.extractall(d, filter="data")
    return moteur_prive.charger(str(d))
