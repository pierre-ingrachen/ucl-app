"""Mesure de performance d'une strategie de paris (partagee par le nouveau modele et, plus tard,
la comparaison avec le modele existant).

Regle de mise du projet : mise = 1 / cote, donc un pari gagne rapporte 1 unite brute.
Pour un pari de cote c : mise 1/c ; profit = 1 - 1/c s'il est gagne, -1/c sinon.
ROI = profit total / mises totales.
"""
import numpy as np
import pandas as pd

ISSUES = ("h", "d", "a")


def paris_possibles(cotes, probas, gains, dates, cote_min=4.0, cote_max=np.inf, marge=0.0):
    """Paris pris par la regle `p_modele x cote - 1 > marge` avec cote_min < cote <= cote_max.
    cotes, probas, gains : tableaux (n_matchs, 3) pour les issues 1 / N / 2 ; gains = 1 si l'issue
    s'est realisee. Renvoie un DataFrame (une ligne par pari), trie par date."""
    n = len(cotes)
    cote = np.asarray(cotes, float).ravel()
    p = np.asarray(probas, float).ravel()
    gagne = np.asarray(gains, float).ravel()
    match = np.repeat(np.arange(n), 3)
    issue = np.tile(np.arange(3), n)
    valeur = p * cote - 1.0
    garde = np.isfinite(cote) & (cote > cote_min) & (cote <= cote_max) & (valeur > marge)
    mise = 1.0 / cote[garde]
    df = pd.DataFrame({
        "match": match[garde], "issue": issue[garde], "cote": cote[garde], "p": p[garde],
        "valeur": valeur[garde], "mise": mise, "gagne": gagne[garde],
        "profit": gagne[garde] - mise, "date": np.asarray(dates)[match[garde]],
    })
    return df.sort_values(["date", "match", "issue"], kind="stable").reset_index(drop=True)


def roi(paris):
    return float(paris.profit.sum() / paris.mise.sum()) if len(paris) else float("nan")


def roi_bootstrap(paris, n=2000, seed=0):
    """Intervalle de confiance a 95 % du ROI (rechantillonnage des paris)."""
    if len(paris) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    profit, mise = paris.profit.to_numpy(), paris.mise.to_numpy()
    idx = rng.integers(0, len(paris), size=(n, len(paris)))
    rois = profit[idx].sum(axis=1) / mise[idx].sum(axis=1)
    return float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5))


def drawdown_max(paris):
    """Pire baisse du cumul de profit (en unites), paris pris dans l'ordre chronologique."""
    if not len(paris):
        return 0.0
    cumul = paris.profit.cumsum().to_numpy()
    return float((np.maximum.accumulate(np.maximum(cumul, 0)) - cumul).max())


def resume(paris, ic=True):
    """Dictionnaire de metriques d'un ensemble de paris."""
    r = {"paris": len(paris), "gagnes": int(paris.gagne.sum()) if len(paris) else 0,
         "profit": round(float(paris.profit.sum()), 2) if len(paris) else 0.0,
         "mises": round(float(paris.mise.sum()), 2) if len(paris) else 0.0,
         "roi_%": round(100 * roi(paris), 1), "drawdown": round(drawdown_max(paris), 2)}
    if ic:
        bas, haut = roi_bootstrap(paris)
        r["ic95_%"] = f"[{100 * bas:.1f} ; {100 * haut:.1f}]"
    return r


def clv(paris, p_cloture):
    """CLV moyen : valeur du pari mesuree avec la probabilite 'juste' de cloture,
    mean(cote_prise x p_cloture - 1). Moins bruite que le ROI : un CLV > 0 indique un vrai avantage.
    p_cloture : tableau (n_matchs, 3) des probabilites de cloture sans marge."""
    if not len(paris):
        return float("nan")
    p = np.asarray(p_cloture)[paris.match.to_numpy(), paris.issue.to_numpy()]
    return float((paris.cote.to_numpy() * p - 1).mean())
