import os
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from veille.sources import Contexte
from veille.sources import alertes_mail as AM
from tests.faux_google import faux_services

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "alertes")
lire = lambda n: open(os.path.join(FIX, n), encoding="utf8").read()


def test_analyser_linkedin_une_offre():
    o = AM.analyser_linkedin(lire("linkedin_1.txt"))
    assert len(o) == 1 and o[0].titre == "VIE - Purchasing Data H/F" and o[0].entreprise == "Volvo Buses" and o[0].lieu == "Göteborg"
    assert o[0].url == "https://www.linkedin.com/jobs/view/4488854249/" and o[0].source == "LinkedIn"


def test_analyser_linkedin_plusieurs_offres_anglais():
    o = AM.analyser_linkedin(lire("linkedin_2.txt"))
    assert [x.entreprise for x in o] == ["Telespazio France", "FoodFlow", "AB InBev"]
    assert o[2].lieu.startswith("Leuven") and "4499999999" in o[2].url


def test_analyser_indeed():
    o = AM.analyser_indeed(lire("indeed_1.txt"))
    assert [x.titre for x in o] == ["Approvisionneur - Acheteur Technique Junior", "Acheteur.euse - Junior (F/H)", "Responsable Comptabilité Flux - H/F"]
    assert o[0].entreprise == "GROUPE TECHNIC ASSISTANCE" and o[0].lieu == "Rouen (76)" and o[0].pays == "France"
    assert o[0].url == "https://fr.indeed.com/viewjob?jk=afd3139ff9f0e377" and "Bac +2" in o[0].description and o[0].source == "Indeed"


def _mail(expediteur, corps):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = expediteur, "moi@example.com", "alerte"
    m.set_content(corps)
    return m.as_bytes()


def test_collecter_sans_modifier_les_mails(monkeypatch):
    s = faux_services()
    s.gmail.ajouter_message(_mail("Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>", lire("linkedin_2.txt")))
    s.gmail.ajouter_message(_mail("Indeed <donotreply@jobalert.indeed.com>", lire("indeed_1.txt")))
    monkeypatch.setattr(AM.LC, "completer", lambda o: o)
    ctx = Contexte(cfg={}, rech={}, depuis=datetime.now(timezone.utc) - timedelta(hours=6), moment="midi", services=s)
    offres = AM.collecter(ctx)
    assert len(offres) == 6
    noms = [a[0] for a in s.gmail.appels]
    assert "messages.modify" not in noms and "messages.batchModify" not in noms
    q = next(a[1] for a in s.gmail.appels if a[0] == "messages.list")
    assert "after:" in q and "jobalerts-noreply@linkedin.com" in q


def test_liens_alertes_generes(tmp_path):
    from outils import liens_alertes
    p = tmp_path / "A.md"
    n = liens_alertes.ecrire({"france_achats": ["acheteur junior"], "france_supply": [], "france_graduate": [], "europe_titres": ["junior buyer"],
                              "french_speaker": [], "vie": []}, str(p))
    t = p.read_text(encoding="utf8")
    assert n >= 5 and t.count("https://www.linkedin.com/jobs/search/") == n and "f_TPR" not in t
