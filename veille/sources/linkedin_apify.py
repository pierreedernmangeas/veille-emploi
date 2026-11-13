# -*- coding: utf-8 -*-
"""LinkedIn, couche 1 : collecteur Apify (crédit gratuit de 5 $ / mois). Recherches ciblées depuis la dernière veille ;
la couche s'arrête d'elle-même quand la dépense du mois atteint le plafond (4,50 $ par défaut)."""
from datetime import datetime, timezone

import requests

from veille.modele import Offre, maintenant
from veille.sources import linkedin_commun as LC

NOM = "LinkedIn (Apify)"
API = "https://api.apify.com/v2"


class PlafondAtteint(RuntimeError):
    pass


def _get(url, **k):
    return requests.get(url, timeout=30, **k)


def _post(url, **k):
    return requests.post(url, timeout=320, **k)


def depense_du_mois(jeton: str) -> float:
    r = _get(f"{API}/users/me/limits", params={"token": jeton})
    d = (r.json() or {}).get("data", {})
    return float((d.get("current") or {}).get("monthlyUsageUsd") or 0)


def _premier(d, *cles):
    for c in cles:
        v = d.get(c)
        if v not in (None, "", []):
            return v
    return None


def _date(v):
    if not v:
        return None
    s = str(v).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _int(v):
    try:
        return int(str(v).replace(",", "").split()[0])
    except (ValueError, IndexError):
        return None


def normaliser(item: dict) -> Offre | None:
    url = _premier(item, "link", "jobUrl", "url", "applyUrl") or ""
    jid = LC.id_offre(url) or str(_premier(item, "id", "jobId") or "")
    titre = _premier(item, "title", "jobTitle", "position")
    if not titre or not jid:
        return None
    ent = _premier(item, "companyName", "company", "company_name")
    ent = ent.get("name", "") if isinstance(ent, dict) else (ent or "")
    return Offre("LinkedIn", str(titre), str(ent), lieu=str(_premier(item, "location", "jobLocation") or ""),
                 url=f"https://www.linkedin.com/jobs/view/{jid}/", publiee_le=_date(_premier(item, "postedAt", "publishedAt", "postedDate", "listedAt")),
                 description=str(_premier(item, "descriptionText", "description", "jobDescription") or ""),
                 contrat_brut=str(_premier(item, "employmentType", "contractType", "jobType") or ""),
                 candidats=_int(_premier(item, "applicantsCount", "applicants", "numApplicants")),
                 niveau_linkedin=str(_premier(item, "seniorityLevel", "experienceLevel") or ""), sources=["LinkedIn"])


def collecter(ctx) -> list:
    jeton = ctx.secrets.get("APIFY_TOKEN")
    a = ctx.cfg.get("apify", {})
    if not jeton or not a.get("acteur"):
        return []
    plafond = float(a.get("plafond_dollars", 4.5))
    if depense_du_mois(jeton) >= plafond:
        raise PlafondAtteint(f"crédit Apify du mois atteint ({plafond} $) : couche en pause jusqu'au mois prochain")
    periode = max(3600, int((maintenant() - ctx.depuis).total_seconds()))
    urls = [u for _, u in LC.urls_recherche(ctx.rech, periode)]
    entree = {"urls": urls, "count": int(a.get("max_resultats_par_requete", 100)), "scrapeCompany": False}
    r = _post(f"{API}/acts/{a['acteur']}/run-sync-get-dataset-items", params={"token": jeton, "timeout": 300}, json=entree)
    if r.status_code >= 400:
        raise RuntimeError(f"Apify HTTP {r.status_code}")
    items = r.json() if isinstance(r.json(), list) else []
    return [o for o in (normaliser(i) for i in items) if o]
