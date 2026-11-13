import types
from datetime import datetime, timedelta, timezone
import pandas as pd
from veille.sources import Contexte
from veille.sources import sites_emploi as SE, api_officielles as AO, vie as V

RECH = {"france_achats": ["acheteur junior", "assistant achats"], "france_supply": ["approvisionneur"], "france_graduate": ["graduate programme achats"],
        "europe_titres": ["junior buyer", "procurement analyst"], "french_speaker": ["French speaking buyer"], "europe_pays": {"Belgium": "Belgium", "Ireland": "Ireland"},
        "pays_francophones": ["Belgium"], "vie": ["VIE", "VIE buyer"]}


class Rep:
    def __init__(self, d, code=200):
        self._d, self.status_code, self.text = d, code, str(d)

    def json(self):
        return self._d


def _rc(**fonctions):
    return types.SimpleNamespace(moteur=None, **fonctions)


def _ctx(moteur=None, secrets=None, heures=12):
    return Contexte(cfg={}, rech=RECH, depuis=datetime.now(timezone.utc) - timedelta(hours=heures), moment="matin", secrets=secrets or {}, moteur=moteur)


def test_indeed_pays_et_heures(monkeypatch):
    appels = []

    def faux(**k):
        appels.append(k)
        return pd.DataFrame([{"title": "Junior Buyer", "company": "X", "location": "Brussels", "job_url": "https://be.indeed.com/viewjob?jk=1",
                              "description": "d" * 400, "job_type": "fulltime", "date_posted": None, "job_level": None}])
    monkeypatch.setattr(SE, "_scrape", faux)
    offres = SE.indeed_et_hellowork(_ctx(heures=12))
    be = [a for a in appels if a.get("country_indeed") == "Belgium"]
    assert be and all(a["hours_old"] == 13 for a in be) and any(a["search_term"] == "acheteur junior" for a in be)      # pays francophone : termes FR aussi
    assert any(a["site_name"] == ["hellowork"] for a in appels) and offres and offres[0].source in ("Indeed", "HelloWork")


def test_wttj_normalise():
    rc = types.SimpleNamespace(wttj=lambda q, j, pays, filtre=None, pages=3: [dict(source="WTTJ", title="Acheteur junior", company="Y", location="Paris",
                               country="France", url="https://wttj/1", posted=None, desc="desc", contract="CDI")])
    m = types.SimpleNamespace(rc=rc)
    offres = SE.wttj(_ctx(moteur=m))
    assert offres[0].source == "WTTJ" and offres[0].titre == "Acheteur junior" and offres[0].contrat_brut == "CDI"


def test_apec_normalise(monkeypatch):
    res = {"resultats": [{"numeroOffre": "178123W", "intitule": "Acheteur junior H/F", "nomCommercial": "Safran", "lieuTexte": "Paris 15e - 75",
                          "datePublication": datetime.now(timezone.utc).isoformat(), "texteOffre": "<p>Missions achats...</p>", "salaireTexte": "35 k€"}]}
    monkeypatch.setattr(SE, "_post", lambda *a, **k: Rep(res))
    offres = SE.apec(_ctx())
    o = offres[0]
    assert o.source == "APEC" and o.entreprise == "Safran" and o.url.endswith("/178123W") and "Missions achats" in o.description and o.pays == "France"


def test_france_travail_cle_absente():
    assert AO.france_travail(_ctx(secrets={})) == []


def test_france_travail_normalise(monkeypatch):
    monkeypatch.setattr(AO, "_post", lambda *a, **k: Rep({"access_token": "tok"}))
    monkeypatch.setattr(AO, "_get", lambda *a, **k: Rep({"resultats": [{"id": "201ABCD", "intitule": "Approvisionneur (H/F)", "entreprise": {"nom": "Z"},
                        "lieuTravail": {"libelle": "69 - Lyon"}, "dateCreation": "2026-11-12T08:00:00.000Z", "description": "Missions " * 50, "typeContrat": "CDI"}]}))
    o = AO.france_travail(_ctx(secrets={"FT_CLIENT_ID": "a", "FT_CLIENT_SECRET": "b"}))[0]
    assert o.source == "France Travail" and o.contrat_brut == "CDI" and o.url.endswith("201ABCD") and o.pays == "France"


def test_vie_mon_vie_et_contrat(monkeypatch):
    monkeypatch.setattr(SE, "_scrape", lambda **k: pd.DataFrame([]))
    rc = types.SimpleNamespace(mon_vie=lambda key="": [dict(source="Mon V.I.E", title="VIE Acheteur", company="Airbus", location="Hambourg, Allemagne",
                                 country="Allemagne", url="https://mon-vie/1", posted=None, desc="", contract="V.I.E")],
                               mon_vie_details=lambda rows, **k: None, wttj=lambda *a, **k: [])
    m = types.SimpleNamespace(rc=rc)
    offres = V.collecter(_ctx(moteur=m))
    assert offres[0].source == "Mon V.I.E" and offres[0].contrat_brut == "V.I.E"


def test_france_travail_en_panne_n_empeche_pas_adzuna(monkeypatch):
    def boum(ctx):
        raise RuntimeError("invalid_scope")
    monkeypatch.setattr(AO, "france_travail", boum)
    monkeypatch.setattr(AO, "adzuna", lambda ctx: ["offre adzuna"])
    ctx = _ctx()
    assert AO.collecter(ctx) == ["offre adzuna"]
    assert any("France Travail" in n for n in ctx.budget.get("notes_sources", []))
