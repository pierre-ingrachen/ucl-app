"""IA-optimisee : modele de paris sur les OUTSIDERS (victoire domicile ou exterieure, cote > 4),
construit pour maximiser le ROI de ce segment. Ne touche ni au reseau de buts, ni au modele D.

Differences avec le premier algorithme (reseau de buts + Poisson) :
- une ligne par candidat (match, equipe sur laquelle on parie), vue du cote de cette equipe ;
- le modele predit directement P(victoire) sur ce segment (pas de Poisson general, pas de ligne de nul) ;
- aucune cote en entree (le marche n'est qu'un prix de pari) ; features : forme sur 5 matchs, Elo,
  buts, repos (modele_d.ratings) ;
- decision : valeur esperee p x cote - 1 > marge, plafond de cote ; marge et plafond choisis sur les
  saisons PRECEDENTES uniquement (walk-forward), jamais sur la saison testee.

Usage : .venv/bin/python -m ia_optimisee.modele
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from modele_d import entrainement as ent

warnings.filterwarnings("ignore")
FICHIER_RESULTATS = "ia_optimisee/resultats.md"
COTE_MIN = 4.0
COTE_APPRENTISSAGE = 3.3  # on apprend sur un segment un peu plus large que les paris (cote moyenne du marche)
SAISONS_TEST = [2024, 2025, 2026, 2027]  # etiquette = annee de fin de saison
MARGES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
PLAFONDS = [6.0, 8.0, 12.0, np.inf]
MIN_PARIS_CHOIX = 150
def arrondi_bookmaker(cote):
    """Cote arrondie a la decimale inferieure, comme sur Winamax (4,94 -> 4,90)."""
    return np.floor(cote * 10 + 1e-6) / 10


SCENARIOS = {
    "Bet365 cloture": lambda d, k: arrondi_bookmaker(d[f"b365c_{k}"]),
    "Bet365 cloture -5%": lambda d, k: arrondi_bookmaker(d[f"b365c_{k}"] * 0.95),
    "Bet365 cloture -10%": lambda d, k: arrondi_bookmaker(d[f"b365c_{k}"] * 0.90),
    "Moyenne cloture": lambda d, k: arrondi_bookmaker(d[f"avgc_{k}"]),
    "Meilleure cote cloture": lambda d, k: arrondi_bookmaker(d[f"maxc_{k}"]),
}


# --- Candidats -------------------------------------------------------------------------

def variables(d, cote):
    """Variables (sans cote) du match vues du cote de l'equipe pariee A (`cote` = "dom" ou "ext") contre B.
    `d` : lignes de matchs avec les 42 features et les ratings (passe ou match a venir)."""
    a, b = cote, "ext" if cote == "dom" else "dom"
    sgn = 1 if cote == "dom" else -1
    x = pd.DataFrame(index=d.index)
    for i in range(1, 6):
        x[f"a_pour{i}"], x[f"a_contre{i}"] = d[f"{a}_m{i}_buts_pour"], d[f"{a}_m{i}_buts_contre"]
        x[f"b_pour{i}"], x[f"b_contre{i}"] = d[f"{b}_m{i}_buts_pour"], d[f"{b}_m{i}_buts_contre"]
    for c, n in ((a, "a"), (b, "b")):
        pour = np.stack([d[f"{c}_m{i}_buts_pour"] for i in range(1, 6)], 1)
        contre = np.stack([d[f"{c}_m{i}_buts_contre"] for i in range(1, 6)], 1)
        x[f"{n}_moy_pour"], x[f"{n}_moy_contre"] = pour.mean(1), contre.mean(1)
        x[f"{n}_pts"] = np.where(pour > contre, 3, np.where(pour == contre, 1, 0)).mean(1)
        x[f"{n}_invaincu"] = (pour >= contre).mean(1)
        x[f"{n}_rang"] = d[f"{c}_rang"]
        x[f"{n}_elo"], x[f"{n}_att"], x[f"{n}_def"] = d[f"elo_{c}"], d[f"att_{c}"], d[f"def_{c}"]
        x[f"{n}_repos"], x[f"{n}_nb"] = d[f"repos_{c}"], d[f"nb_{c}"]
    x["diff_elo"] = sgn * d["elo_diff"]
    x["diff_rang"] = x.b_rang - x.a_rang
    x["diff_pts"] = x.a_pts - x.b_pts
    x["diff_buts"] = (x.a_att - x.b_def) - (x.b_att - x.a_def)
    x["domicile"] = 1.0 if cote == "dom" else 0.0
    x["p_elo"] = 1 / (1 + 10 ** (-(x.diff_elo) / 400))
    return x


def candidats(d):
    """Une ligne par (match, issue) : variables vues du cote de l'equipe sur laquelle on parie (A) contre
    l'adversaire (B). Les cotes ne servent qu'a delimiter le segment et a decider du pari."""
    out = []
    for cote, k, gagne in (("dom", "h", 0), ("ext", "a", 2)):
        x = variables(d, cote)
        x["match"] = d.index
        x["issue"] = cote
        x["saison"] = d.saison_fin
        x["date"] = d.date
        x["gagne"] = (d.y == gagne).astype(int)
        x["avgc"] = d[f"avgc_{k}"]
        for nom, fn in SCENARIOS.items():
            x[nom] = fn(d, k)
        out.append(x)
    c = pd.concat(out, ignore_index=True)
    return c[c.avgc >= COTE_APPRENTISSAGE].reset_index(drop=True)


def colonnes_modele(c):
    return [col for col in c.columns if col not in ("match", "issue", "saison", "date", "gagne", "avgc", *SCENARIOS)]


# --- Modele ------------------------------------------------------------------------------

def entrainer(x, y):
    """Ensemble : gradient boosting regularise + regression logistique (moyenne des probabilites)."""
    gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=200,
                                        l2_regularization=5.0, random_state=0)
    lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=500))
    return [gb.fit(x, y), lr.fit(x, y)]


def predire(modeles, x):
    return np.mean([m.predict_proba(x)[:, 1] for m in modeles], axis=0)


def probas_walk_forward(c, saisons):
    """Probabilite hors echantillon de chaque candidat des saisons `saisons` : modele entraine sur les
    saisons strictement anterieures."""
    cols = colonnes_modele(c)
    p = pd.Series(np.nan, index=c.index)
    for s in saisons:
        tr, te = c.saison < s, c.saison == s
        if tr.sum() < 3000 or te.sum() == 0:
            continue
        p[te] = predire(entrainer(c.loc[tr, cols], c.loc[tr, "gagne"]), c.loc[te, cols])
    return p


# --- Paris et mesures -----------------------------------------------------------------------

def selection(c, p, scen, marge, plafond):
    cote = c[scen]
    return (cote > COTE_MIN) & (cote <= plafond) & (p * cote - 1 > marge)


def mesure(c, k, scen):
    cote = c.loc[k, scen].to_numpy()
    g = c.loc[k, "gagne"].to_numpy()
    mise = 1 / cote
    gain = np.where(g == 1, 1 - mise, -mise)
    return mise, gain


def stats(c, k, scen, ic=True):
    n = int(k.sum())
    if n == 0:
        return dict(paris=0)
    mise, gain = mesure(c, k, scen)
    r = dict(paris=n, gagnes=int(c.loc[k, "gagne"].sum()), mises=round(mise.sum(), 1), profit=round(gain.sum(), 1),
             ROI=f"{gain.sum() / mise.sum():+.1%}")
    if ic:
        idx = np.random.default_rng(0).integers(0, n, (2000, n))
        ro = gain[idx].sum(1) / mise[idx].sum(1)
        r["IC95"] = f"[{np.percentile(ro, 2.5):+.0%} ; {np.percentile(ro, 97.5):+.0%}]"
    cum = np.cumsum(gain[np.argsort(c.loc[k, "date"].to_numpy(), kind="stable")])
    r["drawdown"] = round(float((np.maximum.accumulate(cum) - cum).max()), 1)
    return r


def choisir_regle(c, p, scen, avant):
    """Meilleure (marge, plafond) sur les saisons < `avant` : ROI - 1 ecart-type, au moins MIN_PARIS_CHOIX paris."""
    hist = c.saison < avant
    meilleur, score_max = (0.10, np.inf), -np.inf
    for m in MARGES:
        for pl in PLAFONDS:
            k = hist & p.notna() & selection(c, p.fillna(0), scen, m, pl)
            if k.sum() < MIN_PARIS_CHOIX:
                continue
            mise, gain = mesure(c, k, scen)
            roi = gain.sum() / mise.sum()
            se = gain.std(ddof=1) * np.sqrt(len(gain)) / mise.sum()
            if roi - se > score_max:
                score_max, meilleur = roi - se, (m, pl)
    return meilleur


def tableau(lignes):
    if not lignes:
        return ""
    cols = list(lignes[0][1].keys())
    s = "| " + " | ".join(["", *cols]) + " |\n|" + "---|" * (len(cols) + 1) + "\n"
    for nom, r in lignes:
        s += "| " + " | ".join([str(nom), *[str(r.get(col, "")) for col in cols]]) + " |\n"
    return s


def main():
    d = ent.charger_avec_ratings()
    c = candidats(d)
    print(f"{len(d)} matchs, {len(c)} candidats (cote moyenne du marche >= {COTE_APPRENTISSAGE})", flush=True)
    p = probas_walk_forward(c, [s for s in sorted(c.saison.unique()) if s >= 2022])
    ok = p.notna()
    ll = lambda q: -np.mean(np.where(c.loc[ok, "gagne"] == 1, np.log(q), np.log(1 - q)))
    base = c.loc[ok, "gagne"].mean()
    marche = (1 / c.loc[ok, "avgc"]).clip(0.01, 0.99)
    sortie = ["# IA-optimisee : resultats (walk-forward, hors echantillon)\n",
              f"Candidats evalues : {int(ok.sum())} (victoire dom./ext. a cote moyenne >= {COTE_APPRENTISSAGE}, saisons 2021-22 a 2026-27).\n",
              f"Log-loss de P(victoire) sur ce segment : modele {ll(p[ok]):.4f} | taux de base constant {ll(np.full(ok.sum(), base)):.4f} "
              f"| 1/cote moyenne du marche (non normalisee) {ll(marche):.4f}.\n"]
    print(sortie[-1])
    for scen in SCENARIOS:
        sortie.append(f"\n## Hypothese de cote : {scen}\n")
        lignes, k_tot = [], pd.Series(False, index=c.index)
        for s in SAISONS_TEST:
            m, pl = choisir_regle(c, p, scen, s)
            k = (c.saison == s) & selection(c, p.fillna(0), scen, m, pl) & p.notna()
            k_tot |= k
            lignes.append((f"{s - 1}-{str(s)[2:]} (marge {m:.0%}, plafond {pl})", stats(c, k, scen)))
        lignes.append(("**TOTAL regle choisie sur le passe**", stats(c, k_tot, scen)))
        aveugle = c.saison.isin(SAISONS_TEST) & (c[scen] > COTE_MIN)
        lignes.append(("Pari a l'aveugle (cote > 4)", stats(c, aveugle, scen)))
        for m in (0.0, 0.10, 0.20):
            k = c.saison.isin(SAISONS_TEST) & selection(c, p.fillna(0), scen, m, np.inf) & p.notna()
            lignes.append((f"Regle fixe : marge {m:.0%}, sans plafond", stats(c, k, scen)))
        sortie.append(tableau(lignes))
        print(sortie[-1], flush=True)
        if scen == "Bet365 cloture -5%":
            k = k_tot
            for nom, grp in (("issue", c.issue), ("tranche de cote", pd.cut(c[scen], [4, 5, 6, 8, 100]))):
                sortie.append(f"\nRegle choisie, par {nom} ({scen}) :\n")
                sortie.append(tableau([(str(v), stats(c, k & (grp == v), scen)) for v in grp[k].dropna().unique()]))
    open(FICHIER_RESULTATS, "w").write("\n".join(sortie))
    print("ecrit :", FICHIER_RESULTATS)


if __name__ == "__main__":
    main()
