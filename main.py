from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
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

# Compression des reponses JSON : l'historique complet des qualifications fait plusieurs Mo
# en clair, gzip le divise par ~10 sur le reseau sans rien changer cote client.
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = _variable_environnement_requise("SPORTSDB_API_KEY")
LEAGUE_IDS = ["4480", "4481", "5071"]  # UEFA Champions League, UEFA Europa League, UEFA Conference League
COMPETITIONS_EUROPE = {
    "4480": "UEFA Champions League",
    "4481": "UEFA Europa League",
    "5071": "UEFA Conference League",
}
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
    "4331": "Bundesliga",          # Allemagne
    "4339": "Süper Lig",           # Turquie
    "4422": "Ekstraklasa",         # Pologne
    "4631": "Czech First League",  # Tchéquie
    "4336": "Super League",        # Grèce
    "4358": "Eliteserien",         # Norvège
    "4340": "Superliga",           # Danemark
    "4630": "First Division",      # Chypre
    "4675": "Super League",        # Suisse
    "4621": "Bundesliga",          # Autriche
    "4690": "NB I",                # Hongrie
    "4330": "Premiership",         # Écosse
    "4347": "Allsvenskan"          # Suède
}
DOMESTIC_SEASON = "2026-2027"
DOMESTIC_PAST_SEASONS = ["2025-2026"]

# Championnats à année civile (calendrier printemps-automne) : leur saison TheSportsDB
# est une simple année, pas un intervalle "AAAA-AAAA".
DOMESTIC_LEAGUES_ANNEE_CIVILE = {"4358", "4347"}  # Norvège, Suède
DOMESTIC_SEASON_ANNEE_CIVILE = "2026"
DOMESTIC_PAST_SEASONS_ANNEE_CIVILE = ["2025"]

def saison_actuelle_ligue(league_id):
    if league_id in DOMESTIC_LEAGUES_ANNEE_CIVILE:
        return DOMESTIC_SEASON_ANNEE_CIVILE
    return DOMESTIC_SEASON

def saisons_passees_ligue(league_id):
    if league_id in DOMESTIC_LEAGUES_ANNEE_CIVILE:
        return DOMESTIC_PAST_SEASONS_ANNEE_CIVILE
    return DOMESTIC_PAST_SEASONS

# Places qualificatives / relégables par championnat, pour colorer les zones du classement
# (qu'on recalcule nous-mêmes à partir des résultats, sans la table de la plateforme).
# `cl`/`el`/`ecl` = nombre de places en tête donnant accès à la Ligue des champions / Europa
# League / Conference League ; `releg` = nombre de places en bas synonymes de relégation.
# Valeurs approximatives (barrages, place du vainqueur de coupe, play-offs de fin de saison
# ne sont pas modélisés) : à ajuster librement, ça n'a qu'un rôle indicatif.
ZONES_CHAMPIONNAT = {
    "4328": {"cl": 4, "el": 1, "ecl": 1, "releg": 3},  # Angleterre
    "4335": {"cl": 4, "el": 1, "ecl": 1, "releg": 3},  # Espagne
    "4332": {"cl": 4, "el": 1, "ecl": 1, "releg": 3},  # Italie
    "4331": {"cl": 4, "el": 1, "ecl": 1, "releg": 3},  # Allemagne
    "4334": {"cl": 2, "el": 1, "ecl": 1, "releg": 3},  # France
    "4344": {"cl": 2, "el": 1, "ecl": 1, "releg": 2},  # Portugal
    "4337": {"cl": 2, "el": 1, "ecl": 1, "releg": 2},  # Pays-Bas
    "4338": {"cl": 2, "el": 1, "ecl": 1, "releg": 1},  # Belgique
    "4339": {"cl": 1, "el": 1, "ecl": 1, "releg": 3},  # Turquie
    "4422": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Pologne
    "4631": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Tchéquie
    "4336": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Grèce
    "4358": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Norvège
    "4340": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Danemark
    "4630": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Chypre
    "4675": {"cl": 1, "el": 1, "ecl": 1, "releg": 1},  # Suisse
    "4621": {"cl": 1, "el": 1, "ecl": 1, "releg": 1},  # Autriche
    "4690": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Hongrie
    "4330": {"cl": 1, "el": 1, "ecl": 1, "releg": 1},  # Écosse
    "4347": {"cl": 1, "el": 1, "ecl": 1, "releg": 2},  # Suède
}

def zone_championnat(league_id, rang, total):
    """Libellé de zone (« Champions League », « Relegation »…) pour une position donnée,
    d'après `ZONES_CHAMPIONNAT`. Renvoie None hors de toute zone. Le format des libellés est
    choisi pour rester compatible avec `couleurZone` côté front."""
    if league_id in COMPETITIONS_EUROPE:
        # Phase de ligue (36 équipes) : 1-8 qualifiés directement pour les 8es, 9-24 en
        # barrages, 25-36 éliminés.
        if not rang:
            return None
        if rang <= 8:
            return "Qualifié pour les 8es"
        if rang <= 24:
            return "Barrages"
        return "Éliminé"

    regles = ZONES_CHAMPIONNAT.get(league_id)
    if not regles or not rang:
        return None
    cl, el = regles.get("cl", 0), regles.get("el", 0)
    ecl, releg = regles.get("ecl", 0), regles.get("releg", 0)
    if rang <= cl:
        return "Champions League"
    if rang <= cl + el:
        return "Europa League"
    if rang <= cl + el + ecl:
        return "Conference League"
    if total and rang > total - releg:
        return "Relegation"
    return None

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
    "4339": ["soccer_turkey_super_league"],
    "4422": ["soccer_poland_ekstraklasa"],
    "4336": ["soccer_greece_super_league"],
    "4358": ["soccer_norway_eliteserien"],
    "4340": ["soccer_denmark_superliga"],
    "4675": ["soccer_switzerland_superleague"],
    "4621": ["soccer_austria_bundesliga"],
    "4330": ["soccer_spl"],
    "4347": ["soccer_sweden_allsvenskan"],
    # Pas de cotes The Odds API publiées pour la Tchéquie, Chypre et la Hongrie.
}

CACHE_SEASON_FILE = "cache_season.json"
CACHE_DETAILS_FILE = "cache_details.json"
CACHE_HISTORY_FILE = "cache_history_qualifs.json"
CACHE_TEAMS_FILE = "cache_teams.json"
CACHE_CLASSEMENT_FILE = "cache_classement.json"
CACHE_CHAMPIONNAT_SEASON_FILE = "cache_championnat_season.json"
CACHE_CHAMPIONNAT_HISTORIQUE_FILE = "cache_championnat_historique.json"
CACHE_COTES_FILE = "cache_cotes_winamax.json"
CACHE_PARIS_FILE = "cache_paris.json"
CACHE_PARIS_ML_FILE = "cache_paris_ml.json"
CACHE_PARIS_ENSEMBLE_FILE = "cache_paris_ensemble.json"
# Nombre de matchs reellement analyses par jour (memes matchs pour les 3 modeles) :
# {date -> nb}. Sert a afficher "X matchs analyses" a cote du bilan.
CACHE_PARIS_ANALYSES_FILE = "cache_paris_analyses.json"

# Journaux de paris : un par modèle de probabilité (comparaison de performance).
FICHIERS_PARIS = {
    "rating": CACHE_PARIS_FILE,
    "ml": CACHE_PARIS_ML_FILE,
    "ensemble": CACHE_PARIS_ENSEMBLE_FILE,
}

_DERNIER_APPEL_SPORTSDB = [0.0]
DELAI_MIN_ENTRE_APPELS_SPORTSDB = 0.3  # secondes entre deux appels, pour rester sous la
# limite de débit de l'offre gratuite TheSportsDB (déclenchée dans le passé quand tous
# les appels d'un run partaient sans aucun espacement).

def requete_api_avec_retry(url, tentatives=3, delai=1.5):
    """GET vers TheSportsDB avec espacement global entre appels (throttling) et
    nouvelles tentatives en cas d'indisponibilite ponctuelle (503, frequent sur l'offre
    gratuite) ou de limitation de debit (429, respecte l'en-tete Retry-After si present).
    Point de passage unique pour tous les appels a l'API : ne pas utiliser requests.get
    directement ailleurs, sous peine de recreer le probleme de sur-appel."""
    for tentative in range(tentatives):
        attente = DELAI_MIN_ENTRE_APPELS_SPORTSDB - (time.monotonic() - _DERNIER_APPEL_SPORTSDB[0])
        if attente > 0:
            time.sleep(attente)
        response = requests.get(url, timeout=20)
        _DERNIER_APPEL_SPORTSDB[0] = time.monotonic()

        if response.status_code == 429:
            if tentative == tentatives - 1:
                return response
            try:
                attente_429 = float(response.headers.get("Retry-After", delai * (tentative + 1) * 3))
            except ValueError:
                attente_429 = delai * (tentative + 1) * 3
            time.sleep(attente_429)
            continue
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

# Cache mémoire des fichiers JSON volumineux (season, championnats, historique des qualifs) :
# sans ça, chaque requête re-parse plusieurs Mo depuis le disque (l'ouverture d'une fiche de
# match en relit ~9 Mo rien que pour regrouper les matchs de la semaine). Invalidé
# automatiquement dès que le fichier change sur disque (mtime + taille), donc transparent
# vis-à-vis du rafraîchissement quotidien et des `git pull`.
_cache_memoire_json = {}

def _lire_json_memoise(fichier):
    try:
        st = os.stat(fichier)
    except OSError:
        return None
    signature = (st.st_mtime_ns, st.st_size)
    entree = _cache_memoire_json.get(fichier)
    if entree is not None and entree[0] == signature:
        return entree[1]
    try:
        with open(fichier, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return None
    _cache_memoire_json[fichier] = (signature, data)
    return data

def charger_cache_memoise(fichier):
    """Comme `charger_cache` mais en gardant le contenu parsé en mémoire tant que le fichier
    sur disque est inchangé. Réservé aux fichiers volumineux relus en lecture seule."""
    cache = _lire_json_memoise(fichier)
    if isinstance(cache, dict) and cache.get("date") == str(date.today()):
        return cache.get("data")
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

def _injecter_predictions_ml(match_data):
    """Ajoute les probabilites du modele d'apprentissage (probaML*) et celles de
    l'ensemble (probaEns*). Import paresseux : scikit-learn n'est charge que si une
    fiche de match est reellement consultee. Toute erreur est silencieuse - la
    fiche reste utilisable avec le seul modele de rating."""
    if "probaMLVictoireDomicile" in match_data:
        return
    try:
        from predictions_ml import predire_match_ml, ensemble_probas
        p_ml = predire_match_ml(match_data)
    except Exception:
        return
    match_data["probaMLVictoireDomicile"] = p_ml["probaVictoireDomicile"]
    match_data["probaMLNul"] = p_ml["probaNul"]
    match_data["probaMLVictoireExterieure"] = p_ml["probaVictoireExterieure"]
    match_data["lambdaMLDomicile"] = p_ml.get("lambdaDomicile")
    match_data["lambdaMLExterieure"] = p_ml.get("lambdaExterieure")

    rating = {
        "probaVictoireDomicile": match_data.get("probaVictoireDomicile"),
        "probaNul": match_data.get("probaNul"),
        "probaVictoireExterieure": match_data.get("probaVictoireExterieure"),
    }
    ens = ensemble_probas(rating, p_ml)
    if ens:
        match_data["probaEnsVictoireDomicile"] = ens["probaVictoireDomicile"]
        match_data["probaEnsNul"] = ens["probaNul"]
        match_data["probaEnsVictoireExterieure"] = ens["probaVictoireExterieure"]


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
    else:
        return

    _injecter_predictions_ml(match_data)

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

    est_jour_releve_complet = (
        aujourd_hui.weekday() in JOURS_RELEVE_COMPLET
        and cache.get("dernier_releve_complet") != cle_jour
    )
    peut_relancer = not est_jour_releve_complet and bool(cache.get("dernier_releve_complet"))

    # La plupart des jours, aucune interrogation de The Odds API n'est possible : on relit
    # alors juste le cache sans reconstruire la liste des matchs de la semaine (qui parse
    # plusieurs Mo de JSON).
    if not est_jour_releve_complet and not peut_relancer:
        return cache.get("data", {})

    matchs_semaine = (
        filtrer_matchs_semaine(obtenir_matchs_a_venir())
        + filtrer_matchs_semaine(obtenir_matchs_championnats_a_venir())
    )
    matchs_par_ligue = _grouper_matchs_par_ligue(matchs_semaine)

    a_interroger = {}

    if est_jour_releve_complet:
        a_interroger = ODDS_API_SPORT_KEYS
        cache["dernier_releve_complet"] = cle_jour
    elif peut_relancer:
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
        resp = requete_api_avec_retry(url)
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
        resp = requete_api_avec_retry(url_equipe)
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
                resp_classement = requete_api_avec_retry(url_classement)
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

def charger_historique_championnat(league_id, cache_historique):
    """Tous les matchs déjà joués d'un championnat national, sur les saisons passées
    suivies et la saison en cours."""
    if league_id in cache_historique:
        return cache_historique[league_id]

    matchs = []
    for season in saisons_passees_ligue(league_id) + [saison_actuelle_ligue(league_id)]:
        url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={season}"
        try:
            resp = requete_api_avec_retry(url)
            resp.raise_for_status()
            for m in resp.json().get("events", []) or []:
                if m.get("intHomeScore") is None or m.get("intAwayScore") is None:
                    continue
                matchs.append(m)
        except requests.exceptions.RequestException:
            continue

    cache_historique[league_id] = matchs
    return matchs

def calculer_classements_saison(league_id, league_name, season, matchs_ligue,
                                vues=("general", "domicile", "exterieur"),
                                ecarter_invites=True):
    """Reconstruit le classement d'un championnat pour une saison, uniquement à partir des
    résultats de matchs, dans les déclinaisons demandées : `general`, `domicile` (points
    pris à domicile seulement) et `exterieur`.

    Noms d'équipe et badges viennent des matchs eux-mêmes ; les zones (Ligue des champions,
    relégation…) sont déduites du rang au classement général via `ZONES_CHAMPIONNAT`. L'ordre
    en cas d'égalité de points (Pts, puis différence de buts, puis buts marqués) est une
    approximation : les vrais départages varient selon les pays."""
    def journee_reguliere(m):
        # TheSportsDB numérote les barrages / play-offs de fin de saison avec des `intRound`
        # élevés (125, 160, 180, 200…) : on ne garde que les journées de championnat.
        try:
            return int(m.get("intRound")) < 100
        except (TypeError, ValueError):
            return True

    matchs_saison = sorted(
        (m for m in (matchs_ligue or [])
         if m.get("strSeason") == season
         and m.get("intHomeScore") is not None and m.get("intAwayScore") is not None
         and journee_reguliere(m)),
        key=lambda m: m.get("dateEvent") or ""
    )

    tables = {cle: {} for cle in vues}

    def ligne_equipe(table, team_id, nom, badge):
        l = table.get(team_id)
        if l is None:
            l = table[team_id] = {
                "idTeam": team_id,
                "strTeam": nom or team_id,
                "strBadge": badge or "",
                "strDescription": None,
                "intPlayed": 0, "intWin": 0, "intDraw": 0, "intLoss": 0,
                "intGoalsFor": 0, "intGoalsAgainst": 0, "_form": [],
            }
        else:
            if nom:
                l["strTeam"] = nom
            if badge:
                l["strBadge"] = badge
        return l

    for m in matchs_saison:
        dom, ext = str(m.get("idHomeTeam")), str(m.get("idAwayTeam"))
        try:
            bd, be = int(m["intHomeScore"]), int(m["intAwayScore"])
        except (TypeError, ValueError, KeyError):
            continue

        for cle, tid, nom, badge, marques, encaisses in (
            ("general", dom, m.get("strHomeTeam"), m.get("strHomeTeamBadge"), bd, be),
            ("general", ext, m.get("strAwayTeam"), m.get("strAwayTeamBadge"), be, bd),
            ("domicile", dom, m.get("strHomeTeam"), m.get("strHomeTeamBadge"), bd, be),
            ("exterieur", ext, m.get("strAwayTeam"), m.get("strAwayTeamBadge"), be, bd),
        ):
            if cle not in tables:
                continue
            l = ligne_equipe(tables[cle], tid, nom, badge)
            l["intPlayed"] += 1
            l["intGoalsFor"] += marques
            l["intGoalsAgainst"] += encaisses
            if marques > encaisses:
                l["intWin"] += 1
                l["_form"].append("W")
            elif marques < encaisses:
                l["intLoss"] += 1
                l["_form"].append("L")
            else:
                l["intDraw"] += 1
                l["_form"].append("D")

    # `eventsseason` d'un championnat inclut parfois les barrages d'accession/relégation :
    # on écarte alors les invités (une ou deux rencontres seulement) qui, sinon, gonfleraient
    # l'effectif et fausseraient la zone de relégation. Sur la saison en cours, tout le monde
    # a joué un nombre de matchs voisin : personne n'est écarté.
    if ecarter_invites and tables.get("general"):
        seuil = max(t["intPlayed"] for t in tables["general"].values()) * 0.5
        valides = {tid for tid, t in tables["general"].items() if t["intPlayed"] >= seuil}
        for table in tables.values():
            for tid in [t for t in table if t not in valides]:
                del table[tid]

    resultat = {}
    for cle, table in tables.items():
        lignes = list(table.values())
        for l in lignes:
            l["intGoalDifference"] = l["intGoalsFor"] - l["intGoalsAgainst"]
            l["intPoints"] = l["intWin"] * 3 + l["intDraw"]
            l["strForm"] = "".join(l.pop("_form")[-5:])
        lignes.sort(key=lambda l: (-l["intPoints"], -l["intGoalDifference"],
                                   -l["intGoalsFor"], (l["strTeam"] or "").lower()))
        for i, l in enumerate(lignes, 1):
            l["intRank"] = i
            l["strLeague"] = league_name
            l["strSeason"] = season
            # Les zones (pastille de couleur) ne sont posées que sur le classement général :
            # les décliner sur le rang partiel domicile/extérieur induirait en erreur.
            if cle == "general":
                l["strDescription"] = zone_championnat(league_id, i, len(lignes))
            # La plateforme renvoyait ces champs en chaînes : on garde le même format pour
            # que le front n'ait rien à adapter.
            for champ in ("intRank", "intPlayed", "intWin", "intDraw", "intLoss",
                          "intGoalsFor", "intGoalsAgainst", "intGoalDifference", "intPoints"):
                l[champ] = str(l[champ])
        resultat[cle] = lignes
    return resultat

def obtenir_derniers_matchs_championnat(team_id, league_id, league_name, avant_date, cache_historique, limite=5):
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

    # Le classement d'une saison ne dépend que de ses matchs : on le calcule une fois par
    # saison rencontrée plutôt qu'à chaque adversaire.
    tables_par_saison = {}

    def table_saison(season):
        if season not in tables_par_saison:
            tables_par_saison[season] = calculer_classements_saison(
                league_id, league_name, season, matchs_ligue, vues=("general",)
            )["general"]
        return tables_par_saison[season]

    resultat = []
    for m in matchs_equipe[:limite]:
        est_domicile = m.get("idHomeTeam") == team_id
        id_adversaire = m.get("idAwayTeam") if est_domicile else m.get("idHomeTeam")
        saison_match = m.get("strSeason")
        table = table_saison(saison_match)
        ligne_adv = next((l for l in table if l.get("idTeam") == str(id_adversaire)), None)

        copie = dict(m)
        copie["classementAdversaire"] = {
            "position": int(ligne_adv["intRank"]),
            "total": len(table),
            "saison": saison_match,
            "ligue": league_name,
        } if ligne_adv else None
        resultat.append(copie)

    return resultat

def obtenir_matchs_a_venir():
    """Tous les matchs de la saison en cours des 3 competitions europeennes
    (pas seulement ceux de la semaine), avec mise en cache quotidienne."""
    matchs = charger_cache_memoise(CACHE_SEASON_FILE)

    if matchs is None:
        matchs = []
        for league_id in LEAGUE_IDS:
            url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={SEASON}"
            try:
                response = requete_api_avec_retry(url)
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
    matchs = charger_cache_memoise(CACHE_CHAMPIONNAT_SEASON_FILE)

    if matchs is None:
        matchs = []
        for league_id in DOMESTIC_LEAGUES:
            url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={saison_actuelle_ligue(league_id)}"
            try:
                response = requete_api_avec_retry(url)
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

    nom_ligue = DOMESTIC_LEAGUES[league_id]
    saison_actuelle = saison_actuelle_ligue(league_id)
    saison_precedente = saisons_passees_ligue(league_id)[-1]

    cache_historique = charger_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE) or {}
    deja_en_cache = league_id in cache_historique
    matchs_ligue = charger_historique_championnat(league_id, cache_historique)
    if not deja_en_cache:
        sauvegarder_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE, cache_historique)

    return {
        "ligue": nom_ligue,
        "saisonActuelle": {
            "saison": saison_actuelle,
            **calculer_classements_saison(league_id, nom_ligue, saison_actuelle, matchs_ligue),
        },
        "saisonPrecedente": {
            "saison": saison_precedente,
            **calculer_classements_saison(league_id, nom_ligue, saison_precedente, matchs_ligue),
        },
    }

def isoler_phase_de_ligue(matchs):
    """À partir de tous les matchs d'une compétition européenne sur une saison, ne garde que
    ceux de la phase de ligue (ex-phase de poules).

    Depuis 2024-2025 la phase de ligue est un mini-championnat à 36 équipes. On l'isole ainsi :
    les équipes de la 4e journée (`intRound == 4`, toujours purement phase de ligue) donnent
    la liste des 36 participants ; la phase de ligue est alors l'ensemble des matchs des
    journées 1 à 8 opposant deux participants (un tour de qualification implique forcément au
    moins un club qui n'accède pas à la phase de ligue)."""
    participants = {
        equipe
        for m in matchs if str(m.get("intRound")) == "4"
        for equipe in (m.get("idHomeTeam"), m.get("idAwayTeam"))
        if equipe
    }
    if not participants:
        return []
    journees = {"1", "2", "3", "4", "5", "6", "7", "8"}
    return [
        m for m in matchs
        if str(m.get("intRound")) in journees
        and m.get("idHomeTeam") in participants
        and m.get("idAwayTeam") in participants
    ]

@app.get("/api/competitions/classement/{league_id}")
def get_classement_competition(league_id: str):
    if league_id not in COMPETITIONS_EUROPE:
        raise HTTPException(status_code=404, detail="Compétition inconnue")

    nom = COMPETITIONS_EUROPE[league_id]
    saison_precedente = PAST_SEASONS[-1]

    matchs_actuels = [m for m in obtenir_matchs_a_venir() if m.get("idLeague") == league_id]
    # La saison précédente est déjà dans le cache quotidien de l'historique européen :
    # aucun appel API supplémentaire.
    historique = obtenir_historique_qualifications()
    matchs_precedents = [
        m for m in historique
        if m.get("idLeague") == league_id and m.get("strSeason") == saison_precedente
    ]

    return {
        "ligue": nom,
        "saisonActuelle": {
            "saison": SEASON,
            **calculer_classements_saison(league_id, nom, SEASON,
                                          isoler_phase_de_ligue(matchs_actuels),
                                          ecarter_invites=False),
        },
        "saisonPrecedente": {
            "saison": saison_precedente,
            **calculer_classements_saison(league_id, nom, saison_precedente,
                                          isoler_phase_de_ligue(matchs_precedents),
                                          ecarter_invites=False),
        },
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
        besoin_rating = "probaVictoireDomicile" not in match_data
        besoin_ml = ("probaVictoireDomicile" in match_data
                     and "probaMLVictoireDomicile" not in match_data)
        if besoin_rating or besoin_ml:
            cache_championnat_historique = charger_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE) or {}
            cles_avant = set(cache_championnat_historique)
            if besoin_rating:
                injecter_predictions(match_data, cache_championnat_historique)
            else:
                _injecter_predictions_ml(match_data)
            # Pour un match europeen, `injecter_predictions` ne touche pas ce cache : on evite
            # alors de reecrire 1 Mo de JSON pour rien.
            if set(cache_championnat_historique) != cles_avant:
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
                nom_ligue = DOMESTIC_LEAGUES[id_ligue]
                date_match = match_data.get("dateEvent", "")

                match_data["historiqueDomicile"] = obtenir_derniers_matchs_championnat(
                    match_data.get("idHomeTeam"), id_ligue, nom_ligue, date_match,
                    cache_championnat_historique
                )
                match_data["historiqueExterieur"] = obtenir_derniers_matchs_championnat(
                    match_data.get("idAwayTeam"), id_ligue, nom_ligue, date_match,
                    cache_championnat_historique
                )

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
def get_paris(modele: str = "rating"):
    """Journal des paris "value" repere par bilan_paris.py (execute chaque matin via GitHub
    Actions), le plus recent en premier. `modele` : rating (defaut), ml ou ensemble - un
    journal distinct par modele de probabilite, pour comparer leurs performances."""
    fichier = FICHIERS_PARIS.get(modele)
    if fichier is None:
        raise HTTPException(status_code=404, detail="Modele de paris inconnu")
    bilan = charger_cache_permanent(fichier)
    if not isinstance(bilan, list):
        bilan = []
    analyses = charger_cache_permanent(CACHE_PARIS_ANALYSES_FILE)
    nb_analyses = sum(analyses.values()) if isinstance(analyses, dict) else 0
    return {
        "paris": sorted(bilan, key=lambda p: p.get("date", ""), reverse=True),
        "matchsAnalyses": nb_analyses,
    }

def obtenir_historique_qualifications():
    """Historique complet (3 dernieres saisons + saison en cours deja jouee)
    des matchs de qualification/groupe/finale des 3 competitions europeennes,
    avec pays de chaque equipe injecte. Mise en cache quotidienne."""
    historique = charger_cache_memoise(CACHE_HISTORY_FILE)
    cache_teams = charger_cache_permanent(CACHE_TEAMS_FILE)
    teams_updated = False

    if historique is None:
        historique = []
        equipes_uniques = set()
        
        for league_id in LEAGUE_IDS:
            for season in PAST_SEASONS + [SEASON]:
                url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={league_id}&s={season}"
                try:
                    response = requete_api_avec_retry(url)
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
                    resp = requete_api_avec_retry(url)
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