from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
import requests
from datetime import datetime, timedelta, date
import hashlib
import json
import os
import re
import time

from dotenv import load_dotenv

from calendrier.base import Base
from calendrier.logos import nom_fichier_badge

load_dotenv()

def _variable_environnement_requise(nom):
    """Cle API lue depuis l'environnement (.env en local, secret GitHub Actions en CI) :
    jamais en dur dans le code, pour ne pas finir dans l'historique Git."""
    valeur = os.environ.get(nom)
    if not valeur:
        raise RuntimeError(f"Variable d'environnement '{nom}' manquante (voir .env.example).")
    return valeur

# Mode hors ligne (commande `ucl-1510`) : aucun appel reseau, les caches sont servis meme
# s'ils datent de la veille, et rien n'est reecrit sur disque. Prepare par preparer_hors_ligne.py.
# Seul l'onglet Championnats (Top 5 + 6-10) est servi, limite aux matchs de ces dates
# (separees par des virgules) ; les autres onglets renvoient des listes vides.
HORS_LIGNE = os.environ.get("UCL_HORS_LIGNE") == "1"
DATES_HORS_LIGNE = os.environ.get("UCL_DATES", "2026-10-16,2026-10-17,2026-10-18").split(",")
LIGUES_HORS_LIGNE = ["4328", "4335", "4331", "4332", "4334",   # Top 5
                     "4338", "4337", "4344", "4339", "4422"]   # 6-10
# Base locale (calendrier/base/) : evenements, clubs, classements nationaux et logos de TOUTES les saisons
# affichees par le site. Remplace TheSportsDB (voir calendrier/README.md) ; mise a jour par le workflow.
BASE = Base()
# Logos stockes dans la base, servis sous /badges/ (voir `localiser_badges`).
DOSSIER_BADGES = os.path.join(BASE.racine, "badges")
# Logos TheSportsDB, et logos ESPN (clubs absents de l'annuaire TheSportsDB, cf. calendrier/).
RE_URL_BADGE = re.compile(r'https://[a-z0-9.]*thesportsdb\.com/images/media/(?:team|league)/badge/[^"\\\s]+'
                          r'|https://a\.espncdn\.com/i/teamlogos/soccer/\d+/\d+\.png')

app = FastAPI(title="Champions League API")

@app.middleware("http")
async def localiser_badges(request: Request, call_next):
    """Remplace les URLs de logos distantes (TheSportsDB, ESPN) par leur copie locale (/badges/...) quand
    elle existe dans la base. Declare avant le GZip pour voir le JSON en clair."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        return response
    corps = b"".join([morceau async for morceau in response.body_iterator]).decode("utf-8")
    # Derriere un proxy (Render), le schema et l'hote d'origine sont dans les en-tetes X-Forwarded-*.
    schema = request.headers.get("x-forwarded-proto") or request.url.scheme
    hote = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    racine = f"{schema}://{hote}/badges/"

    def remplacer(m):
        nom = nom_fichier_badge(m.group(0))
        if os.path.exists(os.path.join(DOSSIER_BADGES, nom)):
            return racine + nom
        return m.group(0)

    en_tetes = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    return Response(RE_URL_BADGE.sub(remplacer, corps), status_code=response.status_code,
                    headers=en_tetes, media_type=response.media_type)

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

app.mount("/badges", StaticFiles(directory=DOSSIER_BADGES, check_dir=False), name="badges")

LEAGUE_IDS = ["4480", "4481", "5071"]  # UEFA Champions League, UEFA Europa League, UEFA Conference League
COMPETITIONS_EUROPE = {
    "4480": "UEFA Champions League",
    "4481": "UEFA Europa League",
    "5071": "UEFA Conference League",
}
SEASON = "2026-2027"
PAST_SEASONS = ["2023-2024", "2024-2025", "2025-2026"]
# Saisons européennes masquées de l'historique affiché sur le site (mais gardées en cache
# pour les modèles de prédiction). 2023-2024, dernière saison au format « phases de poules »,
# n'a pas de classement unique à 36 comparable aux saisons suivantes ; ses matchs restent
# malgré tout affichés, classementHome/classementAway valant simplement null.
SAISONS_HISTORIQUE_MASQUEES = set()

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

CACHE_DETAILS_FILE = "cache_details.json"
FICHIER_PARIS_RESEAU = "cache_paris_reseau.json"
FICHIER_ANALYSES_RESEAU = "cache_analyses_reseau.json"
def charger_cache_permanent(fichier):
    if os.path.exists(fichier):
        try:
            with open(fichier, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {}

def sauvegarder_cache_permanent(fichier, data):
    if HORS_LIGNE:
        return
    try:
        with open(fichier, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
    except: pass

def charger_cache(fichier):
    aujourd_hui_str = str(date.today())
    if os.path.exists(fichier):
        try:
            with open(fichier, "r", encoding="utf-8") as f:
                cache = json.load(f)
                if HORS_LIGNE or cache.get("date") == aujourd_hui_str:
                    return cache.get("data")
        except (json.JSONDecodeError, IOError):
            pass
    return None

def sauvegarder_cache(fichier, data):
    if HORS_LIGNE:
        return
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

# Pays forcés pour certaines équipes (l'API renvoie un pays inexact ou "Monaco" / "England")
CORRECTIONS_PAYS = {
    "133823": "France",  # AS Monaco, comptée comme équipe française
    "134312": "Wales",   # The New Saints (TNS), comptée comme équipe galloise
}

def obtenir_pays_equipe(team_id, cache_teams=None):
    """Pays d'une equipe, lu dans la base locale (releve TheSportsDB du snapshot, puis pays de la ligue pour
    les clubs ajoutes depuis). `cache_teams` n'est plus utilise (signature conservee)."""
    if not team_id:
        return ""
    return CORRECTIONS_PAYS.get(team_id) or BASE.pays(team_id)

def _ligue_suivie_du_club(team_id):
    """Id du championnat suivi (DOMESTIC_LEAGUES) dans lequel le club joue la saison en cours, d'apres les
    matchs de la base ; sinon son championnat national releve par TheSportsDB s'il est suivi ; sinon None."""
    for league_id in DOMESTIC_LEAGUES:
        if any(team_id in (m.get("idHomeTeam"), m.get("idAwayTeam"))
               for m in BASE.evenements_saison(league_id, saison_actuelle_ligue(league_id))):
            return league_id
    ligue = BASE.ligue_nationale(team_id)
    return ligue["id"] if ligue and ligue["id"] in DOMESTIC_LEAGUES else None

def obtenir_classement_national(team_id, cache_classement=None):
    """Position du club dans son championnat national (ex: 2e / 12) pour la saison en cours, sinon la
    precedente (la saison affichee le precise).

    - championnat suivi (20 pays) : classement RECALCULE depuis les resultats de la base (meme methode que
      le classement affiche par le site) ;
    - autre championnat (Kazakhstan, Israel...) : table figee au snapshot TheSportsDB (`maj` = date du releve) ;
    - club inconnu : None.
    `cache_classement` n'est plus utilise (signature conservee)."""
    if not team_id:
        return None
    team_id = str(team_id)
    league_id = _ligue_suivie_du_club(team_id)
    if league_id is None:
        return BASE.classement_national_gele(team_id)
    nom_ligue = (BASE.ligue_nationale(team_id) or {}).get("nom") or DOMESTIC_LEAGUES[league_id]
    for saison in (saison_actuelle_ligue(league_id), saisons_passees_ligue(league_id)[-1]):
        table = calculer_classements_saison(league_id, nom_ligue, saison, BASE.evenements_saison(league_id, saison),
                                            vues=("general",))["general"]
        ligne = next((l for l in table if l.get("idTeam") == team_id), None)
        if ligne:
            return {"position": int(ligne["intRank"]), "total": len(table), "saison": saison,
                    "ligue": nom_ligue, "maj": str(date.today())}
    return None

SEUIL_COTE_ELEVEE = 3.50
CACHE_COTES_FILE = "cache_cotes_winamax.json"

def marquer_cotes_elevees(matchs):
    """Ajoute `coteTrouvee` (une cote bookmaker est connue) et `coteElevee` a chaque match : True si la victoire de l'equipe 1 ou de l'equipe 2
    est cotee >= 3.50 (nul ignore). Sans cote connue, False. Les cotes elles-memes ne sont
    jamais renvoyees au front. Travaille sur des copies (les listes viennent d'un cache memoise)."""
    cotes = (_lire_json_ou_defaut(CACHE_COTES_FILE, {}) or {}).get("data", {})
    resultat = []
    for m in matchs:
        c = cotes.get(str(m.get("idEvent"))) or {}
        elevee = any((c.get(cle) or 0) >= SEUIL_COTE_ELEVEE for cle in ("domicile", "exterieure"))
        resultat.append({**m, "coteElevee": elevee, "coteTrouvee": bool(c.get("bookmaker"))})
    return resultat

JOURS_AFFICHES = 8  # TEST (2026-11-13) : 8 jours au lieu de 7 ; remettre 7 apres le test

def filtrer_matchs_semaine(matchs):
    """Restreint une liste de matchs à ceux prévus entre aujourd'hui et dans JOURS_AFFICHES jours."""
    aujourd_hui = datetime.now()
    dans_7_jours = aujourd_hui + timedelta(days=JOURS_AFFICHES)
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

def charger_historique_championnat(league_id, cache_historique=None):
    """Tous les matchs deja joues d'un championnat national, sur les saisons passees suivies et la saison
    en cours, lus dans la base locale. `cache_historique` n'est plus utilise (signature conservee)."""
    return [m for saison in saisons_passees_ligue(league_id) + [saison_actuelle_ligue(league_id)]
            for m in BASE.evenements_saison(league_id, saison)
            if m.get("intHomeScore") is not None and m.get("intAwayScore") is not None]

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
    """Tous les matchs de la saison en cours des 3 competitions europeennes (pas seulement ceux de la
    semaine), depuis la base locale (mise a jour par le workflow quotidien)."""
    return [m for league_id in LEAGUE_IDS for m in BASE.evenements_saison(league_id, SEASON)]

# Calendrier en direct : ESPN avec The Odds API en secours (package `calendrier/`) ; en cas d'echec, la base locale.
DUREE_CACHE_SOURCE = 1200  # secondes : evite ~160 requetes ESPN a chaque affichage du site
_cache_source = {}

def matchs_semaine_via_source(ids_ligues):
    """Matchs des JOURS_AFFICHES prochains jours (et ceux deja joues aujourd'hui) via `calendrier/`, avec
    les identifiants et champs de la base locale ; None si la source est desactivee (mode hors ligne) ou
    injoignable (l'appelant retombe alors sur la base locale seule)."""
    if HORS_LIGNE:
        return None
    cle = (tuple(ids_ligues), date.today())
    en_cache = _cache_source.get(cle)
    if en_cache and time.monotonic() - en_cache[0] < DUREE_CACHE_SOURCE:
        return en_cache[1]
    try:
        from calendrier import source
        locaux = [e for i in ids_ligues
                  for e in BASE.evenements_saison(i, saison_actuelle_ligue(i) if i in DOMESTIC_LEAGUES else SEASON)]
        evenements, rapport = source.a_venir(date.today(), date.today() + timedelta(days=JOURS_AFFICHES), locaux,
                                             list(ids_ligues), inclure_joues=True)
    except Exception as exc:  # noqa: BLE001
        print(f"Calendrier ESPN/Odds API indisponible ({type(exc).__name__}: {exc}), base locale utilisee")
        return None
    if not any(rapport["sources"].values()):
        return None
    _cache_source[cle] = (time.monotonic(), evenements)
    return evenements

@app.get("/api/matchs/a-venir")
def get_matchs_a_venir():
    if HORS_LIGNE:
        return {"events": []}  # onglet non prepare en mode hors ligne
    via_source = matchs_semaine_via_source(list(COMPETITIONS_EUROPE))
    if via_source is not None:
        return {"events": marquer_cotes_elevees(via_source)}
    return {"events": marquer_cotes_elevees(filtrer_matchs_semaine(obtenir_matchs_a_venir()))}

def obtenir_matchs_championnats_a_venir():
    """Tous les matchs de la saison en cours des championnats nationaux suivis (pas seulement ceux de la
    semaine), depuis la base locale (mise a jour par le workflow quotidien)."""
    return [m for league_id in DOMESTIC_LEAGUES
            for m in BASE.evenements_saison(league_id, saison_actuelle_ligue(league_id))]

@app.get("/api/championnats/matchs/a-venir")
def get_matchs_championnats_a_venir():
    if not HORS_LIGNE:
        via_source = matchs_semaine_via_source(list(DOMESTIC_LEAGUES))
        if via_source is not None:
            return {"events": marquer_cotes_elevees(via_source)}
    matchs = obtenir_matchs_championnats_a_venir()

    if HORS_LIGNE:
        return {"events": marquer_cotes_elevees([m for m in matchs if m.get("dateEvent") in DATES_HORS_LIGNE
                                                 and m.get("idLeague") in LIGUES_HORS_LIGNE])}
    return {"events": marquer_cotes_elevees(filtrer_matchs_semaine(matchs))}

@app.get("/api/championnats/classement/{league_id}")
def get_classement_championnat(league_id: str):
    if league_id not in DOMESTIC_LEAGUES:
        raise HTTPException(status_code=404, detail="Championnat inconnu")

    nom_ligue = DOMESTIC_LEAGUES[league_id]
    saison_actuelle = saison_actuelle_ligue(league_id)
    saison_precedente = saisons_passees_ligue(league_id)[-1]
    matchs_ligue = charger_historique_championnat(league_id)

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

def _lire_json_ou_defaut(fichier, defaut):
    if not os.path.exists(fichier):
        return defaut
    with open(fichier, encoding="utf-8") as f:
        return json.load(f)

def _bilan_depuis_journal(journal, nb_analyses):
    """Bilan d'un journal de paris. Mise de chaque pari = 1 / cote : un pari gagne rapporte donc
    1 unite brute. ROI = gain net / mises resolues."""
    resolus = [p for p in journal if p["statut"] != "en_attente"]
    gain = sum(p["gain"] for p in resolus)
    mises = sum(p["mise"] for p in resolus)

    # Plusieurs issues d'un meme match (ex. exterieure + nul) comptent comme un seul pari.
    par_match = {}
    for p in journal:
        par_match.setdefault(p["idEvent"], []).append(p)
    groupes = []
    for legs in par_match.values():
        en_attente = any(l["statut"] == "en_attente" for l in legs)
        groupes.append({
            "idEvent": legs[0]["idEvent"], "date": legs[0]["date"],
            "equipeDomicile": legs[0]["equipeDomicile"], "equipeExterieur": legs[0]["equipeExterieur"],
            "legs": [{"issue": l["issue"], "coteBookmaker": l["coteBookmaker"], "mise": l["mise"]} for l in legs],
            "mise": round(sum(l["mise"] for l in legs), 4),
            "statut": "en_attente" if en_attente else "gagne" if any(l["statut"] == "gagne" for l in legs) else "perdu",
            "gain": None if en_attente else round(sum(l["gain"] for l in legs), 4),
            "source": legs[0].get("source", "direct"),
        })
    resolus_g = [g for g in groupes if g["statut"] != "en_attente"]
    return {
        "matchsAnalyses": nb_analyses,
        "paris": len(groupes),
        "parisGagnes": sum(g["statut"] == "gagne" for g in resolus_g),
        "parisPerdus": sum(g["statut"] == "perdu" for g in resolus_g),
        "parisEnAttente": len(groupes) - len(resolus_g),
        "gainUnites": round(gain, 2),
        "roi": gain / mises if mises else None,
        "detail": sorted(groupes, key=lambda g: g["date"], reverse=True),
    }

@app.get("/api/paris/bilan")
def get_bilan_paris():
    """Bilan des paris du reseau (journal tenu par paris_reseau.py)."""
    journal = _lire_json_ou_defaut(FICHIER_PARIS_RESEAU, [])
    return _bilan_depuis_journal(journal, len(_lire_json_ou_defaut(FICHIER_ANALYSES_RESEAU, {})))

DOSSIER_JOURNAUX_D = "modele_d/journaux"

@app.get("/api/paris/bilans")
def get_bilans_paris():
    """Bilan de chaque algorithme de paris. Le reseau de buts et le modele D (paris du jour) sont tenus
    en direct par paris_reseau.py ; le modele D et l'IA-optimisee ont aussi un rejeu des matchs
    2026-27 deja joues (modele_d/rejeu_2627.py : memes regles, sans fuite du futur, cotes Bet365
    cloture -5 % faute d'historique Winamax)."""
    meta = _lire_json_ou_defaut(f"{DOSSIER_JOURNAUX_D}/rejeu_2627_meta.json", {})
    rejeu = lambda nom: _lire_json_ou_defaut(f"{DOSSIER_JOURNAUX_D}/rejeu_2627_{nom}.json", [])
    note_rejeu = None
    analyses_rejeu = meta.get("analyses", {})
    d_analyses = _lire_json_ou_defaut(f"{DOSSIER_JOURNAUX_D}/analyses.json", {})
    algos = [
        ("reseau", "Réseau de buts", "Premier algorithme : réseau de neurones + loi de Poisson, cote > 4 et cote du modèle 15 % sous celle de Winamax.",
         rejeu("reseau") + _lire_json_ou_defaut(FICHIER_PARIS_RESEAU, []),
         analyses_rejeu.get("reseau", 0) + len(_lire_json_ou_defaut(FICHIER_ANALYSES_RESEAU, {})), None),
        ("modele_d", "Modèle D", "Prédit les cotes du marché à partir de la forme, Elo, buts et repos ; victoire extérieure à cote ]4 ; 6] si le modèle voit 20 % de valeur.",
         rejeu("modele_d") + _lire_json_ou_defaut(f"{DOSSIER_JOURNAUX_D}/paris.json", []), analyses_rejeu.get("modele_d", 0) + len(d_analyses), note_rejeu),
        ("ia_optimisee", "IA-optimisée", "Modèle dédié aux outsiders (cote > 4) : probabilité de victoire par boosting + régression, pari si p × cote − 1 dépasse une marge, plafond de cote choisi sur le passé.",
         rejeu("ia_optimisee") + _lire_json_ou_defaut("ia_optimisee/journaux/paris.json", []),
         analyses_rejeu.get("ia_optimisee", 0) + len(_lire_json_ou_defaut("ia_optimisee/journaux/analyses.json", {})), note_rejeu),
    ]
    sortie = []
    for id_, nom, description, journal, nb_analyses, note in algos:
        sortie.append({"id": id_, "nom": nom, "description": description, "note": note,
                       **_bilan_depuis_journal(journal, nb_analyses)})
    return {"algos": sortie}

@app.get("/api/match/{event_id}")
def get_match_details(event_id: str):
    cache_details = charger_cache(CACHE_DETAILS_FILE) or {}

    if event_id in cache_details:
        fiche = cache_details[event_id]
        # Le classement évolue : on le remet à jour même quand le reste de la fiche vient du cache.
        for cle, cle_equipe in (("classementDomicile", "idHomeTeam"), ("classementExterieur", "idAwayTeam")):
            nouveau = obtenir_classement_national(fiche.get(cle_equipe))
            if nouveau and nouveau != fiche.get(cle):
                fiche[cle] = nouveau
                cache_details[event_id] = fiche
                sauvegarder_cache(CACHE_DETAILS_FILE, cache_details)
        return fiche

    # Le match vient de la base locale ; un match tout juste apparu (pas encore ecrit dans la base par le
    # workflow quotidien) est retrouve dans le calendrier ESPN deja charge pour la liste.
    match_data = BASE.evenement(event_id) or next(
        (e for _, evenements in _cache_source.values() for e in evenements if str(e.get("idEvent")) == event_id), None)
    if not match_data:
        raise HTTPException(status_code=404, detail="Match introuvable")
    match_data = dict(match_data)

    match_data["strHomeCountry"] = obtenir_pays_equipe(match_data.get("idHomeTeam"))
    match_data["strAwayCountry"] = obtenir_pays_equipe(match_data.get("idAwayTeam"))
    match_data["strPhase"] = categoriser_phase(match_data)

    # Position en championnat national, pour toutes les compétitions
    match_data["classementDomicile"] = obtenir_classement_national(match_data.get("idHomeTeam"))
    match_data["classementExterieur"] = obtenir_classement_national(match_data.get("idAwayTeam"))

    # Pour un match de championnat national (onglet "Championnats") : les 5 derniers matchs de chaque équipe
    # dans cette compétition, avec le classement de l'adversaire lors de la saison où chacun a eu lieu.
    id_ligue = match_data.get("idLeague")
    if id_ligue in DOMESTIC_LEAGUES:
        nom_ligue = DOMESTIC_LEAGUES[id_ligue]
        date_match = match_data.get("dateEvent", "")
        match_data["historiqueDomicile"] = obtenir_derniers_matchs_championnat(
            match_data.get("idHomeTeam"), id_ligue, nom_ligue, date_match, None)
        match_data["historiqueExterieur"] = obtenir_derniers_matchs_championnat(
            match_data.get("idAwayTeam"), id_ligue, nom_ligue, date_match, None)

    cache_details[event_id] = match_data
    sauvegarder_cache(CACHE_DETAILS_FILE, cache_details)
    return match_data

_cache_historique_europe = {}

def obtenir_historique_qualifications():
    """Historique complet (3 dernieres saisons + saison en cours deja jouee) des matchs de
    qualification/groupe/finale des 3 competitions europeennes, avec pays de chaque equipe injecte, depuis la
    base locale. Memoise tant que les fichiers de la base ne changent pas."""
    signature = tuple(os.path.getmtime(BASE.chemin_saison(l, s)) if os.path.exists(BASE.chemin_saison(l, s)) else 0
                      for l in LEAGUE_IDS for s in PAST_SEASONS + [SEASON]) + (
        os.path.getmtime(os.path.join(BASE.racine, "equipes.json")) if os.path.exists(
            os.path.join(BASE.racine, "equipes.json")) else 0,)
    if _cache_historique_europe.get("signature") == signature:
        return _cache_historique_europe["historique"]

    historique = []
    for league_id in LEAGUE_IDS:
        for season in PAST_SEASONS + [SEASON]:
            for match in BASE.evenements_saison(league_id, season):
                # Pour la saison en cours, seuls les matchs deja joues comptent comme historique
                if season == SEASON and match.get("intHomeScore") is None:
                    continue
                match = dict(match)
                match["strPhase"] = categoriser_phase(match)
                match["strHomeCountry"] = obtenir_pays_equipe(match.get("idHomeTeam"))
                match["strAwayCountry"] = obtenir_pays_equipe(match.get("idAwayTeam"))
                historique.append(match)
    _cache_historique_europe.update(signature=signature, historique=historique)
    return historique

def enrichir_historique_pour_affichage(historique):
    """Prépare l'historique européen pour l'affichage du site :

    - écarte les saisons de `SAISONS_HISTORIQUE_MASQUEES` (elles restent dans
      `obtenir_historique_qualifications()`, donc disponibles pour les modèles de prédiction) ;
    - injecte, pour chaque match, la position de l'équipe à domicile (`classementHome`) et de
      l'équipe à l'extérieur (`classementAway`) au classement de phase de ligue de cette
      saison-là — même logique et même format que `classementAdversaire` côté championnat.
      `null` quand l'équipe n'est pas dans la phase de ligue (tour de qualification, invité,
      adversaire de phase finale)."""
    visibles = [m for m in historique
                if m.get("strSeason") not in SAISONS_HISTORIQUE_MASQUEES]

    # Le classement d'une phase de ligue ne dépend que de ses matchs : une table par
    # (compétition, saison) rencontrée, réutilisée pour tous les matchs concernés.
    tables = {}

    def table_phase_ligue(league_id, season):
        cle = (league_id, season)
        if cle not in tables:
            matchs_cs = [m for m in historique
                         if m.get("idLeague") == league_id and m.get("strSeason") == season]
            lignes = calculer_classements_saison(
                league_id, COMPETITIONS_EUROPE.get(league_id, ""), season,
                isoler_phase_de_ligue(matchs_cs), vues=("general",), ecarter_invites=False,
            )["general"]
            tables[cle] = ({l.get("idTeam"): l for l in lignes}, len(lignes))
        return tables[cle]

    resultat = []
    for m in visibles:
        copie = dict(m)
        par_equipe, total = table_phase_ligue(m.get("idLeague"), m.get("strSeason"))
        for cote in ("Home", "Away"):
            ligne = par_equipe.get(str(m.get(f"id{cote}Team")))
            copie[f"classement{cote}"] = {
                "position": int(ligne["intRank"]),
                "total": total,
            } if ligne else None
        resultat.append(copie)
    return resultat

@app.get("/api/matchs/historique-qualifications")
def get_historique_qualifications():
    return {"events": enrichir_historique_pour_affichage(obtenir_historique_qualifications())}