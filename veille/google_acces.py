# -*- coding: utf-8 -*-
"""Accès Google du compte pro par jeton OAuth (secret GOOGLE_TOKEN) : Drive, Sheets, Gmail. Aucune adresse n'est écrite dans les journaux."""
import json
import os
from dataclasses import dataclass

PORTEES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets",
           "https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.readonly"]
DOSSIER = "application/vnd.google-apps.folder"


class CompteInattendu(RuntimeError):
    pass


@dataclass
class Services:
    drive: object
    gc: object
    gmail: object
    email: str


def services(jeton_json: str) -> Services:
    import gspread
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    j = json.loads(jeton_json)
    creds = Credentials(None, refresh_token=j["refresh_token"], client_id=j["client_id"], client_secret=j["client_secret"],
                        token_uri="https://oauth2.googleapis.com/token", scopes=PORTEES)
    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    email = gmail.users().getProfile(userId="me").execute(num_retries=3)["emailAddress"]
    return Services(drive=build("drive", "v3", credentials=creds, cache_discovery=False), gc=gspread.authorize(creds, http_client=gspread.http_client.BackOffHTTPClient), gmail=gmail, email=email)


def verifier_compte(s: Services, attendu: str) -> None:
    if (s.email or "").lower() != (attendu or "").lower():
        raise CompteInattendu("Le jeton Google n'est pas celui du compte attendu : refais outils/obtenir_jeton.py avec le compte pro.")


def _q(t):
    return t.replace("\\", "\\\\").replace("'", "\\'")


def trouver(drive, nom: str, parent: str, dossier_seul: bool = False):
    q = f"name = '{_q(nom)}' and '{parent}' in parents and trashed = false" + (f" and mimeType = '{DOSSIER}'" if dossier_seul else "")
    res = drive.files().list(q=q, fields="files(id,name,webViewLink)", pageSize=5).execute(num_retries=3).get("files", [])
    return res[0] if res else None


def dossier(drive, chemin: list, parent: str = "root") -> str:
    """Identifiant du dossier au bout du chemin, créé s'il manque."""
    for nom in chemin:
        f = trouver(drive, nom, parent, True)
        parent = f["id"] if f else drive.files().create(body={"name": nom, "mimeType": DOSSIER, "parents": [parent]}, fields="id").execute(num_retries=3)["id"]
    return parent


def lien_dossier(drive, dossier_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{dossier_id}"


def telecharger(drive, nom: str, dossier_id: str, dest: str) -> bool:
    f = trouver(drive, nom, dossier_id)
    if not f:
        return False
    data = drive.files().get_media(fileId=f["id"]).execute(num_retries=3)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "wb") as h:
        h.write(data)
    return True


def televerser(drive, chemin: str, dossier_id: str, mime: str = "application/octet-stream", remplacer: bool = True) -> str:
    from googleapiclient.http import MediaInMemoryUpload
    nom = os.path.basename(chemin)
    media = MediaInMemoryUpload(open(chemin, "rb").read(), mimetype=mime, resumable=False)
    f = trouver(drive, nom, dossier_id) if remplacer else None
    if f:
        return drive.files().update(fileId=f["id"], media_body=media, fields="id,webViewLink").execute(num_retries=3)["webViewLink"]
    return drive.files().create(body={"name": nom, "parents": [dossier_id]}, media_body=media, fields="id,webViewLink").execute(num_retries=3)["webViewLink"]
