"""Snapshot UNIQUE de TheSportsDB vers la base locale (`calendrier/base/`), a lancer tant que
l'abonnement est actif. Apres cela, plus aucun appel TheSportsDB n'est necessaire.

    .venv/bin/python -m calendrier.migration_tsdb [evenements] [equipes] [classements]   # tout par defaut

- evenements   : saisons de chaque championnat (precedente + en cours) et des 3 coupes d'Europe
                 (3 saisons precedentes + en cours) : `eventsseason`, ~52 requetes ;
- equipes      : fiche de chaque club present (pays, championnat national, nom, logo) : `lookupteam` ;
- classements  : table du championnat national des clubs dont la ligue n'est pas suivie
                 (`lookuptable`), figee a la date du snapshot.

Reprise possible : ce qui est deja ecrit n'est pas retelecharge (option --refresh pour tout refaire).
Requetes espacees de 0,3 s, avec reessais sur 429/5xx.
"""
import os
import sys
import time
from datetime import date

import requests
from dotenv import load_dotenv

import main  # constantes seulement (ligues, saisons) : main n'appelle plus TheSportsDB
from .base import Base

load_dotenv()
API_KEY = os.environ.get("SPORTSDB_API_KEY")
DELAI = 0.3  # secondes entre deux appels (limite de debit de l'offre)
_dernier = [0.0]


def _url(point, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/{point}.php?{q}"


def _json(url, tentatives=4):
    """GET espace de DELAI secondes, avec reessais sur 429 / 5xx."""
    for essai in range(tentatives):
        attente = DELAI - (time.monotonic() - _dernier[0])
        if attente > 0:
            time.sleep(attente)
        resp = requests.get(url, timeout=30)
        _dernier[0] = time.monotonic()
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(3 * (essai + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def saisons_a_telecharger():
    """[(id_ligue, saison)] : championnats = saisons passees suivies + en cours ; coupes = idem."""
    demandes = []
    for id_ligue in main.DOMESTIC_LEAGUES:
        for s in main.saisons_passees_ligue(id_ligue) + [main.saison_actuelle_ligue(id_ligue)]:
            demandes.append((id_ligue, s))
    for id_ligue in main.LEAGUE_IDS:
        for s in main.PAST_SEASONS + [main.SEASON]:
            demandes.append((id_ligue, s))
    return demandes


def migrer_evenements(base, refaire=False):
    demandes = saisons_a_telecharger()
    print(f"{len(demandes)} saisons de ligue a telecharger")
    for id_ligue, saison in demandes:
        if not refaire and base.evenements_saison(id_ligue, saison):
            continue
        evenements = _json(_url("eventsseason", id=id_ligue, s=saison)).get("events") or []
        if not evenements:
            print(f"  ! {id_ligue} {saison} : aucun evenement")
            continue
        base.ecrire_saison(id_ligue, saison, evenements)
        print(f"  {id_ligue} {saison} : {len(evenements)} evenements")


def equipes_presentes(base):
    ids = {}
    for id_ligue in list(main.DOMESTIC_LEAGUES) + list(main.LEAGUE_IDS):
        for e in base.evenements_ligue(id_ligue):
            for cote in ("Home", "Away"):
                if e[f"id{cote}Team"]:
                    ids.setdefault(str(e[f"id{cote}Team"]), (e[f"str{cote}Team"], e[f"str{cote}TeamBadge"]))
    return ids


def migrer_equipes(base, refaire=False):
    equipes = base.equipes()
    presentes = equipes_presentes(base)
    a_faire = [i for i in presentes if refaire or i not in equipes]
    print(f"{len(presentes)} clubs, {len(a_faire)} fiches a telecharger")
    for n, id_club in enumerate(a_faire, 1):
        nom, badge = presentes[id_club]
        try:
            teams = _json(_url("lookupteam", id=id_club)).get("teams") or []
        except requests.exceptions.RequestException as exc:
            print(f"  ! {id_club} {nom} : {type(exc).__name__}")
            continue
        fiche = teams[0] if teams else {}
        equipes[id_club] = {
            "nom": fiche.get("strTeam") or nom,
            "pays": fiche.get("strCountry") or "",
            "ligue": {"id": fiche["idLeague"], "nom": fiche.get("strLeague") or ""} if fiche.get("idLeague") else None,
            "badge": fiche.get("strBadge") or badge or "",
        }
        if n % 50 == 0:
            base.ecrire_equipes(equipes)
            print(f"  {n}/{len(a_faire)}")
    base.ecrire_equipes(equipes)


def migrer_classements(base, refaire=False):
    """Tables des championnats nationaux que le site ne reconstruit pas lui-meme (ligues non suivies)."""
    equipes = base.equipes()
    ligues = {}
    for fiche in equipes.values():
        if fiche.get("ligue") and fiche["ligue"]["id"] not in main.DOMESTIC_LEAGUES:
            ligues[fiche["ligue"]["id"]] = fiche["ligue"]["nom"]
    tables = base.classements_nationaux()
    a_faire = [i for i in ligues if refaire or i not in tables]
    print(f"{len(ligues)} ligues non suivies, {len(a_faire)} tables a telecharger")
    annee = int(main.SEASON.split("-")[0])
    for id_ligue in a_faire:
        for candidate in (f"{annee}-{annee + 1}", str(annee), f"{annee - 1}-{annee}", str(annee - 1)):
            try:
                table = _json(_url("lookuptable", l=id_ligue, s=candidate)).get("table")
            except requests.exceptions.RequestException:
                continue
            if table:
                tables[id_ligue] = {"ligue": ligues[id_ligue], "saison": candidate, "maj": str(date.today()),
                                    "lignes": [{"idTeam": l["idTeam"], "intRank": l["intRank"], "strTeam": l.get("strTeam")}
                                               for l in table]}
                break
        else:
            tables[id_ligue] = {"ligue": ligues[id_ligue], "saison": None, "maj": str(date.today()), "lignes": []}
    base.ecrire_classements_nationaux(tables)


if __name__ == "__main__":
    if not API_KEY:
        sys.exit("SPORTSDB_API_KEY absente : ce snapshot necessite l'abonnement TheSportsDB (a lancer avant de le resilier).")
    etapes = [a for a in sys.argv[1:] if not a.startswith("--")] or ["evenements", "equipes", "classements"]
    refaire = "--refresh" in sys.argv
    base = Base()
    if "evenements" in etapes:
        migrer_evenements(base, refaire)
    if "equipes" in etapes:
        migrer_equipes(base, refaire)
    if "classements" in etapes:
        migrer_classements(base, refaire)
    print("Snapshot termine.")
