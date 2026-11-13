# -*- coding: utf-8 -*-
"""Sites carrières (offres cachées) : ~154 entreprises interrogées directement (Workday, SmartRecruiters, Greenhouse, Lever, Jibe,
Avature, SuccessFactors, pages HTML) ou au navigateur (Playwright) pour les sites sans système reconnu. Connecteurs repris du scan
V.I.E v6, élargis : une offre est gardée si elle est V.I.E OU si son métier est dans la cible (achats / supply), et son contrat n'est
marqué V.I.E que sur preuve (titre, facette Workday V.I.E ou annonce explicite).
Mode complet (veille du matin, navigateur compris) ou léger (midi / soir : connecteurs directs seulement)."""
import asyncio
import html as htmlmod
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urljoin, urlparse  # noqa: F401

from bs4 import BeautifulSoup

from veille.modele import depuis_rc

NOM = "Sites carrières"
MAX_PARALLEL = 10
LIMITE_S = {"complet": 1300, "leger": 600}            # au-delà, on garde ce qui est fini
SITE_BUDGET = 120
UA_NAV = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KEYWORDS = ["VIE", "V.I.E", "Volontariat International"]
SC_KEYWORDS = []                                   # recherches V.I.E + mots métier (recherches.yaml), posés par _preparer
rc = C = S = None                                  # moteur privé, posés par _preparer


def clean(s):
    return rc.clean(s)


def strip_html(s):
    return BeautifulSoup(s or "", "html.parser").get_text(" ") if s and "<" in str(s) else str(s or "")


def CIBLE(t):
    return C.metier(t or "")[0] != "hors"


def _preparer(ctx):
    global rc, C, S, SC_KEYWORDS
    rc, C = ctx.moteur.rc, ctx.moteur.C
    S = rc.S
    SC_KEYWORDS = list(dict.fromkeys(ctx.rech.get("vie", []) + ctx.rech.get("sites_carrieres_mots", [])))


VIE_RE = re.compile(r"(?<![A-Za-z])V\.?\s?I\.?\s?E(?![A-Za-z])|(?i:volontariat international)|(?i:international volunteer)")


STRONG_VIE = re.compile(
    r"(?i:volontariat international|international volunteer)"
    r"|(?i:contrat|contract|poste|position|mission|programme|program|type de contrat|statut|status)\W{0,3}(?:(?i:en|de|as|of|under)\W{1,3})?V\.?I\.?E(?![A-Za-z])"
    r"|(?<![A-Za-z])V\.?I\.?E\.?\W{0,3}(?i:contract|contrat|position|mission|program|programme|offer|opportunity|assignment|de \d|d'une durée|\d+ ?mois|\d+ ?months|for \d)")


METIER = re.compile(
    r"achat|acheteu|purchas|procure|sourcing|buyer|supply|logisti|logístic|logistik|planif|planning|planner|planificat|approvision|supplier|fournisseur|"
    r"vendor|category manag|commodity|demand|s&op|s&oe|ibp|transport|freight|shipping|expédition|expedition|inventory|stock|customs|douane|import|export|"
    r"trade compliance|incoterm|flux|flow|order management|order to|commande|adv|delivery|livraison|distribution|operations|opérations|lean|"
    r"continuous improvement|amélioration continue|industrial performance|performance industrielle|cost control|contract manag|value chain|scm|mrp|"
    r"sap mm|material|matières|packaging|emballage|production plan|ordonnanc", re.I)


INTERN = re.compile(r"stage|stagiaire|intern(?!ational)|trainee|apprenti|apprentice|alternan|ausbildung|est[aá]gio|practicante|pr[aá]cticas|becari|"
                    r"sta[żz]|praktik|tirocin|werkstudent|working student|thesis|th[eè]se|summer job", re.I)


SENIOR = re.compile(r"\bsenior\b|\bsr\.?\b|director|directeur|directrice|head of|\bvp\b|vice president|chief", re.I)


def keep_title(t):
    return bool(METIER.search(t or "")) and not SENIOR.search(t or "") and (VIE_RE.search(t or "") or not INTERN.search(t or ""))


def new_ids(seen, ids):
    ids = [i for i in ids if i]; before = len(seen); seen.update(ids); return len(seen) > before





def offer(ent, titre, lien, lieu="", publie=None, source="", desc="", vie_ok=False):
    """vie_ok vaut "facette" quand Workday range l'offre sous une facette V.I.E : c'est une preuve ; True seul n'en est pas une."""
    if isinstance(lieu, dict):
        lieu = ", ".join(str(x) for x in lieu.values() if isinstance(x, (str, int)))
    if isinstance(lieu, list):
        lieu = ", ".join(clean(x if isinstance(x, str) else x.get("name", "") if isinstance(x, dict) else "") for x in lieu)
    titre = clean(titre)
    texte = rc.clean_html(desc) if desc else ""
    preuve = bool(VIE_RE.search(titre) or (texte and STRONG_VIE.search(texte)) or vie_ok == "facette")
    return rc.offer(source="Site carrières", requete=source, title=titre, company=ent, location=clean(lieu)[:120], url=lien,
                    posted=rc.to_dt(publie), desc=texte, contract="V.I.E" if preuve else "", extra="vie_ok" if vie_ok else "")



def parse_workday(url):
    m = re.search(r"https?://([a-z0-9\-]+)\.(wd\d+)\.myworkdayjobs\.com/([^?#\s\"'<>]*)", url, re.I)
    if not m:
        return None
    tenant, dc = m.group(1), m.group(2)
    segs = [s for s in m.group(3).split("/") if s]
    if segs[:2] == ["wday", "cxs"] and len(segs) >= 4:
        return tenant, dc, segs[3]
    if segs and re.fullmatch(r"[a-z]{2}(-[A-Za-z]{2})?", segs[0]):
        segs = segs[1:]
    return (tenant, dc, segs[0]) if segs and segs[0] not in ("wday", "job") else None


FACET_RE = re.compile(r"(?<![A-Za-z])V\.?I\.?E(?![A-Za-z])|volontariat|international volunteer", re.I)


def wd_facets(facets, param=None, hits=None):
    hits = {} if hits is None else hits
    for f in facets or []:
        p = f.get("facetParameter", param)
        for v in f.get("values", []) or []:
            if v.get("values"):
                wd_facets([v], p, hits)
            elif FACET_RE.search(v.get("descriptor", "") or "") and v.get("id"):
                hits.setdefault(p, []).append(v["id"])
    return hits


def c_workday(name, url):
    tenant, dc, site = parse_workday(url)
    base = f"https://{tenant}.{dc}.myworkdayjobs.com"; api = f"{base}/wday/cxs/{tenant}/{site}"
    H = {"Content-Type": "application/json", "Accept": "application/json"}
    cands, via_facet = {}, set()

    def search(text, facets=None, cap=2000):
        off, total, first = 0, None, None
        while off < cap:
            r = S.post(api + "/jobs", json={"appliedFacets": facets or {}, "limit": 20, "offset": off, "searchText": text}, headers=H, timeout=40)
            r.raise_for_status(); d = r.json()
            first = first or d; total = total or d.get("total", 0)
            jp = d.get("jobPostings", [])
            for j in jp:
                if j.get("externalPath"):
                    cands.setdefault(j["externalPath"], j)
                    if facets:
                        via_facet.add(j["externalPath"])
            off += 20
            if not jp or off >= (total or 0):
                break
        return first or {}
    first = search("", cap=20)
    for p, ids in wd_facets(first.get("facets")).items():
        search("", {p: ids}, cap=3000)
    for kw in KEYWORDS:
        search(kw, cap=1000)
    for kw in SC_KEYWORDS:
        search(kw, cap=200)

    def detail(item):
        path, j = item; t = j.get("title", "")
        if not keep_title(t):
            return None
        info = {}
        try:
            info = S.get(api + path, headers=H, timeout=30).json().get("jobPostingInfo", {})
        except Exception:
            pass
        desc = strip_html(info.get("jobDescription", ""))
        if not (VIE_RE.search(t) or path in via_facet or STRONG_VIE.search(desc) or CIBLE(t)):
            return None
        return offer(name, t, info.get("externalUrl") or f"{base}/{site}{path}", j.get("locationsText") or info.get("location", ""),
                     info.get("startDate") or j.get("postedOn", ""), "workday", desc, "facette" if path in via_facet else True)
    with ThreadPoolExecutor(8) as ex:
        return [o for o in ex.map(detail, cands.items()) if o], len(cands)


def c_smartrecruiters(name, url):
    cid = re.search(r"smartrecruiters\.com/(?:v1/companies/)?([^/?#\s\"']+)", url).group(1)
    cands = {}
    for kw in KEYWORDS + SC_KEYWORDS:
        off = 0
        while off < 2000:
            d = S.get(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings", params={"q": kw, "limit": 100, "offset": off}, timeout=30).json()
            c = d.get("content", [])
            for j in c:
                cands[j["id"]] = j
            off += 100
            if not c or off >= d.get("totalFound", 0):
                break

    def detail(j):
        t = j.get("name", "")
        if not keep_title(t):
            return None
        desc = ""
        try:
            sec = S.get(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings/{j['id']}", timeout=30).json().get("jobAd", {}).get("sections", {})
            desc = " ".join(strip_html(v.get("text", "")) for v in sec.values() if isinstance(v, dict))
        except Exception:
            pass
        if not (VIE_RE.search(t) or VIE_RE.search(str((j.get("typeOfEmployment") or {}).get("label", ""))) or STRONG_VIE.search(desc) or CIBLE(t)):
            return None
        loc = j.get("location") or {}
        return offer(name, t, f"https://jobs.smartrecruiters.com/{cid}/{j['id']}", f"{loc.get('city', '')}, {str(loc.get('country', '')).upper()}",
                     j.get("releasedDate", ""), "smartrecruiters", desc, True)
    with ThreadPoolExecutor(8) as ex:
        return [o for o in ex.map(detail, cands.values()) if o], len(cands)


def c_greenhouse(name, url):
    tok = re.search(r"greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?([A-Za-z0-9_\-]+)", url).group(1)
    js = S.get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs?content=true", timeout=30).json().get("jobs", [])
    out = []
    for j in js:
        d = strip_html(htmlmod.unescape(j.get("content", "")))
        if keep_title(j.get("title", "")) and (VIE_RE.search(j.get("title", "")) or STRONG_VIE.search(d) or CIBLE(j.get("title", ""))):
            out.append(offer(name, j["title"], j.get("absolute_url", ""), (j.get("location") or {}).get("name", ""),
                             j.get("first_published") or j.get("updated_at", ""), "greenhouse", d, True))
    return out, len(js)


def c_lever(name, url):
    co = re.search(r"lever\.co/(?:v0/postings/)?([A-Za-z0-9_\-]+)", url).group(1)
    js = S.get(f"https://api.lever.co/v0/postings/{co}?mode=json", timeout=30).json()
    return [offer(name, j["text"], j.get("hostedUrl", ""), (j.get("categories") or {}).get("location", ""), j.get("createdAt", ""), "lever",
                  j.get("descriptionPlain", ""), True)
            for j in js if keep_title(j.get("text", "")) and (VIE_RE.search(j.get("text", "")) or STRONG_VIE.search(j.get("descriptionPlain", "") or "") or CIBLE(j.get("text", "")))], len(js)


def c_jibe(name, url):
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url.replace("jibe:", "")))
    out, seen = {}, set()
    for kw in KEYWORDS + SC_KEYWORDS:
        for page in range(1, 40):
            d = S.get(f"{origin}/api/jobs", params={"keywords": kw, "page": page, "limit": 100}, timeout=30).json()
            jobs = [x.get("data", x) for x in d.get("jobs", [])]
            if not new_ids(seen, [j.get("slug") or j.get("req_id") for j in jobs]):
                break
            for j in jobs:
                t, ds = j.get("title", ""), strip_html(j.get("description", ""))
                if keep_title(t) and (VIE_RE.search(t) or STRONG_VIE.search(ds) or CIBLE(t)):
                    link = (j.get("meta_data") or {}).get("canonical_url") or f"{origin}/jobs/{j.get('slug')}"
                    out[link] = offer(name, t, link, j.get("full_location") or j.get("city", ""), j.get("posted_date") or j.get("create_date", ""), "jibe", ds, True)
    return list(out.values()), len(seen)


def c_avature(name, url):
    base = re.sub(r"/SearchJobs.*$", "/SearchJobs", url.split("?")[0].rstrip("/"))
    out, seen_all = {}, set()
    for kw in KEYWORDS + SC_KEYWORDS:
        off, seen = 0, set()
        while off < 5000:
            r = S.get(f"{base}/{quote(kw)}", params={"jobRecordsPerPage": 50, "jobOffset": off}, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")
            links = {urljoin(r.url, a["href"]).split("?")[0]: clean(a.get_text(" ")) for a in soup.select("a[href*='JobDetail']")}
            if not new_ids(seen, links.keys()):
                break
            seen_all |= set(links)
            for h, t in links.items():
                if t and (VIE_RE.search(t) or CIBLE(t)) and keep_title(t):
                    out[h] = offer(name, t, h, "", None, "avature", "", True)
            off += max(len(links), 1)
    return list(out.values()), len(seen_all)


def c_rmk(name, url):
    p = urlparse(url); origin = f"{p.scheme}://{p.netloc}"
    out, seen_all = {}, set()

    def parse(r):
        soup = BeautifulSoup(r.text, "html.parser"); res = []
        rows = soup.select("tr.data-row") or soup.select("li.job-tile, div.job-tile")
        for row in rows:
            a = row.select_one("a.jobTitle-link") or row.select_one("a[href*='/job/']")
            if not a:
                continue
            d = row.select_one(".jobDate"); l = row.select_one(".jobLocation")
            res.append((clean(a.get_text(" ")), urljoin(r.url, a["href"]), clean(d.get_text(" ")) if d else "", clean(l.get_text(" ")) if l else ""))
        if not rows:
            res = [(clean(a.get_text(" ")), urljoin(r.url, a["href"]), "", "") for a in soup.select("a.jobTitle-link, a[href*='/job/']")]
        return res
    pages = []
    if "/go/" in p.path:
        basego = origin + p.path.rstrip("/")
        pages.append(lambda n: f"{basego}/{n}/" if n else basego + "/")
    for kw in KEYWORDS + SC_KEYWORDS:
        pages.append(lambda n, kw=kw: f"{origin}/search/?q={quote(kw)}&startrow={n}")
    for mk in pages:
        n, seen = 0, set()
        while n < 3000:
            r = S.get(mk(n), timeout=30, headers={"Accept-Language": "en-US,en;q=0.9"})
            if r.status_code >= 400:
                break
            res = parse(r)
            if not new_ids(seen, [h for _, h, _, _ in res]):
                break
            seen_all |= {h for _, h, _, _ in res}
            for t, h, d, l in res:
                if t and (VIE_RE.search(t) or CIBLE(t)) and keep_title(t):
                    out[h] = offer(name, t, h, l, d, "successfactors", "", True)
            n += max(len(res), 1)
    return list(out.values()), len(seen_all)


def c_htmlpages(name, tpl):
    out, seen = {}, set()
    for page in range(0, 300):
        r = S.get(tpl.format(kw=quote("VIE"), page=page), timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        links = {urljoin(r.url, a["href"]).split("#")[0]: clean(a.get_text(" ")) for a in soup.find_all("a", href=True)}
        if not new_ids(seen, links.keys()):
            break
        for h, t in links.items():
            if t and (VIE_RE.search(t) or CIBLE(t)) and keep_title(t):
                out[h] = offer(name, t, h, "", None, "html", "", True)
    if not seen:
        raise RuntimeError("page vide")
    return list(out.values()), len(seen)


def route(url):
    if url.startswith("jibe:"):
        return "jibe"
    if "myworkdayjobs.com" in url:
        return "workday"
    if "smartrecruiters.com" in url:
        return "smartrecruiters"
    if "greenhouse.io" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "SearchJobs" in url:
        return "avature"
    if "/search/?q=" in url or "/go/" in url:
        return "rmk"
    if "{page}" in url:
        return "htmlpages"
    return "browser"


CONNECTORS = {"workday": c_workday, "smartrecruiters": c_smartrecruiters, "greenhouse": c_greenhouse, "lever": c_lever,
              "jibe": c_jibe, "avature": c_avature, "rmk": c_rmk, "htmlpages": c_htmlpages}


TK = ("title", "jobTitle", "job_title", "postingTitle", "externalName", "jobName", "titre", "Title", "name")
LK = ("url", "applyUrl", "apply_url", "jobUrl", "absolute_url", "hostedUrl", "canonical_url", "externalPath", "link", "detailUrl", "jobDetailUrl",
      "jobPostingUrl", "href", "shareUrl")
DK = ("postedDate", "datePosted", "posted_date", "publicationDate", "publishedDate", "datePublished", "createdAt", "created_at", "createDate",
      "create_date", "releasedDate", "postedOn", "creationDate", "startDate", "dateCreated", "updated_at")
LOCK = ("locationsText", "full_location", "location", "cityState", "city", "locationName", "primaryLocation", "jobLocation", "country")


def walk_json(o, base, out, depth=0):
    if depth > 14:
        return
    if isinstance(o, dict):
        t = next((o[k] for k in TK if isinstance(o.get(k), str) and o[k].strip()), None)
        if t and len(t) < 200 and VIE_RE.search(t):
            link = next((o[k] for k in LK if isinstance(o.get(k), str) and o[k]), "")
            out.append((t, urljoin(base, link) if link else "", next((o[k] for k in DK if o.get(k)), ""), next((o[k] for k in LOCK if o.get(k)), "")))
        for v in o.values():
            walk_json(v, base, out, depth + 1)
    elif isinstance(o, list):
        for v in o:
            walk_json(v, base, out, depth + 1)
    elif isinstance(o, str) and len(o) > 200 and "href" in o and VIE_RE.search(o):
        for a in BeautifulSoup(o, "html.parser").find_all("a", href=True):
            tt = clean(a.get_text(" "))
            if VIE_RE.search(tt):
                out.append((tt, urljoin(base, a["href"]), "", ""))


COOKIES = ["#onetrust-reject-all-handler", "#didomi-notice-disagree-button", "#axeptio_btn_dismiss", "#CybotCookiebotDialogBodyButtonDecline",
           'button:has-text("Tout refuser")', 'button:has-text("Refuser")', 'button:has-text("Continuer sans accepter")', 'button:has-text("Reject all")',
           'button:has-text("Decline")', "#onetrust-accept-btn-handler", "#didomi-notice-agree-button", 'button:has-text("Accepter")', 'button:has-text("Accept")', 'button:has-text("OK")']
SEARCH = ["input[type=search]", "input[name*=keyword i]", "input[name*=search i]", "input[name*=query i]", "input[name=q]", "input[id*=keyword i]",
          "input[id*=search i]", "input[placeholder*=search i]", "input[placeholder*=recherch i]", "input[placeholder*=mot i]", "input[placeholder*=keyword i]",
          "input[placeholder*=job i]", "input[placeholder*=poste i]", "input[placeholder*=métier i]", "input[aria-label*=search i]", "input[aria-label*=recherch i]"]
MORE = ["Load more", "Show more", "More jobs", "View more", "See more", "More results", "Voir plus", "Afficher plus", "Charger plus", "Plus d'offres",
        "Voir plus d'offres", "Afficher plus d'offres", "Plus de résultats"]
NEXT = ["a[rel=next]", "a[aria-label*=next i]", "button[aria-label*=next i]", "a[aria-label*=suivant i]", "button[aria-label*=suivant i]",
        'a:has-text("Suivant")', 'button:has-text("Suivant")', 'a:has-text("Next")', 'button:has-text("Next")', "a.next", "li.next a", "a.pagination-next"]
JOBS_LINK = re.compile(r"offres? d.emploi|nos offres|toutes les offres|voir les offres|rechercher une offre|job offers|search jobs|find (a|your) job|"
                       r"view (all )?jobs|see (all )?jobs|open positions|job search|current openings|nos postes|postuler|jobs$|emplois$|opportunit", re.I)
ATS_PATTERNS = [("workday", r"https?://[a-z0-9\-]+\.wd\d+\.myworkdayjobs\.com/[^\s\"'<>\\]+"),
                ("smartrecruiters", r"(?:careers|jobs)\.smartrecruiters\.com/[A-Za-z0-9_\-]+"),
                ("greenhouse", r"boards(?:-api)?\.greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?[A-Za-z0-9_\-]+"),
                ("lever", r"jobs\.lever\.co/[A-Za-z0-9_\-]+")]
UA = UA_NAV


async def click_first(page, sels, timeout=1000):
    for s in sels:
        try:
            el = page.locator(s).first
            if await el.is_visible(timeout=timeout):
                await el.click(timeout=timeout); return True
        except Exception:
            pass
    return False


async def try_search(page):
    for s in SEARCH:
        try:
            el = page.locator(s).first
            if await el.is_visible(timeout=600):
                await el.fill("VIE"); await el.press("Enter"); await page.wait_for_timeout(5000); return True
        except Exception:
            pass
    return False


async def harvest_dom(page, found):
    try:
        for t, h in await page.eval_on_selector_all("a[href]", "els => els.map(e => [e.innerText || e.textContent || '', e.href])"):
            t = clean(t)
            if t and len(t) < 200 and VIE_RE.search(t):
                found.append((t, h, "", ""))
    except Exception:
        pass


async def c_browser(name, url, browser):
    """Renvoie (offres, méthode, note, adresse directe détectée)."""
    t0 = time.time()
    left = lambda: SITE_BUDGET - (time.time() - t0)
    ctx = await browser.new_context(user_agent=UA, locale="fr-FR", viewport={"width": 1366, "height": 900}, ignore_https_errors=True)
    page = await ctx.new_page()
    found, net, tasks, notes = [], [], [], []
    final_url = url

    async def on_resp(resp):
        try:
            if "json" in (resp.headers.get("content-type") or ""):
                walk_json(await resp.json(), resp.url, found)
        except Exception:
            pass
    page.on("request", lambda r: net.append(r.url))
    page.on("response", lambda r: tasks.append(asyncio.ensure_future(on_resp(r))))
    try:
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3500)
        await click_first(page, COOKIES); await page.wait_for_timeout(800)
        searched = "VIE" in url or await try_search(page)
        if searched and "VIE" not in url:
            notes.append("recherche")
        if not searched:
            try:
                links = await page.eval_on_selector_all("a[href]", "els => els.map(e => [e.innerText || e.getAttribute('aria-label') || '', e.href])")
                cand = [h for t, h in links if t and JOBS_LINK.search(clean(t)) and h.startswith("http")]
                if cand:
                    await page.goto(cand[0], timeout=45000, wait_until="domcontentloaded"); await page.wait_for_timeout(3500)
                    await click_first(page, COOKIES); notes.append("page offres")
                    if await try_search(page):
                        notes.append("recherche")
            except Exception:
                pass
        for pg_i in range(25):
            if left() < 10:
                notes.append("temps max"); break
            for _ in range(15):
                if left() < 10:
                    break
                h = await page.evaluate("document.body.scrollHeight")
                await page.mouse.wheel(0, 20000); await page.wait_for_timeout(1000)
                clicked = await click_first(page, [f'button:has-text("{m}")' for m in MORE] + [f'a:has-text("{m}")' for m in MORE], 500)
                if clicked:
                    await page.wait_for_timeout(2500)
                elif h == await page.evaluate("document.body.scrollHeight"):
                    break
            await harvest_dom(page, found)
            before = page.url
            if not await click_first(page, NEXT, 500):
                break
            await page.wait_for_timeout(3000)
            if pg_i and page.url == before and not found:
                break
        await harvest_dom(page, found)
        net.append(await page.content())
        final_url = page.url
    except Exception as e:
        notes.append(f"navigation: {e.__class__.__name__} {str(e).splitlines()[0][:60] if str(e) else ''}")
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
        await ctx.close()
    own = [offer(name, t, l or url, loc, d, "navigateur") for t, l, d, loc in found]
    blob = "\n".join(x for x in net if isinstance(x, str))
    for kind, rx in ATS_PATTERNS:
        for m in re.finditer(rx, blob):
            u = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
            if kind == "workday" and not parse_workday(u):
                continue
            try:
                extra, n = await asyncio.to_thread(CONNECTORS[kind], name, u)
                return extra + own, f"navigateur -> {kind}", "; ".join(notes), u
            except Exception:
                break
    if "jobTitle-link" in blob or re.search(r"/search/\?q=[^\"']*&?startrow", blob):
        for u in (final_url, url):
            try:
                extra, n = await asyncio.to_thread(c_rmk, name, u)
            except Exception:
                extra = []
            if extra:
                o = urlparse(u)
                return extra + own, "navigateur -> successfactors", "; ".join(notes), f"{o.scheme}://{o.netloc}/search/?q="
    m = re.search(r"https?://[^\s\"'<>]+/(?:[a-z]{2}_[A-Z]{2}/)?(?:careers|jobs)/SearchJobs", blob)
    if m:
        try:
            extra, n = await asyncio.to_thread(c_avature, name, m.group(0))
            return extra + own, "navigateur -> avature", "; ".join(notes), m.group(0)
        except Exception:
            pass
    host = urlparse(url).netloc
    if re.search(re.escape(host) + r"/api/jobs\?", blob):
        try:
            extra, n = await asyncio.to_thread(c_jibe, name, url)
            return extra + own, "navigateur -> jibe", "; ".join(notes), "jibe:" + f"https://{host}"
        except Exception:
            pass
    return [o for o in own if keep_title(o["title"])], "navigateur", "; ".join(notes), ""


async def run_all(companies, navigateur=True, res=None):
    from contextlib import AsyncExitStack
    sem = asyncio.Semaphore(MAX_PARALLEL); res = [] if res is None else res
    async with AsyncExitStack() as pile:
        browser = None
        if navigateur:
            try:
                from playwright.async_api import async_playwright
                p = await pile.enter_async_context(async_playwright())
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-http2",
                                                                       "--disable-blink-features=AutomationControlled"])
            except Exception:
                browser = None                      # navigateur indisponible : les pages concernées sont notées en erreur

        async def one(name, url):
            async with sem:
                t0 = time.time(); kind = route(url); err = note = det = ""; offers = []; meth = kind
                try:
                    if kind == "browser":
                        if browser is None:
                            raise RuntimeError("navigateur indisponible")
                        offers, meth, note, det = await asyncio.wait_for(c_browser(name, url, browser), SITE_BUDGET + 120)
                    else:
                        try:
                            offers, _ = await asyncio.to_thread(CONNECTORS[kind], name, url)
                        except Exception:
                            if kind != "htmlpages" or browser is None:
                                raise
                            offers, meth, note, det = await asyncio.wait_for(c_browser(name, url.format(kw="VIE", page=0), browser), SITE_BUDGET + 120)
                            meth = "html -> " + meth
                    offers = [o for o in offers if keep_title(o["title"])]
                except Exception as e:
                    err = f"{e.__class__.__name__}: {str(e)[:120]}"
                if note.startswith("navigation") or "; navigation" in note:
                    err = err or note
                res.append((name, url, meth, offers, err, note, det, round(time.time() - t0)))
        await asyncio.gather(*(one(n, u) for n, u in companies))
        if browser:
            await browser.close()
    return res


def collecter(ctx) -> list:
    _preparer(ctx)
    complet = ctx.moment in (ctx.cfg.get("sites_carrieres") or {}).get("complet", ["matin"])
    ents = ctx.entreprises or ctx.rech.get("entreprises", [])
    companies = [(e["nom"], e["url"]) for e in ents if e.get("nom") and e.get("url")]
    if not complet:
        companies = [(n, u) for n, u in companies if route(u) != "browser"]
    res = []
    fil = threading.Thread(target=lambda: asyncio.run(run_all(companies, navigateur=complet, res=res)), daemon=True)
    fil.start()
    fil.join((ctx.cfg.get("sites_carrieres") or {}).get("limite_s") or LIMITE_S["complet" if complet else "leger"])
    fini = list(res)                                 # résultats partiels si la limite est atteinte
    out, etat, detectees = [], [], {}
    for name, url, meth, offers, err, note, det, duree in fini:
        out += [depuis_rc(o) for o in offers]
        etat.append({"entreprise": name, "methode": meth, "offres": len(offers), "erreur": err, "duree_s": duree})
        if det and det != url:
            detectees[name] = det
    faits = {e["entreprise"] for e in etat}
    etat += [{"entreprise": n, "methode": route(u), "offres": 0, "erreur": "limite de temps atteinte", "duree_s": None} for n, u in companies if n not in faits]
    ctx.budget["sites_carrieres"] = etat
    ctx.budget["entreprises_detectees"] = detectees
    return out
