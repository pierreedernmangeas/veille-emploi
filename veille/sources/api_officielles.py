# -*- coding: utf-8 -*-
"""API officielles gratuites : France Travail (Offres d'emploi v2) et Adzuna. Branchées seulement si les clés sont fournies."""
from datetime import datetime, timezone

import requests

from veille.modele import Offre, maintenant

NOM = "API officielles"
FT_JETON = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
FT_RECHERCHE = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


def _post(url, **k):
    return requests.post(url, timeout=25, **k)


def _get(url, **k):
    return requests.get(url, timeout=25, **k)


def _date(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _jours(ctx):
    h = (maintenant() - ctx.depuis).total_seconds() / 3600
    return 1 if h <= 24 else 3 if h <= 72 else 7 if h <= 168 else 14


def france_travail(ctx) -> list:
    cid, sec = ctx.secrets.get("FT_CLIENT_ID"), ctx.secrets.get("FT_CLIENT_SECRET")
    if not cid or not sec:
        return []
    jeton = _post(FT_JETON, params={"realm": "/partenaire"}, data={"grant_type": "client_credentials", "client_id": cid, "client_secret": sec,
                                                                   "scope": "api_offresdemploiv2 o2dsoffre"}).json()["access_token"]
    termes = ctx.rech.get("france_achats", [])[:12] + ctx.rech.get("france_supply", [])[:12]
    out, vus = [], set()
    for kw in dict.fromkeys(termes):
        r = _get(FT_RECHERCHE, params={"motsCles": kw, "publieeDepuis": _jours(ctx), "range": "0-149"}, headers={"Authorization": f"Bearer {jeton}"})
        if r.status_code not in (200, 206):
            continue
        for o in r.json().get("resultats", []):
            if o.get("id") in vus:
                continue
            vus.add(o.get("id"))
            out.append(Offre("France Travail", o.get("intitule", ""), (o.get("entreprise") or {}).get("nom", "") or "(non communiqué)",
                             lieu=(o.get("lieuTravail") or {}).get("libelle", ""), pays="France",
                             url=f"https://candidat.francetravail.fr/offres/recherche/detail/{o.get('id')}", publiee_le=_date(o.get("dateCreation")),
                             description=o.get("description", ""), contrat_brut=o.get("typeContrat", "")))
    return out


ADZUNA_PAYS = {"fr": "France", "be": "Belgique", "nl": "Pays-Bas", "ch": "Suisse", "de": "Allemagne", "es": "Espagne", "it": "Italie", "pl": "Pologne", "at": "Autriche"}


def adzuna(ctx) -> list:
    aid, key = ctx.secrets.get("ADZUNA_APP_ID"), ctx.secrets.get("ADZUNA_APP_KEY")
    if not aid or not key:
        return []
    out, vus = [], set()
    for cc, pays in ADZUNA_PAYS.items():
        termes = (ctx.rech.get("france_achats", [])[:6] + ctx.rech.get("france_supply", [])[:6]) if cc in ("fr", "be", "ch") else \
                 [t for t in ctx.rech.get("french_speaker", [])[:4]] + ctx.rech.get("europe_titres", [])[:4]
        for t in termes:
            r = _get(f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1", params={"app_id": aid, "app_key": key, "what": t, "max_days_old": _jours(ctx),
                                                                                    "results_per_page": 50, "sort_by": "date", "content-type": "application/json"})
            if r.status_code != 200:
                continue
            for j in r.json().get("results", []):
                if j.get("id") in vus:
                    continue
                vus.add(j.get("id"))
                out.append(Offre("Adzuna", j.get("title", ""), (j.get("company") or {}).get("display_name", ""),
                                 lieu=(j.get("location") or {}).get("display_name", ""), pays=pays, url=j.get("redirect_url", ""),
                                 publiee_le=_date(j.get("created")), description=j.get("description", ""),
                                 contrat_brut={"permanent": "CDI", "contract": "CDD"}.get(j.get("contract_type"), "")))
    return out


def collecter(ctx) -> list:
    return france_travail(ctx) + adzuna(ctx)
