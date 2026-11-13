import copy
import json

import pytest

from veille import redaction_ia as RI

CFG = {"gemini": {"modele": "gemini-flash-latest", "max_appels": 60}}
DESC = ("Telespazio recrute un Acheteur junior (H/F) en CDI à Toulouse. Missions : suivi des commandes fournisseurs et relance des "
        "retards, analyse des écarts de prix, participation aux appels d'offres, mise à jour des indicateurs de performance fournisseurs "
        "sous Power BI, gestion des litiges de facturation avec la comptabilité. Profil : Bac+5 école de commerce, spécialisation achats "
        "ou supply chain, première expérience en stage, anglais professionnel, Excel. Jeune diplômé bienvenu. Contrat : CDI.")


class Rep:
    def __init__(self, code, js=None):
        self.status_code, self._js = code, js

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _gemini(contenu):
    return Rep(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(contenu, ensure_ascii=False)}]}}]})


@pytest.fixture
def r(moteur_local):
    a = moteur_local.OA.analyse_directe(DESC, "Acheteur junior (H/F)", "Telespazio", "Toulouse", "France", None, "CDI", "", "/tmp/essai_ri")
    moteur_local.OA.finir_analyse(a)
    return a


def _reponse(r, **k):
    ent = r["ent"]
    js = {"metier": "Acheteur", "contrat": "CDI", "famille": "achats", "puces": [],
          "profil": f"Diplômé d'école de commerce en achats, je veux apporter à {ent} une méthode de suivi fournisseurs et d'analyse des coûts.",
          "accroche": f"Le suivi des commandes fournisseurs est au cœur de ce poste chez {ent}. Je suis déjà des prestataires de transport dans mon stage.",
          "preuves": "x", "limite": "y", "projet": "z"}
    js.update(k)
    return js


def test_chiffre_invente_refuse(r, monkeypatch):
    avant = copy.deepcopy(r["lettre"].get("paras"))
    monkeypatch.setattr(RI, "_post", lambda *a, **k: _gemini(_reponse(r, preuves="J'ai audité 3 000 expéditions et négocié les écarts de prix avec 5 prestataires pour la Finance chaque semaine sans exception, avec rigueur et méthode au quotidien.")))
    notes = RI.rediger(r, "cle", CFG, {})
    assert "3 000" not in json.dumps(r["lettre"], ensure_ascii=False)
    assert r["lettre"].get("paras") == avant or "3 000" not in " ".join(r["lettre"].get("paras") or [])
    assert any("À relire" in n for n in notes)


def test_faux_employeur_refuse(r, monkeypatch):
    avant = r["spec"].get("profileTarget")
    monkeypatch.setattr(RI, "_post", lambda *a, **k: _gemini(_reponse(r, profil="Chez Telespazio je gère déjà le suivi des fournisseurs et des commandes au quotidien.")))
    RI.rediger(r, "cle", CFG, {})
    assert r["spec"].get("profileTarget") == avant


def test_429_repli(r, monkeypatch):
    avant = copy.deepcopy({k: r[k] for k in ("spec", "lettre", "forts", "faibles")})
    monkeypatch.setattr(RI, "_post", lambda *a, **k: Rep(429, {}))
    assert RI.rediger(r, "cle", CFG, {}) == ["IA indisponible : version moteur v12"]
    assert {k: r[k] for k in ("spec", "lettre", "forts", "faibles")} == avant


def test_plafond_appels(r, monkeypatch):
    appels = []
    monkeypatch.setattr(RI, "_post", lambda *a, **k: appels.append(1) or _gemini(_reponse(r)))
    compteur = {"appels": 60}
    assert RI.rediger(r, "cle", CFG, compteur) == ["IA indisponible : version moteur v12"]
    assert appels == [] and compteur["appels"] == 60


def test_sans_cle_pas_d_appel(r, monkeypatch):
    monkeypatch.setattr(RI, "_post", lambda *a, **k: pytest.fail("aucun appel sans clé"))
    assert RI.rediger(r, "", CFG, {}) == ["IA indisponible : version moteur v12"]
