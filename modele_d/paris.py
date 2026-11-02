"""Paris automatiques du modele D, en parallele du reseau existant (paris_reseau.py) : memes cotes
Winamax / Betclic / Unibet (cache_cotes_winamax.json), journal separe (modele_d/journaux/paris.json).

Le modele D predit les probabilites du marche (1/N/2) a partir des seules features des matchs (forme,
Elo, buts, repos : aucune cote en entree). Ensemble de 11 modeles (logit, gradient boosting, reseaux),
entraine sur modele_d/donnees/dataset_cotes.csv (28 000 matchs, 2020-21 a aujourd'hui).

Regle de pari (REGLE) : victoire exterieure, cote Winamax dans ]4, 6] et cote du modele au moins 20 %
sous la cote du bookmaker (p x cote - 1 >= 0,25). Mise = 1 / cote. Regle choisie sur les saisons
2023-24 a 2026-27 : elle n'est PAS confirmee statistiquement (voir CLAUDE.md), ce paper-trading sert
justement a la tester sur de vraies cotes Winamax.

Journal d'analyses (modele_d/journaux/analyses.json) : pour CHAQUE match analyse, probabilites du modele,
cotes du bookmaker et resultat final, pour pouvoir evaluer d'autres regles sur de vraies cotes.

Usage : .venv/bin/python -m modele_d.paris [entrainer | paris | bilan]
  entrainer : (re)entraine l'ensemble (2 min) et l'ecrit dans modele_d/ressources/modele.pkl
  paris     : resout les paris, analyse les matchs du jour (reentraine si le modele a > 7 jours)
  bilan     : affiche le bilan sans rien telecharger
"""
import os
import pickle
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from modele_d import entrainement as D
from modele_d import experiences as X
from modele_d import historique as ext
from modele_d import ratings as cr
import paris_reseau as pr
from reseau_buts import EtatChampionnat, noms_features

FICHIER_MODELE = "modele_d/ressources/modele.pkl"
FICHIER_PARIS = "modele_d/journaux/paris.json"
FICHIER_ANALYSES = "modele_d/journaux/analyses.json"
AGE_MAX_MODELE_JOURS = 7
REGLE = {"issue": "exterieure", "cote_min": 4.0, "cote_max": 6.0, "ecart_min": 0.20}
NOMS_ISSUES = ["domicile", "nul", "exterieure"]
ENSEMBLE = [("logit", "ratings+xg", "avgc", 1.0), ("logit", "ratings+xg", "avgc", 0.5),
            ("hgb", "ratings+xg", "avgc", 1.0), ("hgb", "ratings+xg", "avgc", 0.5), ("hgb", "ratings+xg", "avgc", 0.0),
            ("hgb", "ratings+xg", "psc", 1.0), ("hgb", "ratings", "avgc", 0.5),
            ("mlp", "ratings+xg", "avgc", 1.0), ("mlp", "ratings+xg", "avgc", 0.5), ("mlp", "ratings", "avgc", 0.5),
            ("mlp", "ratings+xg", "psc", 0.5)]
GRAINES = 3


# --- Entrainement ---------------------------------------------------------------------------

class PredicteurReseaux:
    def __init__(self, nets):
        self.nets = nets

    def __call__(self, Xn):
        return D.predire(self.nets, torch.tensor(Xn, dtype=torch.float32))


class PredicteurSklearn:
    def __init__(self, m):
        self.m = m

    def __call__(self, Xn):
        return self.m.predict_proba(Xn)


def _ajuster(modele, Xs, tgt, saison, derniere_complete):
    """Ajuste un modele sur toutes les lignes et renvoie un predicteur appelable : proba = predicteur(Xs_nouveau)."""
    if modele == "mlp":
        x, t = torch.tensor(Xs, dtype=torch.float32), torch.tensor(tgt, dtype=torch.float32)
        app, val = np.where(saison <= derniere_complete - 1)[0], np.where(saison == derniere_complete)[0]
        essais = [D.entrainer(x[app], t[app], g, x[val], t[val]) for g in range(GRAINES)]
        epoques = int(np.median([e for _, e in essais]))
        nets = [D.entrainer(x, t, g, epoques=epoques)[0] for g in range(GRAINES)]
        return PredicteurReseaux(nets)
    n = len(Xs)
    Xr, yr = np.vstack([Xs] * 3), np.repeat([0, 1, 2], n)
    wr = np.concatenate([tgt[:, k] for k in range(3)])
    m = (HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.04, l2_regularization=10.0,
                                        min_samples_leaf=200, random_state=0)
         if modele == "hgb" else LogisticRegression(C=0.05, max_iter=3000))
    m.fit(Xr, yr, sample_weight=wr)
    return PredicteurSklearn(m)


def entrainer_ensemble(d=None, ecrire=True):
    """`d` : jeu d'entrainement (defaut : tout le jeu) ; ecrire=False pour un rejeu sans toucher modele.pkl."""
    d = D.charger_avec_ratings() if d is None else d
    ligues = sorted(d.ligue.astype(str).unique())
    saison = d.saison_fin.to_numpy()
    derniere_complete = int(saison.max()) - 1  # la saison en cours (partielle) ne sert pas a choisir les epoques
    membres = []
    t0 = time.time()
    for cfg in ENSEMBLE:
        modele, jeu, tgt_nom, alpha = cfg
        Xb = X.matrice_features(d, ligues, jeu)
        sc = StandardScaler().fit(Xb)
        proba = _ajuster(modele, sc.transform(Xb), X.cible(d, tgt_nom, alpha), saison, derniere_complete)
        membres.append({"cfg": cfg, "scaler": sc, "proba": proba})
        print(f"  [{time.time() - t0:4.0f}s] {cfg}")
    paquet = {"membres": membres, "ligues": ligues, "entraine_le": str(date.today()), "nb_matchs": len(d),
              "derniere_date": d.date.max()}
    if ecrire:
        with open(FICHIER_MODELE, "wb") as f:
            pickle.dump(paquet, f)
        print(f"Ensemble de {len(membres)} modeles entraine sur {len(d)} matchs (jusqu'au {paquet['derniere_date']}) -> {FICHIER_MODELE}")
    return paquet


def charger_ensemble():
    """Charge le modele (modele_d/ressources/modele.pkl). Reentraine s'il a plus de AGE_MAX_MODELE_JOURS jours, sauf si la variable
    d'environnement MODELE_D_FIGE est definie (GitHub Actions : pas de donnees d'entrainement, le
    modele est reentraine en local puis commite)."""
    if os.path.exists(FICHIER_MODELE):
        age_j = (time.time() - os.path.getmtime(FICHIER_MODELE)) / 86400
        if age_j <= AGE_MAX_MODELE_JOURS or os.environ.get("MODELE_D_FIGE"):
            if age_j > AGE_MAX_MODELE_JOURS:
                print(f"- Attention : modele D vieux de {age_j:.0f} jours (reentrainer en local : python -m modele_d.paris entrainer)")
            with open(FICHIER_MODELE, "rb") as f:
                return pickle.load(f)
        print(f"Modele vieux de {age_j:.0f} jours : reentrainement")
    return entrainer_ensemble()


# --- Features des matchs a venir -----------------------------------------------------------------

def etats_courants(calendrier):
    """Rejoue chaque championnat (2020-21 -> aujourd'hui) : (EtatChampionnat, EtatRatings) par ligue."""
    etendu = ext.brut_etendu(ext._lire(ext.FICHIER_BRUTS_EXT))
    etats = {}
    for lid in pr.main.DOMESTIC_LEAGUES:
        saisons = {**etendu.get(lid, {}), **calendrier.get(lid, {})}
        champ, rat = EtatChampionnat(), cr.EtatRatings()
        for saison, evenements in saisons.items():
            champ.changer_saison(saison)
            rat.nouvelle_saison()
            for e in sorted((e for e in evenements if pr.est_joue(e) and e["dateEvent"]),
                            key=lambda e: (e["dateEvent"], e["idEvent"])):
                gd, ge = int(e["intHomeScore"]), int(e["intAwayScore"])
                champ.enregistrer(e["idHomeTeam"], e["idAwayTeam"], gd, ge)
                rat.enregistrer(e["idHomeTeam"], e["idAwayTeam"], gd, ge, date.fromisoformat(e["dateEvent"]))
        etats[lid] = (champ, rat)
    return etats


def probas_ensemble(paquet, lignes):
    """Probabilites 1/N/2 moyennes de l'ensemble pour des lignes de features (DataFrame)."""
    sorties = []
    for m in paquet["membres"]:
        _, jeu, _, _ = m["cfg"]
        Xn = m["scaler"].transform(X.matrice_features(lignes, paquet["ligues"], jeu))
        sorties.append(m["proba"](Xn))
    return np.mean(sorties, axis=0)


# --- Paris ---------------------------------------------------------------------------------------

def pari_retenu(proba, cote):
    """Vrai si la regle de pari est satisfaite pour cette issue (cote du bookmaker, proba du modele)."""
    return bool(cote and REGLE["cote_min"] < cote <= REGLE["cote_max"]
                and 1 - 1 / (proba * cote) >= REGLE["ecart_min"])


def resoudre(journal, analyses, joues):
    for pari in journal:
        e = joues.get(pari["idEvent"])
        if pari["statut"] != "en_attente" or not e:
            continue
        gd, ge = int(e["intHomeScore"]), int(e["intAwayScore"])
        pari["statut"] = "gagne" if NOMS_ISSUES[0 if gd > ge else 2 if gd < ge else 1] == pari["issue"] else "perdu"
        pari["gain"] = round(pari["mise"] * (pari["coteBookmaker"] - 1), 4) if pari["statut"] == "gagne" else -pari["mise"]
    for id_event, a in analyses.items():
        e = joues.get(id_event)
        if e and a.get("resultat") is None:
            gd, ge = int(e["intHomeScore"]), int(e["intAwayScore"])
            a["resultat"] = NOMS_ISSUES[0 if gd > ge else 2 if gd < ge else 1]


def lignes_du_jour(calendrier, cotes, jour, etats=None, ligues=None):
    """[(match, cotes_bookmaker, ligne de features)] pour les matchs de `jour` ayant une cote : 42 features +
    ratings d'AVANT le match (aucune cote). Les features n'utilisent que les matchs deja joues dans `calendrier`
    (a tronquer pour un rejeu). `ligues` : ne garder que ces championnats (defaut : tous)."""
    etats = etats or etats_courants(calendrier)
    sortie = []
    for m in pr.matchs_a_venir(calendrier, jour, jour):
        c = cotes.get(m["idEvent"])
        if not c or not c.get("bookmaker") or (ligues is not None and m["idLeague"] not in ligues):
            continue
        champ, rat = etats[m["idLeague"]]
        x = champ.features(m["idHomeTeam"], m["idAwayTeam"])
        if x is None:
            continue
        ligne = dict(zip(noms_features(), x))
        ligne["ligue"] = m["idLeague"]
        ligne.update(zip(D.COLS_RATINGS, rat.ligne(m["idHomeTeam"], m["idAwayTeam"], date.fromisoformat(m["dateEvent"]))))
        sortie.append((m, c, ligne))
    return sortie


def probas_du_jour(calendrier, cotes, paquet, jour, etats=None):
    """[(match, cotes_bookmaker, probas 1/N/2 du modele)] pour les matchs de `jour` ayant une cote."""
    lignes = lignes_du_jour(calendrier, cotes, jour, etats, ligues=paquet["ligues"])
    if not lignes:
        return []
    probas = probas_ensemble(paquet, pd.DataFrame([l for _, _, l in lignes]))
    return [(m, c, p) for (m, c, _), p in zip(lignes, probas)]


def etape_paris_d(calendrier, cotes, aujourd_hui=None):
    """Analyse les matchs du jour. `calendrier` et `cotes` viennent de paris_reseau (aucun appel API ici)."""
    aujourd_hui = aujourd_hui or str(date.today())
    journal = pr._lire_json(FICHIER_PARIS, [])
    analyses = pr._lire_json(FICHIER_ANALYSES, {})
    joues = {e["idEvent"]: e for saisons in calendrier.values() for evs in saisons.values() for e in evs if pr.est_joue(e)}
    resoudre(journal, analyses, joues)

    paquet = charger_ensemble()
    deja = {(p["idEvent"], p["issue"]) for p in journal}
    analyses_du_jour = probas_du_jour(calendrier, cotes, paquet, aujourd_hui)
    for m, c, p in analyses_du_jour:
        analyses[m["idEvent"]] = {
            "date": m["dateEvent"], "ligue": pr.main.DOMESTIC_LEAGUES[m["idLeague"]],
            "equipeDomicile": m["strHomeTeam"], "equipeExterieur": m["strAwayTeam"],
            "probas": [round(float(v), 4) for v in p], "bookmaker": c["bookmaker"],
            "cotes": [c.get("domicile"), c.get("nul"), c.get("exterieure")], "resultat": None}
        k = NOMS_ISSUES.index(REGLE["issue"])
        cote = c.get(REGLE["issue"])
        if (m["idEvent"], REGLE["issue"]) not in deja and pari_retenu(p[k], cote):
            journal.append({
                "idEvent": m["idEvent"], "date": m["dateEvent"], "ligue": pr.main.DOMESTIC_LEAGUES[m["idLeague"]],
                "equipeDomicile": m["strHomeTeam"], "equipeExterieur": m["strAwayTeam"],
                "issue": REGLE["issue"], "coteBookmaker": cote, "bookmaker": c["bookmaker"],
                "coteModele": round(1 / float(p[k]), 2), "probaModele": round(float(p[k]), 4),
                "mise": round(1 / cote, 4), "statut": "en_attente", "gain": None})
    os.makedirs(os.path.dirname(FICHIER_PARIS), exist_ok=True)  # dossier absent d'un depot fraichement clone
    pr._ecrire_json(FICHIER_PARIS, journal)
    pr._ecrire_json(FICHIER_ANALYSES, analyses)
    bilan(journal, analyses, len(analyses_du_jour), aujourd_hui)


def bilan(journal, analyses, nb_analyses=None, aujourd_hui=None):
    aujourd_hui = aujourd_hui or str(date.today())
    resolus = [p for p in journal if p["statut"] != "en_attente"]
    gain, mises = sum(p["gain"] for p in resolus), sum(p["mise"] for p in resolus)
    print(f"## Bilan des paris du modele D — {aujourd_hui}\n")
    if nb_analyses is not None:
        print(f"- Matchs analyses aujourd'hui : {nb_analyses}")
    print(f"- Matchs analyses depuis le debut : {len(analyses)} ({sum(a.get('resultat') is not None for a in analyses.values())} resolus)")
    print(f"- Paris resolus : {len(resolus)} ({sum(p['statut'] == 'gagne' for p in resolus)} gagnes)")
    print(f"- Gain net cumule : {gain:+.2f} unites" + (f" (ROI {gain / mises:+.1%})" if mises else ""))
    print(f"- Paris en attente : {sum(p['statut'] == 'en_attente' for p in journal)}\n")
    for p in [p for p in journal if p["date"] == aujourd_hui]:
        print(f"- {p['equipeDomicile']} - {p['equipeExterieur']} ({p['issue']}) : cote {p['bookmaker']} "
              f"{p['coteBookmaker']} vs modele {p['coteModele']}, mise {p['mise']}")


if __name__ == "__main__":
    # On passe par l'import du module : les classes sauvegardees dans modele_d.pkl s'appellent
    # alors modele_d.paris.X (et non __main__.X), et le modele se recharge depuis n'importe ou.
    from modele_d import paris as mod
    etape = sys.argv[1] if len(sys.argv) > 1 else "paris"
    if etape == "entrainer":
        mod.entrainer_ensemble()
    elif etape == "bilan":
        mod.bilan(pr._lire_json(FICHIER_PARIS, []), pr._lire_json(FICHIER_ANALYSES, {}))
    elif etape == "paris":
        calendrier = pr.charger_calendrier()
        mod.etape_paris_d(calendrier, pr._lire_json(pr.FICHIER_COTES, {}).get("data", {}))
    else:
        sys.exit(f"Etape inconnue : {etape!r} (entrainer, paris ou bilan)")
