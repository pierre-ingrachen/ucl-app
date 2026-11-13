"""Fournisseur de secours : point `/events` de The Odds API.

    GET https://api.the-odds-api.com/v4/sports/{sport_key}/events?apiKey=...

Il liste les matchs A VENIR d'une competition (id, equipes, heure de coup d'envoi) et ne coute
aucun credit de quota (en-tete `x-requests-last: 0`, verifie le 2026-11-13) : on peut l'appeler
a chaque run sans toucher au quota des cotes (`odds.py`, 1 credit par requete de cotes). Pas de
scores ni de logos : les resultats restent a la charge d'ESPN, et les logos viennent de
l'annuaire. Couvre la Pologne et la Suisse, absentes d'ESPN.
"""
import logging
import os
from datetime import datetime, timezone

import requests

from .ligues import LIGUES, saison

journal = logging.getLogger("calendrier.odds_api")
URL = "https://api.the-odds-api.com/v4/sports/{sport}/events"


class ErreurOddsApi(Exception):
    """The Odds API injoignable, cle absente/invalide ou reponse inexploitable."""


def telecharger_sport(sport_key, cle_api, session=None):
    """Evenements bruts d'une competition. Verifie que l'appel n'a rien coute."""
    http = session or requests
    try:
        r = http.get(URL.format(sport=sport_key), params={"apiKey": cle_api, "dateFormat": "iso"}, timeout=15)
    except requests.exceptions.RequestException as exc:
        raise ErreurOddsApi(f"{sport_key} : {type(exc).__name__}") from exc
    if r.status_code != 200:
        raise ErreurOddsApi(f"{sport_key} : HTTP {r.status_code}")
    cout = r.headers.get("x-requests-last")
    if cout not in (None, "0"):
        journal.warning("The Odds API : %s a coute %s credit(s) (attendu : 0)", sport_key, cout)
    try:
        return r.json() or []
    except ValueError as exc:
        raise ErreurOddsApi(f"{sport_key} : JSON invalide") from exc


def convertir(brut, id_ligue, annuaire):
    """Evenement The Odds API -> evenement au format TheSportsDB, ou None s'il est inexploitable."""
    try:
        horodatage = datetime.strptime(brut["commence_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        nom_dom, nom_ext = brut["home_team"], brut["away_team"]
    except (KeyError, ValueError, TypeError):
        return None
    id_dom = annuaire.resoudre_ou_provisoire(nom_dom, id_ligue)
    id_ext = annuaire.resoudre_ou_provisoire(nom_ext, id_ligue)
    nom_dom, nom_ext = annuaire.nom(id_dom) or nom_dom, annuaire.nom(id_ext) or nom_ext
    return {
        "idEvent": None, "idEventOddsApi": brut.get("id"),
        "idLeague": id_ligue, "strLeague": LIGUES[id_ligue]["nom"], "strLeagueBadge": annuaire.logo_ligue(id_ligue),
        "strSeason": saison(id_ligue, horodatage.date()), "strEvent": f"{nom_dom} vs {nom_ext}",
        "strHomeTeam": nom_dom, "strAwayTeam": nom_ext, "idHomeTeam": id_dom, "idAwayTeam": id_ext,
        "strHomeTeamBadge": annuaire.logo(id_dom), "strAwayTeamBadge": annuaire.logo(id_ext),
        "dateEvent": horodatage.strftime("%Y-%m-%d"), "strTime": horodatage.strftime("%H:%M:%S"),
        "strTimestamp": horodatage.strftime("%Y-%m-%dT%H:%M:%S"),
        "intHomeScore": None, "intAwayScore": None, "strStatus": "NS", "strPostponed": "no", "strVenue": "",
        "source": "odds_api",
    }


def evenements(ids_ligues, annuaire, cle_api=None, session=None):
    """Matchs a venir des `ids_ligues`. Renvoie (evenements, ligues_en_panne, nb_ignores).
    Sans cle (ODDS_API_KEY), toutes les ligues demandees sont « en panne »."""
    cle_api = cle_api or os.environ.get("ODDS_API_KEY")
    resultats, en_panne, ignores = [], set(), 0
    for id_ligue in ids_ligues:
        cles = LIGUES[id_ligue]["odds"]
        if not cles:
            continue  # aucune publication pour cette ligue : rien a demander
        if not cle_api:
            en_panne.add(id_ligue)
            continue
        for sport in cles:
            try:
                bruts = telecharger_sport(sport, cle_api, session)
            except ErreurOddsApi as exc:
                journal.warning("The Odds API : %s", exc)
                en_panne.add(id_ligue)
                continue
            for brut in bruts:
                e = convertir(brut, id_ligue, annuaire)
                if e is None:
                    ignores += 1
                else:
                    resultats.append(e)
    return resultats, en_panne, ignores
