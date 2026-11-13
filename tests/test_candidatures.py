import base64
import types
from datetime import date, datetime, timedelta, timezone
from email import message_from_bytes, policy

from tests.faux_google import faux_services
from veille import candidatures as CA, recap
from veille.base import Base
from veille.modele import Offre, cle
from veille.sheet import Veille

TEXTES = types.SimpleNamespace(
    objet=lambda poste, lang: f"Candidature : {poste} - Candidat" if lang == "fr" else f"Application: {poste} - Candidate",
    corps=lambda poste, ent, lien, lang: f"Bonjour,\nCandidature au poste de {poste} chez {ent} ({lien}).\nCordialement",
    corps_relance=lambda poste, ent, lang: f"Bonjour,\nJe me permets de revenir vers vous au sujet du poste de {poste}.\nCordialement")
JOUR_MS = 86400 * 1000


def _prep(tmp_path, mail="rh@demo.fr"):
    s = faux_services()
    base = Base(str(tmp_path / "v.sqlite"))
    o = Offre("Indeed", "Acheteur junior", "Démo", url="https://ex/1")
    base.ajouter(o, "documents")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4 cv")
    (tmp_path / "lm.pdf").write_bytes(b"%PDF-1.4 lm")
    d = dict(cle=cle(o), mail=mail, objet="", poste="Acheteur junior", ent="Démo", lien="https://ex/1", lang="fr",
             cv_local=str(tmp_path / "cv.pdf"), lm_local=str(tmp_path / "lm.pdf"))
    v = Veille(s.gc, "sheet1")
    v.a_postuler_ajouter([v.ligne_a_postuler(dict(title="Acheteur junior", company="Démo", url="https://ex/1", note=8, cle=d["cle"]), {"mail": mail})])
    return s, base, d, v


def test_pas_de_brouillon_sans_mail(tmp_path):
    s, base, d, _ = _prep(tmp_path, mail="")
    assert CA.preparer_brouillon(s.gmail, d, base, TEXTES) is None
    assert s.gmail.brouillons == {}


def test_brouillon_idempotent(tmp_path):
    s, base, d, _ = _prep(tmp_path)
    assert CA.preparer_brouillon(s.gmail, d, base, TEXTES)
    assert CA.preparer_brouillon(s.gmail, d, base, TEXTES) is None
    assert len(s.gmail.brouillons) == 1
    m = message_from_bytes(next(iter(s.gmail.brouillons.values()))["raw"])
    assert m["To"] == "rh@demo.fr" and m["Subject"] == "Candidature : Acheteur junior - Candidat"
    assert sorted(p.get_filename() for p in m.walk() if p.get_filename()) == ["cv.pdf", "lm.pdf"]


def test_envoi_detecte(tmp_path):
    s, base, d, v = _prep(tmp_path)
    did, _ = CA.preparer_brouillon(s.gmail, d, base, TEXTES)
    s.gmail.drafts().envoyer_simule(did, date_ms=int(datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp() * 1000))
    CA.suivre(s.gmail, v, base, date(2026, 11, 13), relance_jours=7, textes=TEXTES)
    st = v.statuts_lire()[0]
    assert st["Statut"] == "Envoyée" and st["Date d'envoi"] == "2026-11-13"
    assert base.ligne(d["cle"])["etat"] == "envoyee"


def test_reponse_detectee(tmp_path):
    s, base, d, v = _prep(tmp_path)
    did, _ = CA.preparer_brouillon(s.gmail, d, base, TEXTES)
    fil = s.gmail.brouillons[did]["threadId"]
    s.gmail.drafts().envoyer_simule(did, date_ms=int(datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp() * 1000))
    s.gmail.ajouter_message(b"From: rh@demo.fr\r\nSubject: Re: Candidature\r\n\r\nMerci, entretien ?", fil=fil)
    CA.suivre(s.gmail, v, base, date(2026, 11, 14), relance_jours=7, textes=TEXTES)
    assert v.statuts_lire()[0]["Statut"] == "Réponse reçue"


def test_relance_j7_dans_le_fil(tmp_path):
    s, base, d, v = _prep(tmp_path)
    did, _ = CA.preparer_brouillon(s.gmail, d, base, TEXTES)
    fil = s.gmail.brouillons[did]["threadId"]
    envoi = datetime(2026, 11, 13, 9, tzinfo=timezone.utc)
    mid = s.gmail.drafts().envoyer_simule(did, date_ms=int(envoi.timestamp() * 1000))
    message_id = message_from_bytes(s.gmail.msgs[mid]["raw"])["Message-ID"]
    CA.suivre(s.gmail, v, base, date(2026, 11, 13), relance_jours=7, textes=TEXTES)
    CA.suivre(s.gmail, v, base, date(2026, 11, 19), relance_jours=7, textes=TEXTES)
    assert len(s.gmail.brouillons) == 0                                 # J+6 : trop tôt
    CA.suivre(s.gmail, v, base, date(2026, 11, 20), relance_jours=7, textes=TEXTES)
    assert len(s.gmail.brouillons) == 1
    b = next(iter(s.gmail.brouillons.values()))
    m = message_from_bytes(b["raw"])
    assert b["threadId"] == fil and m["In-Reply-To"] == message_id and message_id in m["References"]
    assert m["To"] == "rh@demo.fr" and m["Subject"].startswith("Re: ")
    assert v.statuts_lire()[0]["Statut"] == "Relance prête"
    CA.suivre(s.gmail, v, base, date(2026, 11, 21), relance_jours=7, textes=TEXTES)
    assert len(s.gmail.brouillons) == 1                                 # pas de 2e relance
    s.gmail.drafts().envoyer_simule(next(iter(s.gmail.brouillons)), date_ms=int((envoi + timedelta(days=8)).timestamp() * 1000))
    CA.suivre(s.gmail, v, base, date(2026, 11, 22), relance_jours=7, textes=TEXTES)
    assert v.statuts_lire()[0]["Statut"] == "Relancée"


def test_recap_seulement_a_soi():
    s = faux_services()
    recap.envoyer(s.gmail, s.email, dict(moment="matin", nouvelles=12, documents=3,
                                         top=[dict(note=8.5, title="Acheteur junior", company="Démo", url="https://ex/1", categorie="CDI France")],
                                         brouillons=1, relances=0, erreurs=["APEC : HTTP 403"], lien_sheet="https://sheets/1"))
    envois = [a for a in s.gmail.appels if a[0] == "messages.send"]
    assert len(envois) == 1
    m = message_from_bytes(base64.urlsafe_b64decode(envois[0][1]["raw"]), policy=policy.default)
    assert m["To"] == s.email and not m["Cc"] and not m["Bcc"]
    corps = m.get_body(preferencelist=("html", "plain")).get_content()
    assert "Acheteur junior" in corps and "APEC" in corps


def test_textes_du_moteur_prive(moteur_local, tmp_path):
    import mails
    s, base, d, _ = _prep(tmp_path)
    d["lang"] = "en"
    CA.preparer_brouillon(s.gmail, d, base)                              # textes par défaut : module mails du moteur
    m = message_from_bytes(next(iter(s.gmail.brouillons.values()))["raw"], policy=policy.default)
    assert m["Subject"] == mails.objet("Acheteur junior", "en") and "January 2027" in m.get_body(preferencelist=("plain",)).get_content()


def test_brouillon_supprime_sans_plantage(tmp_path):
    s, base, d, v = _prep(tmp_path)
    did, _ = CA.preparer_brouillon(s.gmail, d, base, TEXTES)
    o2 = Offre("Indeed", "Approvisionneur", "Autre", url="https://ex/2")
    base.ajouter(o2, "documents")
    d2 = dict(d, cle=cle(o2), poste="Approvisionneur", ent="Autre")
    v.a_postuler_ajouter([v.ligne_a_postuler(dict(title="Approvisionneur", company="Autre", url="https://ex/2", note=8, cle=d2["cle"]), {"mail": "rh@autre.fr"})])
    did2, _ = CA.preparer_brouillon(s.gmail, d2, base, TEXTES)
    s.gmail.brouillons.pop(did)                                              # Pierre-Edern supprime le 1er brouillon : le fil disparaît
    s.gmail.drafts().envoyer_simule(did2, date_ms=int(datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp() * 1000))
    CA.suivre(s.gmail, v, base, date(2026, 11, 13), relance_jours=7, textes=TEXTES)
    st = {x["Clé"]: x["Statut"] for x in v.statuts_lire()}
    assert st[d["cle"]] == "Brouillon supprimé" and st[d2["cle"]] == "Envoyée"
    assert base.ligne(d["cle"])["etat"] == "supprime"


def test_accuse_automatique_pas_une_reponse(tmp_path):
    s, base, d, v = _prep(tmp_path)
    did, _ = CA.preparer_brouillon(s.gmail, d, base, TEXTES)
    fil = s.gmail.brouillons[did]["threadId"]
    s.gmail.drafts().envoyer_simule(did, date_ms=int(datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp() * 1000))
    s.gmail.ajouter_message(b"From: noreply@demo.fr\r\nAuto-Submitted: auto-replied\r\nSubject: Accuse de reception\r\n\r\nBien recu.", fil=fil)
    CA.suivre(s.gmail, v, base, date(2026, 11, 14), relance_jours=7, textes=TEXTES)
    assert v.statuts_lire()[0]["Statut"] == "Envoyée"
