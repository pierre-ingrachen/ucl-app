"""Resultats des ligues qu'ESPN ne couvre pas (Pologne, Suisse) : fichiers gratuits de
football-data.co.uk (`/new/POL.csv`, `/new/SWZ.csv`), deja utilises par le projet pour les cotes.

Un fichier par pays, toutes saisons, une ligne par match (Date jj/mm/aaaa, Home, Away, HG, AG).
Mis a jour avec quelques jours de retard (derniere date constatee le 2026-11-13 : le 8 nov.) :
suffisant pour l'historique et le reentrainement, pas pour resoudre un pari le lendemain du
match (il le sera quand le fichier sera a jour). Donnees non fiables : lues avec `csv` uniquement,
jamais executees ; une ligne illisible est ignoree.
"""
import csv
import io
import logging
import time
from datetime import date, datetime

import requests

from .ligues import saison

journal = logging.getLogger("calendrier.footballdata")
URL = "https://www.football-data.co.uk/new/{code}.csv"
CODES = {"4422": "POL", "4675": "SWZ"}  # id TheSportsDB -> code football-data


class ErreurFootballData(Exception):
    """Fichier injoignable ou inexploitable."""


def telecharger(code, session=None, tentatives=3):
    """Lignes du CSV d'un pays (liste de dicts)."""
    http = session or requests
    derniere = None
    for essai in range(tentatives):
        try:
            r = http.get(URL.format(code=code), timeout=30)
            if r.status_code != 200:
                derniere = f"HTTP {r.status_code}"
            else:
                texte = r.content.decode("utf-8-sig", errors="replace") if hasattr(r, "content") else r.text
                lignes = list(csv.DictReader(io.StringIO(texte)))
                if not lignes or "HG" not in lignes[0]:
                    raise ValueError("colonnes attendues absentes")
                return lignes
        except (requests.exceptions.RequestException, ValueError) as exc:
            derniere = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5 * (essai + 1))
    raise ErreurFootballData(f"{code} : {derniere}")


def convertir(ligne, id_ligue, annuaire, depuis):
    """Ligne CSV -> evenement termine au format TheSportsDB, ou None (ligne illisible, match avant
    `depuis`, score absent). Les clubs inconnus de l'annuaire donnent None : un resultat n'est
    jamais ajoute pour un club qu'on ne sait pas rapprocher."""
    try:
        jour = datetime.strptime(ligne["Date"].strip(), "%d/%m/%Y").date()
        score_dom, score_ext = str(int(ligne["HG"])), str(int(ligne["AG"]))
        nom_dom, nom_ext = ligne["Home"].strip(), ligne["Away"].strip()
    except (KeyError, ValueError, AttributeError):
        return None
    if jour < depuis:
        return None
    id_dom, id_ext = annuaire.resoudre(nom_dom, id_ligue), annuaire.resoudre(nom_ext, id_ligue)
    if not id_dom or not id_ext:
        return None
    return {
        "idEvent": None, "idLeague": id_ligue, "strSeason": saison(id_ligue, jour),
        "idHomeTeam": id_dom, "idAwayTeam": id_ext,
        "strHomeTeam": annuaire.nom(id_dom, nom_dom), "strAwayTeam": annuaire.nom(id_ext, nom_ext),
        "dateEvent": jour.isoformat(), "strTime": None, "strTimestamp": None,  # football-data ne donne pas l'heure UTC : jamais utilisee
        "intHomeScore": score_dom, "intAwayScore": score_ext, "strStatus": "FT", "strPostponed": "no",
        "source": "footballdata",
    }


def resultats(ids_ligues, annuaire, depuis, session=None):
    """Resultats termines depuis `depuis` des ligues couvertes par football-data.
    Renvoie (evenements, ligues_en_panne)."""
    evenements, en_panne = [], set()
    for id_ligue in ids_ligues:
        code = CODES.get(id_ligue)
        if not code:
            continue
        try:
            lignes = telecharger(code, session)
        except ErreurFootballData as exc:
            journal.warning("football-data : %s", exc)
            en_panne.add(id_ligue)
            continue
        evenements += [e for e in (convertir(l, id_ligue, annuaire, depuis) for l in lignes) if e]
    return evenements, en_panne
