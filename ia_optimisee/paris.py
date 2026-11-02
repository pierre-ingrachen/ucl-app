"""Paris automatiques de l'IA-optimisee, en parallele des autres algorithmes : memes calendrier et cotes
(Winamax, Betclic ou Unibet, cf. odds.py), journal separe (ia_optimisee/journaux/).

Le modele (modele.pkl) est entraine en local sur dataset_cotes.csv puis commite ; GitHub Actions ne le
reentraine jamais (pas de donnees d'entrainement). Marge et plafond de cote sont choisis a l'entrainement
sur les saisons passees (walk-forward, cf. modele.choisir_regle). Pari sur une victoire (domicile ou
exterieure) si cote du bookmaker > 4, <= plafond, et p x cote - 1 > marge. Mise = 1 / cote.

Usage : .venv/bin/python -m ia_optimisee.paris entrainer
        (l'etape `paris` est appelee par paris_reseau.py)
"""
import os
import pickle
import sys
from datetime import date

import pandas as pd

import paris_reseau as pr
from ia_optimisee import modele as ia
from modele_d import entrainement as ent
from modele_d import paris as pd_

FICHIER_MODELE = "ia_optimisee/modele.pkl"
FICHIER_PARIS = "ia_optimisee/journaux/paris.json"
FICHIER_ANALYSES = "ia_optimisee/journaux/analyses.json"  # {idEvent: date}
SCENARIO_CHOIX = "Bet365 cloture -5%"  # hypothese de cote sur laquelle marge et plafond sont choisis
AGE_MAX_JOURS = 21
COTES_DU_MARCHE = {"domicile": "dom", "exterieure": "ext"}


def entrainer_modele():
    d = ent.charger_avec_ratings()
    c = ia.candidats(d)
    p = ia.probas_walk_forward(c, [s for s in sorted(c.saison.unique()) if s >= 2022])
    marge, plafond = ia.choisir_regle(c, p, SCENARIO_CHOIX, int(c.saison.max()) + 1)
    cols = ia.colonnes_modele(c)
    paquet = {"modeles": ia.entrainer(c[cols], c["gagne"]), "cols": cols, "marge": marge, "plafond": plafond,
              "entraine_le": str(date.today()), "nb_candidats": len(c), "derniere_date": d.date.max()}
    with open(FICHIER_MODELE, "wb") as f:
        pickle.dump(paquet, f)
    print(f"IA-optimisee entrainee sur {len(c)} candidats (jusqu'au {paquet['derniere_date']}), "
          f"marge {marge:.0%}, plafond {plafond} -> {FICHIER_MODELE}")
    return paquet


def charger_modele():
    with open(FICHIER_MODELE, "rb") as f:
        paquet = pickle.load(f)
    age = (date.today() - date.fromisoformat(paquet["entraine_le"])).days
    if age > AGE_MAX_JOURS:
        print(f"- Attention : IA-optimisee entrainee il y a {age} jours (reentrainer en local : python -m ia_optimisee.paris entrainer)")
    return paquet


def probas_victoire(paquet, lignes):
    """{'domicile': p, 'exterieure': p} par ligne de features (liste de dicts)."""
    df = pd.DataFrame(lignes)
    sorties = {}
    for issue, cote in COTES_DU_MARCHE.items():
        x = ia.variables(df, cote)[paquet["cols"]]
        sorties[issue] = ia.predire(paquet["modeles"], x)
    return [{i: float(sorties[i][k]) for i in sorties} for k in range(len(df))]


def pari_retenu(paquet, proba, cote):
    return bool(cote and ia.COTE_MIN < cote <= paquet["plafond"] and proba * cote - 1 > paquet["marge"])


def etape_paris_ia(calendrier, cotes, aujourd_hui=None):
    aujourd_hui = aujourd_hui or str(date.today())
    journal = pr._lire_json(FICHIER_PARIS, [])
    analyses = pr._lire_json(FICHIER_ANALYSES, {})
    joues = {e["idEvent"]: e for saisons in calendrier.values() for evs in saisons.values() for e in evs if pr.est_joue(e)}
    pr.resoudre_paris(journal, joues)

    paquet = charger_modele()
    deja = {(p["idEvent"], p["issue"]) for p in journal}
    lignes = pd_.lignes_du_jour(calendrier, cotes, aujourd_hui)
    probas = probas_victoire(paquet, [l for _, _, l in lignes]) if lignes else []
    for (m, c, _), p in zip(lignes, probas):
        analyses[m["idEvent"]] = m["dateEvent"]
        for issue in COTES_DU_MARCHE:
            cote = c.get(issue)
            if (m["idEvent"], issue) in deja or not pari_retenu(paquet, p[issue], cote):
                continue
            journal.append({
                "idEvent": m["idEvent"], "date": m["dateEvent"], "ligue": pr.main.DOMESTIC_LEAGUES[m["idLeague"]],
                "equipeDomicile": m["strHomeTeam"], "equipeExterieur": m["strAwayTeam"],
                "issue": issue, "coteBookmaker": cote, "bookmaker": c["bookmaker"],
                "coteModele": round(1 / p[issue], 2), "probaModele": round(p[issue], 4),
                "mise": round(1 / cote, 4), "statut": "en_attente", "gain": None})
    os.makedirs(os.path.dirname(FICHIER_PARIS), exist_ok=True)
    pr._ecrire_json(FICHIER_PARIS, journal)
    pr._ecrire_json(FICHIER_ANALYSES, analyses)
    resolus = [p for p in journal if p["statut"] != "en_attente"]
    gain, mises = sum(p["gain"] for p in resolus), sum(p["mise"] for p in resolus)
    print(f"## Bilan des paris de l'IA-optimisee — {aujourd_hui}\n")
    print(f"- Matchs analyses aujourd'hui : {len(lignes)}")
    print(f"- Paris resolus : {len(resolus)} ({sum(p['statut'] == 'gagne' for p in resolus)} gagnes)")
    print(f"- Gain net cumule : {gain:+.2f} unites" + (f" (ROI {gain / mises:+.1%})" if mises else ""))
    print(f"- Paris en attente : {sum(p['statut'] == 'en_attente' for p in journal)}\n")
    for p in [p for p in journal if p["date"] == aujourd_hui]:
        print(f"- {p['equipeDomicile']} - {p['equipeExterieur']} ({p['issue']}) : cote {p['bookmaker']} "
              f"{p['coteBookmaker']} vs modele {p['coteModele']}, mise {p['mise']}")


if __name__ == "__main__":
    from ia_optimisee import paris as mod  # le pickle reference ia_optimisee.modele, pas __main__
    if len(sys.argv) > 1 and sys.argv[1] == "entrainer":
        mod.entrainer_modele()
    else:
        sys.exit("Usage : python -m ia_optimisee.paris entrainer")
