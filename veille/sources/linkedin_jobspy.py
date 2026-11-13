# -*- coding: utf-8 -*-
"""LinkedIn, couche 2 : recherche publique via JobSpy depuis la machine GitHub (adresse différente à chaque veille).
Peu de pages par recherche, pauses aléatoires ; au premier blocage (429), la couche s'arrête et le récap le signale."""
import random
import time

from veille.modele import Offre, maintenant
from veille.sources import linkedin_commun as LC

NOM = "LinkedIn (JobSpy)"
ZONES_JOBSPY = {"France": "France", "Union européenne": "European Union", "Suisse": "Switzerland", "Europe": "Europe", "Monde": "Worldwide",
                "Belgique": "Belgium", "Luxembourg": "Luxembourg"}


class Bloque(RuntimeError):
    pass


def _scrape(**k):
    from jobspy import scrape_jobs
    return scrape_jobs(**k)


def _txt(v):
    s = "" if v is None else str(v)
    return "" if s == "nan" else s


def collecter(ctx) -> list:
    """Recherches dans l'ordre de priorité (France d'abord le matin ; midi et soir commencent plus loin dans la liste). Au premier blocage ou quand le budget de temps est épuisé, on s'arrête
    en gardant ce qui est déjà lu ; seule une couche sans aucune offre est signalée en erreur."""
    c = ctx.cfg.get("linkedin_jobspy", {})
    heures = max(1, int((maintenant() - ctx.depuis).total_seconds() // 3600) + 1)
    pause = c.get("pause_s", [3, 6])
    fin = time.time() + float(c.get("budget_s", 1080))
    notes = ctx.budget.setdefault("notes_sources", [])
    out, erreurs, reussies = [], [], 0
    req = LC.requetes(ctx.rech)
    dec = {"midi": len(req) // 3, "soir": 2 * len(req) // 3}.get(ctx.moment, 0)     # chaque veille commence ailleurs : toutes passent dans la journée
    for cat, mots, zone, _niveaux in req[dec:] + req[:dec]:
        try:
            df = _scrape(site_name=["linkedin"], search_term=mots, location=ZONES_JOBSPY[zone], hours_old=heures,
                         results_wanted=25 * int(c.get("pages_max", 2)), linkedin_fetch_description=True, description_format="markdown", verbose=0)
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                msg = f"{NOM} : LinkedIn a bloqué la recherche publique après {len(out)} offres ; les autres couches continuent"
                if not out:
                    raise Bloque(msg)
                notes.append(msg)
                break
            erreurs.append(f"{type(e).__name__}: {str(e)[:120]}")
            continue
        reussies += 1
        for _, r in df.iterrows():
            url = _txt(r.get("job_url"))
            jid = LC.id_offre(url)
            if not jid:
                continue
            out.append(Offre("LinkedIn", _txt(r.get("title")), _txt(r.get("company")), lieu=_txt(r.get("location")),
                             url=f"https://www.linkedin.com/jobs/view/{jid}/", description=_txt(r.get("description")),
                             contrat_brut=_txt(r.get("job_type")), niveau_linkedin=_txt(r.get("job_level")), sources=["LinkedIn"]))
        if time.time() >= fin:
            notes.append(f"{NOM} : budget de temps atteint après {len(out)} offres (les suivantes passent en tête à une autre veille de la journée)")
            break
        time.sleep(random.uniform(*pause))
    if not reussies and erreurs:
        raise RuntimeError(f"toutes les recherches ont échoué ({len(erreurs)}) ; dernière erreur : {erreurs[-1]}")
    return out
