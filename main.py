from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta, date
import json
import os
import time

app = FastAPI(title="Champions League API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "REDACTED_SPORTSDB_API_KEY"
LEAGUE_IDS = ["4480", "4481", "5071"]  # UEFA Champions League, UEFA Europa League, UEFA Conference League
SEASON = "2026-2027"
PAST_SEASONS = ["2023-2024", "2024-2025", "2025-2026"]

CACHE_SEASON_FILE = "cache_season.json"
CACHE_DETAILS_FILE = "cache_details.json"
CACHE_HISTORY_FILE = "cache_history_qualifs.json"
CACHE_TEAMS_FILE = "cache_teams.json"
CACHE_CLASSEMENT_FILE = "cache_classement.json"

def charger_cache_permanent(fichier):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {}

def sauvegarder_cache_permanent(fichier, data):
    try:
        with open(fichier, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
    except: pass

def charger_cache(fichier):
    aujourd_hui_str = str(date.today())
    if os.path.exists(fichier):
        try:
            with open(fichier, "r", encoding="utf-8") as f:
                cache = json.load(f)
                if cache.get("date") == aujourd_hui_str:
                    return cache.get("data")
        except (json.JSONDecodeError, IOError):
            pass 
    return None

def sauvegarder_cache(fichier, data):
    try:
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump({"date": str(date.today()), "data": data}, f, indent=4)
    except IOError:
        pass

def categoriser_phase(match):
    """Classe un match dans une des 3 phases equivalentes d'une campagne de C1 :
    qualifications, phase de groupe/poule/championnat, ou phase finale (a partir des 8es)."""
    round_num = match.get("intRound")
    event_name = (match.get("strEvent") or "").lower()
    filename = (match.get("strFilename") or "").lower()

    if round_num == "400" or "qual" in event_name or "qual" in filename:
        return "qualifications"

    try:
        r = int(round_num)
    except (TypeError, ValueError):
        return "qualifications"

    if r in (16, 32, 125, 150, 160, 200):
        return "finale"
    if 1 <= r <= 15:
        return "groupe"
    return "qualifications"

def obtenir_pays_equipe(team_id, cache_teams):
    """Retourne le pays d'une équipe, en interrogeant l'API si absent du cache permanent."""
    if not team_id:
        return ""
    if team_id in cache_teams and cache_teams[team_id]:
        return cache_teams[team_id]

    url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookupteam.php?id={team_id}"
    try:
        resp = requests.get(url)
        if resp.status_code == 200 and resp.json().get("teams"):
            pays = resp.json()["teams"][0].get("strCountry", "")
            cache_teams[team_id] = pays
            return pays
    except requests.exceptions.RequestException:
        pass

    cache_teams.setdefault(team_id, "")
    return cache_teams[team_id]

def obtenir_classement_national(team_id, cache_classement):
    """Retourne la position du club dans son championnat national lors de la saison
    domestique précédente (ex: 2e / 12), en interrogeant l'API si absent du cache permanent.
    Le format de saison des championnats nationaux n'est pas uniforme (2025-2026 ou 2025
    selon les pays) : on essaie donc les deux formats possibles."""
    if not team_id:
        return None
    if team_id in cache_classement:
        return cache_classement[team_id]

    resultat = None
    id_ligue_nationale = None
    nom_ligue_nationale = None

    try:
        url_equipe = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookupteam.php?id={team_id}"
        resp = requests.get(url_equipe)
        equipes = resp.json().get("teams") if resp.status_code == 200 else None
        id_ligue_nationale = equipes[0].get("idLeague") if equipes else None
        nom_ligue_nationale = equipes[0].get("strLeague") if equipes else None
    except requests.exceptions.RequestException:
        id_ligue_nationale = None

    if id_ligue_nationale:
        annee = int(SEASON.split("-")[0])
        # Le format de saison varie selon les pays (ex: "2025-2026" en Europe de l'Ouest,
        # "2025" pour les championnats en année civile) : chaque candidat est essayé
        # indépendamment pour qu'un format invalide n'empêche pas de tester l'autre.
        for saison_candidate in (f"{annee - 1}-{annee}", str(annee - 1)):
            try:
                url_classement = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookuptable.php?l={id_ligue_nationale}&s={saison_candidate}"
                resp_classement = requests.get(url_classement)
                table = resp_classement.json().get("table") if resp_classement.status_code == 200 else None
            except requests.exceptions.RequestException:
                continue

            if not table:
                continue

            ligne_equipe = next((ligne for ligne in table if ligne.get("idTeam") == team_id), None)
            if ligne_equipe:
                resultat = {
                    "position": int(ligne_equipe["intRank"]),
                    "total": len(table),
                    "saison": saison_candidate,
                    "ligue": nom_ligue_nationale
                }
                break

    cache_classement[team_id] = resultat
    return resultat

@app.get("/api/matchs/a-venir")
def get_matchs_a_venir():
    matchs = charger_cache(CACHE_SEASON_FILE)

    if matchs is None:
        matchs = []
        for league_id in LEAGUE_IDS:
            url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={SEASON}"
            try:
                response = requests.get(url)
                response.raise_for_status()
                matchs.extend(response.json().get("events", []) or [])
            except requests.exceptions.RequestException:
                raise HTTPException(status_code=500, detail="Erreur lors de la communication avec TheSportsDB")
        sauvegarder_cache(CACHE_SEASON_FILE, matchs)
    
    aujourd_hui = datetime.now()
    dans_7_jours = aujourd_hui + timedelta(days=7)
    matchs_filtres = []
    
    for match in matchs:
        date_str = match.get("dateEvent")
        if date_str:
            try:
                date_match = datetime.strptime(date_str, "%Y-%m-%d")
                if aujourd_hui.date() <= date_match.date() <= dans_7_jours.date():
                    matchs_filtres.append(match)
            except ValueError:
                pass
                
    return {"events": matchs_filtres}

@app.get("/api/match/{event_id}")
def get_match_details(event_id: str):
    cache_details = charger_cache(CACHE_DETAILS_FILE) or {}
    cache_teams = charger_cache_permanent(CACHE_TEAMS_FILE)
    cache_classement = charger_cache_permanent(CACHE_CLASSEMENT_FILE)

    if event_id in cache_details:
        return cache_details[event_id]

    url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookupevent.php?id={event_id}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if data.get("events") and len(data["events"]) > 0:
            match_data = data["events"][0]

            # Injection des pays pour le match cliqué (recherche via l'API si absent du cache)
            match_data["strHomeCountry"] = obtenir_pays_equipe(match_data.get("idHomeTeam"), cache_teams)
            match_data["strAwayCountry"] = obtenir_pays_equipe(match_data.get("idAwayTeam"), cache_teams)
            match_data["strPhase"] = categoriser_phase(match_data)
            sauvegarder_cache_permanent(CACHE_TEAMS_FILE, cache_teams)

            # Position en championnat national la saison précédente, pour toutes les compétitions
            match_data["classementDomicile"] = obtenir_classement_national(match_data.get("idHomeTeam"), cache_classement)
            match_data["classementExterieur"] = obtenir_classement_national(match_data.get("idAwayTeam"), cache_classement)
            sauvegarder_cache_permanent(CACHE_CLASSEMENT_FILE, cache_classement)

            cache_details[event_id] = match_data
            sauvegarder_cache(CACHE_DETAILS_FILE, cache_details)
            return match_data
        else:
            raise HTTPException(status_code=404, detail="Match introuvable")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="Erreur API")

@app.get("/api/matchs/historique-qualifications")
def get_historique_qualifications():
    historique = charger_cache(CACHE_HISTORY_FILE)
    cache_teams = charger_cache_permanent(CACHE_TEAMS_FILE)
    teams_updated = False
    
    if historique is None:
        historique = []
        equipes_uniques = set()
        
        for league_id in LEAGUE_IDS:
            for season in PAST_SEASONS + [SEASON]:
                url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={season}"
                try:
                    response = requests.get(url)
                    response.raise_for_status()
                    matchs = response.json().get("events", [])

                    if matchs:
                        for match in matchs:
                            # Pour la saison en cours, seuls les matchs déjà joués comptent comme historique
                            if season == SEASON and match.get("intHomeScore") is None:
                                continue
                            match["strPhase"] = categoriser_phase(match)
                            historique.append(match)
                            equipes_uniques.add(match.get("idHomeTeam"))
                            equipes_uniques.add(match.get("idAwayTeam"))
                except requests.exceptions.RequestException:
                    continue
                
        # Recherche des pays avec sécurité anti-blocage (0.6s par équipe manquante)
        for team_id in equipes_uniques:
            if team_id and team_id not in cache_teams:
                url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookupteam.php?id={team_id}"
                try:
                    resp = requests.get(url)
                    if resp.status_code == 200 and resp.json().get("teams"):
                        cache_teams[team_id] = resp.json()["teams"][0].get("strCountry", "")
                        teams_updated = True
                        time.sleep(0.6)
                except requests.exceptions.RequestException:
                    cache_teams[team_id] = ""

        # Injection dans l'historique
        for match in historique:
            match["strHomeCountry"] = cache_teams.get(match.get("idHomeTeam"), "")
            match["strAwayCountry"] = cache_teams.get(match.get("idAwayTeam"), "")
            
        sauvegarder_cache(CACHE_HISTORY_FILE, historique)
        if teams_updated: 
            sauvegarder_cache_permanent(CACHE_TEAMS_FILE, cache_teams)
            
    return {"events": historique}