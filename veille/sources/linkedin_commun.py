# -*- coding: utf-8 -*-
"""Outils LinkedIn communs aux 3 couches : adresses de recherche (Apify et liens d'alertes), lecture de la page de résultats publique,
lecture de la fiche publique d'une offre (description, contrat, niveau, candidats). Aucune connexion au compte LinkedIn."""
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from veille.modele import Offre

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
GEO = {"France": "105015875", "Union européenne": "91000000", "Suisse": "106693272", "Europe": "100506914", "Monde": "92000000",
       "Belgique": "100565514", "Luxembourg": "104042105"}


def _get(url, **k):
    return requests.get(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}, timeout=30, **k)


def _ou(mots):
    return " OR ".join(f'"{m}"' for m in mots)


def paquets(liste, n):
    return [liste[i:i + n] for i in range(0, len(liste), n)]


def requetes(rech: dict) -> list:
    """(catégorie, mots-clés, zone, niveaux) : toutes les recherches LinkedIn de la veille."""
    fr = [x for x in rech.get("france_achats", []) if x not in ("acheteur", "acheteuse")]
    sup = [x for x in rech.get("france_supply", []) if x not in ("approvisionneur", "approvisionneuse")]
    r = [("France", _ou(p), "France", "2,3") for p in paquets(fr, 6)]
    r += [("France", _ou(p), "France", "2,3") for p in paquets(sup, 6)]
    r += [("France", "acheteur OR acheteuse OR approvisionneur OR approvisionneuse", "France", "2"),
          ("Graduate", _ou(rech.get("france_graduate", []) + ["graduate program supply chain", "graduate programme procurement"]), "France", "")]
    eu = rech.get("europe_titres", [])
    r += [("Europe", _ou(p), "Union européenne", "2") for p in paquets(eu, 7)]
    r += [("Europe", _ou(p), "Suisse", "2") for p in paquets(eu[:14], 7)]
    r += [("Europe", _ou((fr[:6] + sup[:4])), z, "") for z in ("Belgique", "Luxembourg", "Suisse")]
    r += [("French speaker", '("French speaker" OR "French speaking" OR "fluent French" OR "with French") AND (procurement OR buyer OR purchasing OR sourcing OR "procure to pay")', "Europe", "1,2,3"),
          ("French speaker", '("French speaker" OR "French speaking" OR "fluent French" OR "with French") AND ("supply chain" OR planner OR logistics OR "order management")', "Europe", "1,2,3"),
          ("Graduate", '("graduate programme" OR "graduate program" OR rotational) AND ("supply chain" OR procurement OR purchasing)', "Europe", "")]
    vie = '(VIE OR "V.I.E" OR "volontariat international") AND (achats OR acheteur OR buyer OR purchasing OR procurement OR sourcing)'
    r += [("V.I.E", vie, "Monde", ""),
          ("V.I.E", '(VIE OR "V.I.E") AND ("supply chain" OR logistique OR logistics OR planner OR approvisionnement OR transport)', "Monde", "")]
    return r


def url_recherche(mots: str, zone: str, niveaux: str = "", periode_s: int | None = None) -> str:
    u = f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(mots)}&geoId={GEO[zone]}&sortBy=DD"
    if niveaux:
        u += f"&f_E={quote_plus(niveaux)}"
    if periode_s:
        u += f"&f_TPR=r{int(periode_s)}"
    return u


def urls_recherche(rech: dict, periode_s: int | None) -> list:
    return [(cat, url_recherche(m, z, n, periode_s)) for cat, m, z, n in requetes(rech)]


def id_offre(url: str) -> str:
    m = re.search(r"(?:jobPosting:|currentJobId=|jobs/view/(?:[^/?]*-)?)(\d{6,})", url or "")
    return m.group(1) if m else ""


def _txt(el):
    return el.get_text(" ", strip=True) if el else ""


def analyser_recherche(html: str, source: str = "LinkedIn") -> list:
    """Page de résultats publique -> offres (titre, entreprise, lieu, lien, date)."""
    s = BeautifulSoup(html, "html.parser")
    out = []
    for li in s.select("li"):
        a = li.select_one("a.base-card__full-link") or li.select_one("a[href*='/jobs/view/']")
        if not a:
            continue
        jid = id_offre(a.get("href", "")) or id_offre(str(li.select_one("[data-entity-urn]") or ""))
        if not jid:
            continue
        t = li.select_one("time")
        dt = None
        if t and t.get("datetime"):
            try:
                dt = datetime.fromisoformat(t["datetime"]).replace(tzinfo=timezone.utc)
            except ValueError:
                dt = None
        out.append(Offre(source, _txt(li.select_one(".base-search-card__title")) or _txt(a), _txt(li.select_one(".base-search-card__subtitle")),
                         lieu=_txt(li.select_one(".job-search-card__location")), url=f"https://www.linkedin.com/jobs/view/{jid}/", publiee_le=dt))
    return out


def lire_description_linkedin(jid: str) -> dict:
    """Fiche publique d'une offre : description, contrat, niveau, nombre de candidats, entreprise, lieu. {} si indisponible."""
    r = _get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}")
    if r.status_code != 200:
        return {"indisponible": r.status_code}
    s = BeautifulSoup(r.text, "html.parser")
    crit = {}
    for li in s.find_all("li", class_="description__job-criteria-item"):
        h, v = li.find("h3"), li.find("span")
        if h and v:
            crit[_txt(h).lower()] = _txt(v)
    nap = s.find(class_=lambda c: c and "num-applicants" in c)
    m = re.search(r"(\d[\d\s,.]*)", _txt(nap)) if nap else None
    cand = int(re.sub(r"\D", "", m.group(1))) if m else (10 if nap and re.search(r"first|premiers", _txt(nap), re.I) else None)
    d = s.find("div", class_="show-more-less-html__markup")
    return dict(description=d.get_text("\n", strip=True) if d else "", candidats=cand,
                contrat=crit.get("type d’emploi") or crit.get("type d'emploi") or crit.get("employment type") or "",
                niveau=crit.get("niveau hiérarchique") or crit.get("seniority level") or "",
                entreprise=_txt(s.find("a", class_=lambda c: c and "topcard__org-name-link" in c)),
                lieu=_txt(s.find(class_=lambda c: c and "topcard__flavor--bullet" in c)),
                titre=_txt(s.find("h2")), ferme=bool(re.search(r"no longer accepting|n.accepte plus", r.text[:20000], re.I)))


def completer(o: Offre) -> Offre:
    """Ajoute à une offre LinkedIn la description et les détails de sa fiche publique."""
    jid = id_offre(o.url)
    if not jid or len(o.description or "") >= 300:
        return o
    d = lire_description_linkedin(jid)
    if d.get("description"):
        o.description = d["description"]
        o.contrat_brut = o.contrat_brut or d["contrat"]
        o.niveau_linkedin = o.niveau_linkedin or d["niveau"]
        o.candidats = o.candidats if o.candidats is not None else d["candidats"]
        o.entreprise = o.entreprise or d["entreprise"]
        o.lieu = o.lieu or d["lieu"]
    return o
