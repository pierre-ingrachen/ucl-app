"""Features et modele du reseau de neurones de prediction de buts.

Partage entre la construction du dataset (construire_dataset_reseau.py), l'entrainement
(entrainer_reseau.py) et, plus tard, les predictions de l'app : une seule definition des
features, pour que l'entrainement et la prediction voient exactement les memes entrees.
"""
from collections import defaultdict, deque

NB_MATCHS = 5  # matchs d'historique par equipe
RANG_PROMU = 0.8  # rang normalise (0 = leader, 1 = dernier) d'une equipe sans classement connu
CHAMPS_MATCH = ["buts_pour", "buts_contre", "rang_adv", "domicile"]


def noms_features():
    noms = []
    for cote in ("dom", "ext"):
        for i in range(1, NB_MATCHS + 1):  # 1 = match le plus recent
            noms += [f"{cote}_m{i}_{c}" for c in CHAMPS_MATCH]
    return noms + ["dom_rang", "ext_rang"]


class EtatChampionnat:
    """Etat d'un championnat rejoue chronologiquement : classement de la saison en cours
    et 5 derniers matchs de chaque equipe (saisons precedentes incluses, ce qui complete
    le debut de saison)."""

    def __init__(self):
        self.historique = defaultdict(lambda: deque(maxlen=NB_MATCHS))
        self.saison = None
        self.tableau = {}  # equipe -> [points, buts_pour, buts_contre, matchs]
        self.rang_final_precedent = {}  # equipe -> rang normalise en fin de saison precedente

    def _classement(self):
        """Rang normalise (0 = leader, 1 = dernier) des equipes ayant deja joue cette saison."""
        ordre = sorted(
            (e for e, t in self.tableau.items() if t[3] > 0),
            key=lambda e: (-self.tableau[e][0] / self.tableau[e][3],
                           -(self.tableau[e][1] - self.tableau[e][2]) / self.tableau[e][3],
                           -self.tableau[e][1] / self.tableau[e][3]),
        )
        n = len(ordre)
        return {e: (i / (n - 1) if n > 1 else 0.5) for i, e in enumerate(ordre)}

    def rang(self, equipe, classement=None):
        classement = classement if classement is not None else self._classement()
        if equipe in classement:
            return classement[equipe]
        return self.rang_final_precedent.get(equipe, RANG_PROMU)

    def changer_saison(self, saison):
        if self.saison is not None:
            self.rang_final_precedent = self._classement()
        self.saison = saison
        self.tableau = {}

    def features(self, dom, ext):
        """Vecteur d'entree d'un match a venir (None si une equipe a < 5 matchs d'historique)."""
        if len(self.historique[dom]) < NB_MATCHS or len(self.historique[ext]) < NB_MATCHS:
            return None
        classement = self._classement()
        vecteur = []
        for equipe in (dom, ext):
            for m in reversed(self.historique[equipe]):
                vecteur += [m["buts_pour"], m["buts_contre"], m["rang_adv"], m["domicile"]]
        return vecteur + [self.rang(dom, classement), self.rang(ext, classement)]

    def enregistrer(self, dom, ext, buts_dom, buts_ext):
        """Ajoute un match joue a l'etat (apres en avoir extrait les features)."""
        classement = self._classement()
        rang_dom, rang_ext = self.rang(dom, classement), self.rang(ext, classement)
        self.historique[dom].append(
            {"buts_pour": buts_dom, "buts_contre": buts_ext, "rang_adv": rang_ext, "domicile": 1})
        self.historique[ext].append(
            {"buts_pour": buts_ext, "buts_contre": buts_dom, "rang_adv": rang_dom, "domicile": 0})
        for equipe, pour, contre in ((dom, buts_dom, buts_ext), (ext, buts_ext, buts_dom)):
            t = self.tableau.setdefault(equipe, [0, 0, 0, 0])
            t[0] += 3 if pour > contre else 1 if pour == contre else 0
            t[1] += pour
            t[2] += contre
            t[3] += 1


# --- Modele (PyTorch) -------------------------------------------------------------------

import numpy as np
import torch
from torch import nn
from scipy.stats import poisson


class ReseauButs(nn.Module):
    """MLP dense : features -> (buts attendus domicile, buts attendus exterieur).
    La sortie est un taux de Poisson (softplus => toujours > 0), entraine par vraisemblance
    de Poisson, plus adaptee au comptage de buts qu'une erreur quadratique."""

    def __init__(self, nb_entrees, largeur=64, nb_couches=4, dropout=0.2):
        super().__init__()
        couches, n = [], nb_entrees
        for _ in range(nb_couches):
            couches += [nn.Linear(n, largeur), nn.ReLU(), nn.Dropout(dropout)]
            n = largeur
        couches.append(nn.Linear(n, 2))
        self.reseau = nn.Sequential(*couches)

    def forward(self, x):
        return nn.functional.softplus(self.reseau(x)) + 1e-3


def grille_scores(lambdas, max_buts=10, rho=0.0):
    """P(buts_dom = i, buts_ext = j) pour chaque match : (n, max_buts+1, max_buts+1),
    loi de Poisson pour chaque equipe (taux donnes par le reseau), avec la correction de
    Dixon-Coles de parametre rho sur les scores 0-0, 1-0, 0-1 et 1-1 (rho = 0 : Poisson pur)."""
    k = np.arange(max_buts + 1)
    p_dom = poisson.pmf(k[None, :], lambdas[:, :1])
    p_ext = poisson.pmf(k[None, :], lambdas[:, 1:])
    grille = p_dom[:, :, None] * p_ext[:, None, :]
    if rho:
        l_dom, l_ext = lambdas[:, 0], lambdas[:, 1]
        grille[:, 0, 0] *= np.maximum(1 - l_dom * l_ext * rho, 1e-6)
        grille[:, 1, 0] *= np.maximum(1 + l_ext * rho, 1e-6)
        grille[:, 0, 1] *= np.maximum(1 + l_dom * rho, 1e-6)
        grille[:, 1, 1] *= np.maximum(1 - rho, 1e-6)
    return grille / grille.sum(axis=(1, 2), keepdims=True)  # renormalise la queue tronquee


def estimer_rho(lambdas, buts):
    """rho de Dixon-Coles par maximum de vraisemblance des scores reels observes."""
    from scipy.optimize import minimize_scalar
    idx = np.arange(len(buts))
    i, j = np.minimum(buts[:, 0].astype(int), 10), np.minimum(buts[:, 1].astype(int), 10)

    def nll(rho):
        return -np.log(grille_scores(lambdas, rho=rho)[idx, i, j]).sum()

    return float(minimize_scalar(nll, bounds=(-0.1, 0.1), method="bounded").x)


def probas_1n2(lambdas, max_buts=10, rho=0.0):
    """P(victoire dom, nul, victoire ext) pour des taux de buts (n, 2)."""
    grille = grille_scores(lambdas, max_buts, rho)
    nul = np.trace(grille, axis1=1, axis2=2)
    dom = np.tril(grille, -1).sum(axis=(1, 2))  # buts_dom > buts_ext
    ext = np.triu(grille, 1).sum(axis=(1, 2))
    return np.stack([dom, nul, ext], axis=1)


def cotes_match(lam_dom, lam_ext, nb_scores=3, rho=0.0):
    """Cotes 'justes' (1 / probabilite, sans marge de bookmaker) d'un match a partir des
    buts attendus du reseau : 1N2, double chance, plus/moins de 2,5 buts, les deux equipes
    marquent, et les scores exacts les plus probables."""
    grille = grille_scores(np.array([[lam_dom, lam_ext]]), rho=rho)[0]
    n = grille.shape[0]
    i, j = np.indices((n, n))
    probas = {
        "1": grille[i > j].sum(), "N": grille[i == j].sum(), "2": grille[i < j].sum(),
        "1N": grille[i >= j].sum(), "N2": grille[i <= j].sum(), "12": grille[i != j].sum(),
        "plus_2.5": grille[i + j > 2].sum(), "moins_2.5": grille[i + j <= 2].sum(),
        "btts_oui": grille[(i > 0) & (j > 0)].sum(), "btts_non": grille[(i == 0) | (j == 0)].sum(),
    }
    meilleurs = np.argsort(grille, axis=None)[::-1][:nb_scores]
    scores = {f"{a}-{b}": grille[a, b] for a, b in zip(*np.unravel_index(meilleurs, grille.shape))}
    return {
        "buts_attendus": (float(lam_dom), float(lam_ext)),
        "probas": {k: float(v) for k, v in probas.items()},
        "cotes": {k: round(float(1 / v), 2) for k, v in probas.items()},
        "scores_probables": {k: {"proba": float(v), "cote": round(float(1 / v), 1)} for k, v in scores.items()},
    }


def charger_modele(chemin="reseau_buts.pt"):
    """Charge l'ensemble de reseaux sauvegarde par entrainer_reseau.py."""
    ck = torch.load(chemin, weights_only=False)
    cfg = ck["config"]
    modeles = []
    for etat in ck["etats"]:
        m = ReseauButs(len(ck["noms_features"]), cfg["largeur"], cfg["nb_couches"], cfg["dropout"])
        m.load_state_dict(etat)
        m.eval()
        modeles.append(m)
    return modeles, ck


def predire_lambdas(modeles, ck, X):
    """Buts attendus (n, 2) d'un ensemble de reseaux pour des features brutes (non normalisees)."""
    X = ((np.asarray(X, np.float32) - ck["moyenne"]) / ck["ecart"]).astype(np.float32)
    with torch.no_grad():
        return np.mean([m(torch.tensor(X)).numpy() for m in modeles], axis=0)
