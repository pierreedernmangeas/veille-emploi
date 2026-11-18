# -*- coding: utf-8 -*-
"""Moteur privé (CV, lettre, notation, règles de cible) : il contient des faits du parcours de Pierre-Edern, donc il vit sur son Drive
(`Recherche emploi/Veille_config/moteur.tar.gz`) et non dans ce dépôt public. Téléchargé et installé à chaque veille."""
import importlib
import os
import sys
import tarfile
from dataclasses import dataclass

from veille import google_acces as G


class MoteurAbsent(RuntimeError):
    pass


@dataclass
class Moteur:
    OA: object
    rc: object
    cible_radar: object
    C: object
    dossier: str


MODULES = ["cible", "missions", "lm_compose", "cv_engine", "adapt", "analyse_offre", "pdf_rapide", "offre_auto", "radar_commun", "cible_radar", "cerveau", "mails", "intitule", "qualite", "coller"]


def installer(s: G.Services, dest: str = "/tmp/moteur", ids: dict | None = None) -> Moteur:
    ids = ids or {}
    rech = ids.get("recherche_emploi") or G.dossier(s.drive, ["Recherche emploi"])
    conf = G.trouver(s.drive, "Veille_config", rech, True)
    if not conf:
        raise MoteurAbsent("Moteur absent : dépose moteur.tar.gz dans Drive > Recherche emploi > Veille_config (voir docs/MISE_EN_PLACE.md).")
    archive = os.path.join(dest, "moteur.tar.gz")
    os.makedirs(dest, exist_ok=True)
    if not G.telecharger(s.drive, "moteur.tar.gz", conf["id"], archive):
        raise MoteurAbsent("Moteur absent : dépose moteur.tar.gz dans Drive > Recherche emploi > Veille_config (voir docs/MISE_EN_PLACE.md).")
    with tarfile.open(archive) as t:
        t.extractall(dest, filter="data")
    colab = G.trouver(s.drive, "Offres_Colab", rech, True)
    if colab:                                   # la banque de missions modifiée par Pierre-Edern remplace celle de l'archive
        G.telecharger(s.drive, "missions.json", colab["id"], os.path.join(dest, "missions.json"))
    return charger(dest)


def charger(dest: str) -> Moteur:
    """Importe le moteur déjà extrait dans dest (aussi utilisé par les tests locaux)."""
    for nom in MODULES:                         # une installation propre à chaque appel (tests, veilles successives)
        sys.modules.pop(nom, None)
    if dest not in sys.path:
        sys.path.insert(0, dest)
    cible = importlib.import_module("cible")
    rc = importlib.import_module("radar_commun")
    cr = importlib.import_module("cible_radar")
    oa = importlib.import_module("offre_auto")
    rc.load_banks(dest)
    cr.installer(rc, "cdi")
    return Moteur(OA=oa, rc=rc, cible_radar=cr, C=cible, dossier=dest)
