# -*- coding: utf-8 -*-
"""Sites d'emploi lus directement : Indeed (France + Europe) et HelloWork via JobSpy, Welcome to the Jungle (index public, via le moteur),
APEC (service public de recherche), Cadremploi et Jobijoba (pages de résultats + fiches JSON-LD). Reprise du Radar v7."""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from veille.modele import Offre, depuis_rc, maintenant

NOM = "Sites d'emploi"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
APEC_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"
BOARDS = {"Cadremploi": ("https://www.cadremploi.fr/emploi/liste_offres?motscles={kw}&tri=date", r"/emploi/detail_offre\?offreId=\d+|/emploi/[\w-]+-\d{6,}"),
          "Jobijoba": ("https://www.jobijoba.com/fr/query/?what={kw}&where=France&sort=date", r"/fr/annonce/[\w/-]+|/fr/offre[\w/-]+")}
WTTJ_PAYS = ["FR", "BE", "LU", "CH", "NL", "IE", "DE", "ES", "PT", "IT", "PL", "AT", "DK", "SE"]


def _scrape(**k):
    from jobspy import scrape_jobs
    return scrape_jobs(**k)


def _post(url, **k):
    return requests.post(url, timeout=25, headers={"User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json"}, **k)


def _get(url, **k):
    return requests.get(url, timeout=25, headers={"User-Agent": UA, "Accept": "text/html"}, **k)


def _txt(v):
    s = "" if v is None else str(v)
    return "" if s in ("nan", "None", "NaT") else s


def _date(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if v:
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def heures_depuis(ctx) -> int:
    return max(1, int((maintenant() - ctx.depuis).total_seconds() // 3600) + 1)


def termes_par_pays(rech: dict) -> list:
    """(site, terme, lieu, pays Indeed) : France (tous les intitulés) et chaque pays d'Europe (anglais + French speaker, + français si francophone)."""
    fr = rech.get("france_achats", []) + rech.get("france_supply", []) + rech.get("france_graduate", [])
    t = [("indeed", x, "France", "France") for x in fr]
    for pays, lieu in (rech.get("europe_pays") or {}).items():
        mots = rech.get("europe_titres", [])[:21] + rech.get("french_speaker", [])
        if pays == "Spain":                         # il parle espagnol (B2) : l'Espagne est aussi cherchée en espagnol
            mots += rech.get("espagnol_titres", [])
        if pays in rech.get("pays_francophones", []):
            mots += rech.get("france_achats", [])[:10] + rech.get("france_supply", [])[:8]
        t += [("indeed", x, lieu, pays) for x in dict.fromkeys(mots)]
    hw = list(dict.fromkeys(rech.get("france_achats", [])[:14] + rech.get("france_supply", [])[:12] + rech.get("france_graduate", [])[:2]))
    t += [("hellowork", x, "France", "France") for x in hw]
    return t


def _jobspy(site, terme, lieu, pays, heures):
    df = _scrape(site_name=[site], search_term=terme, location=lieu, country_indeed=pays, hours_old=heures, results_wanted=50 if site == "indeed" else 40,
                 description_format="markdown", fetch_description=(site == "hellowork"), verbose=0)
    nom = {"indeed": "Indeed", "hellowork": "HelloWork"}[site]
    out = []
    for _, r in df.iterrows():
        url = _txt(r.get("job_url"))
        if not url:
            continue
        out.append(Offre(nom, _txt(r.get("title")), _txt(r.get("company")), lieu=_txt(r.get("location")),
                         pays="France" if pays == "France" else "", url=url, publiee_le=_date(r.get("date_posted")),
                         description=_txt(r.get("description")), contrat_brut=_txt(r.get("job_type")), niveau_linkedin=_txt(r.get("job_level"))))
    return out


def indeed_et_hellowork(ctx, plan=None) -> list:
    h = heures_depuis(ctx)
    plan = plan or termes_par_pays(ctx.rech)
    out = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_jobspy, s, t, l, p, h) for s, t, l, p in plan]
        for f in as_completed(futs):
            try:
                out += f.result()
            except Exception:
                pass                                # une recherche ratée n'arrête pas les autres
    return out


def wttj(ctx) -> list:
    termes = list(dict.fromkeys(ctx.rech.get("france_achats", [])[:10] + ctx.rech.get("france_supply", [])[:8] + ctx.rech.get("europe_titres", [])[:8]
                                + ["graduate programme", "French speaker"]))
    jours = max(1, heures_depuis(ctx) // 24 + 1)
    return [depuis_rc(d) for d in ctx.moteur.rc.wttj(termes, jours, WTTJ_PAYS)]


def apec(ctx) -> list:
    termes = ctx.rech.get("france_achats", [])[:8] + ctx.rech.get("france_supply", [])[:6] + ["graduate programme", "jeune diplômé achats"]
    h = heures_depuis(ctx)
    out, vus = [], set()
    for kw in dict.fromkeys(termes):
        payload = {"motsCles": kw, "lieux": [], "fonctions": [], "statutPoste": [], "typesContrat": [], "typesConvention": ["143684", "143685", "143686", "143687"],
                   "niveauxExperience": [], "idsEtablissement": [], "secteursActivite": [], "typesTeletravail": [], "idNomZonesDeplacement": [],
                   "positionNumbersExcluded": [], "typeClient": "CADRE", "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
                   "pagination": {"range": 100, "startIndex": 0}, "activeFiltre": True, "pointGeolocDeReference": {"distance": 0}}
        r = _post(APEC_URL, json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"APEC HTTP {r.status_code}")
        for o in r.json().get("resultats", []):
            num = str(o.get("numeroOffre", ""))
            pub = _date(o.get("datePublication"))
            if not num or num in vus or (pub and (maintenant() - pub).total_seconds() > (h + 6) * 3600):
                continue
            vus.add(num)
            desc = BeautifulSoup(o.get("texteOffre", "") or "", "html.parser").get_text(" ", strip=True)
            out.append(Offre("APEC", o.get("intitule", ""), o.get("nomCommercial") or "(non communiqué)", lieu=o.get("lieuTexte", ""), pays="France",
                             url=f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{num}", publiee_le=pub, description=desc))
        time.sleep(0.5)
    return out


def boards(ctx) -> list:
    rc = ctx.moteur.rc
    termes = list(dict.fromkeys(ctx.rech.get("france_achats", [])[:6] + ctx.rech.get("france_supply", [])[:6]))
    out = []
    for nom, (tpl, rx) in BOARDS.items():
        liens = {}
        host = urlparse(tpl).netloc.replace("www.", "")
        for kw in termes:
            try:
                r = _get(tpl.format(kw=quote(kw)))
            except Exception:
                continue
            if r.status_code != 200:
                continue
            for jl in rc.jsonld_jobs(r.text):
                d = rc.from_jsonld(jl, r.url)
                if d.get("url") and d.get("title"):
                    liens.setdefault(urljoin(r.url, d["url"]), d)
            for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
                h = urljoin(r.url, a["href"]).split("#")[0]
                if urlparse(h).netloc.endswith(host) and re.search(rx, h):
                    liens.setdefault(h, None)
            time.sleep(0.7)

        def lire(item):
            h, d = item
            if d is None or len(d.get("desc") or "") < 300:
                d = rc.fetch_detail(h)
            if not d or not d.get("title"):
                return None
            return Offre(nom, d["title"], d.get("company", ""), lieu=d.get("location", ""), pays=d.get("country") or "France", url=h,
                         publiee_le=d.get("posted"), description=d.get("desc", ""), contrat_brut=d.get("contract", ""))
        with ThreadPoolExecutor(8) as ex:
            out += [o for o in ex.map(lire, list(liens.items())[:120]) if o]
    return out


def collecter(ctx) -> list:
    out, erreurs = [], []
    for f in (indeed_et_hellowork, wttj, apec, boards):
        try:
            out += f(ctx)
        except Exception as e:
            erreurs.append(f"{f.__name__}: {str(e)[:80]}")
    if erreurs and not out:
        raise RuntimeError(" | ".join(erreurs))
    ctx.budget.setdefault("notes_sources", []).extend(erreurs)
    return out
