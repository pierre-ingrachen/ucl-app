"""Rejoue les deux nouveaux algorithmes (modele D, IA-optimisee) sur les matchs de la saison
2026-27 deja joues, sans fuite du futur : modeles entraines uniquement sur les matchs AVANT le
2026-07-01, regles de l'IA-optimisee choisies sur les saisons precedentes, features d'avant-match.

Cotes : Winamax n'existe pas dans l'historique. Hypothese de reference = Bet365 a la cloture reduite de
5 % (HYPOTHESE) ; mise = 1 / cote. Ecrit un journal par algorithme (modele_d/journaux/rejeu_2627_*.json,
lu par l'onglet Bilan du site) et un compte rendu (modele_d/resultats/rejeu_2627.md).

Prerequis : .venv/bin/python -m modele_d.rafraichir_donnees (jeux a jour)
Usage : .venv/bin/python -m modele_d.rejeu_2627
"""
import json
import os

import numpy as np
import pandas as pd

import torch
from sklearn.model_selection import train_test_split

import main as app
from entrainer_reseau import entrainer as entrainer_reseau, predire as predire_reseau
from reseau_buts import noms_features, probas_1n2
from ia_optimisee import modele as ia
from modele_d import entrainement as D
from modele_d import paris as pd_

DEBUT = "2026-07-01"
HYPOTHESES = {"Bet365 cloture -5%": ("b365c", 0.95), "Moyenne cloture": ("avgc", 1.0), "Meilleure cote cloture": ("maxc", 1.0)}
HYPOTHESE = "Bet365 cloture -5%"
LIBELLE_COTE = "Bet365 clôture −5 % (estimée)"
DOSSIER = "modele_d/journaux"
FICHIER_MD = "modele_d/resultats/rejeu_2627.md"
DEBUT_DIRECT_RESEAU = "2026-10-09"  # premier jour du journal en direct du reseau (cache_analyses_reseau.json)
CONFIG_RESEAU = {"largeur": 32, "nb_couches": 4, "dropout": 0.2, "weight_decay": 0.01}  # = reseau_buts.pt
COTE_MIN_RESEAU, ECART_RESEAU = 4.0, 0.15  # = paris_reseau.py
ISSUES = {"domicile": ("h", "H"), "exterieure": ("a", "A")}


def cote(d, issue, hyp):
    col, f = HYPOTHESES[hyp]
    return ia.arrondi_bookmaker(d[f"{col}_{ISSUES[issue][0]}"] * f)


def paris_modele_d(p, d_test, hyp):
    """`p` : probabilites 1/N/2 de l'ensemble (entraine une seule fois) pour les matchs de d_test."""
    c = cote(d_test, "exterieure", hyp).to_numpy()
    k = [pd_.pari_retenu(p[i, 2], c[i]) for i in range(len(d_test))]
    return pd.DataFrame({"i": d_test.index[k], "issue": "exterieure"})


def paris_ia(c, p, hyp):
    """`c`, `p` : candidats et probabilites hors echantillon (ia_optimisee), calcules une seule fois."""
    marge, plafond = ia.choisir_regle(c, p, hyp, 2027)
    k = (c.saison == 2027) & p.notna() & ia.selection(c, p.fillna(0), hyp, marge, plafond)
    return pd.DataFrame({"i": c.loc[k, "match"], "issue": c.loc[k, "issue"].map({"dom": "domicile", "ext": "exterieure"})}), (marge, plafond)


def probas_reseau(d_train, d_test):
    """Reseau de buts d'origine (memes hyperparametres, 5 graines) reentraine sur les matchs AVANT le rejeu
    (reseau_buts.pt a vu 2026-27 dans son split aleatoire) : probabilites 1/N/2 par loi de Poisson."""
    torch.set_num_threads(4)
    noms = noms_features()
    x, y = d_train[noms].to_numpy(np.float32), d_train[["buts_dom", "buts_ext"]].to_numpy(np.float32)
    m, e = x.mean(0), x.std(0) + 1e-6
    xf, xv, yf, yv = train_test_split(((x - m) / e).astype(np.float32), y, test_size=0.1, random_state=42)
    reseaux = [entrainer_reseau(xf, yf, xv, yv, CONFIG_RESEAU, 42 + i)[0] for i in range(5)]
    return probas_1n2(predire_reseau(reseaux, ((d_test[noms].to_numpy(np.float32) - m) / e).astype(np.float32)))


def paris_reseau(p, d_test, hyp):
    """Regle de paris_reseau.py : cote > 4 et cote du modele (1/proba) au moins 15 % sous celle du bookmaker."""
    lignes = []
    for issue, k in (("domicile", 0), ("exterieure", 2)):
        c = cote(d_test, issue, hyp).to_numpy()
        ok = (c > COTE_MIN_RESEAU) & (1 / p[:, k] <= c * (1 - ECART_RESEAU))
        lignes += [{"i": i, "issue": issue} for i in d_test.index[ok]]
    return pd.DataFrame(lignes, columns=["i", "issue"])


def journal(d, paris, hyp):
    out = []
    for _, b in paris.iterrows():
        r = d.loc[b.i]
        c = float(cote(d.loc[[b.i]], b.issue, hyp).iloc[0])
        gagne = r.resultat == ISSUES[b.issue][1]
        mise = round(1 / c, 4)
        out.append({"idEvent": f"rejeu|{r.date}|{r.equipe_dom}|{r.equipe_ext}", "date": r.date,
                    "ligue": app.DOMESTIC_LEAGUES.get(str(r.ligue), str(r.ligue)),
                    "equipeDomicile": r.equipe_dom, "equipeExterieur": r.equipe_ext, "issue": b.issue,
                    "coteBookmaker": round(c, 2), "bookmaker": LIBELLE_COTE, "mise": mise,
                    "statut": "gagne" if gagne else "perdu", "gain": round(mise * (c - 1), 4) if gagne else -mise,
                    "source": "historique"})
    return sorted(out, key=lambda p: p["date"])


def stats(j):
    if not j:
        return dict(paris=0)
    mise = np.array([p["mise"] for p in j]); gain = np.array([p["gain"] for p in j])
    idx = np.random.default_rng(0).integers(0, len(j), (2000, len(j)))
    ro = gain[idx].sum(1) / mise[idx].sum(1)
    return dict(paris=len(j), gagnes=sum(p["statut"] == "gagne" for p in j), mises=round(mise.sum(), 2),
                profit=round(gain.sum(), 2), ROI=f"{gain.sum() / mise.sum():+.1%}",
                IC95=f"[{np.percentile(ro, 2.5):+.0%} ; {np.percentile(ro, 97.5):+.0%}]")


def tableau(lignes):
    cols = list(next(r for _, r in lignes if r.get("paris")).keys())
    s = "| " + " | ".join(["", *cols]) + " |\n|" + "---|" * (len(cols) + 1) + "\n"
    return s + "".join("| " + " | ".join([str(n), *[str(r.get(c, "")) for c in cols]]) + " |\n" for n, r in lignes)


def main():
    d = D.charger_avec_ratings()
    d_train, d_test = d[d.date < DEBUT], d[d.date >= DEBUT]
    print(f"entrainement : {len(d_train)} matchs avant {DEBUT} ; rejeu : {len(d_test)} matchs jusqu'au {d_test.date.max()}")
    md = [f"# Rejeu 2026-27 (matchs du {DEBUT} au {d_test.date.max()}, {len(d_test)} matchs avec cotes)\n",
          "Modeles entraines uniquement sur les matchs avant le 2026-07-01 ; mise = 1/cote ; cotes de reference : "
          f"{LIBELLE_COTE} (Winamax absent de l'historique).\n"]
    paquet = pd_.entrainer_ensemble(d_train, ecrire=False)
    p_d = pd_.probas_ensemble(paquet, d_test)
    c_ia = ia.candidats(d)
    p_ia = ia.probas_walk_forward(c_ia, [s for s in sorted(c_ia.saison.unique()) if s >= 2022])
    p_r = probas_reseau(d_train, d_test)
    resultats = {}
    for hyp in HYPOTHESES:
        resultats[hyp] = {"modele_d": paris_modele_d(p_d, d_test, hyp),
                          "reseau": paris_reseau(p_r, d_test, hyp)}
        resultats[hyp]["ia_optimisee"], resultats[hyp]["regle_ia"] = paris_ia(c_ia, p_ia, hyp)
    json_noms = {"reseau": "Réseau de buts", "modele_d": "Modèle D", "ia_optimisee": "IA-optimisée"}
    lignes_md = {}
    for hyp in HYPOTHESES:
        lignes_md[hyp] = []
        for algo in json_noms:
            lignes_md[hyp].append((json_noms[algo], stats(journal(d, resultats[hyp][algo], hyp))))
        aveugle = pd.concat([pd.DataFrame({"i": d_test.index[cote(d_test, i, hyp) > 4], "issue": i}) for i in ISSUES])
        lignes_md[hyp].append(("Pari à l'aveugle (cote > 4)", stats(journal(d, aveugle, hyp))))
    for algo in json_noms:
        j = journal(d, resultats[HYPOTHESE][algo], HYPOTHESE)
        if algo == "reseau":  # le journal en direct du reseau prend le relais
            j = [p for p in j if p["date"] < DEBUT_DIRECT_RESEAU]
        os.makedirs(DOSSIER, exist_ok=True)
        with open(f"{DOSSIER}/rejeu_2627_{algo}.json", "w", encoding="utf-8") as f:
            json.dump(j, f, ensure_ascii=False, indent=1)
        print(algo, stats(j))
    # matchs reellement passes dans chaque algorithme : tous pour le modele D, ceux ayant au moins un candidat
    # (victoire dom./ext. a cote moyenne >= 3,3) pour l'IA
    analyses = {"reseau": int((d_test.date < DEBUT_DIRECT_RESEAU).sum()), "modele_d": int(len(d_test)),
                "ia_optimisee": int(c_ia.loc[(c_ia.saison == 2027) & p_ia.notna(), "match"].nunique())}
    with open(f"{DOSSIER}/rejeu_2627_meta.json", "w", encoding="utf-8") as f:
        json.dump({"matchs": int(len(d_test)), "jusqu_au": d_test.date.max(), "cotes": LIBELLE_COTE, "analyses": analyses}, f, ensure_ascii=False)
    for hyp in HYPOTHESES:
        md += [f"\n## Hypothèse de cote : {hyp}\n", tableau(lignes_md[hyp])]
    md.append(f"\nIA-optimisée : marge {resultats[HYPOTHESE]['regle_ia'][0]:.0%}, plafond de cote {resultats[HYPOTHESE]['regle_ia'][1]} "
              f"(choisis sur les saisons avant 2026-27).\n")
    open(FICHIER_MD, "w").write("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
