"""Accès au modèle de prédiction par apprentissage pour le reste de
l'application (API et bilan des paris).

Le modèle entraîné est mis en cache sur disque (`cache_modele_ml.pkl`,
régénérable, gitignoré) et reconstruit une fois par jour, comme les modèles de
rating de `main.py`. La reconstruction (~10 s) n'a lieu qu'au premier appel de
la journée ; ensuite c'est un simple `pickle.load`.
"""

import os
import pickle
from datetime import date

from dataset_ml import Historique
from modele_ml import ModeleML, _probas_depuis_lambdas, construire_dataset

CACHE_MODELE_ML_FILE = "cache_modele_ml.pkl"

_modele_ml = None
_modele_ml_date = None
_historique = None


def obtenir_modele_ml():
    """Modèle ML du jour (pickle si déjà entraîné aujourd'hui, sinon entraînement)."""
    global _modele_ml, _modele_ml_date
    aujourd_hui = date.today()
    if _modele_ml is not None and _modele_ml_date == aujourd_hui:
        return _modele_ml

    if os.path.exists(CACHE_MODELE_ML_FILE):
        mtime = date.fromtimestamp(os.path.getmtime(CACHE_MODELE_ML_FILE))
        if mtime == aujourd_hui:
            try:
                _modele_ml = ModeleML.charger(CACHE_MODELE_ML_FILE)
                _modele_ml_date = aujourd_hui
                return _modele_ml
            except (pickle.UnpicklingError, AttributeError, EOFError):
                pass

    _modele_ml = ModeleML().entrainer(construire_dataset())
    _modele_ml_date = aujourd_hui
    try:
        _modele_ml.sauvegarder(CACHE_MODELE_ML_FILE)
    except OSError:
        pass
    return _modele_ml


def obtenir_historique():
    """État Elo + historique de toutes les équipes, rejoué une fois par jour."""
    global _historique
    aujourd_hui = date.today()
    if _historique is None or getattr(obtenir_historique, "_date", None) != aujourd_hui:
        _historique = Historique.depuis_caches()
        obtenir_historique._date = aujourd_hui
    return _historique


def _fixture_depuis_match(match):
    """Match brut TheSportsDB (matchs à venir) -> fixture pour `Historique.ligne_pour`."""
    ligue = match.get("idLeague")
    europe = ligue in {"4480", "4481", "5071"}
    return {
        "idEvent": match.get("idEvent"),
        "date": match.get("dateEvent"),
        "leagueId": ligue,
        "typeCompetition": "europe" if europe else "championnat",
        "phase": match.get("strPhase") or ("" if europe else "championnat"),
        "homeId": match.get("idHomeTeam"),
        "awayId": match.get("idAwayTeam"),
        "homeName": match.get("strHomeTeam"),
        "awayName": match.get("strAwayTeam"),
    }


def predire_match_ml(match):
    """Probabilités 1X2 d'un match à venir (schéma identique à
    `rating.predire_resultat` : probaVictoireDomicile / probaNul / probaVictoireExterieure)."""
    modele = obtenir_modele_ml()
    ligne = obtenir_historique().ligne_pour(_fixture_depuis_match(match))
    p = modele.predire(ligne)
    return {
        "probaVictoireDomicile": p["domicile"],
        "probaNul": p["nul"],
        "probaVictoireExterieure": p["exterieure"],
        "lambdaDomicile": p["lambdaDomicile"],
        "lambdaExterieure": p["lambdaExterieure"],
    }


def ensemble_probas(proba_rating, proba_ml):
    """Moyenne géométrique renormalisée de deux jeux de probabilités 1X2
    (meilleure combinaison au backtest : logloss 0.988 vs 0.995 chacun seul)."""
    if not proba_rating or not proba_ml:
        return None
    cles = ["probaVictoireDomicile", "probaNul", "probaVictoireExterieure"]
    g = {c: (max(proba_rating.get(c, 0.0), 1e-12) * max(proba_ml.get(c, 0.0), 1e-12)) ** 0.5
         for c in cles}
    s = sum(g.values()) or 1.0
    return {c: g[c] / s for c in cles}
