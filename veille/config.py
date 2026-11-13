# -*- coding: utf-8 -*-
"""Lecture de config.yaml (réglages) et recherches.yaml (mots-clés, pays, entreprises) : modifiables sans toucher au code."""
import os

import yaml

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lire(chemin):
    if not os.path.isabs(chemin):
        chemin = os.path.join(ICI, chemin)
    with open(chemin, encoding="utf8") as f:
        return yaml.safe_load(f) or {}


def charger(chemin: str = "config.yaml") -> dict:
    return _lire(chemin)


def recherches(chemin: str = "recherches.yaml") -> dict:
    return _lire(chemin)
