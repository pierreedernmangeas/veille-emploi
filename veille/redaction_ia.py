# -*- coding: utf-8 -*-
"""Rédaction IA contrôlée : Gemini (offre gratuite) lit l'offre comme un recruteur et rédige profil, accroche et lettre ;
le moteur privé (cerveau.py) vérifie chaque champ contre les faits du dossier (chiffres, employeur, formules interdites, langue).
Un champ refusé est corrigé une fois, sinon il repasse sur la version moteur v12. Sans clé, au-delà du plafond d'appels
ou à la moindre erreur, la candidature reste entièrement celle du moteur v12."""
import copy
import json
import re
import time

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"
REPLI = ["IA indisponible : version moteur v12"]
CHAMPS = ("spec", "lettre", "note", "analyse", "forts", "faibles", "table", "entreprise", "lieu", "avis", "metier", "a_relire")


class PlafondIA(RuntimeError):
    pass


def _post(url, **k):
    return requests.post(url, **k)


def _json(texte: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (texte or "").strip())
    d = json.loads(t)
    if not isinstance(d, dict):
        raise ValueError("réponse IA sans objet JSON")
    return d


def client(cle: str, cfg: dict, compteur: dict):
    """ia_json(prompt, delai, prompt_court=None, cles=None) -> dict, au format attendu par cerveau.penser."""
    g = cfg.get("gemini") or {}
    modele, plafond = g.get("modele", "gemini-flash-latest"), int(g.get("max_appels", 60))

    def appel(prompt, delai):
        if compteur.get("appels", 0) >= plafond:
            raise PlafondIA(f"plafond de {plafond} appels atteint")
        compteur["appels"] = compteur.get("appels", 0) + 1
        r = _post(URL.format(modele=modele), headers={"x-goog-api-key": cle, "Content-Type": "application/json"}, timeout=max(10, delai),
                  json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}})
        if r.status_code == 429:
            raise PlafondIA("quota Gemini atteint (429)")
        r.raise_for_status()
        return _json(r.json()["candidates"][0]["content"]["parts"][0]["text"])

    def ia_json(prompt, delai, prompt_court=None, cles=None):
        try:
            return appel(prompt, delai)
        except (requests.Timeout, ValueError, KeyError):
            if not prompt_court:
                raise
            return appel(prompt_court, delai)   # une seconde chance, avec le dossier court
    return ia_json


def rediger(r: dict, cle: str, cfg: dict, compteur: dict) -> list:
    """Améliore r (analyse du moteur, avant fabrication des PDF). Renvoie les notes « À relire » (vide si tout a passé)."""
    if not cle:
        return list(REPLI)
    g = cfg.get("gemini") or {}
    if compteur.get("appels", 0) >= int(g.get("max_appels", 60)):
        return list(REPLI)
    copie = copy.deepcopy({k: r[k] for k in CHAMPS if k in r})
    try:
        import cerveau
        t0 = time.time()
        notes = cerveau.penser(r, client(cle, cfg, compteur), delai=int(g.get("delai_s", 40)))
    except Exception as e:                      # jamais de candidature perdue à cause de l'IA
        notes = [f"IA indisponible : {str(e)[:120]}"]
    if any(n.startswith(("IA indisponible", "Réponse de l'IA inutilisable", "Contrôles trop longs")) for n in notes):
        for k in list(r):
            if k in CHAMPS and k not in copie:
                r.pop(k)
        r.update(copie)
        return list(REPLI)
    r["temps_ia_s"] = round(time.time() - t0, 1)
    return [f"À relire : {n}" for n in notes]
