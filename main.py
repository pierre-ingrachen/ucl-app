from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime, timedelta, date
import json
import os
import time

from dotenv import load_dotenv

from rating import construire_modele, construire_modele_championnat, predire_resultat
from odds import recuperer_toutes_les_cotes

load_dotenv()

def _variable_environnement_requise(nom):
    """Cle API lue depuis l'environnement (.env en local, secret GitHub Actions en CI) :
    jamais en dur dans le code, pour ne pas finir dans l'historique Git."""
    valeur = os.environ.get(nom)
    if not valeur:
        raise RuntimeError(f"Variable d'environnement '{nom}' manquante (voir .env.example).")
    return valeur

app = FastAPI(title="Champions League API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = _variable_environnement_requise("SPORTSDB_API_KEY")
LEAGUE_IDS = ["4480", "4481", "5071"]  # UEFA Champions League, UEFA Europa League, UEFA Conference League
SEASON = "2026-2027"
PAST_SEASONS = ["2023-2024", "2024-2025", "2025-2026"]

# Championnats nationaux (onglet "Championnats")
DOMESTIC_LEAGUES = {
    "4344": "Primeira Liga",       # Portugal
    "4337": "Eredivisie",          # Pays-Bas
    "4338": "Pro League",          # Belgique
    "4328": "Premier League",      # Angleterre
    "4334": "Ligue 1",             # France
    "4335": "La Liga",             # Espagne
    "4332": "Serie A",             # Italie
    "4331": "Bundesliga"           # Allemagne
}
DOMESTIC_SEASON = "2026-2027"
DOMESTIC_PAST_SEASONS = ["2025-2026"]

# The Odds API (cotes Winamax) : cle du compte de l'utilisateur, a n'appeler qu'aux jours
# convenus (cf. obtenir_cotes_semaine) pour rester tres largement sous le quota gratuit.
ODDS_API_KEY = _variable_environnement_requise("ODDS_API_KEY")

# Releve complet des cotes le mardi et le vendredi matin (avant le choix des paris du jour) :
# mardi couvre les matchs europeens du mardi/mercredi (C1) et se rapproche des matchs du jeudi
# (Europa/Conference League), vendredi couvre le week-end des championnats nationaux et une
# derniere chance de capter des cotes Europa/Conference publiees tardivement par les books.
JOURS_RELEVE_COMPLET = {1, 4}  # lundi=0 ... mardi=1 ... vendredi=4

# Correspondance entre nos identifiants de ligue (TheSportsDB) et les cles de competition
# The Odds API. La Champions League a deux cles distinctes cote Odds API (qualifications et
# phase principale) alors qu'une seule couvre toutes les phases d'Europa/Conference League.
ODDS_API_SPORT_KEYS = {
    "4480": ["soccer_uefa_champs_league_qualification", "soccer_uefa_champs_league"],
    "4481": ["soccer_uefa_europa_league"],
    "5071": ["soccer_uefa_europa_conference_league"],
    "4344": ["soccer_portugal_primeira_liga"],
    "4337": ["soccer_netherlands_eredivisie"],
    "4338": ["soccer_belgium_first_div"],
    "4328": ["soccer_epl"],
    "4334": ["soccer_france_ligue_one"],
    "4335": ["soccer_spain_la_liga"],
    "4332": ["soccer_italy_serie_a"],
    "4331": ["soccer_germany_bundesliga"],
}

CACHE_SEASON_FILE = "cache_season.json"
CACHE_DETAILS_FILE = "cache_details.json"
CACHE_HISTORY_FILE = "cache_history_qualifs.json"
CACHE_TEAMS_FILE = "cache_teams.json"
CACHE_CLASSEMENT_FILE = "cache_classement.json"
CACHE_CHAMPIONNAT_SEASON_FILE = "cache_championnat_season.json"
CACHE_CHAMPIONNAT_HISTORIQUE_FILE = "cache_championnat_historique.json"
CACHE_CLASSEMENT_SAISON_FILE = "cache_classement_saison.json"
CACHE_CLASSEMENT_ACTUELLE_FILE = "cache_classement_actuelle.json"
CACHE_COTES_FILE = "cache_cotes_winamax.json"
CACHE_PARIS_FILE = "cache_paris.json"

def requete_api_avec_retry(url, tentatives=3, delai=1.5):
    """GET avec quelques nouvelles tentatives en cas d'indisponibilite ponctuelle de
    TheSportsDB (503), frequente sur l'offre gratuite. Laisse remonter le dernier echec."""
    for tentative in range(tentatives):
        response = requests.get(url)
        if response.status_code != 503 or tentative == tentatives - 1:
            return response
        time.sleep(delai)
    return response

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

_modele_rating = None
_modele_rating_date = None

def obtenir_modele_rating():
    """Modele de probabilite de resultat (rating pays + effet club), reconstruit une fois
    par jour (l'historique sous-jacent n'est lui-meme rafraichi qu'une fois par jour)."""
    global _modele_rating, _modele_rating_date
    aujourd_hui = date.today()
    if _modele_rating is None or _modele_rating_date != aujourd_hui:
        _modele_rating = construire_modele(obtenir_historique_qualifications())
        _modele_rating_date = aujourd_hui
    return _modele_rating

_modeles_championnat = {}
_modeles_championnat_date = None

def obtenir_modele_championnat(league_id, historique_ligue):
    """Modele de probabilite de resultat pour un championnat national, reconstruit une fois
    par jour (un rating par club, pas de niveau pays vu qu'un seul pays par championnat)."""
    global _modeles_championnat, _modeles_championnat_date
    aujourd_hui = date.today()
    if _modeles_championnat_date != aujourd_hui:
        _modeles_championnat = {}
        _modeles_championnat_date = aujourd_hui
    if league_id not in _modeles_championnat:
        _modeles_championnat[league_id] = construire_modele_championnat(historique_ligue)
    return _modeles_championnat[league_id]

def injecter_predictions(match_data, cache_championnat_historique):
    """Ajoute les probabilites de resultat a une fiche de match, europeen ou national, si ce
    n'est pas deja fait. Ne fait rien pour les competitions hors perimetre des modeles."""
    if "probaVictoireDomicile" in match_data:
        return

    id_ligue = match_data.get("idLeague")
    if id_ligue in LEAGUE_IDS:
        modele = obtenir_modele_rating()
        match_data.update(predire_resultat(
            modele, match_data.get("idHomeTeam"), match_data.get("idAwayTeam"),
            match_data.get("strHomeCountry"), match_data.get("strAwayCountry")
        ))
    elif id_ligue in DOMESTIC_LEAGUES:
        matchs_ligue = charger_historique_championnat(id_ligue, cache_championnat_historique)
        modele = obtenir_modele_championnat(id_ligue, matchs_ligue)
        match_data.update(predire_resultat(
            modele, match_data.get("idHomeTeam"), match_data.get("idAwayTeam"), "", ""
        ))

def _grouper_matchs_par_ligue(matchs):
    groupes = {}
    for m in matchs:
        groupes.setdefault(m.get("idLeague"), []).append(m)
    return groupes

def obtenir_cotes_semaine():
    """Cotes Winamax des matchs de la semaine (europeens + championnats suivis).

    Releve complet le mardi et le vendredi matin, au plus une fois par jour (cf.
    JOURS_RELEVE_COMPLET), toujours avant le choix des paris du jour. Les autres jours, une
    relance ciblee et minimale : uniquement pour les competitions ayant un match LE LENDEMAIN
    et encore sans cote Winamax trouvee (certaines competitions, notamment les qualifications
    europeennes, ont un delai de synchronisation entre le site Winamax et The Odds API - voire
    aucune cote publiee du tout par les books tant que le tour n'approche pas). Chaque
    competition n'est relancee au plus qu'une fois par jour. Le reste du temps, on relit juste
    le fichier de cache sans appeler l'API, pour rester tres largement sous le quota gratuit
    (1 requete par competition, jamais une requete par match)."""
    cache = charger_cache_permanent(CACHE_COTES_FILE)
    semaine_actuelle = list(date.today().isocalendar()[:2])

    if cache.get("semaine") != semaine_actuelle:
        cache = {"semaine": semaine_actuelle, "data": {}, "quota": None,
                  "dernier_releve_complet": None, "relances_faites": []}

    aujourd_hui = date.today()
    cle_jour = str(aujourd_hui)
    matchs_semaine = (
        filtrer_matchs_semaine(obtenir_matchs_a_venir())
        + filtrer_matchs_semaine(obtenir_matchs_championnats_a_venir())
    )
    matchs_par_ligue = _grouper_matchs_par_ligue(matchs_semaine)

    a_interroger = {}

    if aujourd_hui.weekday() in JOURS_RELEVE_COMPLET and cache.get("dernier_releve_complet") != cle_jour:
        a_interroger = ODDS_API_SPORT_KEYS
        cache["dernier_releve_complet"] = cle_jour
    elif cache.get("dernier_releve_complet"):
        demain_str = str(aujourd_hui + timedelta(days=1))
        for id_ligue, sport_keys in ODDS_API_SPORT_KEYS.items():
            cle_relance = f"{id_ligue}:{cle_jour}"
            match_demain_sans_cote = any(
                m.get("dateEvent") == demain_str
                and cache["data"].get(m["idEvent"], {}).get("bookmaker") is None
                for m in matchs_par_ligue.get(id_ligue, [])
            )
            if match_demain_sans_cote and cle_relance not in cache["relances_faites"]:
                a_interroger[id_ligue] = sport_keys
                cache["relances_faites"].append(cle_relance)

    if a_interroger:
        nouvelles_cotes, quota = recuperer_toutes_les_cotes(a_interroger, matchs_par_ligue, ODDS_API_KEY)
        cache["data"].update(nouvelles_cotes)
        if quota:
            cache["quota"] = quota
        sauvegarder_cache_permanent(CACHE_COTES_FILE, cache)

    return cache.get("data", {})

def injecter_cotes(match_data, event_id, cotes_semaine):
    """Ajoute les cotes du bookmaker trouve (Winamax en priorite, sinon Betclic, sinon
    Unibet) a la fiche. Si le match est reconnu par The Odds API mais qu'aucun des trois
    n'a de cote, `coteBookmaker` est explicitement present avec la valeur None, pour que
    le frontend puisse afficher "indisponible" plutot que de ne rien afficher du tout."""
    cotes = cotes_semaine.get(event_id)
    if cotes:
        match_data["coteBookmaker"] = cotes.get("bookmaker")
        match_data["coteDomicile"] = cotes.get("domicile")
        match_data["coteNul"] = cotes.get("nul")
        match_data["coteExterieure"] = cotes.get("exterieure")

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

def filtrer_matchs_semaine(matchs):
    """Restreint une liste de matchs à ceux prévus entre aujourd'hui et dans 7 jours."""
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

    return matchs_filtres

def obtenir_table_saison(league_id, season, cache_tables):
    """Retourne le classement complet (tous les clubs) d'un championnat pour une saison
    donnée, en interrogeant l'API si absent du cache.

    La saison en cours évolue à chaque journée jouée : elle est donc rafraîchie tous les
    jours (cache quotidien), contrairement aux saisons passées, figées, qui profitent d'un
    cache permanent."""
    if season == DOMESTIC_SEASON:
        cache_actuelle = charger_cache(CACHE_CLASSEMENT_ACTUELLE_FILE) or {}
        if league_id in cache_actuelle:
            return cache_actuelle[league_id]

        table = None
        try:
            url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookuptable.php?l={league_id}&s={season}"
            resp = requests.get(url)
            if resp.status_code == 200:
                table = resp.json().get("table")
        except requests.exceptions.RequestException:
            pass

        cache_actuelle[league_id] = table
        sauvegarder_cache(CACHE_CLASSEMENT_ACTUELLE_FILE, cache_actuelle)
        return table

    clef = f"{league_id}_{season}"
    if cache_tables.get(clef):
        return cache_tables[clef]

    table = None
    try:
        url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookuptable.php?l={league_id}&s={season}"
        resp = requests.get(url)
        if resp.status_code == 200:
            table = resp.json().get("table")
    except requests.exceptions.RequestException:
        pass

    if table:
        cache_tables[clef] = table
    return table

def obtenir_classement_equipe_pour_saison(team_id, league_id, league_name, season, cache_tables):
    """Position d'une équipe dans un championnat, lors d'une saison précise (celle du match
    d'historique concerné, pas forcément la saison en cours)."""
    if not team_id or not season:
        return None
    table = obtenir_table_saison(league_id, season, cache_tables)
    if not table:
        return None
    ligne = next((l for l in table if l.get("idTeam") == team_id), None)
    if not ligne:
        return None
    rang = ligne.get("intRank")
    if rang is None:
        return None
    return {
        "position": int(rang),
        "total": len(table),
        "saison": season,
        "ligue": league_name
    }

def charger_historique_championnat(league_id, cache_historique):
    """Tous les matchs déjà joués d'un championnat national, sur les saisons passées
    suivies et la saison en cours."""
    if league_id in cache_historique:
        return cache_historique[league_id]

    matchs = []
    for season in DOMESTIC_PAST_SEASONS + [DOMESTIC_SEASON]:
        url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={season}"
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            for m in resp.json().get("events", []) or []:
                if m.get("intHomeScore") is None or m.get("intAwayScore") is None:
                    continue
                matchs.append(m)
        except requests.exceptions.RequestException:
            continue

    cache_historique[league_id] = matchs
    return matchs

def obtenir_derniers_matchs_championnat(team_id, league_id, league_name, avant_date, cache_historique, cache_tables, limite=5):
    """Les `limite` derniers matchs joués par une équipe dans son championnat national avant
    une date donnée, chacun enrichi du classement de l'adversaire lors de LA SAISON de ce
    match précis (et non la saison en cours)."""
    matchs_ligue = charger_historique_championnat(league_id, cache_historique)
    matchs_equipe = [
        m for m in matchs_ligue
        if (m.get("idHomeTeam") == team_id or m.get("idAwayTeam") == team_id)
        and m.get("dateEvent") and m["dateEvent"] < avant_date
    ]
    matchs_equipe.sort(key=lambda m: m["dateEvent"], reverse=True)

    resultat = []
    for m in matchs_equipe[:limite]:
        est_domicile = m.get("idHomeTeam") == team_id
        id_adversaire = m.get("idAwayTeam") if est_domicile else m.get("idHomeTeam")
        saison_match = m.get("strSeason")

        copie = dict(m)
        copie["classementAdversaire"] = obtenir_classement_equipe_pour_saison(
            id_adversaire, league_id, league_name, saison_match, cache_tables
        )
        resultat.append(copie)

    return resultat

def obtenir_matchs_a_venir():
    """Tous les matchs de la saison en cours des 3 competitions europeennes
    (pas seulement ceux de la semaine), avec mise en cache quotidienne."""
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

    return matchs

@app.get("/api/matchs/a-venir")
def get_matchs_a_venir():
    return {"events": filtrer_matchs_semaine(obtenir_matchs_a_venir())}

def obtenir_matchs_championnats_a_venir():
    """Tous les matchs de la saison en cours des championnats nationaux suivis (pas seulement
    ceux de la semaine), avec mise en cache quotidienne."""
    matchs = charger_cache(CACHE_CHAMPIONNAT_SEASON_FILE)

    if matchs is None:
        matchs = []
        for league_id in DOMESTIC_LEAGUES:
            url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={DOMESTIC_SEASON}"
            try:
                response = requests.get(url)
                response.raise_for_status()
                matchs.extend(response.json().get("events", []) or [])
            except requests.exceptions.RequestException:
                raise HTTPException(status_code=500, detail="Erreur lors de la communication avec TheSportsDB")
        sauvegarder_cache(CACHE_CHAMPIONNAT_SEASON_FILE, matchs)

    return matchs

@app.get("/api/championnats/matchs/a-venir")
def get_matchs_championnats_a_venir():
    matchs = obtenir_matchs_championnats_a_venir()

    return {"events": filtrer_matchs_semaine(matchs)}

@app.get("/api/championnats/classement/{league_id}")
def get_classement_championnat(league_id: str):
    if league_id not in DOMESTIC_LEAGUES:
        raise HTTPException(status_code=404, detail="Championnat inconnu")

    cache_tables = charger_cache_permanent(CACHE_CLASSEMENT_SAISON_FILE)
    saison_precedente = DOMESTIC_PAST_SEASONS[-1]

    table_actuelle = obtenir_table_saison(league_id, DOMESTIC_SEASON, cache_tables)
    table_precedente = obtenir_table_saison(league_id, saison_precedente, cache_tables)
    sauvegarder_cache_permanent(CACHE_CLASSEMENT_SAISON_FILE, cache_tables)

    return {
        "ligue": DOMESTIC_LEAGUES[league_id],
        "saisonActuelle": {"saison": DOMESTIC_SEASON, "classement": table_actuelle},
        "saisonPrecedente": {"saison": saison_precedente, "classement": table_precedente}
    }

@app.get("/api/match/{event_id}")
def get_match_details(event_id: str):
    cache_details = charger_cache(CACHE_DETAILS_FILE) or {}
    cache_teams = charger_cache_permanent(CACHE_TEAMS_FILE)
    cache_classement = charger_cache_permanent(CACHE_CLASSEMENT_FILE)

    if event_id in cache_details:
        match_data = cache_details[event_id]
        # Comble une fiche mise en cache avant l'ajout des probabilites (sinon elle resterait
        # sans prediction jusqu'au renouvellement du cache le lendemain).
        if "probaVictoireDomicile" not in match_data:
            cache_championnat_historique = charger_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE) or {}
            injecter_predictions(match_data, cache_championnat_historique)
            sauvegarder_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE, cache_championnat_historique)
            cache_details[event_id] = match_data
            sauvegarder_cache(CACHE_DETAILS_FILE, cache_details)
        injecter_cotes(match_data, event_id, obtenir_cotes_semaine())
        return match_data

    url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/lookupevent.php?id={event_id}"

    try:
        response = requete_api_avec_retry(url)
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

            # Pour un match de championnat national (onglet "Championnats") : les 5 derniers
            # matchs de chaque équipe dans cette compétition, avec le classement de l'adversaire
            # lors de la saison où chacun de ces matchs a eu lieu.
            id_ligue = match_data.get("idLeague")
            cache_championnat_historique = charger_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE) or {}

            # Probabilites de resultat : modele rating pays + effet club pour les 3 competitions
            # europeennes, modele rating club pour les championnats nationaux.
            injecter_predictions(match_data, cache_championnat_historique)

            if id_ligue in DOMESTIC_LEAGUES:
                cache_classement_saison = charger_cache_permanent(CACHE_CLASSEMENT_SAISON_FILE)
                nom_ligue = DOMESTIC_LEAGUES[id_ligue]
                date_match = match_data.get("dateEvent", "")

                match_data["historiqueDomicile"] = obtenir_derniers_matchs_championnat(
                    match_data.get("idHomeTeam"), id_ligue, nom_ligue, date_match,
                    cache_championnat_historique, cache_classement_saison
                )
                match_data["historiqueExterieur"] = obtenir_derniers_matchs_championnat(
                    match_data.get("idAwayTeam"), id_ligue, nom_ligue, date_match,
                    cache_championnat_historique, cache_classement_saison
                )

                sauvegarder_cache_permanent(CACHE_CLASSEMENT_SAISON_FILE, cache_classement_saison)

            sauvegarder_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE, cache_championnat_historique)

            cache_details[event_id] = match_data
            sauvegarder_cache(CACHE_DETAILS_FILE, cache_details)

            # Cotes Winamax : toujours relues depuis le cache hebdomadaire dedie (jamais
            # persistees ici) pour ne pas figer une cote obtenue avant leur recuperation du lundi.
            injecter_cotes(match_data, event_id, obtenir_cotes_semaine())
            return match_data
        else:
            raise HTTPException(status_code=404, detail="Match introuvable")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=500, detail="Erreur API")

@app.get("/api/paris")
def get_paris():
    """Journal des paris "value" repere par bilan_paris.py (execute chaque matin via GitHub
    Actions), le plus recent en premier."""
    bilan = charger_cache_permanent(CACHE_PARIS_FILE)
    if not isinstance(bilan, list):
        bilan = []
    return {"paris": sorted(bilan, key=lambda p: p.get("date", ""), reverse=True)}

def obtenir_historique_qualifications():
    """Historique complet (3 dernieres saisons + saison en cours deja jouee)
    des matchs de qualification/groupe/finale des 3 competitions europeennes,
    avec pays de chaque equipe injecte. Mise en cache quotidienne."""
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

    return historique

@app.get("/api/matchs/historique-qualifications")
def get_historique_qualifications():
    return {"events": obtenir_historique_qualifications()}