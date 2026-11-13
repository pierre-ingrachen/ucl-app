"""Logos (clubs et ligues) stockes dans le depot : `calendrier/base/badges/`.

Chaque logo est enregistre sous un nom derive de son URL d'origine (`nom_fichier_badge`, identique a celui
de `main.py`), de sorte que le backend peut remplacer n'importe quelle URL distante par sa copie locale.
Les logos TheSportsDB sont telecharges en version « /small » (~30 Ko au lieu de ~100 Ko ; le site les
affiche a 80-120 px) ; les logos ESPN (clubs absents de TheSportsDB) tels quels. C'est le CDN d'images, pas
l'API : aucune cle n'est necessaire.

    .venv/bin/python -m calendrier.logos          # telecharge les logos manquants de la base
"""
import hashlib
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from .base import Base

journal = logging.getLogger("calendrier.logos")
RE_LOGO = re.compile(r"^https://(?:[a-z0-9.]*thesportsdb\.com/images/media/(?:team|league)/badge/|a\.espncdn\.com/i/teamlogos/soccer/)")
TAILLE_MAX = 2_000_000  # un « logo » plus gros est suspect : ignore


def nom_fichier_badge(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16] + os.path.splitext(url)[1]


def url_a_telecharger(url):
    return url + "/small" if "thesportsdb.com" in url else url


def dossier(base):
    return os.path.join(base.racine, "badges")


def urls_de_la_base(base):
    """Toutes les URLs de logos referencees par la base (evenements, clubs)."""
    urls = set()
    dossier_ev = os.path.join(base.racine, "evenements")
    if os.path.isdir(dossier_ev):
        for f in os.listdir(dossier_ev):
            for e in base._lire(os.path.join(dossier_ev, f), []):
                urls.update(e[k] for k in ("strHomeTeamBadge", "strAwayTeamBadge", "strLeagueBadge") if e.get(k))
    urls.update(f["badge"] for f in base.equipes().values() if f.get("badge"))
    return {u for u in urls if RE_LOGO.match(u)}


def telecharger_un(url, cible, session=None, tentatives=3):
    http = session or requests
    for essai in range(tentatives):
        try:
            r = http.get(url_a_telecharger(url), timeout=30)
            if r.status_code == 200 and r.content and len(r.content) <= TAILLE_MAX \
                    and "image" in (r.headers.get("content-type") or "image"):
                tmp = cible + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, cible)
                return True
            if r.status_code == 404:
                return False
        except requests.exceptions.RequestException:
            pass
        time.sleep(1 + essai)
    return False


def telecharger_manquants(base, session=None, workers=8):
    """Telecharge les logos de la base absents du disque. Renvoie (telecharges, echecs, deja_presents)."""
    os.makedirs(dossier(base), exist_ok=True)
    urls = sorted(urls_de_la_base(base))
    manquants = [u for u in urls if not os.path.exists(os.path.join(dossier(base), nom_fichier_badge(u)))]

    def tache(u):
        return u, telecharger_un(u, os.path.join(dossier(base), nom_fichier_badge(u)), session)

    with ThreadPoolExecutor(workers) as pool:
        resultats = list(pool.map(tache, manquants))
    echecs = [u for u, ok in resultats if not ok]
    for u in echecs:
        journal.warning("logo non telecharge : %s", u)
    return len(manquants) - len(echecs), echecs, len(urls) - len(manquants)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok, echecs, deja = telecharger_manquants(Base())
    taille = sum(os.path.getsize(os.path.join(dossier(Base()), f)) for f in os.listdir(dossier(Base())))
    print(f"{ok} logos telecharges, {len(echecs)} echecs, {deja} deja presents ({taille / 1e6:.1f} Mo au total)")
