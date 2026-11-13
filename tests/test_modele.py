from veille.modele import Offre, cle, cle_url, fusionner, vers_rc, depuis_rc


def test_cle_identique_entre_sources():
    a = Offre("LinkedIn", "Acheteur Junior H/F", "Telespazio France SAS")
    b = Offre("Indeed", "Acheteur junior (F/H) - CDD", "TELESPAZIO")
    assert cle(a) == cle(b)


def test_cle_differe_entre_postes():
    assert cle(Offre("LinkedIn", "Acheteur junior", "X")) != cle(Offre("LinkedIn", "Approvisionneur", "X"))


def test_cle_url_linkedin():
    assert cle_url("https://www.linkedin.com/jobs/view/acheteur-junior-at-x-4123456789?refId=abc&trk=x") == "linkedin:4123456789"
    assert cle_url("https://fr.linkedin.com/jobs/view/4123456789/") == "linkedin:4123456789"


def test_cle_url_sans_suivi():
    assert cle_url("https://jobs.x.com/offre/12?utm_source=a&utm_medium=b") == "https://jobs.x.com/offre/12"


def test_fusion_garde_le_plus_riche():
    a = Offre("Indeed", "Acheteur", "X", description="court", candidats=None)
    b = Offre("LinkedIn", "Acheteur", "X", description="long " * 100, candidats=12)
    f = fusionner(a, b)
    assert len(f.description) > 100 and f.candidats == 12 and set(f.sources) == {"Indeed", "LinkedIn"}


def test_fusion_url_source_prioritaire():
    a = Offre("Indeed", "Acheteur", "X", url="https://indeed/1")
    b = Offre("Site carrières", "Acheteur", "X", url="https://x.wd3.myworkdayjobs.com/1")
    assert fusionner(a, b).url == "https://x.wd3.myworkdayjobs.com/1"


def test_aller_retour_rc():
    o = Offre("LinkedIn", "Buyer", "Y", lieu="Lyon", pays="France", url="u", description="d", candidats=4)
    d = vers_rc(o)
    assert d["title"] == "Buyer" and d["company"] == "Y" and d["desc"] == "d"
    assert depuis_rc(d).titre == "Buyer" and depuis_rc(d).candidats == 4
