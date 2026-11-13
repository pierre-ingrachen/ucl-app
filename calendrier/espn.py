"""Fournisseur principal : API publique ESPN (aucune cle, aucun quota annonce).

    https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates=AAAAMMJJ

Contraintes constatees le 2026-11-13 : une plage de dates (`AAAAMMJJ-AAAAMMJJ`) renvoie 400, il
faut donc une requete par ligue et par jour ; le point `soccer/all/scoreboard` plafonne a 100
matchs par jour (inutilisable). API non officielle : elle peut changer sans prevenir, d'ou le
secours `odds_api` et la verification des champs ici (un match mal forme est ignore et compte,
jamais devine).
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from .ligues import LIGUES, saison

journal = logging.getLogger("calendrier.espn")
URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
THREADS = 6  # requetes en parallele (politesse : ESPN n'annonce pas de limite)

# Statuts ESPN (status.type.name) -> statut TheSportsDB. Tout statut inconnu est traite comme « pas
# joue » (jamais de score invente).
STATUTS_TERMINES = {"STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_AET", "STATUS_FINAL_PEN",
                    "STATUS_END_OF_EXTRATIME", "STATUS_FINAL_ET"}
STATUTS_REPORTES = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED", "STATUS_ABANDONED",
                    "STATUS_SUSPENDED", "STATUS_DELAYED_RAIN"}


class ErreurEspn(Exception):
    """ESPN injoignable ou reponse inexploitable pour une ligue/un jour."""


def telecharger_jour(slug, jour, session=None, tentatives=3):
    """Evenements bruts ESPN d'une ligue pour un jour. Leve ErreurEspn apres `tentatives` essais
    (reseau, 5xx, JSON invalide) ; un 400/404 (ligue absente ce jour-la) donne une liste vide."""
    http = session or requests
    derniere = None
    for essai in range(tentatives):
        try:
            r = http.get(URL.format(slug=slug), params={"dates": jour.strftime("%Y%m%d")}, timeout=20)
            if r.status_code in (400, 404):
                return []
            if r.status_code == 429 or r.status_code >= 500:
                derniere = f"HTTP {r.status_code}"
                time.sleep(1.5 * (essai + 1))
                continue
            r.raise_for_status()
            evenements = r.json().get("events")
            if evenements is None:
                raise ValueError("champ `events` absent")
            return evenements
        except (requests.exceptions.RequestException, ValueError) as exc:
            derniere = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (essai + 1))
    raise ErreurEspn(f"{slug} {jour} : {derniere}")


def convertir(brut, id_ligue, annuaire):
    """Evenement ESPN -> evenement au format TheSportsDB, ou None s'il est inexploitable.
    Le logo ESPN n'est utilise que si le club n'a pas de logo TheSportsDB dans l'annuaire."""
    try:
        comp = brut["competitions"][0]
        equipes = {c["homeAway"]: c for c in comp["competitors"]}
        dom, ext = equipes["home"], equipes["away"]
        horodatage = datetime.strptime(brut["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        statut = (brut.get("status") or comp.get("status") or {}).get("type") or {}
    except (KeyError, IndexError, ValueError, TypeError):
        return None

    # Club inconnu de l'historique local (promu, nouveau) : id provisoire stable, sans historique.
    id_dom = annuaire.resoudre_ou_provisoire(dom["team"]["displayName"], id_ligue, dom["team"].get("id"))
    id_ext = annuaire.resoudre_ou_provisoire(ext["team"]["displayName"], id_ligue, ext["team"].get("id"))

    termine = statut.get("name") in STATUTS_TERMINES or (statut.get("completed") and statut.get("state") == "post"
                                                       and statut.get("name") not in STATUTS_REPORTES)
    reporte = statut.get("name") in STATUTS_REPORTES
    score_dom = ext_score = None
    if termine:
        try:
            score_dom, ext_score = str(int(dom["score"])), str(int(ext["score"]))
        except (KeyError, ValueError, TypeError):
            termine = False  # score illisible : on ne devine pas, le match reste « a jouer »

    nom_dom = annuaire.nom(id_dom) or dom["team"]["displayName"]
    nom_ext = annuaire.nom(id_ext) or ext["team"]["displayName"]
    return {
        "idEvent": None,  # attribue par source.py (id TheSportsDB existant ou id stable)
        "idEventEspn": str(brut.get("id")),
        "idLeague": id_ligue,
        "strLeague": LIGUES[id_ligue]["nom"],
        "strLeagueBadge": annuaire.logo_ligue(id_ligue),
        "strSeason": saison(id_ligue, horodatage.date()),
        "strEvent": f"{nom_dom} vs {nom_ext}",
        "strHomeTeam": nom_dom, "strAwayTeam": nom_ext,
        "idHomeTeam": id_dom, "idAwayTeam": id_ext,
        "strHomeTeamBadge": annuaire.logo(id_dom, dom["team"].get("logo")),
        "strAwayTeamBadge": annuaire.logo(id_ext, ext["team"].get("logo")),
        "dateEvent": horodatage.strftime("%Y-%m-%d"),
        "strTime": horodatage.strftime("%H:%M:%S"),
        "strTimestamp": horodatage.strftime("%Y-%m-%dT%H:%M:%S"),
        "intHomeScore": score_dom, "intAwayScore": ext_score,
        "strStatus": "FT" if termine else "Postponed" if reporte else "NS",
        "strPostponed": "yes" if reporte else "no",
        "strVenue": (brut.get("venue") or comp.get("venue") or {}).get("fullName")
                    or (comp.get("venue") or {}).get("displayName") or "",
        "source": "espn",
    }


def evenements(taches, annuaire, session=None):
    """Evenements ESPN pour des couples (id_ligue, jour). Les ligues sans slug ESPN sont ignorees.
    Renvoie (evenements, ligues_en_panne, nb_ignores) : une ligue est « en panne » si au moins un
    de ses jours a echoue (l'appelant la completera par le secours The Odds API)."""
    taches = [(i, j) for i, j in taches if LIGUES[i]["espn"]]
    resultats, en_panne = [], set()

    def tache(t):
        id_ligue, jour = t
        try:
            return id_ligue, telecharger_jour(LIGUES[id_ligue]["espn"], jour, session), None
        except ErreurEspn as exc:
            return id_ligue, [], exc

    with ThreadPoolExecutor(THREADS) as pool:
        retours = list(pool.map(tache, taches))
    ignores = 0
    for id_ligue, bruts, erreur in retours:
        if erreur:
            journal.warning("ESPN : %s", erreur)
            en_panne.add(id_ligue)
        for brut in bruts:
            e = convertir(brut, id_ligue, annuaire)
            if e is None:
                ignores += 1
            else:
                resultats.append(e)
    return resultats, en_panne, ignores
