# -*- coding: utf-8 -*-
"""Base des offres déjà vues (SQLite), gardée sur Drive entre les veilles : une offre n'est jamais présentée deux fois,
qu'elle vienne de 4 sources dans la même veille ou qu'elle réapparaisse le lendemain."""
import os
import sqlite3
import tempfile

from veille import google_acces as G
from veille.modele import Offre, cle, cle_url, fusionner, maintenant

NOM = "veille.sqlite"
COLONNES = ["cle", "url", "titre", "entreprise", "source", "sources", "premiere_vue", "derniere_vue", "etat", "note", "brouillon_id",
            "fil_id", "date_envoi", "relance_id", "dossier", "cv", "lm"]


class Base:
    def __init__(self, chemin: str):
        self.chemin = chemin
        self.db = sqlite3.connect(chemin)
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS offres (cle TEXT PRIMARY KEY, url TEXT, titre TEXT, entreprise TEXT, source TEXT, sources TEXT,"
                        " premiere_vue TEXT, derniere_vue TEXT, etat TEXT, note REAL, brouillon_id TEXT, fil_id TEXT, date_envoi TEXT,"
                        " relance_id TEXT, dossier TEXT, cv TEXT, lm TEXT)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_url ON offres(url)")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (nom TEXT PRIMARY KEY, valeur TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS alias (valeur TEXT PRIMARY KEY, cle TEXT)")   # autres clés / URL d'une offre fusionnée
        self.db.commit()

    # --- Drive
    @classmethod
    def ouvrir_depuis_drive(cls, s: G.Services, dossier_id: str, chemin: str | None = None) -> "Base":
        chemin = chemin or os.path.join(tempfile.gettempdir(), NOM)
        if os.path.exists(chemin):
            os.remove(chemin)
        G.telecharger(s.drive, NOM, dossier_id, chemin)
        return cls(chemin)

    def sauver_vers_drive(self, s: G.Services, dossier_id: str) -> None:
        """Copie cohérente de la base (même en cours d'écriture) envoyée sous le nom veille.sqlite."""
        self.db.commit()
        with tempfile.TemporaryDirectory() as d:
            copie = os.path.join(d, NOM)
            dst = sqlite3.connect(copie)
            self.db.backup(dst)
            dst.close()
            G.televerser(s.drive, copie, dossier_id, "application/x-sqlite3")

    # --- méta (dernière veille, premier passage)
    def meta(self, nom: str, valeur: str | None = None):
        if valeur is None:
            r = self.db.execute("SELECT valeur FROM meta WHERE nom = ?", (nom,)).fetchone()
            return r["valeur"] if r else None
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (nom, valeur))
        self.db.commit()

    # --- offres
    def connue(self, o: Offre) -> bool:
        u = cle_url(o.url) if o.url else None
        r = self.db.execute("SELECT 1 FROM offres WHERE cle = ? OR (url IS NOT NULL AND url != '' AND url = ?)", (cle(o), u or "\0")).fetchone()
        if r is None:
            r = self.db.execute("SELECT 1 FROM alias WHERE valeur = ? OR valeur = ?", ("cle:" + cle(o), "url:" + (u or "\0"))).fetchone()
        return r is not None

    def ajouter(self, o: Offre, etat: str) -> None:
        t = maintenant().isoformat(timespec="seconds")
        self.db.execute("INSERT OR IGNORE INTO offres (cle, url, titre, entreprise, source, sources, premiere_vue, derniere_vue, etat)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (cle(o), cle_url(o.url) if o.url else "", o.titre, o.entreprise, o.source, ", ".join(o.sources), t, t, etat))
        k = cle(o)
        self.db.executemany("INSERT OR IGNORE INTO alias (valeur, cle) VALUES (?, ?)",
                            [("cle:" + a, k) for a in getattr(o, "alias_cles", ())] + [("url:" + a, k) for a in getattr(o, "alias_urls", ())])
        self.db.commit()

    def importer_cles(self, cles: list, urls: list, etat: str = "historique") -> None:
        t = maintenant().isoformat(timespec="seconds")
        self.db.executemany("INSERT OR IGNORE INTO offres (cle, url, premiere_vue, derniere_vue, etat) VALUES (?, '', ?, ?, ?)",
                            [(c, t, t, etat) for c in cles if c])
        self.db.executemany("INSERT OR IGNORE INTO offres (cle, url, premiere_vue, derniere_vue, etat) VALUES (?, ?, ?, ?, ?)",
                            [("url:" + cle_url(u), cle_url(u), t, t, etat) for u in urls if u])
        self.db.commit()

    def marquer(self, cle_offre: str, **champs) -> None:
        champs = {k: v for k, v in champs.items() if k in COLONNES}
        if champs:
            self.db.execute(f"UPDATE offres SET {', '.join(k + ' = ?' for k in champs)} WHERE cle = ?", (*champs.values(), cle_offre))
            self.db.commit()

    def ligne(self, cle_offre: str) -> dict | None:
        r = self.db.execute("SELECT * FROM offres WHERE cle = ?", (cle_offre,)).fetchone()
        return dict(r) if r else None

    def lignes(self, etats: tuple) -> list:
        q = f"SELECT * FROM offres WHERE etat IN ({', '.join('?' * len(etats))})"
        return [dict(r) for r in self.db.execute(q, etats).fetchall()]

    @staticmethod
    def fusionner_lot(offres: list) -> list:
        """Dédoublonne un lot : même clé ou même URL = même offre (on garde la vue la plus riche)."""
        par_cle, par_url = {}, {}
        for o in offres:
            k, u = cle(o), (cle_url(o.url) if o.url else None)
            cible = par_cle.get(k) or (par_url.get(u) if u else None)
            if cible is None:
                par_cle[k] = o
                if u:
                    par_url[u] = k
                continue
            kk = cible if isinstance(cible, str) else k
            par_cle[kk] = fusionner(par_cle[kk], o)
            if u:
                par_url[u] = kk
        groupes = {}                                # toutes les clés et URL vues pour chaque offre gardée
        for o in offres:
            k, u = cle(o), (cle_url(o.url) if o.url else None)
            kk = k if k in par_cle else par_url.get(u, k)
            g = groupes.setdefault(kk, (set(), set()))
            g[0].add(k)
            if u:
                g[1].add(u)
        for kk, o in par_cle.items():
            cles, urls = groupes.get(kk, (set(), set()))
            o.alias_cles, o.alias_urls = sorted(cles - {cle(o)}), sorted(urls - {cle_url(o.url) if o.url else ""})
        return list(par_cle.values())

    def nouvelles(self, offres: list) -> list:
        return [o for o in offres if not self.connue(o)]
