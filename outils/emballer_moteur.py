# -*- coding: utf-8 -*-
"""Construit moteur.tar.gz (moteur privé) depuis le dossier offre_cv, à déposer dans Drive > Recherche emploi > Veille_config.

Usage : python3 outils/emballer_moteur.py /chemin/offre_cv moteur.tar.gz
radar_commun.py est extrait de la cellule « 🧰 Module commun » du Radar emploi v7."""
import io
import json
import os
import re
import sys
import tarfile

PY = ["offre_auto", "missions", "cible", "cible_radar", "adapt", "pdf_rapide", "analyse_offre", "cv_engine", "lm_compose", "mails"]
JSON = ["missions", "cv_bank", "keywords", "cours_bank", "lm_bank"]
POLICES = [f"fonts/Serif-{x}.ttf" for x in ["Regular", "Bold", "Italic", "BoldItalic"]]


def radar_commun(source: str) -> bytes:
    nb = json.load(open(os.path.join(source, "radars", "Radar_emploi_v7.ipynb"), encoding="utf8"))
    cel = next("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code" and "#@title 🧰" in "".join(c["source"]))
    m = re.search(r'radar_commun\.py", "w", encoding="utf8"\)\.write\(r\'\'\'(.*?)\'\'\'\)', cel, re.S)
    return m.group(1).encode("utf8")


def emballer(source: str, sortie: str) -> list:
    noms = []
    with tarfile.open(sortie, "w:gz") as t:
        def ajouter(nom, data=None):
            data = data if data is not None else open(os.path.join(source, nom), "rb").read()
            info = tarfile.TarInfo(nom)
            info.size, info.mode = len(data), 0o644
            t.addfile(info, io.BytesIO(data))
            noms.append(nom)
        for f in PY:
            ajouter(f + ".py")
        if os.path.exists(os.path.join(source, "cerveau.py")):
            ajouter("cerveau.py")
        for f in JSON:
            ajouter(f + ".json")
        for f in POLICES:
            ajouter(f)
        ajouter("radar_commun.py", radar_commun(source))
    return noms


if __name__ == "__main__":
    n = emballer(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[2]} : {len(n)} fichiers")
