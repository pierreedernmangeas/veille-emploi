# -*- coding: utf-8 -*-
"""Le Google Sheet « Veille emploi », dans cet ordre :
- « À postuler » : le suivi global de toutes les offres retenues (plus récentes en haut, statut à jour, liens courts et cliquables) ;
- un onglet par veille (« 15/11 matin ») : uniquement les offres sorties à cette veille, triées par note ; les 21 dernières sont gardées ;
- « Toutes les offres » (tout ce qui a été gardé), « Sources » (santé de chaque source), « Entreprises » (sites carrières, modifiables)."""
import re
from datetime import datetime, timedelta

COLONNES_A_POSTULER = ["Vue le", "Veille", "Note", "Statut", "Poste", "Entreprise", "Lieu", "Contrat", "Catégorie", "Candidature", "Offre", "CV",
                       "Lettre", "Dossier", "Brouillon", "Date d'envoi", "Relance", "Publiée", "Candidats", "Points forts", "Manques", "Clé"]
COLONNES_VEILLE = ["Note", "Poste", "Entreprise", "Lieu", "Contrat", "Catégorie", "Candidature", "Offre", "CV", "Lettre", "Dossier", "Publiée"]
COLONNES_TOUTES = ["Vue le", "Note", "Catégorie", "Poste", "Entreprise", "Lieu", "Contrat", "Publiée", "Sources", "Lien de l'offre", "Verdict", "Clé"]
COLONNES_SOURCES = ["Date", "Veille", "Source", "Offres", "Durée (s)", "Erreur"]
COLONNES_ENTREPRISES = ["Entreprise", "Adresse", "Méthode", "Offres (dernière veille)", "Erreur", "Adresse d'origine", "Mise à jour"]
ONGLETS = {"À postuler": COLONNES_A_POSTULER, "Toutes les offres": COLONNES_TOUTES, "Sources": COLONNES_SOURCES, "Entreprises": COLONNES_ENTREPRISES}
ANCIENS_NOMS = {"Mode": "Candidature", "Lien de l'offre": "Offre"}       # premier format du Sheet (13/11/2026)
LIENS = {"Offre": "Ouvrir", "CV": "CV", "Lettre": "Lettre", "Dossier": "Dossier", "Brouillon": "Brouillon"}
STATUTS = ["À envoyer", "Envoyée", "Réponse reçue", "Relance prête", "Relancée", "Entretien", "Refus", "Pas intéressé", "Brouillon supprimé"]
ONGLETS_VEILLE_MAX = 21                                                  # une semaine de veilles (3 par jour)
NOM_VEILLE = re.compile(r"^\d\d/\d\d ")
VIDES = {"Feuille 1", "Feuil1", "Sheet1"}                                # onglet créé d'office avec un nouveau Sheet
LARGEURS_A_POSTULER = {"Vue le": 120, "Veille": 95, "Note": 50, "Statut": 115, "Poste": 280, "Entreprise": 170, "Lieu": 150, "Contrat": 85,
                       "Catégorie": 140, "Candidature": 140, "Offre": 60, "CV": 45, "Lettre": 55, "Dossier": 65, "Brouillon": 75,
                       "Date d'envoi": 95, "Relance": 85, "Publiée": 90, "Candidats": 80, "Points forts": 320, "Manques": 260, "Clé": 60}
LARGEURS_VEILLE = {"Note": 50, "Poste": 300, "Entreprise": 180, "Lieu": 160, "Contrat": 85, "Catégorie": 150, "Candidature": 150, "Offre": 60,
                   "CV": 45, "Lettre": 55, "Dossier": 65, "Publiée": 90}


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


def _colonne(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _candidature(docs: dict) -> str:
    return "Mail (brouillon prêt)" if docs.get("mail") and docs.get("brouillon") else "Mail" if docs.get("mail") else "Site / LinkedIn"


class Veille:
    def __init__(self, gc, sheet_id: str):
        self.classeur = gc.open_by_key(sheet_id)
        self.sep = "," if str(getattr(self.classeur, "locale", "") or "").startswith("en") else ";"   # séparateur des formules
        self.f = {}
        existants = {w.title: w for w in self.classeur.worksheets()}
        a_mettre_en_forme = []
        for nom, cols in ONGLETS.items():
            w = existants.get(nom) or self.classeur.add_worksheet(title=nom, rows=1000, cols=len(cols))
            v = _sans_vide(w.get_all_values())
            if not v:                               # gspread renvoie [[]] pour un onglet vide
                w.update(values=[cols], range_name="A1", value_input_option="RAW")
                a_mettre_en_forme.append(nom)
            elif nom == "À postuler" and v[0] != cols and "Clé" in v[0]:
                self._reprendre_ancien_format(w, v)  # ancien format : colonnes réordonnées, liens raccourcis, veilles passées en onglets
                a_mettre_en_forme.append(nom)
            elif v[0][:1] != cols[:1]:              # données sans en-tête (veille interrompue) : en-tête réinséré au-dessus
                w.insert_row(cols, index=1, value_input_option="RAW")
            self.f[nom] = w
        for w in self.classeur.worksheets():        # « Feuille 1 » vide créée d'office avec le Sheet
            if w.title in VIDES and not _sans_vide(w.get_all_values()) and len(self.classeur.worksheets()) > 1:
                self._essayer(lambda w=w: self.classeur.del_worksheet(w))
        for nom in a_mettre_en_forme:
            self._mettre_en_forme(self.f[nom], ONGLETS[nom], nom == "À postuler")

    # --- outils ---------------------------------------------------------------------------------------------------
    @staticmethod
    def _essayer(f):
        try:                                        # la mise en page ne doit jamais faire échouer une veille
            return f()
        except Exception:
            return None

    def _lien(self, url, texte) -> str:
        url = str(url or "").strip()
        if not url.startswith("http"):
            return ""
        return f'=HYPERLINK("{url.replace(chr(34), "%22")}"{self.sep}"{texte}")'

    def _mettre_en_forme(self, w, cols, suivi=False):
        """En-tête figé et coloré, largeurs, textes longs coupés ; pour le suivi : notes en couleur, statut en liste, filtre."""
        sid = w.id
        largeurs = LARGEURS_A_POSTULER if suivi else LARGEURS_VEILLE if cols == COLONNES_VEILLE else {}
        req = [{"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
               {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                               "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                                                              "backgroundColor": {"red": 0.09, "green": 0.2, "blue": 0.31}, "verticalAlignment": "MIDDLE"}},
                               "fields": "userEnteredFormat(textFormat,backgroundColor,verticalAlignment)"}},
               {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1},
                               "cell": {"userEnteredFormat": {"wrapStrategy": "CLIP", "verticalAlignment": "TOP"}},
                               "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}}]
        req += [{"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": cols.index(c), "endIndex": cols.index(c) + 1},
                                               "properties": {"pixelSize": px}, "fields": "pixelSize"}} for c, px in largeurs.items() if c in cols]
        if "Note" in cols:
            n = cols.index("Note")
            lettre = _colonne(n)
            for rang, (seuil, rgb) in enumerate([(8, (0.72, 0.88, 0.74)), (7, (0.87, 0.94, 0.8)), (0, (1, 0.95, 0.8))]):
                req.append({"addConditionalFormatRule": {"index": rang, "rule": {
                    "ranges": [{"sheetId": sid, "startRowIndex": 1, "startColumnIndex": n, "endColumnIndex": n + 1}],
                    "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=AND(${lettre}2<>\"\"{self.sep}${lettre}2>={seuil})"}]},
                                    "format": {"backgroundColor": {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}, "textFormat": {"bold": True}}}}}})
        if suivi:
            st = cols.index("Statut")
            req.append({"setDataValidation": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": st, "endColumnIndex": st + 1},
                                              "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": x} for x in STATUTS]},
                                                       "showCustomUi": True, "strict": False}}})
            req.append({"setBasicFilter": {"filter": {"range": {"sheetId": sid, "startRowIndex": 0, "startColumnIndex": 0, "endColumnIndex": len(cols)}}}})
            cle = cols.index("Clé")
            req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": cle, "endIndex": cle + 1},
                                                      "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}})
        self._essayer(lambda: self.classeur.batch_update({"requests": req}))

    # --- onglet par veille ----------------------------------------------------------------------------------------
    def nom_onglet_veille(self, moment: str, quand: datetime | None = None) -> str:
        quand = quand or datetime.now()
        base = f"{quand.strftime('%d/%m')} {moment}"
        noms = {w.title for w in self.classeur.worksheets()}
        nom, k = base, 2
        while nom in noms:                          # deuxième veille du même moment (relance à la main)
            nom, k = f"{base} ({k})", k + 1
        return nom

    def _ligne_veille(self, o: dict, docs: dict) -> list:
        d = {"Note": o.get("note"), "Poste": _txt(o.get("title")), "Entreprise": _txt(o.get("company")), "Lieu": _txt(_lieu(o)),
             "Contrat": o.get("contrat_n") or o.get("contract") or "", "Catégorie": o.get("categorie") or "", "Candidature": _candidature(docs),
             "Offre": self._lien(o.get("url"), LIENS["Offre"]), "CV": self._lien(docs.get("cv"), "CV"), "Lettre": self._lien(docs.get("lm"), "Lettre"),
             "Dossier": self._lien(docs.get("dossier"), "Dossier"), "Publiée": _date(o.get("posted"))}
        return [d[c] for c in COLONNES_VEILLE]

    def onglet_veille(self, moment: str, offres: list, quand: datetime | None = None, nom: str | None = None) -> str:
        """offres : [(offre, docs)] gardées à cette veille. Onglet placé juste après « À postuler », triées par note."""
        nom = nom or self.nom_onglet_veille(moment, quand)
        lignes = [self._ligne_veille(o, d) for o, d in sorted(offres, key=lambda x: -(x[0].get("note") or 0))]
        if not lignes:                              # une veille sans nouveauté a quand même son onglet : on voit qu'elle a tourné
            lignes = [["", "Aucune nouvelle offre retenue à cette veille"] + [""] * (len(COLONNES_VEILLE) - 2)]
        self._creer_onglet_veille(nom, [COLONNES_VEILLE] + lignes)
        return nom

    def _creer_onglet_veille(self, nom, valeurs):
        w = self.classeur.add_worksheet(title=nom, rows=max(30, len(valeurs) + 5), cols=len(COLONNES_VEILLE), index=1)
        w.update(values=valeurs, range_name="A1", value_input_option="USER_ENTERED")
        self._mettre_en_forme(w, COLONNES_VEILLE)
        veilles = [x for x in self.classeur.worksheets() if NOM_VEILLE.match(x.title)]
        for x in veilles[ONGLETS_VEILLE_MAX:]:      # les plus anciennes sont à droite
            self._essayer(lambda x=x: self.classeur.del_worksheet(x))

    # --- reprise de l'ancien format -------------------------------------------------------------------------------
    def _reprendre_ancien_format(self, w, v):
        tete = [ANCIENS_NOMS.get(c, c) for c in v[0]]
        anciennes = [dict(zip(tete, l + [""] * (len(tete) - len(l)))) for l in v[1:]]
        anciennes.sort(key=lambda d: d.get("Vue le", ""))
        groupes, precedent = [], None                # une veille = des lignes écrites à moins d'une heure d'intervalle
        for d in anciennes:
            try:
                t = datetime.strptime(d.get("Vue le", "")[:16], "%Y-%m-%d %H:%M")
            except ValueError:
                t = precedent
            if not groupes or t is None or precedent is None or t - precedent > timedelta(minutes=60):
                groupes.append(((t or datetime.now()).strftime("%d/%m %Hh%M"), []))
            groupes[-1][1].append(d)
            precedent = t or precedent
        lignes = []
        for etiquette, ds in groupes:
            for d in ds:
                d["Veille"] = d.get("Veille") or etiquette
                for c, texte in LIENS.items():
                    if str(d.get(c, "")).startswith("http"):
                        d[c] = self._lien(d[c], texte)
                for c in ("Poste", "Entreprise", "Lieu", "Points forts", "Manques"):
                    d[c] = _txt(d.get(c, ""))
                lignes.append(d)
        lignes.sort(key=lambda d: (d.get("Vue le", ""), _note(d.get("Note"))), reverse=True)
        w.clear()
        w.update(values=[COLONNES_A_POSTULER] + [[d.get(c, "") for c in COLONNES_A_POSTULER] for d in lignes],
                 range_name="A1", value_input_option="USER_ENTERED")
        if not any(NOM_VEILLE.match(x.title) for x in self.classeur.worksheets()):
            for etiquette, ds in groupes:            # chronologique : chaque nouvel onglet passe devant le précédent
                ds = sorted(ds, key=lambda d: -_note(d.get("Note")))
                self._creer_onglet_veille(etiquette, [COLONNES_VEILLE] + [[d.get(c, "") for c in COLONNES_VEILLE] for d in ds])

    # --- lignes ---------------------------------------------------------------------------------------------------
    def ligne_a_postuler(self, o: dict, docs: dict, veille: str = "") -> list:
        d = {"Vue le": _maintenant(), "Veille": veille, "Note": o.get("note"), "Statut": "À envoyer", "Poste": _txt(o.get("title")),
             "Entreprise": _txt(o.get("company")), "Lieu": _txt(_lieu(o)), "Contrat": o.get("contrat_n") or o.get("contract") or "",
             "Catégorie": o.get("categorie") or "", "Candidature": _candidature(docs), "Offre": self._lien(o.get("url"), LIENS["Offre"]),
             "CV": self._lien(docs.get("cv"), "CV"), "Lettre": self._lien(docs.get("lm"), "Lettre"), "Dossier": self._lien(docs.get("dossier"), "Dossier"),
             "Brouillon": self._lien(docs.get("brouillon"), "Brouillon"), "Date d'envoi": "", "Relance": "", "Publiée": _date(o.get("posted")),
             "Candidats": "" if o.get("candidats") is None else o["candidats"],
             "Points forts": _txt("\n".join("• " + x for x in docs.get("forts") or o.get("forts") or [])),
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

    def a_postuler_trier(self) -> None:
        """Plus récentes en haut, puis meilleure note."""
        w = self.f["À postuler"]
        c = COLONNES_A_POSTULER
        self._essayer(lambda: self.classeur.batch_update({"requests": [{"sortRange": {
            "range": {"sheetId": w.id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": len(c)},
            "sortSpecs": [{"dimensionIndex": c.index("Vue le"), "sortOrder": "DESCENDING"}, {"dimensionIndex": c.index("Note"), "sortOrder": "DESCENDING"}]}}]}))

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
        """Écrit seulement les cellules demandées : les liens et les modifications faites à la main restent intacts."""
        tete, lignes = self._tableau("À postuler")
        ic = tete.index("Clé")
        for k, l in enumerate(lignes):
            if len(l) > ic and l[ic] == cle:
                for nom, v in champs.items():
                    if nom in tete:
                        self.f["À postuler"].update(values=[[v]], range_name=f"{_colonne(tete.index(nom))}{k + 2}", value_input_option="USER_ENTERED")
                return True
        return False


def _note(v) -> float:
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return 0.0
