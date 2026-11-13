import types
from datetime import datetime, timedelta, timezone

from veille.sources import Contexte
from veille.sources import sites_carrieres as SC

RECH = {"vie": ["VIE buyer"], "sites_carrieres_mots": ["acheteur"], "entreprises": [{"nom": "Démo", "url": "https://demo.wd3.myworkdayjobs.com/Careers"},
                                                                                    {"nom": "Cachée", "url": "https://www.cachee.fr/carrieres"}]}
CFG = {"sites_carrieres": {"complet": ["matin"], "leger": ["midi", "soir"]}}


class Rep:
    def __init__(self, d):
        self._d = d

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


class FauxSession:
    """Workday : 3 offres en liste, une fiche par offre."""
    POSTES = {"/job/1": "Acheteur Junior", "/job/2": "VIE Buyer", "/job/3": "Sales Manager"}

    def post(self, url, json=None, **k):
        if json.get("offset", 0) > 0:
            return Rep({"total": 3, "jobPostings": []})
        return Rep({"total": 3, "facets": [], "jobPostings": [{"title": t, "externalPath": p, "locationsText": "Toulouse"} for p, t in self.POSTES.items()]})

    def get(self, url, **k):
        p = "/job/" + url.rsplit("/", 1)[-1]
        desc = "Contrat à durée indéterminée, achats." if p == "/job/1" else "Mission de 12 mois."
        return Rep({"jobPostingInfo": {"jobDescription": f"<p>{desc}</p>", "externalUrl": f"https://demo.example{p}"}})


def _moteur():
    def offer(**k):
        base = dict(source="", title="", company="", location="", country="", contract="", posted=None, url="", desc="", extra="")
        base.update(k)
        return base
    rc = types.SimpleNamespace(S=FauxSession(), clean=lambda s: " ".join(str(s or "").split()), clean_html=lambda s: s, to_dt=lambda v: None, offer=offer)
    C = types.SimpleNamespace(metier=lambda t, d="": ("hors", "") if "sales" in t.lower() else ("coeur", ""))
    return types.SimpleNamespace(rc=rc, C=C)


def _ctx(moment):
    return Contexte(cfg=CFG, rech=RECH, depuis=datetime.now(timezone.utc) - timedelta(hours=8), moment=moment, moteur=_moteur())


def test_workday_garde_cdi_achats_et_vie(monkeypatch):
    ctx = _ctx("midi")
    ctx.entreprises = RECH["entreprises"][:1]
    offres = SC.collecter(ctx)
    titres = {o.titre: o for o in offres}
    assert set(titres) == {"Acheteur Junior", "VIE Buyer"}                    # « Sales Manager » écarté
    assert titres["VIE Buyer"].contrat_brut == "V.I.E"
    assert titres["Acheteur Junior"].contrat_brut == ""                       # pas de preuve V.I.E : pas de contrat V.I.E
    assert all(o.source == "Site carrières" and o.entreprise == "Démo" for o in offres)


def test_mode_leger_sans_navigateur(monkeypatch):
    lances = []

    async def faux_run_all(companies, navigateur=True, res=None):
        lances.extend(companies)
        return []
    monkeypatch.setattr(SC, "run_all", faux_run_all)
    SC.collecter(_ctx("midi"))
    assert [n for n, _ in lances] == ["Démo"]                                  # midi : la page « Cachée » (navigateur) est sautée
    lances.clear()
    SC.collecter(_ctx("matin"))
    assert [n for n, _ in lances] == ["Démo", "Cachée"]                        # matin : tout, navigateur compris


def test_limite_de_temps_garde_les_resultats_finis(monkeypatch):
    async def lent(companies, navigateur=True, res=None):
        res.append(("Démo", "u", "workday", [SC.rc.offer(source="Site carrières", title="Acheteur", company="Démo", url="https://d/1")], "", "", "", 1))
        await SC.asyncio.sleep(5)
    monkeypatch.setattr(SC, "run_all", lent)
    ctx = _ctx("matin")
    ctx.cfg = {"sites_carrieres": {"complet": ["matin"], "limite_s": 0.5}}
    offres = SC.collecter(ctx)
    assert [o.titre for o in offres] == ["Acheteur"]
    assert {e["entreprise"]: e["erreur"] for e in ctx.budget["sites_carrieres"]}["Cachée"] == "limite de temps atteinte"
