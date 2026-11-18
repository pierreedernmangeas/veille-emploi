# -*- coding: utf-8 -*-
"""Mail récapitulatif d'une veille, envoyé uniquement au compte lui-même (jamais à un recruteur)."""
import base64
import html
from email.message import EmailMessage


def _ligne(o):
    return (f"<tr><td><b>{o.get('note', '')}</b></td><td>{html.escape(str(o.get('categorie') or ''))}</td>"
            f"<td><a href=\"{html.escape(o.get('url') or '')}\">{html.escape(str(o.get('title') or ''))}</a></td>"
            f"<td>{html.escape(str(o.get('company') or ''))}</td><td>{html.escape(str(o.get('ats') or ''))}</td>"
            f"<td>{html.escape(str(o.get('atout') or ''))}</td></tr>")


def contenu(resume: dict) -> tuple:
    r = resume
    sujet = f"Veille emploi ({r.get('moment', '')}) : {r.get('gardees', r.get('nouvelles', 0))} offres pour toi, {r.get('documents', 0)} CV + lettres prêts"
    top = "".join(_ligne(o) for o in (r.get("top") or [])[:10])
    urg = "".join(_ligne(o) for o in (r.get("top") or []) if o.get("urgent"))
    err = "".join(f"<li>{html.escape(e)}</li>" for e in r.get("erreurs") or [])
    corps = (f"<p><b>{r.get('nouvelles', 0)}</b> nouvelles offres trouvées, <b>{r.get('gardees', 0)}</b> gardées, <b>{r.get('documents', 0)}</b> CV + lettres prêts, "
             f"<b>{r.get('brouillons', 0)}</b> brouillons de candidature et <b>{r.get('relances', 0)}</b> relances prêts dans Gmail.</p>"
             + (f"<p><a href=\"{html.escape(r['lien_sheet'])}\">Ouvrir le Sheet « Veille emploi »</a></p>" if r.get("lien_sheet") else "")
             + (f"<h3>À envoyer aujourd'hui (publiées depuis moins de 48 h, peu de candidats)</h3><table cellpadding=\"4\">{urg}</table>" if urg else "")
             + (f"<h3>Les 10 meilleures</h3><table cellpadding=\"4\"><tr><th>Note</th><th>Catégorie</th><th>Poste</th><th>Entreprise</th><th>Adéquation CV</th><th>Ton atout pour ce poste</th></tr>{top}</table>" if top else "")
             + (f"<h3>Sources en erreur</h3><ul>{err}</ul>" if err else ""))
    return sujet, corps


def envoyer(gmail, email: str, resume: dict) -> None:
    sujet, corps = contenu(resume)
    m = EmailMessage()
    m["To"] = email
    m["From"] = email
    m["Subject"] = sujet
    m.set_content("Ouvre ce mail en HTML pour voir le récapitulatif.")
    m.add_alternative(corps, subtype="html")
    gmail.users().messages().send(userId="me", body={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}).execute()
