"""Suivi de la regle "marche recalibre" : parametres figes, paris rejoues et journalises.

Regle : sur chaque issue (1, N, 2) dont la meilleure cote de cloture est > COTE_MIN, on parie
si proba recalibree x meilleure cote > 1 + MARGE (mise = 1/cote). La proba recalibree vient d'une
regression logistique qui ne prend que les probas implicites du marche (cotes moyennes de cloture,
marge retiree) : aucune statistique de forme.

Commandes :
  .venv/bin/python -m modele_d.suivi_regle figer   # entraine sur les matchs AVANT le 2026-07-01, ecrit regle_figee.json
  .venv/bin/python -m modele_d.suivi_regle bilan   # rejoue la regle figee sur les matchs depuis le 2026-07-01

Le fichier de parametres est fige : `figer` refuse de l'ecraser (supprimer le fichier a la main pour
repartir de zero). Phase "retro" = matchs joues avant la date de gel (la regle a ete choisie en
connaissant une partie de ces matchs) ; phase "direct" = matchs apres la date de gel (vrai test).
"""
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from modele_d import cotes_historiques

log = logging.getLogger("suivi_regle")

COTE_MIN = 4.0
MARGE = 0.05
DEBUT_SAISON = "2026-07-01"  # les matchs a partir de cette date ne servent jamais a l'entrainement
FICHIER_REGLE = os.path.join("modele_d", "ressources", "regle_figee.json")
FICHIER_JOURNAL = os.path.join("modele_d", "journaux", "suivi_regle.json")
FICHIER_BILAN = os.path.join("modele_d", "resultats", "suivi_regle.md")
ISSUES = ("h", "d", "a")
NOMS_ISSUE = {"h": "1 (domicile)", "d": "N (nul)", "a": "2 (exterieur)"}


def _caracteristiques(df):
    """Log-ratios des probas du marche (cotes moyennes de cloture, marge retiree)."""
    p = df[["p_avgc_h", "p_avgc_d", "p_avgc_a"]].to_numpy()
    return np.column_stack([np.log(p[:, 0] / p[:, 1]), np.log(p[:, 2] / p[:, 1])])


def figer(date_gel=None):
    if os.path.exists(FICHIER_REGLE):
        raise SystemExit(f"{FICHIER_REGLE} existe deja : regle figee, non modifiee.")
    cotes = cotes_historiques.charger_toutes_les_cotes()
    train = cotes[(cotes["date"] < DEBUT_SAISON) & cotes["resultat"].isin(["H", "D", "A"])
                  & cotes["p_avgc_h"].notna() & cotes["p_avgc_d"].notna() & cotes["p_avgc_a"].notna()]
    X, y = _caracteristiques(train), train["resultat"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=0.5, max_iter=500).fit(sc.transform(X), y)
    params = {
        "date_gel": date_gel or date.today().isoformat(), "cote_min": COTE_MIN, "marge": MARGE,
        "entrainement": {"avant": DEBUT_SAISON, "matchs": int(len(train))},
        "moyenne": sc.mean_.tolist(), "ecart_type": sc.scale_.tolist(),
        "coef": lr.coef_.tolist(), "intercept": lr.intercept_.tolist(),
    }
    params["empreinte"] = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    with open(FICHIER_REGLE, "w") as f:
        json.dump(params, f, indent=2)
    log.info("regle figee le %s sur %d matchs (empreinte %s)", params["date_gel"], len(train), params["empreinte"][:12])


def charger_regle():
    with open(FICHIER_REGLE) as f:
        params = json.load(f)
    verif = {k: v for k, v in params.items() if k != "empreinte"}
    if hashlib.sha256(json.dumps(verif, sort_keys=True).encode()).hexdigest() != params["empreinte"]:
        raise SystemExit("regle_figee.json a ete modifie : empreinte invalide.")
    return params


def probas_recalibrees(df, params):
    """Probas (h, d, a) recalibrees, tableau n x 3."""
    z = (_caracteristiques(df) - np.array(params["moyenne"])) / np.array(params["ecart_type"])
    with np.errstate(all="ignore"):  # BLAS macOS : faux avertissements "divide by zero" dans matmul (verifie : valeurs finies)
        logits = z @ np.array(params["coef"]).T + np.array(params["intercept"])
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def paris(df, params):
    """Un pari par (match, issue) qui remplit la regle. `df` : cotes du schema commun, avec p_avgc_*."""
    df = df[df["p_avgc_h"].notna() & df["p_avgc_d"].notna() & df["p_avgc_a"].notna()].reset_index(drop=True)
    p = probas_recalibrees(df, params)
    lignes = []
    for k, issue in enumerate(ISSUES):
        cote = df[f"maxc_{issue}"].to_numpy()
        ok = (cote > params["cote_min"]) & (p[:, k] * cote > 1 + params["marge"])
        for i in np.flatnonzero(ok):
            r = df.iloc[i]
            gagne = None if r["resultat"] not in ("H", "D", "A") else r["resultat"].lower() == issue
            lignes.append({
                "id": f"{r['date']:%Y-%m-%d}|{r['equipe_dom']}|{r['equipe_ext']}|{issue}",
                "date": f"{r['date']:%Y-%m-%d}", "ligue": r["div"] if "div" in r else "",
                "equipe_dom": r["equipe_dom"], "equipe_ext": r["equipe_ext"], "issue": issue,
                "cote_max": float(cote[i]),
                "cote_moyenne": None if pd.isna(r[f"avgc_{issue}"]) else float(r[f"avgc_{issue}"]),
                "cote_b365c": None if pd.isna(r[f"b365c_{issue}"]) else float(r[f"b365c_{issue}"]),
                "p_marche": float(r[f"p_avgc_{issue}"]), "p_modele": float(p[i, k]),
                "gagne": gagne, "score": f"{r['buts_dom']:.0f}-{r['buts_ext']:.0f}" if gagne is not None else None,
            })
    return lignes


def _roi(df, colonne):
    """(paris, gagnes, profit, mises, roi %) avec mise = 1/cote ; les paris sans cote sont ignores."""
    d = df[df[colonne].notna()]
    if d.empty:
        return 0, 0, 0.0, 0.0, float("nan")
    mise = 1 / d[colonne]
    gain = np.where(d["gagne"], 1 - mise, -mise)
    return len(d), int(d["gagne"].sum()), float(gain.sum()), float(mise.sum()), float(gain.sum() / mise.sum() * 100)


def _ic(df, colonne="cote_max", n=2000):
    d = df[df[colonne].notna()]
    if len(d) < 10:
        return float("nan"), float("nan")
    mise = (1 / d[colonne]).to_numpy()
    gain = np.where(d["gagne"], 1 - mise, -mise)
    rng = np.random.default_rng(0)
    b = []
    for _ in range(n):
        i = rng.integers(0, len(d), len(d))
        b.append(gain[i].sum() / mise[i].sum() * 100)
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def bilan():
    params = charger_regle()
    cotes = cotes_historiques.charger_toutes_les_cotes()
    nouveaux = cotes[(cotes["date"] >= DEBUT_SAISON) & cotes["resultat"].isin(["H", "D", "A"])]
    journal = []
    if os.path.exists(FICHIER_JOURNAL):
        with open(FICHIER_JOURNAL) as f:
            journal = json.load(f)
    connus = {p["id"] for p in journal}
    ajoutes = 0
    maintenant = datetime.now().isoformat(timespec="seconds")
    for p in paris(nouveaux, params):
        if p["id"] not in connus:  # un pari deja journalise n'est jamais modifie
            p["phase"] = "retro" if p["date"] <= params["date_gel"] else "direct"
            p["ajoute_le"] = maintenant
            journal.append(p)
            ajoutes += 1
    with open(FICHIER_JOURNAL, "w") as f:
        json.dump(journal, f, indent=1, ensure_ascii=False)
    log.info("%d paris ajoutes au journal (%d au total), %d matchs rejoues", ajoutes, len(journal), len(nouveaux))
    ecrire_bilan(pd.DataFrame(journal), params, len(nouveaux), nouveaux["date"].max())


def _ligne(nom, df, ic=True):
    n, g, profit, mises, roi = _roi(df, "cote_max")
    if n == 0:
        return f"| {nom} | 0 | 0 | | | | |"
    lo, hi = _ic(df)
    return f"| {nom} | {n} | {g} | {profit:+.2f} | {mises:.2f} | {roi:+.1f} % | [{lo:+.1f} ; {hi:+.1f}] |"


def ecrire_bilan(j, params, nb_matchs, dernier):
    L = [f"# Suivi de la regle « marche recalibre » (genere le {date.today()})", "",
         f"- Regle figee le **{params['date_gel']}** (empreinte `{params['empreinte'][:12]}`), entrainee sur {params['entrainement']['matchs']} "
         f"matchs joues avant le {params['entrainement']['avant']}.",
         f"- Pari sur une issue si meilleure cote de cloture > {params['cote_min']} et proba recalibree x cote > {1 + params['marge']:.2f} ; mise = 1/cote.",
         f"- {nb_matchs} matchs rejoues depuis le {DEBUT_SAISON} (dernier match : {dernier:%Y-%m-%d}).",
         "- Phase `retro` = matchs avant la date de gel : la marge (0,05) a ete choisie en regardant des saisons dont celle-ci faisait partie, "
         "donc ces paris ne sont pas un test propre. Phase `direct` = matchs apres le gel : vrai test.",
         "- Les cotes sont celles de football-data.co.uk (meilleure cote de cloture parmi les bookmakers) : a verifier que l'on peut les obtenir.", ""]
    if j.empty:
        L.append("Aucun pari pour l'instant.")
    else:
        j = j.copy()
        en_cours = j["gagne"].isna()
        j = j[~en_cours]
        en_tete = ["| | Paris | Gagnes | Profit | Mises | ROI | IC95 |", "|---|---|---|---|---|---|---|"]
        L += ["## ROI a la meilleure cote (mise = 1/cote)", ""] + en_tete
        L.append(_ligne("**Tous les paris**", j))
        for ph, nom in (("retro", "Phase retro (avant gel)"), ("direct", "Phase directe (apres gel)")):
            L.append(_ligne(nom, j[j["phase"] == ph]))
        for k in ISSUES:
            L.append(_ligne(f"Issue {NOMS_ISSUE[k]}", j[j["issue"] == k]))
        L += ["", "## Memes paris a d'autres prix", "", "| Cote supposee | Paris | Gagnes | Profit | Mises | ROI |", "|---|---|---|---|---|---|"]
        for nom, col in (("Meilleure cote", "cote_max"), ("Cote moyenne du marche", "cote_moyenne"), ("Bet365 cloture", "cote_b365c")):
            n, g, pr, mi, roi = _roi(j, col)
            L.append(f"| {nom} | {n} | {g} | {pr:+.2f} | {mi:.2f} | {roi:+.1f} % |")
        j["mois"] = j["date"].str[:7]
        L += ["", "## Par mois", "", "| Mois | Paris | Gagnes | Profit | Mises | ROI |", "|---|---|---|---|---|---|"]
        for m, d in j.groupby("mois"):
            n, g, pr, mi, roi = _roi(d, "cote_max")
            L.append(f"| {m} | {n} | {g} | {pr:+.2f} | {mi:.2f} | {roi:+.1f} % |")
        L += ["", "## Liste des paris", "", "| Date | Match | Issue | Cote max | Cote moy. | Proba modele | Proba marche | Score | Resultat | Phase |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in j.sort_values("date").iterrows():
            moy = "" if pd.isna(r["cote_moyenne"]) else f"{r['cote_moyenne']:.2f}"
            L.append(f"| {r['date']} | {r['equipe_dom']} - {r['equipe_ext']} | {NOMS_ISSUE[r['issue']]} | {r['cote_max']:.2f} | {moy} | "
                     f"{r['p_modele']*100:.1f} % | {r['p_marche']*100:.1f} % | {r['score']} | {'gagne' if r['gagne'] else 'perdu'} | {r['phase']} |")
    with open(FICHIER_BILAN, "w") as f:
        f.write("\n".join(L) + "\n")
    log.info("bilan ecrit dans %s", FICHIER_BILAN)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    commande = sys.argv[1] if len(sys.argv) > 1 else "bilan"
    {"figer": figer, "bilan": bilan}[commande]()
