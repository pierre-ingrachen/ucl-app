"""Modele de probabilite de resultat pour les qualifications europeennes.

Approche en 3 etapes, sur l'historique des matchs (idHomeTeam/idAwayTeam,
scores, strHomeCountry/strAwayCountry) :

1. Regression ponderee (graphe pays) : chaque pays est un noeud, chaque match
   une arete ponderee par l'ecart de buts. Resout aussi un avantage du
   terrain global. Permet de comparer des equipes qui n'ont jamais joue
   l'une contre l'autre via des adversaires communs.
2. Regression a crete (ridge) par club sur les residus du graphe pays : un
   effet club qui vient nuancer le rating pays, avec retrait ("shrinkage")
   automatique vers 0 pour les clubs peu representes dans l'historique.
3. Regression logistique ordonnee (victoire domicile / nul / victoire
   exterieure) qui convertit l'ecart de force (etapes 1+2) en probabilites.

Chaque match est pondere par une decroissance exponentielle selon son
anciennete (demi-vie d'un an) : un match d'il y a 3 ans compte donc environ
8 fois moins qu'un match de la semaine derniere.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

HALF_LIFE_DAYS = 365.0
MAX_GOAL_DIFF = 5.0
LAMBDA_TEAM = 6.0
LAMBDA_CLUB_CHAMPIONNAT = 6.0


@dataclass
class ModeleRating:
    country_ratings: dict = field(default_factory=dict)
    team_effects: dict = field(default_factory=dict)
    home_advantage: float = 0.0
    beta: float = 1.0
    c: float = 0.5

    def rating_pays(self, pays):
        return self.country_ratings.get(pays, 0.0)

    def effet_club(self, team_id):
        return self.team_effects.get(team_id, 0.0)


def _poids_temporel(date_event_str, aujourd_hui=None):
    """Poids de decroissance exponentielle d'un match selon son anciennete."""
    if not date_event_str:
        return 0.0
    try:
        date_match = datetime.strptime(date_event_str, "%Y-%m-%d").date()
    except ValueError:
        return 0.0

    aujourd_hui = aujourd_hui or date.today()
    age_jours = (aujourd_hui - date_match).days
    if age_jours < 0:
        age_jours = 0
    return 0.5 ** (age_jours / HALF_LIFE_DAYS)


def _matchs_exploitables(historique):
    """Filtre et normalise les matchs utilisables pour l'entrainement :
    scores connus, equipes et pays renseignes, poids temporel non nul."""
    matchs = []
    for m in historique:
        home_score, away_score = m.get("intHomeScore"), m.get("intAwayScore")
        home_id, away_id = m.get("idHomeTeam"), m.get("idAwayTeam")
        home_pays, away_pays = m.get("strHomeCountry"), m.get("strAwayCountry")

        if home_score is None or away_score is None or not home_id or not away_id:
            continue
        try:
            diff = int(home_score) - int(away_score)
        except (TypeError, ValueError):
            continue

        poids = _poids_temporel(m.get("dateEvent"))
        if poids <= 0:
            continue

        matchs.append({
            "home_id": home_id,
            "away_id": away_id,
            "home_pays": home_pays or "",
            "away_pays": away_pays or "",
            "diff": max(-MAX_GOAL_DIFF, min(MAX_GOAL_DIFF, diff)),
            "poids": poids,
        })
    return matchs


def _regression_pays(matchs):
    """Ratings pays + avantage du terrain par regression lineaire ponderee.

    Chaque match oppposant deux pays differents ajoute une ligne au systeme
    ecart_buts = avantage_domicile + rating(pays_domicile) - rating(pays_exterieur).
    Resolu par moindres carres (numpy se charge de l'indetermination residuelle
    liee aux composantes du graphe non reliees entre elles)."""
    pays_utilises = sorted({m["home_pays"] for m in matchs if m["home_pays"] and m["home_pays"] != m["away_pays"]}
                            | {m["away_pays"] for m in matchs if m["away_pays"] and m["home_pays"] != m["away_pays"]})
    index_pays = {p: i for i, p in enumerate(pays_utilises)}
    n = len(pays_utilises)

    lignes = [m for m in matchs if m["home_pays"] and m["away_pays"] and m["home_pays"] != m["away_pays"]]
    if n == 0 or not lignes:
        return {}, 0.0

    X = np.zeros((len(lignes), n + 1))
    y = np.zeros(len(lignes))
    w = np.zeros(len(lignes))

    for i, m in enumerate(lignes):
        X[i, index_pays[m["home_pays"]]] = 1.0
        X[i, index_pays[m["away_pays"]]] = -1.0
        X[i, n] = 1.0  # colonne avantage du terrain (toujours du point de vue domicile)
        y[i] = m["diff"]
        w[i] = m["poids"]

    racine_w = np.sqrt(w)
    solution, *_ = np.linalg.lstsq(X * racine_w[:, None], y * racine_w, rcond=None)

    ratings = {pays: float(solution[i]) for pays, i in index_pays.items()}
    avantage_domicile = float(solution[n])
    return ratings, avantage_domicile


def _regression_clubs(matchs, country_ratings, avantage_domicile):
    """Effet club (ecart au rating pays) par regression a crete ponderee.

    La penalisation L2 (LAMBDA_TEAM) retrecit automatiquement l'effet des
    clubs peu representes dans l'historique vers 0 (i.e. vers le seul rating
    pays), et laisse les clubs bien representes s'en ecarter davantage :
    c'est le "shrinkage" du modele hierarchique."""
    equipes = sorted({m["home_id"] for m in matchs} | {m["away_id"] for m in matchs})
    index_equipe = {t: i for i, t in enumerate(equipes)}
    n = len(equipes)

    if n == 0:
        return {}

    X = np.zeros((len(matchs), n))
    y = np.zeros(len(matchs))
    w = np.zeros(len(matchs))

    for i, m in enumerate(matchs):
        X[i, index_equipe[m["home_id"]]] = 1.0
        X[i, index_equipe[m["away_id"]]] = -1.0
        rating_pays = country_ratings.get(m["home_pays"], 0.0) - country_ratings.get(m["away_pays"], 0.0)
        y[i] = m["diff"] - avantage_domicile - rating_pays
        w[i] = m["poids"]

    XtW = X.T * w
    A = XtW @ X + LAMBDA_TEAM * np.eye(n)
    b = XtW @ y
    solution = np.linalg.solve(A, b)

    return {equipe: float(solution[i]) for equipe, i in index_equipe.items()}


def _regression_ridge_avec_avantage(matchs, lambda_reg):
    """Comme `_regression_clubs`, mais a un seul niveau (pas de rating pays prealable) : sert
    aux championnats nationaux, ou toutes les equipes d'une meme ligue partagent deja le meme
    pays (un rating pays n'y apporterait aucune information). L'avantage du terrain est estime
    conjointement, dans la meme colonne non penalisee que dans `_regression_pays`."""
    equipes = sorted({m["home_id"] for m in matchs} | {m["away_id"] for m in matchs})
    index_equipe = {t: i for i, t in enumerate(equipes)}
    n = len(equipes)

    if n == 0:
        return {}, 0.0

    X = np.zeros((len(matchs), n + 1))
    y = np.zeros(len(matchs))
    w = np.zeros(len(matchs))

    for i, m in enumerate(matchs):
        X[i, index_equipe[m["home_id"]]] = 1.0
        X[i, index_equipe[m["away_id"]]] = -1.0
        X[i, n] = 1.0
        y[i] = m["diff"]
        w[i] = m["poids"]

    XtW = X.T * w
    penalites = np.full(n + 1, lambda_reg)
    penalites[n] = 0.0  # l'avantage du terrain n'est pas retreint vers 0
    A = XtW @ X + np.diag(penalites)
    b = XtW @ y
    solution = np.linalg.solve(A, b)

    ratings = {equipe: float(solution[i]) for equipe, i in index_equipe.items()}
    avantage_domicile = float(solution[n])
    return ratings, avantage_domicile


def _marge_predite(country_ratings, team_effects, avantage_domicile, home_id, away_id, home_pays, away_pays):
    return (
        avantage_domicile
        + country_ratings.get(home_pays, 0.0) + team_effects.get(home_id, 0.0)
        - country_ratings.get(away_pays, 0.0) - team_effects.get(away_id, 0.0)
    )


def _calibrer_logit_ordonne(marges, resultats, poids):
    """Ajuste (beta, c) d'un logit ordonne a 3 issues par maximum de
    vraisemblance pondere : beta est l'echelle appliquee a la marge de force,
    c la demi-largeur de la zone de match nul autour de 0."""
    marges = np.asarray(marges)
    resultats = np.asarray(resultats)  # -1 exterieur, 0 nul, 1 domicile
    poids = np.asarray(poids)

    def cout(params):
        log_beta, log_c = params
        beta, c = np.exp(log_beta), np.exp(log_c)
        s = beta * marges

        p_exterieur = expit(-c - s)
        p_domicile = expit(s - c)
        p_nul = np.clip(1.0 - p_exterieur - p_domicile, 1e-9, 1.0)

        log_vraisemblance = np.where(
            resultats > 0, np.log(np.clip(p_domicile, 1e-9, 1.0)),
            np.where(resultats < 0, np.log(np.clip(p_exterieur, 1e-9, 1.0)), np.log(p_nul))
        )
        return -np.sum(poids * log_vraisemblance)

    depart = np.array([0.0, np.log(0.5)])
    resultat = minimize(cout, depart, method="Nelder-Mead")

    if not resultat.success or not np.all(np.isfinite(resultat.x)):
        return 1.0, 0.5

    log_beta, log_c = resultat.x
    return float(np.exp(log_beta)), float(np.exp(log_c))


def construire_modele(historique):
    """Construit le modele complet (ratings pays, effets clubs, calibration
    des probabilites) a partir de l'historique brut des matchs."""
    matchs = _matchs_exploitables(historique)
    if not matchs:
        return ModeleRating()

    country_ratings, avantage_domicile = _regression_pays(matchs)
    team_effects = _regression_clubs(matchs, country_ratings, avantage_domicile)

    marges = [
        _marge_predite(country_ratings, team_effects, avantage_domicile,
                        m["home_id"], m["away_id"], m["home_pays"], m["away_pays"])
        for m in matchs
    ]
    resultats = [0 if m["diff"] == 0 else (1 if m["diff"] > 0 else -1) for m in matchs]
    poids = [m["poids"] for m in matchs]

    beta, c = _calibrer_logit_ordonne(marges, resultats, poids)

    return ModeleRating(
        country_ratings=country_ratings,
        team_effects=team_effects,
        home_advantage=avantage_domicile,
        beta=beta,
        c=c,
    )


def construire_modele_championnat(historique_ligue):
    """Construit un modele de probabilite de resultat pour un championnat national : un
    rating par club (regression a crete ponderee, avec avantage du terrain), puis la meme
    calibration logit ordonne que pour les competitions europeennes. Pas de niveau pays ici,
    puisque toutes les equipes d'un championnat national partagent le meme pays."""
    matchs = _matchs_exploitables(historique_ligue)
    if not matchs:
        return ModeleRating()

    team_effects, avantage_domicile = _regression_ridge_avec_avantage(matchs, LAMBDA_CLUB_CHAMPIONNAT)

    marges = [
        _marge_predite({}, team_effects, avantage_domicile, m["home_id"], m["away_id"], "", "")
        for m in matchs
    ]
    resultats = [0 if m["diff"] == 0 else (1 if m["diff"] > 0 else -1) for m in matchs]
    poids = [m["poids"] for m in matchs]

    beta, c = _calibrer_logit_ordonne(marges, resultats, poids)

    return ModeleRating(team_effects=team_effects, home_advantage=avantage_domicile, beta=beta, c=c)


def predire_resultat(modele, home_id, away_id, home_pays, away_pays):
    """Probabilites (victoire domicile / nul / victoire exterieure) pour un
    match donne, a partir d'un modele deja construit."""
    marge = _marge_predite(
        modele.country_ratings, modele.team_effects, modele.home_advantage,
        home_id, away_id, home_pays or "", away_pays or ""
    )
    s = modele.beta * marge

    p_exterieur = float(expit(-modele.c - s))
    p_domicile = float(expit(s - modele.c))
    p_nul = max(0.0, 1.0 - p_exterieur - p_domicile)

    total = p_exterieur + p_domicile + p_nul
    return {
        "probaVictoireDomicile": p_domicile / total,
        "probaNul": p_nul / total,
        "probaVictoireExterieure": p_exterieur / total,
        "margeForce": marge,
    }
