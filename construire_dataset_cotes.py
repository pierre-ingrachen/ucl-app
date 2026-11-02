"""Construit dataset_cotes.csv : les matchs de dataset_reseau_etendu.csv (resultat + 42 features
"matchs precedents", sans fuite du futur) pour lesquels football-data.co.uk fournit des cotes.
Un match sans cote est exclu. dataset_reseau.csv reste inchange : ce sont deux jeux distincts.

Rapprochement : meme championnat, date a +/- 1 jour (TheSportsDB est en UTC), noms de clubs
domicile ET exterieur proches (`odds._similaire`). Chaque match n'est rapproche qu'une fois.

Usage : .venv/bin/python construire_dataset_cotes.py [--refresh]
"""
import logging
import sys
from collections import Counter, defaultdict
from datetime import timedelta

import pandas as pd

import cotes_historiques as ch
from odds import _normaliser_nom, _similaire

FICHIER_RESEAU = "dataset_reseau_etendu.csv"  # 2020-21 a aujourd'hui (construire_dataset_etendu.py)
FICHIER_DATASET = "dataset_cotes.csv"
SEUIL_NOM = 0.6

log = logging.getLogger("cotes")

# Noms differents entre football-data et TheSportsDB que la similarite ne rattrape pas
# (clefs : noms normalises par `_normaliser_nom`). Complete a partir du rapport de non-rapprochement.
ALIAS = {
    "mancity": "manchestercity", "manunited": "manchesterunited", "nott'mforest": "nottinghamforest",
    "m'gladbach": "monchengladbach", "borussiamonchengladbach": "monchengladbach",
    "splisbon": "sportingcp", "buyuksehyr": "istanbulbasaksehir", "athenskallithea": "kallithea",
    "waregem": "zultewaregem", "lacoruna": "deportivodeacoruna", "santander": "racingdesantander",
    "oviedo": "realoviedo", "a.lustenau": "austrialustenau", "tirol": "wsgtirol",
    "wsgswarovskitirol": "wsgtirol", "a.klagenfurt": "austriaklagenfurt", "aalborg": "aab",
    "termalicab-b.": "bruk-bettermalicanieciecza", "ham-kam": "hamarkameratene", "reims": "stadedereims", "erzurumbb": "erzurumspor", "admira": "trenkwalderadmira",
    "gornikz.": "gornikzabrze", "leczna": "gornikleczna", "legnica": "miedzlegnica", "hamkam": "hamarkameratene",
}


def _sim(a, b):
    na, nb = _normaliser_nom(a), _normaliser_nom(b)
    return 1.0 if ALIAS.get(na, na) == ALIAS.get(nb, nb) else _similaire(a, b)


def rapprocher(reseau, cotes):
    """Renvoie (paires, cotes_sans_match) : paires = liste (index reseau, index cotes)."""
    par_ligue_date = defaultdict(list)
    for i, r in reseau[["ligue", "date", "equipe_dom", "equipe_ext"]].iterrows():
        par_ligue_date[(str(r.ligue), r.date)].append((i, r.equipe_dom, r.equipe_ext))

    utilises, paires, sans_match = set(), [], []
    for j, c in cotes.iterrows():
        meilleur = None
        for delta in (0, -1, 1):
            date = (c.date + timedelta(days=delta)).strftime("%Y-%m-%d")
            for i, dom, ext in par_ligue_date.get((c.ligue_id, date), ()):
                if i in utilises:
                    continue
                score = min(_sim(c.equipe_dom, dom), _sim(c.equipe_ext, ext))
                if score >= SEUIL_NOM and (meilleur is None or score > meilleur[0]):
                    meilleur = (score, i)
            if meilleur and meilleur[0] == 1.0:
                break
        if meilleur:
            utilises.add(meilleur[1])
            paires.append((meilleur[1], j))
        else:
            sans_match.append(j)
    return paires, sans_match


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    cotes = ch.charger_toutes_les_cotes(force="--refresh" in sys.argv)
    # un match sans aucune cote 1X2 est exclu d'emblee
    cols_1x2 = [f"{p}_{x}" for p in ch.COLS_1X2 for x in "hda"]
    cotes = cotes.dropna(subset=cols_1x2, how="all").reset_index(drop=True)
    reseau = pd.read_csv(FICHIER_RESEAU, dtype={"ligue": str}, low_memory=False)
    log.info("%d matchs avec cotes ; %d matchs dans %s", len(cotes), len(reseau), FICHIER_RESEAU)

    paires, sans_match = rapprocher(reseau, cotes)
    ir, ic = zip(*paires)
    odds = cotes.loc[list(ic)].drop(columns=["ligue_id", "equipe_dom", "equipe_ext", "date"]) \
        .rename(columns={"buts_dom": "fd_buts_dom", "buts_ext": "fd_buts_ext"}).reset_index(drop=True)
    fusion = pd.concat([reseau.loc[list(ir)].reset_index(drop=True), odds], axis=1)

    # controle de coherence : meme score dans les deux sources, sinon le rapprochement est faux
    faux = (fusion.buts_dom != fusion.fd_buts_dom) | (fusion.buts_ext != fusion.fd_buts_ext)
    if faux.any():
        log.warning("%d rapprochements au score different, exclus :\n%s", faux.sum(),
                    fusion.loc[faux, ["ligue", "date", "equipe_dom", "equipe_ext", "buts_dom", "buts_ext",
                                      "fd_buts_dom", "fd_buts_ext"]].head(15).to_string())
    fusion = fusion[~faux].drop(columns=["fd_buts_dom", "fd_buts_ext"]).reset_index(drop=True)
    fusion.to_csv(FICHIER_DATASET, index=False)
    log.info("%d matchs ecrits dans %s", len(fusion), FICHIER_DATASET)

    print(f"\nRapprochement : {len(paires)} matchs, {len(sans_match)} lignes de cotes sans match "
          f"dans {FICHIER_RESEAU}")
    sm = cotes.loc[sans_match]
    print("\nCotes sans match, par ligue (matchs hors dataset_reseau : <5 matchs d'historique, ligue/saison "
          "non telechargee, ou nom de club a ajouter dans ALIAS) :")
    print(Counter(sm["div"]).most_common())
    print("\nMatchs de dataset_reseau.csv par ligue : total -> avec cotes")
    tot, ok = reseau.groupby("ligue").size(), fusion.groupby("ligue").size()
    print(pd.DataFrame({"total": tot, "avec_cotes": ok}).fillna(0).astype(int).to_string())
    ch.resume(fusion)


if __name__ == "__main__":
    main()
