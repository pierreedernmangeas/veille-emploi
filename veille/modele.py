# -*- coding: utf-8 -*-
"""Offre normalisée, commune à toutes les sources, et clés de dédoublonnage."""
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def maintenant():
    return datetime.now(timezone.utc)


@dataclass
class Offre:
    source: str
    titre: str
    entreprise: str
    lieu: str = ""
    pays: str = ""
    url: str = ""
    publiee_le: datetime | None = None
    description: str = ""
    contrat_brut: str = ""
    candidats: int | None = None
    niveau_linkedin: str = ""
    collectee_le: datetime = field(default_factory=maintenant)
    sources: list = field(default_factory=list)

    def __post_init__(self):
        if not self.sources:
            self.sources = [self.source]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


FORMES = r"\b(sa|sas|sasu|sarl|se|gmbh|ag|bv|nv|ltd|limited|inc|llc|plc|spa|srl|group|groupe|france|holding|international|corporation|corp|co)\b"
MOTS_VIDES = {"h", "f", "m", "w", "d", "x", "junior", "jr", "cdi", "cdd", "vie", "the", "de", "des", "du", "la", "le", "les", "en", "et", "and",
              "of", "a", "e", "se", "euse", "rice"}


def cle(o: Offre) -> str:
    """Même poste dans la même entreprise = même clé, quelle que soit la source."""
    ent = re.sub(FORMES, " ", norm(o.entreprise))
    ent = re.sub(r"[^a-z0-9]+", "", ent)[:20]
    t = re.sub(r"\((?:h|f|m)\s*/\s*(?:h|f|m)(?:\s*/\s*\w)?\)|\b[hf]\s*/\s*[hf]\b", " ", norm(o.titre))
    mots = sorted({w.rstrip("s") for w in re.findall(r"[a-z0-9]+", t) if w not in MOTS_VIDES and len(w) > 1})
    return ent + "|" + " ".join(mots[:8])


SUIVI = re.compile(r"^(utm_|ref|refid|trk|trackingid|src|source|from|fbclid|gclid|mc_)", re.I)


def cle_url(url: str) -> str:
    u = (url or "").strip()
    m = re.search(r"linkedin\.com/.*?(?:currentJobId=|jobs/view/(?:[^/?]*-)?)(\d{6,})", u)
    if m:
        return "linkedin:" + m.group(1)
    p = urlparse(u)
    q = [(k, v) for k, v in parse_qsl(p.query) if not SUIVI.match(k)]
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/") or p.path, "", urlencode(q), ""))


PRIORITE = ["Site carrières", "LinkedIn", "APEC", "France Travail", "WTTJ", "Indeed", "HelloWork"]


def _rang(source):
    return PRIORITE.index(source) if source in PRIORITE else len(PRIORITE)


def fusionner(a: Offre, b: Offre) -> Offre:
    """Une seule offre à partir de deux vues du même poste : on garde le plus riche."""
    base, autre = (a, b) if _rang(a.source) <= _rang(b.source) else (b, a)
    f = replace(base)
    if len(autre.description or "") > len(f.description or ""):
        f.description = autre.description
    for champ in ("lieu", "pays", "contrat_brut", "niveau_linkedin", "url"):
        if not getattr(f, champ):
            setattr(f, champ, getattr(autre, champ))
    if f.candidats is None:
        f.candidats = autre.candidats
    dates = [d for d in (a.publiee_le, b.publiee_le) if d]
    f.publiee_le = max(dates) if dates else None
    f.sources = list(dict.fromkeys(list(a.sources) + list(b.sources)))
    return f


def vers_rc(o: Offre) -> dict:
    """Format attendu par radar_commun (moteur privé)."""
    return dict(source=o.source, requete="", title=o.titre, company=o.entreprise, location=o.lieu, country=o.pays, url=o.url,
                posted=o.publiee_le, desc=o.description or "", contract=o.contrat_brut or "", candidats=o.candidats,
                exp_txt=o.niveau_linkedin or "", salary="", extra="filtre_source", sources=", ".join(o.sources), lu=len(o.description or "") >= 300)


def depuis_rc(d: dict) -> Offre:
    src = d.get("source") or "?"
    sources = [s.strip() for s in str(d.get("sources") or src).split(",") if s.strip()]
    return Offre(source=src, titre=d.get("title") or "", entreprise=d.get("company") or "", lieu=d.get("location") or "",
                 pays=d.get("country") or "", url=d.get("url") or "", publiee_le=d.get("posted"), description=d.get("desc") or "",
                 contrat_brut=d.get("contract") or "", candidats=d.get("candidats"), niveau_linkedin=d.get("exp_txt") or "", sources=sources)
