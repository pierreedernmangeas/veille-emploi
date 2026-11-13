import time, types
from datetime import datetime, timezone
from veille.modele import Offre
from veille.sources import Contexte, tout_collecter


def _src(nom, f):
    return types.SimpleNamespace(NOM=nom, collecter=f)


def _ctx():
    return Contexte(cfg={}, rech={}, depuis=datetime.now(timezone.utc), moment="matin", services=None, secrets={}, budget={})


def test_source_qui_plante_n_arrete_pas_les_autres():
    def boum(ctx):
        raise RuntimeError("HTTP 429")
    ok = _src("ok", lambda ctx: [Offre("ok", "Acheteur", "X"), Offre("ok", "Buyer", "Y")])
    offres, sante = tout_collecter(_ctx(), [_src("boum", boum), ok])
    assert len(offres) == 2
    s = {x.source: x for x in sante}
    assert s["boum"].erreur.startswith("RuntimeError") and "429" in s["boum"].erreur and s["ok"].n == 2 and s["ok"].erreur == ""


def test_source_trop_lente_coupee():
    def lent(ctx):
        time.sleep(5)
        return [Offre("lent", "A", "B")]
    t0 = time.time()
    offres, sante = tout_collecter(_ctx(), [_src("lent", lent), _src("vite", lambda c: [])], delai_s=1)
    assert time.time() - t0 < 3 and offres == [] and "délai" in sante[0].erreur + sante[1].erreur


def test_duree_propre_a_chaque_source():
    rapide, lente = _src("Rapide", lambda c: []), _src("Lente", lambda c: time.sleep(1.2) or [])
    _, sante = tout_collecter(_ctx(), [rapide, lente], delai_s=10)
    d = {x.source: x.duree_s for x in sante}
    assert d["Rapide"] < 0.5 and d["Lente"] >= 1.0
