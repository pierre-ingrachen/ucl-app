"""Banc d'essai du modele D (predire le marche a partir des features, parier sur les ecarts).

Protocole anti-sur-apprentissage :
- DEV : saisons de test 2023-24 et 2024-25 (modele entraine sur le passe uniquement). Toutes les
  experiences et le choix de la configuration finale se font ici.
- CONFIRMATION : 2025-26 et 2026-27, jamais utilisees pour choisir ; evaluees une fois a la fin.
- La configuration est choisie sur le plus faible des deux ROI de dev (robustesse), avec un minimum de paris.

Les probabilites de chaque modele sont calculees une fois par fold ; les regles de pari (ecart exige,
plafond de cote, issues autorisees, proba minimale) sont ensuite de simples filtres.

Usage : .venv/bin/python experiences_modele.py
"""
import itertools
import pickle
import time
import warnings

import numpy as np
import pandas as pd
import torch
from scipy.stats import poisson
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import entrainer_modele_b as b
import entrainer_modele_d as D

warnings.filterwarnings("ignore")

FOLDS_DEV, FOLDS_CONF = [2024, 2025], [2026, 2027]
FICHIER_PROBAS = "experiences_probas.pkl"
SCEN_SELECTION = "Bet365 cloture -5%"       # scenario sur lequel on choisit la regle
SCENS = ["Bet365 cloture -10%", "Bet365 cloture -5%", "Bet365 cloture"]
MIN_PARIS_PAR_SAISON_DEV = 80


# --- Features ---------------------------------------------------------------------------

def feats_xg(d):
    """Probabilites 1/N/2 d'un modele de Poisson a partir des forces offensive/defensive long terme."""
    lh = ((d.att_dom + d.def_ext) / 2).clip(0.2, 4).to_numpy()
    la = ((d.att_ext + d.def_dom) / 2).clip(0.2, 4).to_numpy()
    k = np.arange(9)
    g = poisson.pmf(k[None, :, None], lh[:, None, None]) * poisson.pmf(k[None, None, :], la[:, None, None])
    ph, pd_, pa = np.tril(g, -1).sum((1, 2)), np.trace(g, axis1=1, axis2=2), np.triu(g, 1).sum((1, 2))
    s = ph + pd_ + pa
    return np.stack([lh, la, lh - la, np.log(ph / s), np.log(pd_ / s), np.log(pa / s)], axis=1)


def matrice_features(d, ligues, jeu):
    ratings = jeu in ("ratings", "ratings+xg")
    X = D.features(d, ligues, ratings)
    if jeu == "ratings+xg":
        X = np.hstack([X, feats_xg(d)])
    return X


def cible(d, nom, alpha):
    marche = d[D.CIBLE].to_numpy()
    if nom == "psc":  # Pinnacle a la cloture quand disponible, sinon moyenne
        psc = d[["p_psc_h", "p_psc_d", "p_psc_a"]].to_numpy()
        marche = np.where(np.isnan(psc).any(1, keepdims=True), marche, psc)
    return (1 - alpha) * np.eye(3)[d.y.astype(int).to_numpy()] + alpha * marche


# --- Modeles : renvoient les probabilites du fold de test --------------------------------

def fit_predict(modele, X, T, saison, tgt):
    tr, te = np.where(saison <= T - 1)[0], np.where(saison == T)[0]
    sc = StandardScaler().fit(X[tr])
    Xs = sc.transform(X)
    if modele == "mlp":
        x = torch.tensor(Xs, dtype=torch.float32)
        t = torch.tensor(tgt, dtype=torch.float32)
        app, val = np.where(saison <= T - 2)[0], np.where(saison == T - 1)[0]
        essais = [D.entrainer(x[app], t[app], g, x[val], t[val]) for g in range(3)]
        ep = int(np.median([e for _, e in essais]))
        nets = [D.entrainer(x[tr], t[tr], g, epoques=ep)[0] for g in range(3)]
        return te, D.predire(nets, x[te])
    # modeles sklearn : etiquettes souples via repetition des lignes ponderees par la cible
    Xr = np.vstack([Xs[tr]] * 3)
    yr = np.repeat([0, 1, 2], len(tr))
    wr = np.concatenate([tgt[tr, k] for k in range(3)])
    if modele == "hgb":
        m = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.04, l2_regularization=10.0,
                                           min_samples_leaf=200, random_state=0)
    else:
        m = LogisticRegression(C=0.05, max_iter=3000)
    m.fit(Xr, yr, sample_weight=wr)
    return te, m.predict_proba(Xs[te])


# --- Paris candidats et regles ---------------------------------------------------------

def candidats(d, pos, proba, scen, T):
    sous = d.iloc[pos]
    cotes = D.cotes_scenario(sous, scen)
    gains = b.gains(sous)
    n = len(pos)
    c, p, g = cotes.ravel(), proba.ravel(), gains.ravel()
    ok = np.isfinite(c) & (c > b.COTE_MIN)
    idx = np.where(ok)[0]
    df = pd.DataFrame({"match": pos[idx // 3], "issue": idx % 3, "cote": c[idx], "p": p[idx],
                       "gagne": g[idx], "saison": T, "date": sous.date.to_numpy()[idx // 3]})
    df["ecart"] = 1 - 1 / (df.p * df.cote)
    df["mise"] = 1 / df.cote
    df["profit"] = df.gagne - df.mise
    return df


ISSUES_SETS = {"1N2": (0, 1, 2), "N": (1,), "2": (2,), "N2": (1, 2), "1N": (0, 1)}
GRILLE = list(itertools.product([0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50], [5.0, 6.0, 8.0, 12.0, np.inf],
                                list(ISSUES_SETS), [0.0, 0.10, 0.15]))


def appliquer(df, regle):
    e, cap, iss, pmin = regle
    return df[(df.ecart >= e) & (df.cote <= cap) & df.issue.isin(ISSUES_SETS[iss]) & (df.p >= pmin)]


def roi(q):
    return q.profit.sum() / q.mise.sum() if len(q) else np.nan


def critere_dev(df_dev, regle):
    """min(ROI saison 1, ROI saison 2) si assez de paris dans chaque saison, sinon -inf."""
    q = appliquer(df_dev, regle)
    rois = []
    for T in FOLDS_DEV:
        s = q[q.saison == T]
        if len(s) < MIN_PARIS_PAR_SAISON_DEV:
            return -np.inf, len(q)
        rois.append(roi(s))
    return min(rois), len(q)


# --- Programme principal ------------------------------------------------------------------

def main():
    t0 = time.time()
    d = D.charger_avec_ratings()
    ligues = sorted(d.ligue.astype(str).unique())
    saison = d.saison_fin.to_numpy()
    modeles = [("logit", "ratings+xg", "avgc", 1.0), ("logit", "ratings+xg", "avgc", 0.5),
               ("hgb", "ratings+xg", "avgc", 1.0), ("hgb", "ratings+xg", "avgc", 0.5), ("hgb", "ratings+xg", "avgc", 0.0),
               ("hgb", "ratings+xg", "psc", 1.0), ("hgb", "ratings", "avgc", 0.5), ("hgb", "base", "avgc", 0.5),
               ("mlp", "ratings+xg", "avgc", 1.0), ("mlp", "ratings+xg", "avgc", 0.5), ("mlp", "ratings", "avgc", 0.5),
               ("mlp", "ratings+xg", "psc", 0.5)]
    try:
        probas = pickle.load(open(FICHIER_PROBAS, "rb"))
    except Exception:
        probas = {}
    Xs = {}
    for cfg in modeles:
        if cfg in probas:
            continue
        mod, jeu, tgt_nom, alpha = cfg
        if jeu not in Xs:
            Xs[jeu] = matrice_features(d, ligues, jeu)
        tgt = cible(d, tgt_nom, alpha)
        probas[cfg] = {T: fit_predict(mod, Xs[jeu], T, saison, tgt) for T in FOLDS_DEV + FOLDS_CONF}
        pickle.dump(probas, open(FICHIER_PROBAS, "wb"))
        print(f"[{time.time() - t0:5.0f}s] modele {cfg} calcule", flush=True)

    # qualite des probabilites
    from sklearn.metrics import log_loss
    lignes = []
    for cfg, folds in probas.items():
        row = {"modele": " / ".join(map(str, cfg))}
        for nom, Ts in (("dev", FOLDS_DEV), ("conf", FOLDS_CONF)):
            pos = np.concatenate([folds[T][0] for T in Ts]); p = np.concatenate([folds[T][1] for T in Ts])
            pm = d[D.CIBLE].to_numpy()[pos]
            row[f"logloss {nom}"] = round(log_loss(d.y.astype(int).to_numpy()[pos], p, labels=[0, 1, 2]), 4)
            row[f"KL marche {nom}"] = round((pm * np.log(pm / p)).sum(1).mean(), 4)
        lignes.append(row)
    sortie = ["# Experiences modele D\n", f"Scenario de selection : {SCEN_SELECTION}. Dev = {FOLDS_DEV}, confirmation = {FOLDS_CONF}.\n",
              "## Qualite des probabilites (log-loss : marche dev/conf = voir tableau D)\n", D.table_md(lignes, list(lignes[0]))]

    # recherche de regle sur le dev
    resultats = []
    for cfg, folds in probas.items():
        cand = {scen: pd.concat([candidats(d, *folds[T], scen, T) for T in FOLDS_DEV + FOLDS_CONF], ignore_index=True)
                for scen in SCENS}
        dev = cand[SCEN_SELECTION][cand[SCEN_SELECTION].saison.isin(FOLDS_DEV)]
        for regle in GRILLE:
            crit, n = critere_dev(dev, regle)
            if np.isfinite(crit):
                resultats.append((crit, cfg, regle))
    resultats.sort(key=lambda t: -t[0])
    print(f"{len(resultats)} (modele, regle) admissibles sur {len(probas) * len(GRILLE)}", flush=True)

    # top configurations : dev puis confirmation (tous les scenarios)
    candidats_cache = {}
    def cands(cfg, scen):
        if (cfg, scen) not in candidats_cache:
            candidats_cache[(cfg, scen)] = pd.concat([candidats(d, *probas[cfg][T], scen, T) for T in FOLDS_DEV + FOLDS_CONF],
                                                     ignore_index=True)
        return candidats_cache[(cfg, scen)]

    def decrire(cfg, regle, scen):
        df = cands(cfg, scen)
        out = {}
        for nom, Ts in (("dev", FOLDS_DEV), ("conf", FOLDS_CONF)):
            q = appliquer(df[df.saison.isin(Ts)], regle)
            out[nom] = (len(q), round(100 * roi(q), 1) if len(q) else None, round(q.profit.sum(), 1))
        return out

    sortie.append(f"\n## 15 meilleures (modele, regle) selon le plus faible ROI de dev ({SCEN_SELECTION}), puis leur resultat en confirmation\n")
    lignes = []
    for crit, cfg, regle in resultats[:15]:
        r = {"modele": " / ".join(map(str, cfg)), "regle (ecart, plafond, issues, p min)": str(regle),
             "critere dev %": round(100 * crit, 1)}
        for scen in SCENS:
            x = decrire(cfg, regle, scen)
            r[f"{scen} dev (n, ROI%)"] = f"{x['dev'][0]}, {x['dev'][1]}"
            r[f"{scen} CONF (n, ROI%, profit)"] = f"{x['conf'][0]}, {x['conf'][1]}, {x['conf'][2]}"
        lignes.append(r)
    sortie.append(D.table_md(lignes, list(lignes[0])))

    # biais de selection : parmi les 200 meilleures regles du dev, que valent-elles en confirmation ?
    conf_rois = []
    for crit, cfg, regle in resultats[:200]:
        q = appliquer(cands(cfg, SCEN_SELECTION)[lambda x: x.saison.isin(FOLDS_CONF)], regle)
        if len(q) >= 30:
            conf_rois.append(roi(q))
    conf_rois = np.array(conf_rois)
    sortie.append(f"\n## Effet de selection\nSur les 200 meilleures regles du dev ({len(conf_rois)} avec >= 30 paris en confirmation), "
                  f"ROI de confirmation ({SCEN_SELECTION}) : mediane {100 * np.median(conf_rois):.1f} %, "
                  f"moyenne {100 * conf_rois.mean():.1f} %, {100 * (conf_rois > 0).mean():.0f} % positives.")
    texte = "\n".join(sortie)
    open("resultats_experiences.md", "w", encoding="utf-8").write(texte + "\n")
    print(texte)


if __name__ == "__main__":
    main()
