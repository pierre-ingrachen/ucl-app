"""Modèle de prédiction par apprentissage : double régression de Poisson.

Un unique régresseur `HistGradientBoostingRegressor(loss="poisson")` apprend le
nombre de buts marqués par un camp à partir de ses features et de celles de
l'adversaire. Chaque match d'entraînement fournit deux lignes (perspective
domicile, puis perspective extérieur), ce qui rend le modèle symétrique et
double la taille de l'échantillon.

À la prédiction, on obtient (lambda_domicile, lambda_extérieur), d'où toute la
matrice des scores (Poisson indépendants + correction Dixon-Coles des petits
scores, dont le paramètre rho est calibré sur l'historique). On en déduit :
probas 1X2, over/under 2.5, BTTS.

Ce module ne fait aucun appel réseau : il consomme le dataset de `dataset_ml.py`.
"""

import math
import pickle

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from dataset_ml import ELO_HOME_ADVANTAGE, construire_dataset

# Colonnes numériques d'une ligne (perspective d'un camp). Préfixe t_ = équipe qui
# marque, o_ = adversaire.
_FEAT_EQUIPE = ["nb_matchs", "gf_5", "ga_5", "gd_5", "ppg_5", "gf_10", "ga_10",
                "gd_10", "ppg_10", "gf_lieu", "ga_lieu", "gf_ewm", "ga_ewm",
                "serie", "jours_repos", "matchs_14j"]

_COLS_NUM = (["is_home", "elo_team", "elo_opp", "elo_diff", "h2h_gd", "mois", "est_europe"]
             + [f"t_{k}" for k in _FEAT_EQUIPE]
             + [f"o_{k}" for k in _FEAT_EQUIPE])
_COLS_CAT = ["league_id", "phase"]
_COLS = _COLS_NUM + _COLS_CAT
_IDX_CAT = [len(_COLS_NUM), len(_COLS_NUM) + 1]

MAX_BUTS = 10  # troncature de la matrice des scores


def _ligne_perspective(ligne, domicile):
    """Vecteur de features d'un camp. `domicile`=True -> le camp qui marque est
    l'équipe à domicile."""
    ctx = ligne["ctx"]
    feat_t = ligne["featHome"] if domicile else ligne["featAway"]
    feat_o = ligne["featAway"] if domicile else ligne["featHome"]
    elo_t = ctx["eloHome"] if domicile else ctx["eloAway"]
    elo_o = ctx["eloAway"] if domicile else ctx["eloHome"]
    signe = 1.0 if domicile else -1.0
    h2h = ctx["h2hGdHome"]

    vec = {
        "is_home": 1.0 if domicile else 0.0,
        "elo_team": elo_t,
        "elo_opp": elo_o,
        "elo_diff": elo_t - elo_o + signe * ELO_HOME_ADVANTAGE,
        "h2h_gd": (signe * h2h) if not math.isnan(h2h) else math.nan,
        "mois": ctx["mois"],
        "est_europe": ctx["estEurope"],
        "league_id": ctx["leagueId"],
        "phase": ctx["phase"] or "NA",
    }
    for k in _FEAT_EQUIPE:
        vec[f"t_{k}"] = feat_t[k]
        vec[f"o_{k}"] = feat_o[k]
    return vec


class _EncodeurCat:
    """Encodage entier stable des colonnes catégorielles (vocabulaire figé à
    l'entraînement, valeurs inconnues -> -1, gérées comme catégorie manquante)."""

    def __init__(self):
        self.vocab = {}

    def fit(self, valeurs_par_col):
        for col, valeurs in valeurs_par_col.items():
            self.vocab[col] = {v: i for i, v in enumerate(sorted(set(valeurs)))}

    def encode(self, col, valeur):
        return self.vocab[col].get(valeur, -1)


def _matrice(lignes, encodeur):
    n = len(lignes) * 2
    X = np.full((n, len(_COLS)), np.nan)
    y = np.zeros(n)
    w = np.zeros(n)
    for i, ligne in enumerate(lignes):
        for j, domicile in enumerate((True, False)):
            r = i * 2 + j
            vec = _ligne_perspective(ligne, domicile)
            for c, col in enumerate(_COLS_NUM):
                X[r, c] = vec[col]
            for c, col in enumerate(_COLS_CAT):
                code = encodeur.encode(col, vec[col])
                X[r, len(_COLS_NUM) + c] = code if code >= 0 else np.nan
            y[r] = ligne["yHome"] if domicile else ligne["yAway"]
            w[r] = ligne["poids"]
    return X, y, w


def _calibrer_rho(lambda_home, lambda_away, resultats, poids):
    """Paramètre de dépendance Dixon-Coles, par recherche 1D du maximum de
    vraisemblance pondéré sur les issues 1X2 observées."""
    meilleurs = (0.0, -np.inf)
    for rho in np.linspace(-0.25, 0.10, 36):
        ll = 0.0
        for lh, la, res, pd in zip(lambda_home, lambda_away, resultats, poids):
            p = _probas_depuis_lambdas(lh, la, rho)
            ll += pd * math.log(max(p[res], 1e-12))
        if ll > meilleurs[1]:
            meilleurs = (float(rho), ll)
    return meilleurs[0]


def _tau_dixon_coles(i, j, lh, la, rho):
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def _matrice_scores(lh, la, rho):
    i = np.arange(MAX_BUTS + 1)
    ph = np.exp(-lh) * lh ** i / np.array([math.factorial(k) for k in i])
    pa = np.exp(-la) * la ** i / np.array([math.factorial(k) for k in i])
    M = np.outer(ph, pa)
    for a in (0, 1):
        for b in (0, 1):
            M[a, b] *= _tau_dixon_coles(a, b, lh, la, rho)
    M = np.clip(M, 0.0, None)
    return M / M.sum()


def _probas_depuis_lambdas(lh, la, rho):
    M = _matrice_scores(lh, la, rho)
    idx = np.arange(MAX_BUTS + 1)
    p_dom = np.tril(M, -1).sum()
    p_ext = np.triu(M, 1).sum()
    p_nul = 1.0 - p_dom - p_ext
    total_buts = idx[:, None] + idx[None, :]
    p_over = M[total_buts > 2.5].sum()
    p_btts = M[1:, 1:].sum()
    return {
        "domicile": float(p_dom), "nul": float(p_nul), "exterieure": float(p_ext),
        "over25": float(p_over), "btts": float(p_btts),
    }


class ModeleML:
    def __init__(self, params=None):
        self.params = params or dict(
            loss="poisson", learning_rate=0.05, max_iter=500,
            max_leaf_nodes=31, min_samples_leaf=60, l2_regularization=1.0,
            max_bins=255, early_stopping=True, validation_fraction=0.1,
            n_iter_no_change=25, random_state=0,
        )
        self.reg = None
        self.encodeur = _EncodeurCat()
        self.rho = 0.0

    def entrainer(self, lignes):
        self.encodeur = _EncodeurCat()
        self.encodeur.fit({
            "league_id": [l["ctx"]["leagueId"] for l in lignes],
            "phase": [(l["ctx"]["phase"] or "NA") for l in lignes],
        })
        X, y, w = _matrice(lignes, self.encodeur)
        cat_mask = np.zeros(len(_COLS), dtype=bool)
        for c in _IDX_CAT:
            cat_mask[c] = True
        self.reg = HistGradientBoostingRegressor(categorical_features=cat_mask, **self.params)
        self.reg.fit(X, y, sample_weight=w)

        # Calibration rho sur un sous-échantillon récent (poids les plus forts).
        lignes_cal = sorted(lignes, key=lambda l: l["date"])[-6000:]
        lh, la = self._lambdas_lignes(lignes_cal)
        res = [("domicile" if l["yHome"] > l["yAway"]
                else "exterieure" if l["yHome"] < l["yAway"] else "nul")
               for l in lignes_cal]
        self.rho = _calibrer_rho(lh, la, res, [l["poids"] for l in lignes_cal])
        return self

    def _lambdas_lignes(self, lignes):
        Xh = np.full((len(lignes), len(_COLS)), np.nan)
        Xa = np.full((len(lignes), len(_COLS)), np.nan)
        for i, ligne in enumerate(lignes):
            for M, dom in ((Xh, True), (Xa, False)):
                vec = _ligne_perspective(ligne, dom)
                for c, col in enumerate(_COLS_NUM):
                    M[i, c] = vec[col]
                for c, col in enumerate(_COLS_CAT):
                    code = self.encodeur.encode(col, vec[col])
                    M[i, len(_COLS_NUM) + c] = code if code >= 0 else np.nan
        return (np.clip(self.reg.predict(Xh), 1e-4, None),
                np.clip(self.reg.predict(Xa), 1e-4, None))

    def predire(self, ligne):
        """Probabilités complètes pour un match (dict `ligne` façonné comme dans
        `dataset_ml.construire_dataset`, sans cible)."""
        lh, la = self._lambdas_lignes([ligne])
        p = _probas_depuis_lambdas(float(lh[0]), float(la[0]), self.rho)
        p["lambdaDomicile"] = float(lh[0])
        p["lambdaExterieure"] = float(la[0])
        return p

    def predire_lot(self, lignes):
        lh, la = self._lambdas_lignes(lignes)
        return [
            {**_probas_depuis_lambdas(float(a), float(b), self.rho),
             "lambdaDomicile": float(a), "lambdaExterieure": float(b)}
            for a, b in zip(lh, la)
        ]

    def sauvegarder(self, chemin):
        with open(chemin, "wb") as fh:
            pickle.dump(self, fh)

    @staticmethod
    def charger(chemin):
        with open(chemin, "rb") as fh:
            return pickle.load(fh)


if __name__ == "__main__":
    lignes = construire_dataset()
    print(f"{len(lignes)} matchs -> entraînement...")
    modele = ModeleML().entrainer(lignes)
    print("rho Dixon-Coles calibré :", round(modele.rho, 4))
    for l in lignes[-3:]:
        p = modele.predire(l)
        print(f"{l['homeName']} - {l['awayName']} "
              f"({l['yHome']}-{l['yAway']}) -> "
              f"1 {p['domicile']:.2f} / N {p['nul']:.2f} / 2 {p['exterieure']:.2f} "
              f"| λ {p['lambdaDomicile']:.2f}-{p['lambdaExterieure']:.2f}")
