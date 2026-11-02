"""Modele D : un reseau de neurones apprend a PREDIRE LES COTES DU MARCHE a partir des seules
caracteristiques des matchs (aucune cote en entree). On parie ensuite quand la cote du modele
(1 / probabilite) est nettement plus basse que la cote proposee par le bookmaker.

- Entrees : 42 features "matchs precedents" + features derivees (moyennes, points, ecarts) + ligue.
- Cible (sortie attendue) : probabilites du marche (moyenne des bookmakers a la cloture, marge retiree),
  eventuellement melangees aux resultats reels : cible = (1 - ALPHA) x resultat + ALPHA x marche.
  ALPHA = 1 : imitation pure du marche ; 0 : resultats seuls (sans marche du tout).
- Cote proposee par le bookmaker : Bet365 a la cloture, REDUITE (scenarios ci-dessous), car
  Winamax est absent de l'historique. Un pari est pris sur une issue si cote proposee > 4 et
  cote_modele <= cote_proposee x (1 - ECART).
- Mise = 1 / cote. Validation walk-forward : test sur 2023-24, 2024-25, 2025-26, 2026-27 ; ALPHA,
  nombre d'epoques, ECART et plafond de cote choisis sur la saison precedente uniquement.

Sortie : tableaux detailles a l'ecran et dans resultats_modele_d.md.

Usage : .venv/bin/python -m modele_d.entrainement
"""
import warnings

import numpy as np
import pandas as pd
import torch
from torch import nn

from modele_d import evaluation as ev

warnings.filterwarnings("ignore")
torch.set_num_threads(4)

FICHIER_RESULTATS = "modele_d/resultats/comparaison_modeles.md"
FICHIER = "modele_d/donnees/dataset_cotes.csv"
FICHIER_RATINGS = "modele_d/donnees/ratings_matchs.csv"
SAISONS_TEST = [2024, 2025, 2026, 2027]  # etiquette = annee de fin de saison (2024 = 2023-24)
COTE_MIN = 4.0
ALPHAS = [1.0, 0.5, 0.0]
ECARTS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]  # la cote du modele doit etre >= ECART % sous celle du bookmaker
PLAFONDS = [6.0, 8.0, 12.0, np.inf]
SCENARIO_PRINCIPAL = "Bet365 cloture -10%"
SCENARIOS = {
    "Bet365 cloture -10%": lambda d, k: d[f"b365c_{k}"] * 0.90,
    "Bet365 cloture -5%": lambda d, k: d[f"b365c_{k}"] * 0.95,
    "Bet365 cloture": lambda d, k: d[f"b365c_{k}"],
    "Moyenne marche -10%": lambda d, k: d[f"avgc_{k}"] * 0.90,
}
MIN_PARIS_VALIDATION = 60
NB_GRAINES, EPOQUES_MAX, LARGEUR, DROPOUT, LR, DECAY, BATCH = 5, 80, 96, 0.3, 1e-3, 1e-3, 512
CIBLE = ["p_avgc_h", "p_avgc_d", "p_avgc_a"]


# --- Donnees ---------------------------------------------------------------------------

def charger():
    """dataset_cotes.csv trie par date, avec la saison (annee de fin), la cible y (0 = 1, 1 = N, 2 = 2)
    et la probabilite du marche de reference (moyenne des bookmakers a la cloture, marge retiree)."""
    d = pd.read_csv(FICHIER, low_memory=False).sort_values(["date", "ligue", "equipe_dom"]).reset_index(drop=True)
    d["saison_fin"] = d.date.str[:4].astype(int) + (d.date.str[5:7].astype(int) >= 7)
    d["y"] = d.resultat.map({"H": 0, "D": 1, "A": 2})
    return d.dropna(subset=["y", "p_avgc_h", "p_avgc_d", "p_avgc_a"]).reset_index(drop=True)


def colonnes_features(d):
    return [c for c in d.columns if c.startswith(("dom_m", "ext_m")) or c in ("dom_rang", "ext_rang")]


def gains(d):
    """Matrice (n, 3) : 1 pour l'issue realisee, 0 sinon."""
    return np.eye(3)[d.y.astype(int).to_numpy()]


# --- Donnees et features ----------------------------------------------------------------

COLS_RATINGS = ["elo_dom", "elo_ext", "elo_diff", "att_dom", "def_dom", "att_ext", "def_ext",
                "repos_dom", "repos_ext", "nb_dom", "nb_ext"]


def charger_avec_ratings():
    """dataset_cotes.csv + ratings de force (ratings.py)."""
    d = charger()
    r = pd.read_csv(FICHIER_RATINGS, dtype={"ligue": str}).drop_duplicates(["ligue", "date", "equipe_dom", "equipe_ext"])
    d["ligue"] = d.ligue.astype(str)
    d = d.merge(r, on=["ligue", "date", "equipe_dom", "equipe_ext"], how="left", validate="m:1")
    assert d[COLS_RATINGS].notna().all().all(), "ratings manquants : relancer : python -m modele_d.ratings"
    return d

def features(d, ligues, ratings=False):
    """Matrice d'entree : features brutes + derivees + ligue. Aucune cote."""
    base = colonnes_features(d)
    cols = {}
    for cote in ("dom", "ext"):
        pour = np.stack([d[f"{cote}_m{i}_buts_pour"] for i in range(1, 6)], axis=1)
        contre = np.stack([d[f"{cote}_m{i}_buts_contre"] for i in range(1, 6)], axis=1)
        cols[f"{cote}_moy_pour"] = pour.mean(1)
        cols[f"{cote}_moy_contre"] = contre.mean(1)
        cols[f"{cote}_pts"] = np.where(pour > contre, 3, np.where(pour == contre, 1, 0)).mean(1)
        cols[f"{cote}_pts_recent"] = np.where(pour[:, :2] > contre[:, :2], 3, np.where(pour[:, :2] == contre[:, :2], 1, 0)).mean(1)
    cols["diff_attaque"] = cols["dom_moy_pour"] - cols["ext_moy_pour"]
    cols["diff_defense"] = cols["dom_moy_contre"] - cols["ext_moy_contre"]
    cols["diff_pts"] = cols["dom_pts"] - cols["ext_pts"]
    cols["diff_rang"] = d["dom_rang"].to_numpy() - d["ext_rang"].to_numpy()
    derivees = np.stack(list(cols.values()), axis=1)
    ligue = np.stack([(d.ligue.astype(str) == l).to_numpy(float) for l in ligues], axis=1)
    blocs = [d[base].to_numpy(float), derivees, ligue]
    if ratings:
        blocs.append(d[COLS_RATINGS].to_numpy(float))
    return np.hstack(blocs)


def cibles(d, alpha):
    marche = d[CIBLE].to_numpy()
    return (1 - alpha) * np.eye(3)[d.y.astype(int).to_numpy()] + alpha * marche


def cotes_scenario(d, nom):
    return np.stack([SCENARIOS[nom](d, k).to_numpy(float) for k in "hda"], axis=1)


# --- Reseau ---------------------------------------------------------------------------

def creer_reseau(n):
    return nn.Sequential(nn.Linear(n, LARGEUR), nn.ReLU(), nn.Dropout(DROPOUT),
                         nn.Linear(LARGEUR, LARGEUR // 2), nn.ReLU(), nn.Dropout(DROPOUT),
                         nn.Linear(LARGEUR // 2, 3))


def ce_doux(logits, cible):
    return -(cible * torch.log_softmax(logits, dim=1)).sum(1).mean()


def entrainer(x, t, graine, x_val=None, t_val=None, epoques=EPOQUES_MAX):
    """Renvoie (reseau, meilleure epoque sur validation). Cible t = distribution cible (n, 3)."""
    torch.manual_seed(graine)
    net = creer_reseau(x.shape[1])
    opt = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=DECAY)
    n, meilleur, meilleure = len(x), np.inf, epoques
    for ep in range(1, epoques + 1):
        net.train()
        ordre = torch.randperm(n)
        for i in range(0, n, BATCH):
            idx = ordre[i:i + BATCH]
            opt.zero_grad()
            ce_doux(net(x[idx]), t[idx]).backward()
            opt.step()
        if x_val is not None:
            net.eval()
            with torch.no_grad():
                l = ce_doux(net(x_val), t_val).item()
            if l < meilleur:
                meilleur, meilleure = l, ep
    return net, meilleure


def predire(reseaux, x):
    out = []
    for net in reseaux:
        net.eval()
        with torch.no_grad():
            out.append(torch.softmax(net(x), dim=1).numpy())
    return np.mean(out, axis=0)


# --- Paris ----------------------------------------------------------------------------

def marge_depuis_ecart(ecart):
    """cote_modele <= cote_book x (1 - ecart)  <=>  p x cote_book - 1 >= 1 / (1 - ecart) - 1."""
    return 1.0 / (1.0 - ecart) - 1.0


def paris(d_sous, proba, scen, ecart, plafond):
    return ev.paris_possibles(cotes_scenario(d_sous, scen), proba, gains(d_sous), d_sous.date.to_numpy(),
                              COTE_MIN, plafond, marge_depuis_ecart(ecart))


def grille(d_sous, proba, scen):
    """{(ecart, plafond): DataFrame des paris}."""
    return {(e, c): paris(d_sous, proba, scen, e, c) for c in PLAFONDS for e in ECARTS}


def choisir_seuils(d_val, proba_val):
    """(ecart, plafond) au meilleur ROI de validation (>= MIN_PARIS_VALIDATION paris), scenario principal."""
    meilleur, choix, trouve = -np.inf, (0.20, np.inf), False
    for (e, c), p in grille(d_val, proba_val, SCENARIO_PRINCIPAL).items():
        if len(p) >= MIN_PARIS_VALIDATION and ev.roi(p) > meilleur:
            meilleur, choix, trouve = ev.roi(p), (e, c), True
    return choix, (meilleur if trouve else float("nan")), trouve


def fmt_c(c):
    return "sans plafond" if np.isinf(c) else f"<= {c:g}"


# --- Programme principal ----------------------------------------------------------------

def run_arm(d, ligues, alpha, log, ratings=False):
    """Walk-forward complet pour un ALPHA. Renvoie la liste (T, positions, probas, ecart, plafond)."""
    X = torch.tensor(features(d, ligues, ratings), dtype=torch.float32)
    sorties, details = [], []
    for T in SAISONS_TEST:
        i_app = np.where(d.saison_fin <= T - 2)[0]
        i_val = np.where(d.saison_fin == T - 1)[0]
        i_tout = np.where(d.saison_fin <= T - 1)[0]
        i_test = np.where(d.saison_fin == T)[0]
        if not len(i_test):
            continue
        moy, ecart_type = X[i_app].mean(0), X[i_app].std(0) + 1e-6
        norm = lambda idx, m=moy, s=ecart_type: (X[idx] - m) / s
        t = torch.tensor(cibles(d, alpha), dtype=torch.float32)
        essais = [entrainer(norm(i_app), t[i_app], g, norm(i_val), t[i_val]) for g in range(NB_GRAINES)]
        epoques = int(np.median([e for _, e in essais]))
        p_val = predire([n for n, _ in essais], norm(i_val))
        (ecart, plafond), roi_val, trouve = choisir_seuils(d.iloc[i_val], p_val)
        # re-entrainement sur toutes les saisons <= T-1, avec les statistiques de normalisation du nouvel ensemble
        moy2, sd2 = X[i_tout].mean(0), X[i_tout].std(0) + 1e-6
        norm2 = lambda idx: (X[idx] - moy2) / sd2
        reseaux = [entrainer(norm2(i_tout), t[i_tout], g, epoques=epoques)[0] for g in range(NB_GRAINES)]
        p_test = predire(reseaux, norm2(i_test))
        sorties.append((T, i_test, p_test, ecart, plafond))
        details.append((T, epoques, ecart, plafond, roi_val, trouve, len(i_app), len(i_val), len(i_test)))
        log(f"  {'+ratings' if ratings else 'base'} alpha={alpha}  test {T - 1}-{str(T)[2:]} : {len(i_app)} matchs d'entrainement, {epoques} epoques, "
            f"seuils choisis sur validation : ecart {ecart:.0%}, plafond {fmt_c(plafond)}, "
            f"ROI validation {'n/a (trop peu de paris)' if not trouve else f'{100 * roi_val:.1f} %'}")
    return sorties, details


def metriques_arm(d, sorties, scen, ic=True):
    lignes = []
    for T, pos, p_test, ecart, plafond in sorties:
        sous = d.iloc[pos]
        q = paris(sous, p_test, scen, ecart, plafond)
        q["match"] = pos[q.match.to_numpy()]
        q["saison"] = T
        lignes.append(q)
    return pd.concat(lignes, ignore_index=True).sort_values(["date", "match"], kind="stable")


def table_md(lignes, colonnes):
    out = ["| " + " | ".join(colonnes) + " |", "|" + "|".join("---" for _ in colonnes) + "|"]
    out += ["| " + " | ".join(str(l.get(c, "")) for c in colonnes) + " |" for l in lignes]
    return "\n".join(out)


def main():
    sortie = []
    def log(msg=""):
        print(msg)
        sortie.append(msg)

    d = charger_avec_ratings()
    ligues = sorted(d.ligue.astype(str).unique())
    pm = d[CIBLE].to_numpy()
    test_all = d[d.saison_fin.isin(SAISONS_TEST)]
    log(f"# Modele D : predire les cotes du marche a partir des features seules\n")
    log(f"{len(d)} matchs avec cotes, {len(features(d.head(5), ligues)[0])} entrees (sans aucune cote), "
        f"reseau {LARGEUR}-{LARGEUR // 2}, {NB_GRAINES} graines. Tests : {len(test_all)} matchs des saisons "
        f"{', '.join(f'{T - 1}-{str(T)[2:]}' for T in SAISONS_TEST)}.\n")

    log("## Choix faits sur la saison de validation (jamais sur le test)")
    arms = {}
    for ratings in (False, True):
        for alpha in ALPHAS:
            arms[(ratings, alpha)] = run_arm(d, ligues, alpha, log, ratings)
    nom = lambda k: f"D {'+ratings' if k[0] else 'base'} alpha={k[1]}"

    # --- qualite de prediction ---
    from sklearn.metrics import log_loss
    log("\n## Qualite des probabilites sur les saisons de test")
    lignes = []
    for cle, (sorties, _) in arms.items():
        pos = np.concatenate([s[1] for s in sorties])
        p = np.concatenate([s[2] for s in sorties])
        y = d.y.astype(int).to_numpy()[pos]
        lignes.append({"modele (alpha)": nom(cle), "log-loss vs resultats": f"{log_loss(y, p, labels=[0, 1, 2]):.4f}",
                       "ecart moyen au marche (|p - p_marche|)": f"{np.abs(p - pm[pos]).mean():.4f}",
                       "KL vs marche": f"{(pm[pos] * np.log(pm[pos] / p)).sum(1).mean():.4f}"})
    pos0 = np.concatenate([s[1] for s in arms[(False, ALPHAS[0])][0]])
    lignes.append({"modele (alpha)": "marche lui-meme", "log-loss vs resultats":
                   f"{log_loss(d.y.astype(int).to_numpy()[pos0], pm[pos0], labels=[0, 1, 2]):.4f}",
                   "ecart moyen au marche (|p - p_marche|)": "0", "KL vs marche": "0"})
    log(table_md(lignes, list(lignes[0])))

    # --- resultats de paris ---
    log("\n## Resultats de paris hors echantillon (mise = 1/cote, cote proposee > 4)")
    log("alpha = poids du marche dans la cible. ROI = profit / total mise. IC95 par rééchantillonnage des paris. "
        "CLV = mean(cote prise x proba juste de cloture - 1).\n")
    resultats = {}
    for scen in SCENARIOS:
        log(f"### Cote proposee : {scen}")
        lignes = []
        cotes = cotes_scenario(test_all, scen)
        aveugle = ev.paris_possibles(cotes, np.ones_like(cotes), gains(test_all), test_all.date.to_numpy(), COTE_MIN)
        r = ev.resume(aveugle); r["modele"] = "pari a l'aveugle (toute cote > 4)"; lignes.append(r)
        for cle, (sorties, _) in arms.items():
            p = metriques_arm(d, sorties, scen)
            resultats[(cle, scen)] = p
            r = ev.resume(p); r["modele"] = nom(cle)
            r["CLV_%"] = round(100 * ev.clv(p, pm), 1)
            lignes.append(r)
        log(table_md(lignes, ["modele", "paris", "gagnes", "profit", "mises", "roi_%", "ic95_%", "drawdown", "CLV_%"]))
        log("")

    # --- detail par saison, scenario principal ---
    log(f"## Detail par saison ({SCENARIO_PRINCIPAL})")
    for cle in arms:
        lignes = []
        for T, _, _, ecart, plafond in arms[cle][0]:
            q = resultats[(cle, SCENARIO_PRINCIPAL)]
            q = q[q.saison == T]
            r = ev.resume(q, ic=False); r["saison"] = f"{T - 1}-{str(T)[2:]}"
            r["seuils"] = f"ecart {ecart:.0%}, {fmt_c(plafond)}"
            lignes.append(r)
        log(nom(cle))
        log(table_md(lignes, ["saison", "seuils", "paris", "gagnes", "profit", "mises", "roi_%", "drawdown"]))
        log("")

    # --- sensibilite aux seuils (descriptive, pas une selection) ---
    meilleur_alpha = max(arms, key=lambda a: ev.roi(resultats[(a, SCENARIO_PRINCIPAL)]) if len(resultats[(a, SCENARIO_PRINCIPAL)]) else -9)
    log(f"## Sensibilite aux seuils, {nom(meilleur_alpha)} (meilleur ROI du scenario principal), "
        f"memes seuils appliques a toutes les saisons de test. Descriptif uniquement.")
    sorties = arms[meilleur_alpha][0]
    lignes = []
    for plafond in PLAFONDS:
        for ecart in ECARTS:
            lg = []
            for T, pos, p_test, _, _ in sorties:
                sous = d.iloc[pos]
                q = paris(sous, p_test, SCENARIO_PRINCIPAL, ecart, plafond); lg.append(q)
            q = pd.concat(lg)
            lignes.append({"plafond de cote": fmt_c(plafond), "ecart exige": f"{ecart:.0%}", "paris": len(q),
                           "roi_%": round(100 * ev.roi(q), 1) if len(q) else "n/a",
                           "profit": round(q.profit.sum(), 2) if len(q) else 0})
    log(table_md(lignes, ["plafond de cote", "ecart exige", "paris", "roi_%", "profit"]))

    with open(FICHIER_RESULTATS, "w", encoding="utf-8") as f:
        f.write("\n".join(sortie) + "\n")
    print(f"\n(resultats complets dans {FICHIER_RESULTATS})")


if __name__ == "__main__":
    main()
