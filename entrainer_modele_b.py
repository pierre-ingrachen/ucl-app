"""Modele B : probabilites 1/N/2 qui partent du marche et apprennent l'ecart avec lui, puis
paris sur les issues a cote > 4 dont la valeur `p_modele x cote - 1` depasse une marge.

Validation "walk-forward" : pour chaque saison de test T, le modele est choisi (hyperparametres,
marge, plafond de cote) sur la saison T-1 en n'ayant vu que les saisons < T-1, puis re-entraine
sur les saisons <= T-1 et applique a T. Jamais de decoupage aleatoire. Les saisons de test
sont 2023-24, 2024-25, 2025-26 et 2026-27 (en cours).

La cote Winamax n'existe pas dans l'historique : on teste plusieurs hypotheses (SCENARIOS), et
les seuils sont choisis sur le scenario le plus prudent.

Usage : .venv/bin/python entrainer_modele_b.py
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

import evaluation_paris as ev

warnings.filterwarnings("ignore")

FICHIER = "dataset_cotes.csv"
FICHIER_PARIS_TEST = "paris_modele_b_test.csv"
SAISONS_TEST = [2024, 2025, 2026, 2027]  # etiquette = annee de fin de saison (2024 = 2023-24)
COTE_MIN = 4.0
MARGES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
PLAFONDS = [6.0, 8.0, 12.0, np.inf]
MIN_PARIS_VALIDATION = 40
SCENARIO_CHOIX = "avgc_-3%"  # scenario prudent sur lequel on choisit marge et plafond

# hypotheses sur la cote proposee par Winamax (par issue)
SCENARIOS = {
    "avgc": lambda d, k: d[f"avgc_{k}"],                       # moyenne du marche a la cloture
    "avgc_-3%": lambda d, k: d[f"avgc_{k}"] * 0.97,            # Winamax plus pauvre que le marche
    "b365c": lambda d, k: d[f"b365c_{k}"],                     # Bet365 a la cloture
    "maxc (irrealiste)": lambda d, k: d[f"maxc_{k}"],          # meilleure cote du marche : borne haute
}


# --- Donnees --------------------------------------------------------------------------

def charger():
    d = pd.read_csv(FICHIER, low_memory=False).sort_values(["date", "ligue", "equipe_dom"]).reset_index(drop=True)
    d["saison_fin"] = d.date.str[:4].astype(int) + (d.date.str[5:7].astype(int) >= 7)
    # le marche de reference : moyenne des bookmakers a la cloture, marge retiree (dispo. 100 %)
    d["y"] = d.resultat.map({"H": 0, "D": 1, "A": 2})
    return d.dropna(subset=["y", "p_avgc_h", "p_avgc_d", "p_avgc_a"]).reset_index(drop=True)


def colonnes_features(d):
    return [c for c in d.columns if c.startswith(("dom_m", "ext_m")) or c in ("dom_rang", "ext_rang")]


def matrice(d, cols_f, ligues):
    """Entrees du modele : log des probabilites du marche + 42 features + ligue (one-hot)."""
    pm = d[["p_avgc_h", "p_avgc_d", "p_avgc_a"]].to_numpy()
    marche = np.log(pm)
    feats = d[cols_f].to_numpy(float)
    ligue = np.stack([(d.ligue.astype(str) == l).to_numpy(float) for l in ligues], axis=1)
    return marche, feats, ligue


# --- Modeles --------------------------------------------------------------------------

class Candidat:
    """Un modele de probabilites 1/N/2 : regression logistique ou gradient boosting, tous deux
    alimentes par les probabilites du marche (le modele apprend le biais et l'ecart)."""

    def __init__(self, nom, fabrique, avec_ligue=True):
        self.nom, self.fabrique, self.avec_ligue = nom, fabrique, avec_ligue

    def _x(self, d, cols_f, ligues, ajuster=False):
        marche, feats, ligue = matrice(d, cols_f, ligues)
        x = np.hstack([marche, feats] + ([ligue] if self.avec_ligue else []))
        if ajuster:
            self.scaler = StandardScaler().fit(x)
        return self.scaler.transform(x)

    def fit(self, d, cols_f, ligues):
        self.modele = self.fabrique()
        self.modele.fit(self._x(d, cols_f, ligues, ajuster=True), d.y.astype(int))
        return self

    def predict(self, d, cols_f, ligues):
        return self.modele.predict_proba(self._x(d, cols_f, ligues))


def candidats():
    c = []
    for C in (0.003, 0.03, 0.3):
        c.append(Candidat(f"logit C={C}", lambda C=C: LogisticRegression(C=C, max_iter=2000)))
    for prof, it in ((2, 150), (3, 250)):
        c.append(Candidat(f"gbm prof={prof} it={it}", lambda p=prof, i=it: HistGradientBoostingClassifier(
            max_depth=p, max_iter=i, learning_rate=0.03, l2_regularization=10.0, min_samples_leaf=100,
            random_state=0)))
    return c


# --- Evaluation -----------------------------------------------------------------------

def cotes_scenario(d, nom):
    return np.stack([SCENARIOS[nom](d, k).to_numpy(float) for k in "hda"], axis=1)


def gains(d):
    return np.eye(3)[d.y.astype(int).to_numpy()]


def choisir_seuils(d_val, proba_val):
    """(marge, plafond) au meilleur ROI de validation, sur le scenario prudent, avec assez de paris."""
    cotes = cotes_scenario(d_val, SCENARIO_CHOIX)
    meilleur, choix = -np.inf, (max(MARGES), np.inf)
    for plafond in PLAFONDS:
        for marge in MARGES:
            p = ev.paris_possibles(cotes, proba_val, gains(d_val), d_val.date.to_numpy(), COTE_MIN, plafond, marge)
            if len(p) >= MIN_PARIS_VALIDATION and ev.roi(p) > meilleur:
                meilleur, choix = ev.roi(p), (marge, plafond)
    return choix, meilleur


def rapport(d, sorties, ll_table, fichier_paris, nom="modele B"):
    """Resultats hors echantillon de `sorties` [(saison, positions, probas, marge, plafond)] sur tous
    les scenarios de cote, plus les bases de comparaison. Partage avec le modele C."""
    # --- resultats hors echantillon, tous scenarios de cote ---
    print("\n" + "=" * 100 + "\nRESULTATS HORS ECHANTILLON (saisons de test cumulees)\n" + "=" * 100)
    tot = sum(n for _, _, _, n in ll_table)
    print(f"log-loss test pondere : modele {sum(a * n for _, a, _, n in ll_table) / tot:.4f}"
          f" / marche {sum(b * n for _, _, b, n in ll_table) / tot:.4f}")
    pm_all = d[["p_avgc_h", "p_avgc_d", "p_avgc_a"]].to_numpy()
    toutes = {}
    for scen in SCENARIOS:
        lignes = []
        for T, pos, p_test, marge, plafond in sorties:
            sous = d.loc[pos]
            p = ev.paris_possibles(cotes_scenario(sous, scen), p_test, gains(sous), sous.date.to_numpy(),
                                   COTE_MIN, plafond, marge)
            p["match"] = pos[p.match.to_numpy()]
            p["saison"] = T
            lignes.append(p)
        toutes[scen] = pd.concat(lignes, ignore_index=True).sort_values(["date", "match"], kind="stable")
    for scen, p in toutes.items():
        print(f"\n[{scen}]  {nom}")
        print("  total :", ev.resume(p), "| CLV", round(100 * ev.clv(p, pm_all), 1), "%")
        for T in SAISONS_TEST:
            q = p[p.saison == T]
            if len(q):
                print(f"  {T - 1}-{str(T)[2:]} :", ev.resume(q, ic=False))
    toutes[SCENARIO_CHOIX].to_csv(fichier_paris, index=False)

    # --- bases de comparaison, sur les memes matchs de test ---
    test_all = d[d.saison_fin.isin(SAISONS_TEST)]
    print("\n" + "=" * 100 + "\nBASES DE COMPARAISON (memes matchs de test, cote > 4)\n" + "=" * 100)
    for scen in SCENARIOS:
        cotes = cotes_scenario(test_all, scen)
        aveugle = ev.paris_possibles(cotes, np.ones_like(cotes), gains(test_all), test_all.date.to_numpy(), COTE_MIN)
        print(f"[{scen}] pari a l'aveugle :", ev.resume(aveugle))
    # mise en concurrence des bookmakers : on parie la ou Bet365 paye plus que le consensus juste
    cotes = cotes_scenario(test_all, "b365c")
    p_mkt = test_all[["p_avgc_h", "p_avgc_d", "p_avgc_a"]].to_numpy()
    for marge in (0.0, 0.05):
        bk = ev.paris_possibles(cotes, p_mkt, gains(test_all), test_all.date.to_numpy(), COTE_MIN, np.inf, marge)
        print(f"[b365c] suivre le marche seul (p_marche x cote - 1 > {marge}):", ev.resume(bk))


def main():
    d = charger()
    cols_f = colonnes_features(d)
    ligues = sorted(d.ligue.astype(str).unique())
    print(f"{len(d)} matchs, {len(cols_f)} features, {len(ligues)} ligues, saisons {sorted(d.saison_fin.unique())}")

    sorties = []  # (saison, positions, probabilites modele, marge, plafond)
    ll_table = []
    for T in SAISONS_TEST:
        apprent, val, test = d[d.saison_fin <= T - 2], d[d.saison_fin == T - 1], d[d.saison_fin == T]
        if not len(test):
            continue
        # choix du modele sur la validation (log-loss), a comparer au marche seul
        evals = []
        for cand in candidats():
            cand.fit(apprent, cols_f, ligues)
            evals.append((log_loss(val.y.astype(int), cand.predict(val, cols_f, ligues), labels=[0, 1, 2]), cand))
        evals.sort(key=lambda t: t[0])
        ll_val, cand = evals[0]
        ll_marche_val = log_loss(val.y.astype(int), val[["p_avgc_h", "p_avgc_d", "p_avgc_a"]].to_numpy(), labels=[0, 1, 2])
        (marge, plafond), roi_val = choisir_seuils(val, cand.predict(val, cols_f, ligues))
        # re-entrainement sur toutes les saisons <= T-1, puis application a T
        cand.fit(d[d.saison_fin <= T - 1], cols_f, ligues)
        p_test = cand.predict(test, cols_f, ligues)
        ll_test = log_loss(test.y.astype(int), p_test, labels=[0, 1, 2])
        ll_marche_test = log_loss(test.y.astype(int), test[["p_avgc_h", "p_avgc_d", "p_avgc_a"]].to_numpy(), labels=[0, 1, 2])
        print(f"\nTest {T - 1}-{str(T)[2:]} : modele {cand.nom}, marge {marge:.2f}, plafond {plafond}, "
              f"ROI validation {100 * roi_val:.1f} %")
        print(f"  log-loss validation : modele {ll_val:.4f} / marche {ll_marche_val:.4f}"
              f" ; test : modele {ll_test:.4f} / marche {ll_marche_test:.4f}")
        ll_table.append((T, ll_test, ll_marche_test, len(test)))
        sorties.append((T, test.index.to_numpy(), p_test, marge, plafond))

    rapport(d, sorties, ll_table, FICHIER_PARIS_TEST)


if __name__ == "__main__":
    main()
