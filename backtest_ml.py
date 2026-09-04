"""Backtest temporel glissant du modèle d'apprentissage (`modele_ml.py`),
comparé au modèle de rating existant (`rating.py`) et aux références naïves.

Protocole strict « train sur le passé, teste sur le futur » : pour chaque date
de coupure, on entraîne sur tous les matchs antérieurs et on évalue sur les
~3 mois suivants. Aucune information postérieure à la coupure n'entre dans
l'entraînement (features déjà causales, poids temporel recalé sur la coupure).

Métriques 1X2 : log-loss et score de Brier (les deux comptent la calibration,
pas seulement l'ordre). Métriques buts : MAE / RMSE. Plus une table de
calibration sur l'ensemble des prédictions ML hors échantillon.

Pas de ROI ici : nous n'avons pas d'historique de cotes bookmaker. La
comparaison de rentabilité des deux modèles se fera en conditions réelles via
les deux journaux de paris.
"""

import math
from collections import defaultdict
from datetime import date

import numpy as np

import rating
from dataset_ml import construire_dataset, _charger_matchs
from modele_ml import ModeleML

ISSUES = ("domicile", "nul", "exterieure")


def _issue_reelle(yh, ya):
    return "domicile" if yh > ya else ("exterieure" if yh < ya else "nul")


def _logloss(p, issue):
    return -math.log(max(p[issue], 1e-12))


def _brier(p, issue):
    return sum((p[i] - (1.0 if i == issue else 0.0)) ** 2 for i in ISSUES)


# ---------------------------------------------------------------------------
# Référence : modèle de rating existant, reconstruit sur la même fenêtre.
# ---------------------------------------------------------------------------
def _record_brut(m):
    return {
        "idHomeTeam": m["homeId"], "idAwayTeam": m["awayId"],
        "intHomeScore": m["homeGoals"], "intAwayScore": m["awayGoals"],
        "strHomeCountry": m["homePays"], "strAwayCountry": m["awayPays"],
        "dateEvent": m["date"],
    }


def _predicteur_rating(matchs_bruts, cutoff_str):
    passe = [m for m in matchs_bruts if m["date"] < cutoff_str]
    par_id = {m["idEvent"]: m for m in matchs_bruts}
    europe = [_record_brut(m) for m in passe if m["typeCompetition"] == "europe"]
    modele_eu = rating.construire_modele(europe)

    par_ligue = defaultdict(list)
    for m in passe:
        if m["typeCompetition"] == "championnat":
            par_ligue[m["leagueId"]].append(_record_brut(m))
    modeles_dom = {lid: rating.construire_modele_championnat(recs)
                   for lid, recs in par_ligue.items() if len(recs) >= 200}

    def predire(ligne):
        m = par_id.get(ligne["idEvent"])
        if m is None:
            return None
        if m["typeCompetition"] == "europe":
            r = rating.predire_resultat(modele_eu, m["homeId"], m["awayId"],
                                        m["homePays"], m["awayPays"])
        else:
            mod = modeles_dom.get(m["leagueId"])
            if mod is None:
                return None
            r = rating.predire_resultat(mod, m["homeId"], m["awayId"], "", "")
        return {"domicile": r["probaVictoireDomicile"], "nul": r["probaNul"],
                "exterieure": r["probaVictoireExterieure"]}

    return predire


# ---------------------------------------------------------------------------
def _cutoffs():
    annees_mois = [(a, mo) for a in (2024, 2025, 2026) for mo in (2, 5, 8, 11)]
    return [date(a, mo, 1) for a, mo in annees_mois
            if date(2024, 8, 1) <= date(a, mo, 1) <= date(2026, 9, 1)]


def _fin_fold(cutoff):
    mo = cutoff.month + 3
    a = cutoff.year + (mo - 1) // 12
    return date(a, (mo - 1) % 12 + 1, 1)


def backtest():
    matchs_bruts = _charger_matchs()
    base_taux = {"domicile": 0.0, "nul": 0.0, "exterieure": 0.0}

    agg = {nom: defaultdict(float)
           for nom in ("ml", "rating", "ensemble", "taux_base", "toujours_dom")}
    calib = defaultdict(lambda: [0.0, 0.0])  # bucket -> [somme_proba, nb_realisations]
    calib_n = defaultdict(int)

    for cutoff in _cutoffs():
        cutoff_str = cutoff.isoformat()
        fin_str = _fin_fold(cutoff).isoformat()
        ref_ord = cutoff.toordinal()

        lignes = construire_dataset(ref_ordinal=ref_ord)
        train = [l for l in lignes if l["date"] < cutoff_str]
        test = [l for l in lignes if cutoff_str <= l["date"] < fin_str]
        if len(test) < 50 or len(train) < 2000:
            continue

        # Taux de base observés sur le train (référence naïve).
        cnt = defaultdict(int)
        for l in train:
            cnt[_issue_reelle(l["yHome"], l["yAway"])] += 1
        tot = sum(cnt.values())
        taux = {i: cnt[i] / tot for i in ISSUES}

        modele = ModeleML().entrainer(train)
        preds_ml = modele.predire_lot(test)
        predire_rating = _predicteur_rating(matchs_bruts, cutoff_str)

        n_rating = 0
        for l, p_ml in zip(test, preds_ml):
            issue = _issue_reelle(l["yHome"], l["yAway"])

            agg["ml"]["ll"] += _logloss(p_ml, issue)
            agg["ml"]["brier"] += _brier(p_ml, issue)
            agg["ml"]["acc"] += (max(ISSUES, key=lambda i: p_ml[i]) == issue)
            agg["ml"]["mae"] += abs(p_ml["lambdaDomicile"] - l["yHome"]) + abs(p_ml["lambdaExterieure"] - l["yAway"])
            agg["ml"]["se"] += (p_ml["lambdaDomicile"] - l["yHome"]) ** 2 + (p_ml["lambdaExterieure"] - l["yAway"]) ** 2
            agg["ml"]["n"] += 1
            agg["ml"]["ngoals"] += 2

            for i in ISSUES:
                b = round(p_ml[i], 1)
                calib[b][0] += p_ml[i]
                calib[b][1] += (1.0 if i == issue else 0.0)
                calib_n[b] += 1

            agg["taux_base"]["ll"] += _logloss(taux, issue)
            agg["taux_base"]["brier"] += _brier(taux, issue)
            agg["taux_base"]["n"] += 1

            td = {"domicile": 1 - 2e-12, "nul": 1e-12, "exterieure": 1e-12}
            agg["toujours_dom"]["ll"] += _logloss(td, issue)
            agg["toujours_dom"]["acc"] += (issue == "domicile")
            agg["toujours_dom"]["n"] += 1

            p_rt = predire_rating(l)
            if p_rt is not None:
                agg["rating"]["ll"] += _logloss(p_rt, issue)
                agg["rating"]["brier"] += _brier(p_rt, issue)
                agg["rating"]["acc"] += (max(ISSUES, key=lambda i: p_rt[i]) == issue)
                agg["rating"]["n"] += 1
                n_rating += 1

                g = {i: math.sqrt(max(p_ml[i], 1e-12) * max(p_rt[i], 1e-12)) for i in ISSUES}
                s = sum(g.values())
                pe = {i: g[i] / s for i in ISSUES}
                agg["ensemble"]["ll"] += _logloss(pe, issue)
                agg["ensemble"]["brier"] += _brier(pe, issue)
                agg["ensemble"]["acc"] += (max(ISSUES, key=lambda i: pe[i]) == issue)
                agg["ensemble"]["n"] += 1

        print(f"{cutoff_str} → {fin_str} : train {len(train):>5}, test {len(test):>4}, "
              f"rating couvert {n_rating:>4}")

    def ligne(nom):
        a = agg[nom]
        n = a["n"] or 1
        out = f"{nom:>13} | n={int(a['n']):>5} | logloss {a['ll']/n:.4f}"
        if a["brier"]:
            out += f" | brier {a['brier']/n:.4f}"
        if a["acc"]:
            out += f" | acc {a['acc']/n:.3f}"
        if a["ngoals"]:
            out += f" | MAE buts {a['mae']/a['ngoals']:.3f} | RMSE {math.sqrt(a['se']/a['ngoals']):.3f}"
        return out

    print("\n=== Résultats hors échantillon (agrégé sur tous les folds) ===")
    for nom in ("ml", "rating", "ensemble", "taux_base", "toujours_dom"):
        print(ligne(nom))

    print("\n=== Calibration ML (proba prédite vs fréquence observée) ===")
    for b in sorted(calib):
        somme, real = calib[b]
        n = calib_n[b]
        if n >= 30:
            print(f"  p≈{b:.1f} : prédit {somme/n:.3f} | observé {real/n:.3f} | n={n}")


if __name__ == "__main__":
    backtest()
