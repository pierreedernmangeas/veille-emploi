# -*- coding: utf-8 -*-
"""Une seule fois, sur ton Mac : obtient le jeton Google de ton compte PRO pour la veille emploi.

1. pip3 install google-auth-oauthlib
2. python3 obtenir_jeton.py chemin/vers/client_secret.json
3. Une page Google s'ouvre : choisis ton adresse Gmail pro, accepte (« Paramètres avancés » puis « Accéder à… » si Google
   affiche « application non validée » : c'est ta propre application).
4. Copie TOUT le texte affiché entre les deux lignes de tirets dans le secret GitHub GOOGLE_TOKEN. Ne l'envoie à personne."""
import json, sys
from google_auth_oauthlib.flow import InstalledAppFlow

PORTEES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets",
           "https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.readonly"]

if len(sys.argv) < 2:
    sys.exit("Usage : python3 obtenir_jeton.py client_secret.json")
flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], PORTEES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
info = json.load(open(sys.argv[1]))
client = info.get("installed") or info.get("web") or {}
print("-" * 60)
print(json.dumps({"client_id": client["client_id"], "client_secret": client["client_secret"], "refresh_token": creds.refresh_token}))
print("-" * 60)
print("Copie la ligne ci-dessus dans le secret GitHub GOOGLE_TOKEN.")
