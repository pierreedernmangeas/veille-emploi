import json, os
from datetime import datetime, timedelta, timezone
import pytest
from veille.sources import Contexte
from veille.sources import linkedin_apify as LA, linkedin_jobspy as LJ, linkedin_commun as LC

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
RECH = {"france_achats": ["acheteur junior", "assistant achats"], "france_supply": ["approvisionneur junior"], "france_graduate": ["graduate programme achats"],
        "europe_titres": ["junior buyer"], "french_speaker": ["French speaking buyer"], "vie": ["VIE", "VIE buyer"]}


def _ctx(secrets=None, cfg=None):
    return Contexte(cfg=cfg or {"apify": {"acteur": "x~y", "plafond_dollars": 4.5, "max_resultats_par_requete": 50},
                               "linkedin_jobspy": {"pages_max": 2, "pause_s": [0, 0]}},
                    rech=RECH, depuis=datetime.now(timezone.utc) - timedelta(hours=12), moment="matin", secrets=secrets or {})


class Rep:
    def __init__(self, data, code=200):
        self._d, self.status_code, self.text = data, code, json.dumps(data) if not isinstance(data, str) else data

    def json(self):
        return self._d


def test_urls_recherche_periode_et_zones():
    urls = LC.urls_recherche(RECH, 43200)
    assert any("geoId=105015875" in u and "f_TPR=r43200" in u for _, u in urls)          # France
    assert any(c == "V.I.E" and "geoId=92000000" in u for c, u in urls)                    # V.I.E monde
    assert any(c == "French speaker" for c, _ in urls)


def test_apify_cle_absente():
    assert LA.collecter(_ctx(secrets={})) == []


def test_apify_plafond_atteint_saute(monkeypatch):
    appels = []
    monkeypatch.setattr(LA, "_get", lambda url, **k: Rep({"data": {"current": {"monthlyUsageUsd": 4.6}}}))
    monkeypatch.setattr(LA, "_post", lambda *a, **k: appels.append(a) or Rep([]))
    with pytest.raises(LA.PlafondAtteint):
        LA.collecter(_ctx(secrets={"APIFY_TOKEN": "t"}))
    assert appels == []


def test_apify_normalise(monkeypatch):
    items = json.load(open(os.path.join(FIX, "apify_linkedin.json")))
    monkeypatch.setattr(LA, "_get", lambda url, **k: Rep({"data": {"current": {"monthlyUsageUsd": 0.5}}}))
    monkeypatch.setattr(LA, "_post", lambda *a, **k: Rep(items))
    offres = LA.collecter(_ctx(secrets={"APIFY_TOKEN": "t"}))
    o = next(x for x in offres if x.entreprise == "FoodFlow")
    assert o.titre.startswith("Approvisionneur") and LC.id_offre(o.url) == "4489091659" and o.candidats == 194 and o.source == "LinkedIn"
    b = next(x for x in offres if x.entreprise == "AB InBev")
    assert b.titre == "Junior Buyer" and b.candidats == 12 and b.publiee_le.year == 2026


def test_jobspy_arret_429(monkeypatch):
    appels = []

    def faux(**k):
        appels.append(k)
        raise Exception("429 Client Error: Too Many Requests")
    monkeypatch.setattr(LJ, "_scrape", faux)
    with pytest.raises(LJ.Bloque):
        LJ.collecter(_ctx())
    assert len(appels) == 1


def _df_un(jid):
    import pandas as pd
    return pd.DataFrame([{"job_url": f"https://www.linkedin.com/jobs/view/{jid}/", "title": "Acheteur junior", "company": "X", "location": "Paris",
                          "description": "d" * 400, "job_type": "fulltime", "job_level": "entry level"}])


def test_jobspy_429_garde_les_offres_deja_lues(monkeypatch):
    n = []

    def faux(**k):
        n.append(1)
        if len(n) > 2:
            raise Exception("429 Client Error: Too Many Requests")
        return _df_un(4000000 + len(n))
    monkeypatch.setattr(LJ, "_scrape", faux)
    ctx = _ctx()
    offres = LJ.collecter(ctx)
    assert len(offres) == 2 and len(n) == 3
    assert any("bloqué" in x for x in ctx.budget.get("notes_sources", []))


def test_jobspy_budget_de_temps(monkeypatch):
    n = []
    monkeypatch.setattr(LJ, "_scrape", lambda **k: n.append(1) or _df_un(5000000 + len(n)))
    ctx = _ctx(cfg={"linkedin_jobspy": {"pages_max": 2, "pause_s": [0, 0], "budget_s": 0}})
    offres = LJ.collecter(ctx)
    assert len(n) == 1 and len(offres) == 1                                    # budget épuisé après la 1re recherche
    assert any("temps" in x for x in ctx.budget.get("notes_sources", []))


def test_lecture_description_guest(monkeypatch):
    html = open(os.path.join(FIX, "linkedin_guest_posting.html"), encoding="utf8").read()
    monkeypatch.setattr(LC, "_get", lambda url, **k: Rep(html))
    d = LC.lire_description_linkedin("4489091659")
    assert len(d["description"]) > 1000 and d["candidats"] == 194 and d["contrat"] == "Temps plein" and d["entreprise"] == "FoodFlow"


def test_recherche_guest_html():
    html = open(os.path.join(FIX, "linkedin_guest_recherche.html"), encoding="utf8").read()
    offres = LC.analyser_recherche(html)
    assert len(offres) >= 5 and all(o.url.startswith("https://www.linkedin.com/jobs/view/") for o in offres) and offres[0].titre


def test_jobspy_toutes_recherches_en_erreur_signalee(monkeypatch):
    def faux(**k):
        raise ValueError("format inattendu")
    monkeypatch.setattr(LJ, "_scrape", faux)
    with pytest.raises(RuntimeError) as e:
        LJ.collecter(_ctx())
    assert "format inattendu" in str(e.value)
