# -*- coding: utf-8 -*-
"""Le Google Sheet « Veille emploi » : onglets À postuler (offres avec CV + lettre prêts), Toutes les offres (tout ce qui a été
gardé), Sources (santé de chaque source à chaque veille), Entreprises (sites carrières interrogés, modifiables à la main)."""
from datetime import datetime

COLONNES_A_POSTULER = ["Vue le", "Note", "Catégorie", "Poste", "Entreprise", "Lieu", "Contrat", "Publiée", "Candidats", "Mode", "Lien de l'offre", "CV",
                       "Lettre", "Dossier", "Brouillon", "Statut", "Date d'envoi", "Relance", "Points forts", "Manques", "Clé"]
COLONNES_TOUTES = ["Vue le", "Note", "Catégorie", "Poste", "Entreprise", "Lieu", "Contrat", "Publiée", "Sources", "Lien de l'offre", "Verdict", "Clé"]
COLONNES_SOURCES = ["Date", "Veille", "Source", "Offres", "Durée (s)", "Erreur"]
COLONNES_ENTREPRISES = ["Entreprise", "Adresse", "Méthode", "Offres (dernière veille)", "Erreur", "Adresse d'origine", "Mise à jour"]
ONGLETS = {"À postuler": COLONNES_A_POSTULER, "Toutes les offres": COLONNES_TOUTES, "Sources": COLONNES_SOURCES, "Entreprises": COLONNES_ENTREPRISES}


def _txt(v) -> str:
    """Une cellule n'est jamais lue comme une formule."""
    s = "" if v is None else str(v)[:45000]
    return "'" + s if s[:1] in "=+-@" else s


def _date(v) -> str:
    return v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else (str(v)[:10] if v else "")


def _sans_vide(v: list) -> list:
    """Lignes d'un onglet sans les lignes entièrement vides de fin ([[]] pour un onglet vide)."""
    v = [list(r) for r in (v or [])]
    while v and not any(str(c).strip() for c in v[-1]):
        v.pop()
    return v


def _lieu(o: dict) -> str:
    lieu, pays = str(o.get("location") or ""), str(o.get("country") or "")
    return f"{lieu}, {pays}" if lieu and pays and pays.lower() not in lieu.lower() else lieu or pays


def _maintenant() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Veille:
    def __init__(self, gc, sheet_id: str):
        self.classeur = gc.open_by_key(sheet_id)
        self.f = {}
        existants = {w.title: w for w in self.classeur.worksheets()}
        for nom, cols in ONGLETS.items():
            w = existants.get(nom) or self.classeur.add_worksheet(title=nom, rows=1000, cols=len(cols))
            v = _sans_vide(w.get_all_values())
            if not v:                               # gspread renvoie [[]] pour un onglet vide
                w.update(values=[cols], range_name="A1", value_input_option="RAW")
            elif v[0][:1] != cols[:1]:              # données sans en-tête (veille interrompue) : en-tête réinséré au-dessus
                w.insert_row(cols, index=1, value_input_option="RAW")
            try:
                w.freeze(rows=1)
            except Exception:
                pass
            self.f[nom] = w

    # --- lignes ---------------------------------------------------------------------------------------------------
    @staticmethod
    def ligne_a_postuler(o: dict, docs: dict) -> list:
        mode = "Mail (brouillon prêt)" if docs.get("mail") and docs.get("brouillon") else "Mail" if docs.get("mail") else "Site / LinkedIn"
        d = {"Vue le": _maintenant(), "Note": o.get("note"), "Catégorie": o.get("categorie"), "Poste": _txt(o.get("title")), "Entreprise": _txt(o.get("company")),
             "Lieu": _txt(_lieu(o)),
             "Contrat": o.get("contrat_n") or o.get("contract") or "", "Publiée": _date(o.get("posted")),
             "Candidats": "" if o.get("candidats") is None else o["candidats"], "Mode": mode, "Lien de l'offre": o.get("url") or "",
             "CV": docs.get("cv", ""), "Lettre": docs.get("lm", ""), "Dossier": docs.get("dossier", ""), "Brouillon": docs.get("brouillon", ""),
             "Statut": "À envoyer", "Date d'envoi": "", "Relance": "", "Points forts": _txt("\n".join("• " + x for x in docs.get("forts") or o.get("forts") or [])),
             "Manques": _txt("\n".join("• " + x for x in docs.get("manques") or o.get("manques") or [])), "Clé": o.get("cle", "")}
        return [d[c] for c in COLONNES_A_POSTULER]

    @staticmethod
    def ligne_toutes(o: dict) -> list:
        d = {"Vue le": _maintenant(), "Note": o.get("note"), "Catégorie": o.get("categorie"), "Poste": _txt(o.get("title")), "Entreprise": _txt(o.get("company")),
             "Lieu": _txt(o.get("location")), "Contrat": o.get("contrat_n") or o.get("contract") or "", "Publiée": _date(o.get("posted")),
             "Sources": o.get("sources") or o.get("source") or "", "Lien de l'offre": o.get("url") or "", "Verdict": o.get("verdict") or "", "Clé": o.get("cle", "")}
        return [d[c] for c in COLONNES_TOUTES]

    def a_postuler_ajouter(self, lignes: list) -> None:
        if lignes:
            self.f["À postuler"].append_rows(lignes, value_input_option="USER_ENTERED")

    def toutes_ajouter(self, lignes: list) -> None:
        if lignes:
            self.f["Toutes les offres"].append_rows(lignes, value_input_option="USER_ENTERED")

    def sources_ecrire(self, sante: list, moment: str) -> None:
        q = _maintenant()
        self.f["Sources"].append_rows([[q, moment, x.source, x.n, x.duree_s, _txt(x.erreur)] for x in sante], value_input_option="USER_ENTERED")

    # --- entreprises ----------------------------------------------------------------------------------------------
    def _tableau(self, nom):
        v = _sans_vide(self.f[nom].get_all_values())
        return (v[0], v[1:]) if v else (ONGLETS[nom], [])

    def entreprises_initialiser(self, entreprises: list) -> None:
        """Premier lancement : la liste de recherches.yaml est copiée dans l'onglet, que Pierre-Edern peut ensuite compléter."""
        _, lignes = self._tableau("Entreprises")
        if not lignes and entreprises:
            self.f["Entreprises"].append_rows([[e["nom"], e["url"], "", "", "", e["url"], ""] for e in entreprises], value_input_option="RAW")

    def entreprises_lire(self) -> list:
        tete, lignes = self._tableau("Entreprises")
        i, j = tete.index("Entreprise"), tete.index("Adresse")
        return [(l[i].strip(), l[j].strip()) for l in lignes if len(l) > j and l[i].strip() and l[j].strip()]

    def entreprises_maj(self, resultats: list, detectees: dict) -> None:
        tete, lignes = self._tableau("Entreprises")
        par_nom = {r["entreprise"]: r for r in resultats}
        q = _maintenant()
        for l in lignes:
            l += [""] * (len(tete) - len(l))
            nom = l[0]
            if nom in par_nom:
                r = par_nom[nom]
                l[tete.index("Méthode")], l[tete.index("Offres (dernière veille)")] = r.get("methode", ""), r.get("offres", 0)
                l[tete.index("Erreur")], l[tete.index("Mise à jour")] = _txt(r.get("erreur", "")), q
            if nom in detectees:             # système caché trouvé par le navigateur : interrogé directement la prochaine fois
                l[tete.index("Adresse")] = detectees[nom]
        if lignes:
            self.f["Entreprises"].update(values=lignes, range_name="A2", value_input_option="RAW")

    # --- suivi des candidatures -----------------------------------------------------------------------------------
    def statuts_lire(self) -> list:
        tete, lignes = self._tableau("À postuler")
        return [dict(zip(tete, l + [""] * (len(tete) - len(l))), _ligne=k + 2) for k, l in enumerate(lignes)]

    def statut_maj(self, cle: str, **champs) -> bool:
        tete, lignes = self._tableau("À postuler")
        ic = tete.index("Clé")
        for k, l in enumerate(lignes):
            if len(l) > ic and l[ic] == cle:
                l += [""] * (len(tete) - len(l))
                for nom, v in champs.items():
                    if nom in tete:
                        l[tete.index(nom)] = v
                self.f["À postuler"].update(values=[l], range_name=f"A{k + 2}", value_input_option="USER_ENTERED")
                return True
        return False
