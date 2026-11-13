# -*- coding: utf-8 -*-
"""Faux services Google en mémoire (Drive, Gmail, gspread) pour les tests : aucun appel réseau."""
import base64
import itertools
import re
from email import message_from_bytes

_ids = itertools.count(1)


class _Exec:
    def __init__(self, f):
        self._f = f

    def execute(self, num_retries=0):
        return self._f()


class FauxDrive:
    FOLDER = "application/vnd.google-apps.folder"

    def __init__(self):
        self.fichiers = {}          # id -> dict(name, mimeType, parents, data)

    # API files()
    def files(self):
        return self

    def ajouter(self, nom, parent="root", data=b"", mime="application/octet-stream"):
        fid = f"f{next(_ids)}"
        self.fichiers[fid] = dict(id=fid, name=nom, mimeType=mime, parents=[parent], data=data, trashed=False)
        return fid

    def _filtre(self, q):
        res = list(self.fichiers.values())
        m = re.search(r"name = '((?:[^'\\]|\\.)*)'", q or "")
        if m:
            nom = m.group(1).replace("\\'", "'")
            res = [f for f in res if f["name"] == nom]
        m = re.search(r"'([^']+)' in parents", q or "")
        if m:
            res = [f for f in res if m.group(1) in f["parents"]]
        if "mimeType = 'application/vnd.google-apps.folder'" in (q or ""):
            res = [f for f in res if f["mimeType"] == self.FOLDER]
        return [f for f in res if not f["trashed"]]

    def list(self, q=None, fields=None, pageSize=None, **k):
        return _Exec(lambda: {"files": [dict(id=f["id"], name=f["name"], webViewLink=f"https://drive/{f['id']}") for f in self._filtre(q)]})

    def get(self, fileId=None, fields=None, **k):
        def f():
            if fileId not in self.fichiers and fileId != "root":
                raise KeyError(fileId)
            return {"id": fileId}
        return _Exec(f)

    def get_media(self, fileId=None, **k):
        return _Exec(lambda: self.fichiers[fileId]["data"])

    def create(self, body=None, media_body=None, fields=None, **k):
        def f():
            data = media_body.getbytes(0, media_body.size()) if media_body is not None else b""
            fid = self.ajouter(body["name"], (body.get("parents") or ["root"])[0], data, body.get("mimeType", "application/octet-stream"))
            return dict(id=fid, webViewLink=f"https://drive/{fid}")
        return _Exec(f)

    def update(self, fileId=None, media_body=None, fields=None, **k):
        def f():
            self.fichiers[fileId]["data"] = media_body.getbytes(0, media_body.size())
            return dict(id=fileId, webViewLink=f"https://drive/{fileId}")
        return _Exec(f)

    def about(self):
        return self


class FauxGmail:
    def __init__(self, adresse="moi@exemple.fr"):
        self.adresse = adresse
        self.msgs = {}              # id -> dict(raw bytes, threadId, labelIds, internalDate)
        self.brouillons = {}        # id -> dict(message)
        self.appels = []

    def users(self):
        return self

    def getProfile(self, userId="me"):
        return _Exec(lambda: {"emailAddress": self.adresse})

    # --- messages
    def ajouter_message(self, raw: bytes, fil=None, envoye=False, date_ms=0):
        mid = f"m{next(_ids)}"
        self.msgs[mid] = dict(id=mid, raw=raw, threadId=fil or f"t{mid}", labelIds=["SENT"] if envoye else ["INBOX"], internalDate=str(date_ms))
        return mid

    def messages(self):
        return _MessagesAPI(self)

    def drafts(self):
        return _BrouillonsAPI(self)

    def threads(self):
        return _FilsAPI(self)


def _entetes(raw):
    m = message_from_bytes(raw)
    return [{"name": k, "value": v} for k, v in m.items()]


class _MessagesAPI:
    def __init__(self, g):
        self.g = g

    def list(self, userId="me", q="", maxResults=None, pageToken=None):
        self.g.appels.append(("messages.list", q))
        return _Exec(lambda: {"messages": [{"id": i, "threadId": m["threadId"]} for i, m in self.g.msgs.items()]})

    def get(self, userId="me", id=None, format="full"):
        self.g.appels.append(("messages.get", id))
        m = self.g.msgs[id]
        return _Exec(lambda: dict(id=id, threadId=m["threadId"], labelIds=m["labelIds"], internalDate=m["internalDate"],
                                  raw=base64.urlsafe_b64encode(m["raw"]).decode(), payload={"headers": _entetes(m["raw"])}))

    def send(self, userId="me", body=None):
        self.g.appels.append(("messages.send", body))
        raw = base64.urlsafe_b64decode(body["raw"])
        return _Exec(lambda: {"id": self.g.ajouter_message(raw, body.get("threadId"), envoye=True)})

    def modify(self, *a, **k):
        self.g.appels.append(("messages.modify", k))
        return _Exec(lambda: {})

    def batchModify(self, *a, **k):
        self.g.appels.append(("messages.batchModify", k))
        return _Exec(lambda: {})


class _BrouillonsAPI:
    def __init__(self, g):
        self.g = g

    def create(self, userId="me", body=None):
        self.g.appels.append(("drafts.create", body))
        raw = base64.urlsafe_b64decode(body["message"]["raw"])
        fil = body["message"].get("threadId") or f"t{next(_ids)}"
        did = f"d{next(_ids)}"
        self.g.brouillons[did] = dict(id=did, raw=raw, threadId=fil)
        return _Exec(lambda: {"id": did, "message": {"id": f"m{did}", "threadId": fil}})

    def get(self, userId="me", id=None, format=None):
        def f():
            if id not in self.g.brouillons:
                raise LookupError("404 brouillon introuvable")
            return {"id": id, "message": {"threadId": self.g.brouillons[id]["threadId"]}}
        return _Exec(f)

    def envoyer_simule(self, did, date_ms=0):
        """Ce que fait Pierre-Edern en cliquant « Envoyer »."""
        b = self.g.brouillons.pop(did)
        return self.g.ajouter_message(b["raw"], b["threadId"], envoye=True, date_ms=date_ms)


class _FilsAPI:
    def __init__(self, g):
        self.g = g

    def get(self, userId="me", id=None, format="metadata", metadataHeaders=None):
        msgs = [m for m in self.g.msgs.values() if m["threadId"] == id]
        brouillons = [b for b in self.g.brouillons.values() if b["threadId"] == id]

        def f():
            if not msgs and not brouillons:
                raise LookupError("HttpError 404: Requested entity was not found.")     # comme Gmail : fil disparu
            return {"id": id, "messages": [dict(id=m["id"], labelIds=m["labelIds"], internalDate=m["internalDate"],
                                                payload={"headers": _entetes(m["raw"])}) for m in msgs]}
        return _Exec(f)


class FauxFeuille:
    def __init__(self, titre):
        self.title = titre
        self.lignes = []

    def get_all_values(self):
        return [list(l) for l in self.lignes] or [[]]          # comme gspread : un onglet vide renvoie [[]]

    def insert_row(self, values, index=1, value_input_option=None):
        self.lignes.insert(index - 1, list(values))

    def append_rows(self, rows, value_input_option=None):
        self.lignes += [list(r) for r in rows]

    def append_row(self, row, value_input_option=None):
        self.lignes.append(list(row))

    def update(self, values=None, range_name="A1", value_input_option=None):
        m = re.match(r"A(\d+)", range_name)
        start = int(m.group(1)) - 1 if m else 0
        for k, r in enumerate(values):
            while len(self.lignes) <= start + k:
                self.lignes.append([])
            self.lignes[start + k] = list(r)

    def clear(self):
        self.lignes = []

    def row_values(self, i):
        return self.lignes[i - 1] if len(self.lignes) >= i else []

    def freeze(self, rows=None):
        pass

    def format(self, *a, **k):
        pass

    def resize(self, *a, **k):
        pass

    @property
    def row_count(self):
        return max(1000, len(self.lignes))

    @property
    def col_count(self):
        return 30


class FauxClasseur:
    def __init__(self, sid, titre="classeur"):
        self.id, self.title, self.feuilles = sid, titre, {}
        self.url = f"https://sheets/{sid}"

    def worksheet(self, titre):
        if titre not in self.feuilles:
            import gspread
            raise gspread.exceptions.WorksheetNotFound(titre)
        return self.feuilles[titre]

    def add_worksheet(self, title, rows=100, cols=26):
        self.feuilles[title] = FauxFeuille(title)
        return self.feuilles[title]

    def get_worksheet(self, i):
        return list(self.feuilles.values())[i]

    def worksheets(self):
        return list(self.feuilles.values())


class FauxGc:
    def __init__(self):
        self.classeurs = {}

    def open_by_key(self, sid):
        return self.classeurs.setdefault(sid, FauxClasseur(sid))


def faux_services(adresse="moi@exemple.fr"):
    from veille.google_acces import Services
    return Services(drive=FauxDrive(), gc=FauxGc(), gmail=FauxGmail(adresse), email=adresse)
