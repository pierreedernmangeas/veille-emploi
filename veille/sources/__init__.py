# -*- coding: utf-8 -*-
"""Registre des sources : chacune expose NOM et collecter(ctx) -> list[Offre]. Elles tournent en parallèle ;
une source qui plante ou traîne n'arrête jamais les autres, et sa santé (nombre, erreur, durée) est notée pour le récap."""
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Contexte:
    cfg: dict
    rech: dict
    depuis: datetime
    moment: str
    services: object = None
    secrets: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    moteur: object = None
    entreprises: list = field(default_factory=list)


@dataclass
class Sante:
    source: str
    n: int
    erreur: str
    duree_s: float


def tout_collecter(ctx: Contexte, modules: list, delai_s: int = 1500) -> tuple:
    offres, sante, debut, fin = [], [], {}, {}
    ex = ThreadPoolExecutor(max_workers=max(1, len(modules)))

    def lancer(m):
        debut[m.NOM] = time.time()
        try:
            return m.collecter(ctx)
        finally:
            fin[m.NOM] = time.time()

    futurs = {ex.submit(lancer, m): m for m in modules}
    fini, restant = wait(futurs, timeout=delai_s)
    for f in fini:
        m = futurs[f]
        d = round(fin.get(m.NOM, time.time()) - debut.get(m.NOM, time.time()), 1)
        try:
            res = f.result() or []
            offres += res
            sante.append(Sante(m.NOM, len(res), "", d))
        except Exception as e:                      # une source en panne : notée, les autres continuent
            sante.append(Sante(m.NOM, 0, f"{type(e).__name__}: {str(e)[:200]}", d))
    for f in restant:
        sante.append(Sante(futurs[f].NOM, 0, f"délai dépassé ({delai_s} s)", float(delai_s)))
    ex.shutdown(wait=False, cancel_futures=True)
    return offres, sante
