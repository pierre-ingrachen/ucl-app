"""Recuperation des cotes des matchs suivis (via The Odds API), par ordre de preference
Winamax puis Betclic puis Unibet.

Une seule requete par competition suffit : The Odds API renvoie en un appel tous les matchs
a venir d'une competition, pas match par match (le cout de quota est de 1 credit par
region x marche demande, quel que soit le nombre de matchs renvoyes). Le rythme d'appel
(une fois par semaine, le lundi) est gere par l'appelant (`main.obtenir_cotes_semaine`) ;
ce module se contente d'aller chercher les cotes et de les associer aux matchs internes.
"""

import unicodedata
from difflib import SequenceMatcher

import requests

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
# Ordre de preference : Winamax d'abord, puis Betclic, puis Unibet si aucun des deux premiers
# n'a de cote sur le match (delai de synchronisation frequent sur les petites competitions).
BOOKMAKERS_PRIORITE = ["winamax_fr", "betclic_fr", "unibet_fr"]
NOMS_BOOKMAKERS = {"winamax_fr": "Winamax", "betclic_fr": "Betclic", "unibet_fr": "Unibet"}
SEUIL_SIMILARITE_NOM = 0.6

MOTS_IGNORES_NOM_CLUB = {"fc", "cf", "sc", "ac", "afc", "cfc", "club", "cd", "ss", "us", "ud", "sk", "fk"}


def _normaliser_nom(nom):
    """Normalise un nom d'equipe pour comparaison entre fournisseurs de donnees differents
    (accents, casse, sigles de club type FC/CF qui varient d'une source a l'autre)."""
    nom = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode("ascii").lower()
    mots = [m for m in nom.split() if m not in MOTS_IGNORES_NOM_CLUB]
    return "".join(mots)


def _similaire(a, b):
    return SequenceMatcher(None, _normaliser_nom(a), _normaliser_nom(b)).ratio()


def recuperer_cotes_sport(sport_key, api_key):
    """Cotes 1X2 de tous les matchs a venir d'une competition The Odds API, en un seul appel
    (les 3 bookmakers de `BOOKMAKERS_PRIORITE` sont demandes ensemble : ca ne coute pas plus
    cher, le cout depend du nombre de marches x regions, pas du nombre de bookmakers). Ne
    leve jamais : liste vide en cas d'erreur reseau, de cle invalide ou de quota epuise (les
    problemes de credit se gerent en amont, pas ici). Renvoie aussi le quota restant
    (en-tetes de reponse), pour pouvoir le surveiller sans requete dediee."""
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds/"
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h",
        "bookmakers": ",".join(BOOKMAKERS_PRIORITE),
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return [], None
        quota = {
            "restant": resp.headers.get("x-requests-remaining"),
            "utilise": resp.headers.get("x-requests-used"),
        }
        return resp.json() or [], quota
    except requests.exceptions.RequestException:
        return [], None


def _meilleure_correspondance(match_odds, matchs_internes_meme_jour):
    """Associe un match The Odds API a un match interne : meme date deja filtree en amont,
    puis meilleure similarite de nom sur le domicile ET l'exterieur (les identifiants de match
    ne sont jamais partages entre fournisseurs, donc l'appariement se fait par nom+date)."""
    meilleur, meilleur_score = None, 0.0
    for m in matchs_internes_meme_jour:
        score = min(
            _similaire(match_odds.get("home_team", ""), m.get("strHomeTeam", "")),
            _similaire(match_odds.get("away_team", ""), m.get("strAwayTeam", "")),
        )
        if score > meilleur_score:
            meilleur, meilleur_score = m, score
    return meilleur if meilleur_score >= SEUIL_SIMILARITE_NOM else None


def associer_cotes(matchs_odds_api, matchs_internes):
    """Associe chaque match renvoye par The Odds API a un match interne, et en extrait les
    cotes 1X2 du premier bookmaker disponible dans `BOOKMAKERS_PRIORITE` (Winamax, sinon
    Betclic, sinon Unibet). Un match sans correspondance fiable est ignore ; en revanche un
    match reconnu mais sans aucun des 3 bookmakers est tout de meme enregistre (bookmaker a
    None), pour que l'absence de cote soit affichee explicitement plutot que silencieuse."""
    par_date = {}
    for m in matchs_internes:
        par_date.setdefault(m.get("dateEvent"), []).append(m)

    resultat = {}
    for mo in matchs_odds_api:
        date_odds = (mo.get("commence_time") or "")[:10]
        match_interne = _meilleure_correspondance(mo, par_date.get(date_odds, []))
        if not match_interne:
            continue

        cotes = {"bookmaker": None, "domicile": None, "nul": None, "exterieure": None}

        for cle_bookmaker in BOOKMAKERS_PRIORITE:
            bookmaker = next((b for b in mo.get("bookmakers", []) if b.get("key") == cle_bookmaker), None)
            if not bookmaker:
                continue
            marche = next((mk for mk in bookmaker.get("markets", []) if mk.get("key") == "h2h"), None)
            if not marche:
                continue

            cotes = {"bookmaker": NOMS_BOOKMAKERS[cle_bookmaker], "domicile": None, "nul": None, "exterieure": None}
            for issue in marche.get("outcomes", []):
                if issue.get("name") == mo.get("home_team"):
                    cotes["domicile"] = issue.get("price")
                elif issue.get("name") == mo.get("away_team"):
                    cotes["exterieure"] = issue.get("price")
                elif issue.get("name") == "Draw":
                    cotes["nul"] = issue.get("price")
            break

        resultat[match_interne["idEvent"]] = cotes

    return resultat


def recuperer_toutes_les_cotes(mapping_ligues, matchs_par_ligue, api_key):
    """Une requete par cle de competition The Odds API (jamais une requete par match, et
    aucune requete pour une competition sans match cette semaine), puis association aux
    matchs internes. `mapping_ligues` associe chaque identifiant de ligue interne
    (TheSportsDB) a la ou les cles de competition The Odds API correspondantes. Renvoie
    (cotes, dernier_quota_connu)."""
    resultat = {}
    dernier_quota = None
    for id_ligue, sport_keys in mapping_ligues.items():
        matchs_internes = matchs_par_ligue.get(id_ligue, [])
        if not matchs_internes:
            continue
        for sport_key in sport_keys:
            matchs_odds_api, quota = recuperer_cotes_sport(sport_key, api_key)
            if quota:
                dernier_quota = quota
            resultat.update(associer_cotes(matchs_odds_api, matchs_internes))
    return resultat, dernier_quota
