"""Entraine le reseau de buts sur dataset_reseau.csv.

Split 80/20 melange (le jeu de test n'est utilise qu'une fois, a la fin). Les
hyperparametres sont choisis par validation croisee sur le jeu d'entrainement uniquement.
Usage : .venv/bin/python entrainer_reseau.py
"""
import itertools
import json

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import KFold, train_test_split

from reseau_buts import ReseauButs, estimer_rho, noms_features, probas_1n2

SEED = 42
torch.set_num_threads(4)
GRILLE = {
    "largeur": [32, 64],
    "nb_couches": [4, 5],
    "dropout": [0.2, 0.4],
    "weight_decay": [1e-3, 1e-2],
}


def perte_poisson(lam, y):
    return (lam - y * torch.log(lam)).mean()


def entrainer(X_tr, y_tr, X_val, y_val, config, seed, max_epoques=300, patience=25):
    """Entraine un reseau avec early stopping sur la perte de validation ; renvoie le meilleur."""
    torch.manual_seed(seed)
    modele = ReseauButs(X_tr.shape[1], config["largeur"], config["nb_couches"], config["dropout"])
    opt = torch.optim.AdamW(modele.parameters(), lr=1e-3, weight_decay=config["weight_decay"])
    X_tr, y_tr = torch.tensor(X_tr), torch.tensor(y_tr)
    X_val, y_val = torch.tensor(X_val), torch.tensor(y_val)
    meilleur, etat, sans_progres = float("inf"), None, 0
    for _ in range(max_epoques):
        modele.train()
        perm = torch.randperm(len(X_tr))
        for i in range(0, len(perm), 128):
            idx = perm[i:i + 128]
            opt.zero_grad()
            perte_poisson(modele(X_tr[idx]), y_tr[idx]).backward()
            opt.step()
        modele.eval()
        with torch.no_grad():
            perte_val = perte_poisson(modele(X_val), y_val).item()
        if perte_val < meilleur - 1e-4:
            meilleur, sans_progres = perte_val, 0
            etat = {k: v.clone() for k, v in modele.state_dict().items()}
        else:
            sans_progres += 1
            if sans_progres >= patience:
                break
    modele.load_state_dict(etat)
    modele.eval()
    return modele, meilleur


def predire(modeles, X):
    """Moyenne des taux de buts d'un ensemble de reseaux."""
    with torch.no_grad():
        return np.mean([m(torch.tensor(X)).numpy() for m in modeles], axis=0)


def classe_1n2(probas, seuil_nul):
    """Argmax des probabilites, sauf match serre (|P(dom)-P(ext)| < seuil) predit nul."""
    pred = probas.argmax(axis=1)
    pred[np.abs(probas[:, 0] - probas[:, 2]) < seuil_nul] = 1
    return pred


def resultat_reel(y):
    return np.where(y[:, 0] > y[:, 1], 0, np.where(y[:, 0] == y[:, 1], 1, 2))


def main():
    df = pd.read_csv("dataset_reseau.csv")
    X = df[noms_features()].to_numpy(np.float32)
    y = df[["buts_dom", "buts_ext"]].to_numpy(np.float32)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEED, shuffle=True)
    moyenne, ecart = X_tr.mean(axis=0), X_tr.std(axis=0) + 1e-6
    norm = lambda a: ((a - moyenne) / ecart).astype(np.float32)
    X_tr, X_te = norm(X_tr), norm(X_te)
    print(f"entrainement : {len(X_tr)} matchs, test : {len(X_te)} matchs")

    # 1) choix des hyperparametres par validation croisee (jeu de test non touche)
    resultats = []
    for valeurs in itertools.product(*GRILLE.values()):
        config = dict(zip(GRILLE, valeurs))
        pertes, bons = [], []
        for tr, va in KFold(5, shuffle=True, random_state=SEED).split(X_tr):
            modele, perte = entrainer(X_tr[tr], y_tr[tr], X_tr[va], y_tr[va], config, SEED)
            pertes.append(perte)
            bons.append((classe_1n2(probas_1n2(predire([modele], X_tr[va])), 0) == resultat_reel(y_tr[va])).mean())
        resultats.append((np.mean(pertes), np.mean(bons), config))
        print(f"{config} -> perte CV {np.mean(pertes):.4f}, 1N2 CV {np.mean(bons):.3f}", flush=True)
    perte_cv, _, config = min(resultats, key=lambda r: r[0])
    print("meilleure config :", config, f"(perte CV {perte_cv:.4f})")

    # 2) ensemble de 5 reseaux (seeds differentes) sur 90 % / 10 % du jeu d'entrainement
    X_fit, X_val, y_fit, y_val = train_test_split(X_tr, y_tr, test_size=0.1, random_state=SEED)
    modeles = [entrainer(X_fit, y_fit, X_val, y_val, config, SEED + i)[0] for i in range(5)]

    # seuil "match serre => nul" calibre sur la validation uniquement
    p_val = probas_1n2(predire(modeles, X_val))
    seuils = np.arange(0, 0.3, 0.01)
    seuil_nul = max(seuils, key=lambda s: (classe_1n2(p_val, s) == resultat_reel(y_val)).mean())

    # rho de Dixon-Coles estime sur l'entrainement uniquement
    rho = estimer_rho(predire(modeles, X_tr), y_tr)
    print(f"rho Dixon-Coles : {rho:.4f}")

    # 3) evaluation finale, une seule fois, sur le test
    lam = predire(modeles, X_te)
    p_te = probas_1n2(lam)
    reel = resultat_reel(y_te)
    moyenne_buts = y_tr.mean(axis=0)
    print(f"\n=== TEST ({len(X_te)} matchs) ===")
    print(f"1N2 reseau (argmax)        : {(classe_1n2(p_te, 0) == reel).mean():.3f}")
    print(f"1N2 reseau (seuil nul {seuil_nul:.2f})  : {(classe_1n2(p_te, seuil_nul) == reel).mean():.3f}")
    p_dc = probas_1n2(lam, rho=rho)
    log_loss = lambda p: -np.log(p[np.arange(len(reel)), reel]).mean()
    print(f"nuls : reels {(reel == 1).mean():.3f} | Poisson {p_te[:, 1].mean():.3f} | Dixon-Coles {p_dc[:, 1].mean():.3f}")
    print(f"log-loss 1N2 : Poisson {log_loss(p_te):.4f} | Dixon-Coles {log_loss(p_dc):.4f}")
    print(f"1N2 Dixon-Coles (argmax)   : {(classe_1n2(p_dc, 0) == reel).mean():.3f}")
    print(f"1N2 baseline 'toujours dom': {(reel == 0).mean():.3f}")
    print(f"MAE buts reseau   : {np.abs(lam - y_te).mean():.3f}")
    print(f"MAE buts baseline : {np.abs(moyenne_buts - y_te).mean():.3f} (moyenne constante)")
    print(f"perte Poisson reseau/baseline : {perte_poisson(torch.tensor(lam), torch.tensor(y_te)).item():.4f}"
          f" / {perte_poisson(torch.tensor(np.tile(moyenne_buts, (len(y_te), 1))), torch.tensor(y_te)).item():.4f}")
    print(f"exemple : prevu {lam[0].round(2)} reel {y_te[0]}")

    torch.save({"etats": [m.state_dict() for m in modeles], "config": config,
                "moyenne": moyenne, "ecart": ecart, "seuil_nul": float(seuil_nul), "rho": rho,
                "noms_features": noms_features()}, "reseau_buts.pt")
    print("modele sauvegarde dans reseau_buts.pt")


if __name__ == "__main__":
    main()
