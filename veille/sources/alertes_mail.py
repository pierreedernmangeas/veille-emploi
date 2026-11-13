# -*- coding: utf-8 -*-
"""LinkedIn couche 3 (+ Indeed) : lecture des mails d'alerte reçus depuis la dernière veille, dans la boîte Gmail pro.
Lecture seule : aucun mail n'est marqué lu, déplacé ni étiqueté. Les offres LinkedIn sont complétées par leur fiche publique."""
import base64
import re
from email import message_from_bytes, policy

from veille.modele import Offre
from veille.sources import linkedin_commun as LC

NOM = "Alertes mail"
EXPEDITEURS = ["jobalerts-noreply@linkedin.com", "jobs-noreply@linkedin.com", "jobs-listings@linkedin.com",
               "donotreply@jobalert.indeed.com", "alert@indeed.com", "donotreply@match.indeed.com"]
MAX_MAILS = 300
MAX_COMPLETER = 150

LI_LIEN = re.compile(r"^(?:Voir l.offre d.emploi|View job|Voir l.offre)\s*:\s*(https?://\S*linkedin\.com\S*/jobs/view/(\d{6,})\S*)", re.I)
INDEED_LIEN = re.compile(r"^https?://[\w.]*indeed\.\w+/\S*[?&]jk=([0-9a-f]{8,})", re.I)
INDEED_FIN = re.compile(r"^(il y a \d+|aujourd'hui|just posted|\d+ days? ago|à l'instant|publiée)", re.I)


def _lignes(texte):
    return [l.strip() for l in (texte or "").replace("\r", "").split("\n")]


def analyser_linkedin(texte: str) -> list:
    """Bloc LinkedIn : intitulé / entreprise / lieu / « Voir l'offre d'emploi : lien »."""
    l = _lignes(texte)
    out = []
    for i, ligne in enumerate(l):
        m = LI_LIEN.match(ligne)
        if not m:
            continue
        avant = [x for x in l[max(0, i - 4):i] if x and not x.startswith(("http", "---", "Votre alerte", "Your job alert"))]
        if len(avant) < 2:
            continue
        titre, ent, lieu = (avant[-3], avant[-2], avant[-1]) if len(avant) >= 3 else (avant[-2], avant[-1], "")
        out.append(Offre("LinkedIn", titre, ent, lieu=lieu, url=f"https://www.linkedin.com/jobs/view/{m.group(2)}/", sources=["LinkedIn"]))
    return out


def analyser_indeed(texte: str) -> list:
    """Bloc Indeed : intitulé / « Entreprise - Ville » / [salaire] / [Candidature simplifiée] / extrait / « il y a N jours » / lien jk=."""
    l = _lignes(texte)
    out = []
    for i, ligne in enumerate(l):
        m = INDEED_LIEN.match(ligne)
        if not m:
            continue
        j = i - 1
        bloc = []
        while j >= 0 and l[j] and not l[j].startswith("http"):
            bloc.insert(0, l[j])
            j -= 1
        if len(bloc) < 2:
            continue
        titre, ligne_ent = bloc[0], bloc[1]
        ent, _, lieu = ligne_ent.rpartition(" - ")
        if not ent:
            ent, lieu = ligne_ent, ""
        extrait = [x for x in bloc[2:] if not INDEED_FIN.match(x) and not re.match(r"^(de \d|à partir de \d|jusqu.à \d|candidature simplifi|easily apply|€|\d)", x, re.I)]
        out.append(Offre("Indeed", titre, ent.strip(), lieu=lieu.strip(), pays="France" if "fr.indeed" in ligne else "",
                         url=f"https://fr.indeed.com/viewjob?jk={m.group(1)}" if "fr.indeed" in ligne else f"https://www.indeed.com/viewjob?jk={m.group(1)}",
                         description=" ".join(extrait), sources=["Indeed"]))
    return out


def _texte(raw: bytes) -> tuple:
    msg = message_from_bytes(raw, policy=policy.default)
    exp = str(msg.get("From", "")).lower()
    corps = msg.get_body(preferencelist=("plain",))
    if corps is None:
        corps = msg.get_body(preferencelist=("html",))
        texte = re.sub(r"<[^>]+>", "\n", corps.get_content()) if corps else ""
    else:
        texte = corps.get_content()
    return exp, texte


def collecter(ctx) -> list:
    g = ctx.services.gmail
    q = "from:(" + " OR ".join(EXPEDITEURS) + f") after:{int(ctx.depuis.timestamp())}"
    ids, token = [], None
    while len(ids) < MAX_MAILS:
        r = g.users().messages().list(userId="me", q=q, maxResults=100, pageToken=token).execute(num_retries=3)
        ids += [m["id"] for m in r.get("messages", [])]
        token = r.get("nextPageToken")
        if not token:
            break
    out = []
    ctx.budget["alertes_mails_lus"] = len(ids[:MAX_MAILS])
    for mid in ids[:MAX_MAILS]:
        m = g.users().messages().get(userId="me", id=mid, format="raw").execute(num_retries=3)
        exp, texte = _texte(base64.urlsafe_b64decode(m["raw"]))
        if "linkedin" in exp:
            out += analyser_linkedin(texte)
        elif "indeed" in exp:
            out += analyser_indeed(texte)
    vus, uniques = set(), []
    for o in out:
        if o.url not in vus:
            vus.add(o.url)
            uniques.append(o)
    for o in [x for x in uniques if x.source == "LinkedIn"][:MAX_COMPLETER]:
        try:
            LC.completer(o)
        except Exception:
            break                                   # fiche publique indisponible : on garde l'offre sans description
    return uniques
