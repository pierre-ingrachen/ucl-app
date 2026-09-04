"""Construit `cache_ml_matchs.json` : le jeu de matchs terminés servant à
entraîner le modèle de prédiction par apprentissage (`modele_ml.py`).

Ce cache est *régénérable* via l'API TheSportsDB (donc gitignoré et versionné sur
la branche `cache-snapshot`, comme les autres `cache_*.json`). Il n'est jamais
envoyé au navigateur : seul le backend le lit, une fois par jour, pour
reconstruire le modèle. Le site reste donc aussi léger qu'avant.

On va plus loin dans le passé que les caches du site (qui n'ont besoin que de
2-3 saisons pour les ratings) : ici on veut le maximum d'historique exploitable,
car un modèle à features apprend d'autant mieux qu'il voit de matchs.

Usage :
    python construire_cache_ml.py            # relève complète (API)
    python construire_cache_ml.py --dry-run  # n'écrit pas le fichier
"""

import json
import os
import sys

import requests
from dotenv import load_dotenv

from main import (
    LEAGUE_IDS,
    DOMESTIC_LEAGUES,
    DOMESTIC_LEAGUES_ANNEE_CIVILE,
    categoriser_phase,
    charger_cache_permanent,
    sauvegarder_cache_permanent,
    requete_api_avec_retry,
)

load_dotenv()

CACHE_ML_FILE = "cache_ml_matchs.json"
CACHE_TEAMS_FILE = "cache_teams.json"

# Fenêtre d'historique : bien plus large que celle des ratings du site. TheSportsDB
# (offre gratuite) expose de façon fiable ~4 saisons glissantes.
SAISONS_EUROPE = ["2022-2023", "2023-2024", "2024-2025", "2025-2026", "2026-2027"]
SAISONS_DOMESTIQUES = ["2022-2023", "2023-2024", "2024-2025", "2025-2026", "2026-2027"]
SAISONS_DOMESTIQUES_ANNEE_CIVILE = ["2022", "2023", "2024", "2025", "2026"]

API_KEY = os.environ.get("SPORTSDB_API_KEY")


def _url_saison(league_id, saison):
    return f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={saison}"


def _saisons(league_id, est_europe):
    if est_europe:
        return SAISONS_EUROPE
    if league_id in DOMESTIC_LEAGUES_ANNEE_CIVILE:
        return SAISONS_DOMESTIQUES_ANNEE_CIVILE
    return SAISONS_DOMESTIQUES


def _match_termine(m):
    h, a = m.get("intHomeScore"), m.get("intAwayScore")
    if h is None or a is None or h == "" or a == "":
        return False
    try:
        int(h), int(a)
    except (TypeError, ValueError):
        return False
    return bool(m.get("idHomeTeam") and m.get("idAwayTeam") and m.get("dateEvent"))


def _normaliser(m, est_europe, cache_teams):
    home_id, away_id = m.get("idHomeTeam"), m.get("idAwayTeam")
    return {
        "idEvent": m.get("idEvent"),
        "date": m.get("dateEvent"),
        "timestamp": m.get("strTimestamp") or f"{m.get('dateEvent')}T00:00:00",
        "leagueId": m.get("idLeague"),
        "league": m.get("strLeague"),
        "typeCompetition": "europe" if est_europe else "championnat",
        "phase": categoriser_phase(m) if est_europe else "championnat",
        "saison": m.get("strSeason"),
        "homeId": home_id,
        "awayId": away_id,
        "homeName": m.get("strHomeTeam"),
        "awayName": m.get("strAwayTeam"),
        "homePays": (m.get("strHomeCountry") or cache_teams.get(home_id, "")) if est_europe else "",
        "awayPays": (m.get("strAwayCountry") or cache_teams.get(away_id, "")) if est_europe else "",
        "homeGoals": int(m["intHomeScore"]),
        "awayGoals": int(m["intAwayScore"]),
    }


def _completer_pays(matchs, cache_teams):
    """Renseigne le pays des équipes européennes encore inconnues (throttlé par
    requete_api_avec_retry, cf. main.py)."""
    manquantes = {
        m["homeId"] for m in matchs if m["typeCompetition"] == "europe" and not m["homePays"]
    } | {
        m["awayId"] for m in matchs if m["typeCompetition"] == "europe" and not m["awayPays"]
    }
    manquantes.discard(None)
    if not manquantes:
        return False

    print(f"  {len(manquantes)} pays d'équipe à récupérer...")
    for team_id in manquantes:
        url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookupteam.php?id={team_id}"
        try:
            resp = requete_api_avec_retry(url)
            if resp.status_code == 200 and resp.json().get("teams"):
                cache_teams[team_id] = resp.json()["teams"][0].get("strCountry", "") or ""
            else:
                cache_teams[team_id] = ""
        except requests.exceptions.RequestException:
            cache_teams[team_id] = ""

    for m in matchs:
        if m["typeCompetition"] != "europe":
            continue
        m["homePays"] = m["homePays"] or cache_teams.get(m["homeId"], "")
        m["awayPays"] = m["awayPays"] or cache_teams.get(m["awayId"], "")
    return True


def construire(dry_run=False):
    if not API_KEY:
        raise RuntimeError("Variable d'environnement 'SPORTSDB_API_KEY' manquante.")

    cache_teams = charger_cache_permanent(CACHE_TEAMS_FILE)
    ligues = [(lid, True) for lid in LEAGUE_IDS] + [(lid, False) for lid in DOMESTIC_LEAGUES]

    par_id = {}
    for league_id, est_europe in ligues:
        for saison in _saisons(league_id, est_europe):
            try:
                resp = requete_api_avec_retry(_url_saison(league_id, saison))
                resp.raise_for_status()
                events = resp.json().get("events") or []
            except requests.exceptions.RequestException as e:
                print(f"  ! {league_id} {saison} : {e}")
                continue
            n = 0
            for m in events:
                if not _match_termine(m):
                    continue
                norm = _normaliser(m, est_europe, cache_teams)
                if norm["idEvent"]:
                    par_id[norm["idEvent"]] = norm
                    n += 1
            print(f"  {league_id:>6} {saison} : {n:>4} matchs terminés")

    matchs = sorted(par_id.values(), key=lambda m: (m["timestamp"], m["idEvent"]))
    teams_maj = _completer_pays(matchs, cache_teams)

    print(f"\nTotal : {len(matchs)} matchs, "
          f"{sum(m['typeCompetition'] == 'europe' for m in matchs)} européens.")

    if dry_run:
        print("(--dry-run : rien écrit)")
        return matchs

    sauvegarder_cache_permanent(CACHE_ML_FILE, {"date": None, "data": matchs})
    if teams_maj:
        sauvegarder_cache_permanent(CACHE_TEAMS_FILE, cache_teams)
    print(f"Écrit dans {CACHE_ML_FILE}.")
    return matchs


if __name__ == "__main__":
    construire(dry_run="--dry-run" in sys.argv)
