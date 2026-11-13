# -*- coding: utf-8 -*-
"""V.I.E : Mon V.I.E (Business France, toutes les offres, via le moteur) + recherches V.I.E sur Indeed France et Welcome to the Jungle.
LinkedIn V.I.E est déjà dans les 3 couches LinkedIn ; les sites carrières V.I.E sont dans sites_carrieres."""
from veille.modele import depuis_rc
from veille.sources import sites_emploi as SE

NOM = "V.I.E"


def collecter(ctx) -> list:
    rc = ctx.moteur.rc
    brut = rc.mon_vie(ctx.secrets.get("VIE_API_KEY", ""))
    rc.mon_vie_details(brut)
    out = [depuis_rc(d) for d in brut]
    for o in out:
        o.contrat_brut = o.contrat_brut or "V.I.E"
    mots = ctx.rech.get("vie", [])
    out += SE.indeed_et_hellowork(ctx, plan=[("indeed", m, "France", "France") for m in mots if m.lower().startswith(("vie ", "v.i.e", "volontariat"))])
    out += [depuis_rc(d) for d in rc.wttj([m for m in mots if m.lower().startswith(("vie", "v.i.e", "volontariat"))][:8], max(1, SE.heures_depuis(ctx) // 24 + 1), None, {"V.I.E"})]
    return out
