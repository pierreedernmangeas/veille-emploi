# -*- coding: utf-8 -*-
"""Premier passage : ce que Pierre-Edern a déjà vu ou envoyé (Suivi_offres, Candidatures_envoyees, Radar historique, Offres_CV)
est importé comme « déjà vu », pour ne pas refaire ces offres. Colonnes reconnues par leur nom, dans tous les onglets."""
import re

from veille.modele import Offre, cle

CLES_IDS = ("suivi_offres", "candidatures", "offres_cv", "radar")
ENT = re.compile(r"^(entreprise|company|soci[ée]t[ée]|employeur)$", re.I)
POSTE = re.compile(r"^(poste|intitul[ée]|titre|title|job title|offre)$", re.I)
LIEN = re.compile(r"^(lien|lien de l.offre|url|link|lien offre|annonce)$", re.I)


def _colonne(tete, rx):
    return next((i for i, c in enumerate(tete) if rx.match(c.strip())), None)


def importer(s, base, ids: dict) -> int:
    """Renvoie le nombre de lignes importées. Un classeur illisible est ignoré (la veille continue)."""
    cles, urls, n = [], [], 0
    for k in CLES_IDS:
        sid = ids.get(k)
        if not sid:
            continue
        try:
            onglets = s.gc.open_by_key(sid).worksheets()
        except Exception:
            continue
        for w in onglets:
            v = w.get_all_values()
            if not v:
                continue
            tete = v[0]
            ie, ip, il = _colonne(tete, ENT), _colonne(tete, POSTE), _colonne(tete, LIEN)
            if ie is None and il is None:
                continue
            for l in v[1:]:
                ent = l[ie].strip() if ie is not None and len(l) > ie else ""
                poste = l[ip].strip() if ip is not None and len(l) > ip else ""
                url = l[il].strip() if il is not None and len(l) > il else ""
                if ent and poste:
                    cles.append(cle(Offre("historique", poste, ent)))
                if url.startswith("http"):
                    urls.append(url)
                if (ent and poste) or url.startswith("http"):
                    n += 1
    base.importer_cles(cles, urls)
    return n
