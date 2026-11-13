# -*- coding: utf-8 -*-
"""Candidatures par mail : brouillon Gmail prêt (jamais envoyé automatiquement), suivi de l'envoi et des réponses,
brouillon de relance à J+7 dans le même fil. Les textes (nom, parcours) viennent du moteur privé (module mails)."""
import base64
import mimetypes
import os
from datetime import date, datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid

LIEN_BROUILLONS = "https://mail.google.com/mail/u/0/#drafts"


def _textes(textes):
    if textes is not None:
        return textes
    import mails                                # moteur privé
    return mails


def _brut(m: EmailMessage) -> str:
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


def preparer_brouillon(gmail, d: dict, base, textes=None):
    """(id du brouillon, lien) si l'annonce donne une adresse ; None sinon, ou si le brouillon existe déjà (idempotent)."""
    if not d.get("mail"):
        return None
    ligne = base.ligne(d["cle"]) or {}
    if ligne.get("brouillon_id"):
        return None
    t = _textes(textes)
    lang = d.get("lang") or "fr"
    m = EmailMessage()
    m["To"] = d["mail"]
    m["Subject"] = d.get("objet") or t.objet(d["poste"], lang)
    m["Message-ID"] = make_msgid(domain="veille.local")
    m.set_content(t.corps(d["poste"], d["ent"], d.get("lien", ""), lang))
    for chemin in (d.get("cv_local"), d.get("lm_local")):
        if chemin and os.path.exists(chemin):
            typ = (mimetypes.guess_type(chemin)[0] or "application/pdf").split("/")
            m.add_attachment(open(chemin, "rb").read(), maintype=typ[0], subtype=typ[1], filename=os.path.basename(chemin))
    b = gmail.users().drafts().create(userId="me", body={"message": {"raw": _brut(m)}}).execute(num_retries=3)
    base.marquer(d["cle"], brouillon_id=b["id"], fil_id=b["message"]["threadId"], etat="brouillon")
    return b["id"], LIEN_BROUILLONS


def _entete(msg, nom):
    return next((h["value"] for h in msg.get("payload", {}).get("headers", []) if h["name"].lower() == nom.lower()), "")


def _brouillon_existe(gmail, did) -> bool:
    if not did:
        return False
    try:
        gmail.users().drafts().get(userId="me", id=did, format="minimal").execute(num_retries=3)
        return True
    except Exception:
        return False


def _jour(ms) -> date:
    return datetime.fromtimestamp(int(ms or 0) / 1000, tz=timezone.utc).date()


def _relance(gmail, fil, envoye, textes, poste, ent, lang):
    t = _textes(textes)
    m = EmailMessage()
    m["To"] = _entete(envoye, "To")
    sujet = _entete(envoye, "Subject")
    m["Subject"] = sujet if sujet.lower().startswith("re:") else "Re: " + sujet
    mid = _entete(envoye, "Message-ID")
    if mid:
        m["In-Reply-To"] = mid
        m["References"] = (_entete(envoye, "References") + " " + mid).strip()
    m.set_content(t.corps_relance(poste, ent, lang))
    return gmail.users().drafts().create(userId="me", body={"message": {"raw": _brut(m), "threadId": fil}}).execute(num_retries=3)["id"]


def _automatique(msg) -> bool:
    """Accusé de réception automatique ou retour d'erreur : ce n'est pas une réponse du recruteur."""
    auto = _entete(msg, "Auto-Submitted").lower()
    de = _entete(msg, "From").lower()
    return bool(auto and auto != "no") or any(x in de for x in ("mailer-daemon", "postmaster@"))   # un « no-reply » d'ATS peut être un vrai refus


def _introuvable(e) -> bool:
    return "404" in str(e) or "not found" in str(e).lower()


def suivre(gmail, veille, base, aujourd_hui: date, relance_jours: int = 7, textes=None) -> dict:
    """Met à jour les statuts « À postuler » à partir de Gmail. Renvoie les compteurs (envoyees, reponses, relances, relancees, erreurs).
    Une erreur sur un fil n'arrête jamais les autres."""
    c = dict(envoyees=0, reponses=0, relances=0, relancees=0, erreurs=0)
    for l in base.lignes(("brouillon", "envoyee", "relance_prete", "relancee")):
        try:
            _suivre_un(gmail, veille, base, l, aujourd_hui, relance_jours, textes, c)
        except Exception:
            c["erreurs"] += 1
    return c


def _suivre_un(gmail, veille, base, l, aujourd_hui, relance_jours, textes, c):
    fil = l.get("fil_id")
    if not fil:
        return
    try:
        msgs = gmail.users().threads().get(userId="me", id=fil, format="metadata",
                                           metadataHeaders=["From", "To", "Subject", "Message-ID", "References", "Auto-Submitted"]
                                           ).execute(num_retries=3).get("messages", [])
    except Exception as e:
        if not _introuvable(e):
            raise
        if l["etat"] == "brouillon":            # brouillon supprimé sans envoi : fil disparu
            base.marquer(l["cle"], etat="supprime")
            veille.statut_maj(l["cle"], Statut="Brouillon supprimé")
        return
    envoyes = sorted([x for x in msgs if "SENT" in x.get("labelIds", [])], key=lambda x: int(x.get("internalDate") or 0))
    recus = [x for x in msgs if "SENT" not in x.get("labelIds", []) and "DRAFT" not in x.get("labelIds", []) and not _automatique(x)]
    etat = l["etat"]
    if etat == "brouillon":
        if _brouillon_existe(gmail, l.get("brouillon_id")) or not envoyes:
            if not envoyes and not _brouillon_existe(gmail, l.get("brouillon_id")):
                base.marquer(l["cle"], etat="supprime")
                veille.statut_maj(l["cle"], Statut="Brouillon supprimé")
            return
        j = _jour(envoyes[0].get("internalDate")).isoformat()
        base.marquer(l["cle"], etat="envoyee", date_envoi=j)
        veille.statut_maj(l["cle"], Statut="Envoyée", **{"Date d'envoi": j})
        c["envoyees"] += 1
        etat = "envoyee"
    if recus:
        base.marquer(l["cle"], etat="reponse")
        veille.statut_maj(l["cle"], Statut="Réponse reçue")
        c["reponses"] += 1
        return
    if etat == "envoyee" and not l.get("relance_id") and envoyes:
        if (aujourd_hui - date.fromisoformat(l.get("date_envoi") or _jour(envoyes[0].get("internalDate")).isoformat())).days >= relance_jours:
            lang = "en" if "application" in _entete(envoyes[0], "Subject").lower() else "fr"
            rid = _relance(gmail, fil, envoyes[0], textes, l.get("titre") or "", l.get("entreprise") or "", lang)
            base.marquer(l["cle"], etat="relance_prete", relance_id=rid)
            veille.statut_maj(l["cle"], Statut="Relance prête", Relance=aujourd_hui.isoformat())
            c["relances"] += 1
    elif etat == "relance_prete" and len(envoyes) >= 2 and not _brouillon_existe(gmail, l.get("relance_id")):
        base.marquer(l["cle"], etat="relancee")
        veille.statut_maj(l["cle"], Statut="Relancée")
        c["relancees"] += 1
