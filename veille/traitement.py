# -*- coding: utf-8 -*-
"""Tri et note des offres nouvelles, avec les règles du moteur privé (radar_commun + cible_radar) :
pays, filtres (stage, senior, langue, expérience, zone, expirée), puis note /10 et catégorie d'affichage.
Les V.I.E sont jugés en mode « vie » (monde entier, jamais en France), les autres en mode « cdi » (France + Europe).
La proximité avec le CV est à échelle fixe : la note d'une offre ne dépend pas des autres offres du lot."""
from collections import Counter

import numpy as np

from veille.modele import Offre, vers_rc

SIM_BAS, SIM_HAUT = 0.20, 0.50          # calibré sur 62 vraies offres (0,27 à 0,48) et des annonces hors cible (0,10 à 0,19)
LECTURES_MAX = 200
_PROFIL = {}


def _profil(rc):
    """Texte du parcours (puces FR + EN, profils, compétences), vectorisé une fois par moteur."""
    cle = id(rc)
    if cle not in _PROFIL:
        from sklearn.feature_extraction.text import HashingVectorizer
        B, prof = rc.BANK, []
        for b in B["bullets"].values():
            for L in ("fr", "en"):
                prof += list(b.get(L, {}).values())
        for fam in B["profile_parts"]["s2"].values():
            prof += [fam["fr"], fam["en"]]
        for line in B["skills"].values():
            prof += [i["fr"] + " " + i["en"] for i in line["items"] if not i["formation"]]
        hv = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 5), n_features=2 ** 20, alternate_sign=False, norm=None, preprocessor=rc.norm)
        _PROFIL[cle] = (hv, _vecteurs(hv, [" ".join(prof)]))
    return _PROFIL[cle]


def _vecteurs(hv, textes):
    from sklearn.preprocessing import normalize
    X = hv.transform(textes)
    X.data = np.log1p(X.data)
    return normalize(X)


def similarite(o: dict, rc) -> float:
    hv, p = _profil(rc)
    doc = (rc.strip_hf(o.get("title") or "") + " ") * 3 + (o.get("desc") or "")[:6000]
    s = float((_vecteurs(hv, [doc]) @ p.T).toarray().ravel()[0])
    return round(max(0.0, min(1.0, (s - SIM_BAS) / (SIM_HAUT - SIM_BAS))), 4)


def _juger(rows, m, mode, zone, max_age_days, rejets):
    m.cible_radar.installer(m.rc, mode)
    gardees = []
    for o in rows:
        r = m.rc.reject_reason(o, hours=None, max_age_days=max_age_days, zone=zone)
        if r:
            rejets[r] += 1
            continue
        o["sim"] = similarite(o, m.rc)
        m.rc.noter(o, o["sim"])
        o["categorie"] = "V.I.E" if mode == "vie" else m.cible_radar.categorie(o, m.rc)
        gardees.append(o)
    return gardees


def trier(offres: list, m, max_age_days=None, lire=True) -> tuple:
    """-> (offres gardées en dict radar_commun, triées par note puis fraîcheur ; Counter des raisons de rejet)."""
    rc, rejets = m.rc, Counter()
    rows = []
    for x in offres:
        o = vers_rc(x) if isinstance(x, Offre) else x
        o["title"] = rc.clean(o.get("title") or "")
        o["country"] = rc.country_of(o)
        r = rc.title_reason(o)                  # tri sur l'intitulé avant toute lecture de page
        if r:
            rejets[r] += 1
        else:
            rows.append(o)
    if lire:
        a_lire = [o for o in rows if len(o.get("desc") or "") < 300 and o.get("source") not in ("LinkedIn", "Mon V.I.E")]
        if a_lire:
            rc.enrich(a_lire, LECTURES_MAX)
    for o in rows:
        o["lu"] = len(o.get("desc") or "") >= 300
    vie = [o for o in rows if m.cible_radar._vie(o)]
    autres = [o for o in rows if not m.cible_radar._vie(o)]
    try:
        gardees = _juger(vie, m, "vie", "monde", max_age_days, rejets) + _juger(autres, m, "cdi", "europe", max_age_days, rejets)
    finally:
        m.cible_radar.installer(rc, "cdi")      # le moteur reste dans son mode par défaut pour la suite (CV, lettre)
    gardees.sort(key=lambda o: (-(o.get("note") or 0), -(o["posted"].timestamp() if o.get("posted") else 0)))
    return _sans_doublons_proches(gardees, rc, rejets), rejets


VIDES_TITRE = {"cdi", "cdd", "h", "f", "m", "x", "d", "w", "ou", "et", "de", "des", "du", "la", "le", "les", "en", "a", "the", "and", "of",
               "temps", "plein", "partiel", "full", "time", "e", "se", "euse", "rice"}
VIDES_ENT = {"groupe", "group", "le", "la", "les", "l", "de", "du", "des", "et", "the", "and", "sa", "sas", "sasu", "sarl", "gmbh", "ag", "bv", "nv",
             "ltd", "limited", "inc", "llc", "plc", "spa", "srl", "france", "international", "holding", "corporation", "corp", "co", "company"}


def _mots(t, vides):
    import re
    return [w.rstrip("s") for w in re.findall(r"[a-z0-9]+", t) if w not in vides and len(w) > 1]


def _sans_doublons_proches(gardees, rc, rejets):
    """Même intitulé et même entreprise écrite autrement (« Le Bon Marché » / « GROUPE BON MARCHÉ : Le Bon Marché Rive Gauche »,
    « Groupe SOS » / « Groupe SOS Seniors ») : un seul dossier, le mieux noté (la liste est déjà triée)."""
    vus, out = [], []
    for o in gardees:
        titre = frozenset(_mots(rc.norm(rc.strip_hf(o.get("title") or "")), VIDES_TITRE))
        ent = _mots(rc.norm(o.get("company") or ""), VIDES_ENT)
        doublon = False
        for t2, e2 in vus:
            if titre and titre == t2 and ent and e2:
                court, long_ = (ent, e2) if len(ent) <= len(e2) else (e2, ent)
                if court[0] in long_:
                    doublon = True
                    break
        if doublon:
            rejets["doublon (même poste, même entreprise)"] += 1
            continue
        vus.append((titre, ent))
        out.append(o)
    return out
