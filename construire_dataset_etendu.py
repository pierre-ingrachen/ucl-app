"""Construit dataset_reseau_etendu.csv : comme dataset_reseau.csv mais en remontant jusqu'a la
saison 2020-21 (le football a beaucoup change a partir de cette saison). Sert au nouveau modele
(approche B) ; dataset_reseau.csv et matchs_reseau_bruts.json, utilises par le modele existant,
ne sont jamais modifies.

Les saisons supplementaires sont telechargees dans matchs_reseau_bruts_ext.json, une requete par
(championnat, saison) et seulement celles qui manquent : relancer le script reprend la ou il
s'est arrete (le fichier est ecrit apres chaque requete).

Usage : .venv/bin/python construire_dataset_etendu.py
"""
import csv
import json
import os

import construire_dataset_reseau as base
import main

FICHIER_BRUTS_EXT = "matchs_reseau_bruts_ext.json"
FICHIER_DATASET_ETENDU = "dataset_reseau_etendu.csv"
SAISONS_EXT = ["2020-2021", "2021-2022", "2022-2023"]
SAISONS_EXT_ANNEE_CIVILE = ["2020", "2021", "2022"]  # Norvege, Suede
CHAMPS = ("idEvent", "dateEvent", "idHomeTeam", "idAwayTeam", "strHomeTeam", "strAwayTeam",
          "intHomeScore", "intAwayScore")


def saisons_ext(league_id):
    return SAISONS_EXT_ANNEE_CIVILE if league_id in main.DOMESTIC_LEAGUES_ANNEE_CIVILE else SAISONS_EXT


def _lire(fichier):
    if os.path.exists(fichier):
        with open(fichier, encoding="utf-8") as f:
            return json.load(f)
    return {}


def telecharger_saisons_ext():
    """Complete matchs_reseau_bruts_ext.json avec les (championnat, saison) manquants."""
    ext = _lire(FICHIER_BRUTS_EXT)
    a_faire = [(lid, s) for lid in main.DOMESTIC_LEAGUES for s in saisons_ext(lid)
               if s not in ext.get(lid, {})]
    print(f"{len(a_faire)} requetes TheSportsDB a faire")
    for lid, saison in a_faire:
        url = (f"https://www.thesportsdb.com/api/v1/json/{main.API_KEY}/"
               f"eventsseason.php?id={lid}&s={saison}")
        resp = main.requete_api_avec_retry(url)
        resp.raise_for_status()
        evenements = resp.json().get("events") or []
        ext.setdefault(lid, {})[saison] = [{k: e.get(k) for k in CHAMPS} for e in evenements]
        with open(FICHIER_BRUTS_EXT, "w", encoding="utf-8") as f:
            json.dump(ext, f, ensure_ascii=False)
        print(f"{main.DOMESTIC_LEAGUES[lid]} {saison} : {len(evenements)} evenements")
    return ext


def brut_etendu(ext):
    """Saisons supplementaires puis saisons du cache existant, par ligue (ordre chronologique)."""
    existant = _lire(base.FICHIER_BRUTS)
    return {lid: {**ext.get(lid, {}), **saisons} for lid, saisons in existant.items()}


if __name__ == "__main__":
    brut = brut_etendu(telecharger_saisons_ext())
    colonnes, lignes = base.rejouer_matchs(brut)
    with open(FICHIER_DATASET_ETENDU, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(colonnes)
        writer.writerows(lignes)
    print(f"{len(lignes)} matchs ecrits dans {FICHIER_DATASET_ETENDU}")
