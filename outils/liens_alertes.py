# -*- coding: utf-8 -*-
"""Génère docs/ALERTES_LINKEDIN.md : les liens de recherche LinkedIn à transformer en alertes mail (couche 3 de la veille).
Usage : python3 -m outils.liens_alertes"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from veille import config  # noqa: E402
from veille.sources import linkedin_commun as LC  # noqa: E402


def ecrire(rech: dict, chemin: str) -> int:
    lignes = ["# Alertes LinkedIn à créer (une fois, 10 minutes)", "",
              "Pour chaque lien : ouvre-le connecté à LinkedIn, clique **« Créer une alerte »** (interrupteur en haut des résultats),",
              "fréquence **« Dès que possible »** (sinon « Quotidienne »), réception **par e-mail**. La veille lit ces mails sans les marquer lus.",
              "Si une alerte identique existe déjà, passe au lien suivant.", ""]
    n = 0
    for cat, mots, zone, niveaux in LC.requetes(rech):
        n += 1
        lignes.append(f"{n}. **{cat} · {zone}** : [{mots[:90]}{'…' if len(mots) > 90 else ''}]({LC.url_recherche(mots, zone, niveaux)})")
    os.makedirs(os.path.dirname(os.path.abspath(chemin)), exist_ok=True)
    open(chemin, "w", encoding="utf8").write("\n".join(lignes) + "\n")
    return n


if __name__ == "__main__":
    print(ecrire(config.recherches(), os.path.join(config.ICI, "docs", "ALERTES_LINKEDIN.md")), "liens")
