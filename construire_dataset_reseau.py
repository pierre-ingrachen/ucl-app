"""Construit dataset_reseau.csv : un match joue par ligne (20 championnats nationaux, de
2023-2024 a la saison en cours), avec les 42 features d'entree et les buts reels en sortie.

Etape 1 : telechargement des saisons (cache dans matchs_reseau_bruts.json, une seule fois).
Etape 2 : rejeu chronologique de chaque championnat pour reconstruire le classement et les
5 derniers matchs a la date de chaque rencontre (sans fuite du futur).

Usage : .venv/bin/python construire_dataset_reseau.py [--refresh]
"""
import csv
import json
import os
import sys

import main  # constantes (ligues, saisons) et requete_api_avec_retry (throttling TheSportsDB)
from reseau_buts import EtatChampionnat, noms_features

FICHIER_BRUTS = "matchs_reseau_bruts.json"
FICHIER_DATASET = "dataset_reseau.csv"


SAISONS_ANTERIEURES = ["2023-2024", "2024-2025"]
SAISONS_ANTERIEURES_ANNEE_CIVILE = ["2023", "2024"]  # Norvege, Suede


def saisons_ligue(league_id):
    """Saisons a telecharger, de la plus ancienne a la saison en cours."""
    if league_id in main.DOMESTIC_LEAGUES_ANNEE_CIVILE:
        anterieures = SAISONS_ANTERIEURES_ANNEE_CIVILE
    else:
        anterieures = SAISONS_ANTERIEURES
    return anterieures + main.saisons_passees_ligue(league_id) + [main.saison_actuelle_ligue(league_id)]


def telecharger_matchs():
    """Tous les evenements (joues ou non) de chaque ligue, sur la saison precedente et la courante."""
    brut = {}
    for league_id, nom in main.DOMESTIC_LEAGUES.items():
        brut[league_id] = {}
        for saison in saisons_ligue(league_id):
            url = (f"https://www.thesportsdb.com/api/v1/json/{main.API_KEY}/"
                   f"eventsseason.php?id={league_id}&s={saison}")
            resp = main.requete_api_avec_retry(url)
            resp.raise_for_status()
            evenements = resp.json().get("events") or []
            brut[league_id][saison] = [
                {k: e.get(k) for k in ("idEvent", "dateEvent", "idHomeTeam", "idAwayTeam",
                                       "strHomeTeam", "strAwayTeam", "intHomeScore", "intAwayScore")}
                for e in evenements
            ]
            print(f"{nom} {saison} : {len(evenements)} evenements")
    return brut


def main_build():
    if "--refresh" in sys.argv or not os.path.exists(FICHIER_BRUTS):
        brut = telecharger_matchs()
        with open(FICHIER_BRUTS, "w", encoding="utf-8") as f:
            json.dump(brut, f, ensure_ascii=False)
    else:
        with open(FICHIER_BRUTS, encoding="utf-8") as f:
            brut = json.load(f)

    colonnes = ["ligue", "saison", "date", "equipe_dom", "equipe_ext"] + noms_features() + \
               ["buts_dom", "buts_ext"]
    lignes = []
    for league_id, saisons in brut.items():
        etat = EtatChampionnat()
        for saison, evenements in saisons.items():  # ordre chronologique : precedente puis courante
            etat.changer_saison(saison)
            joues = sorted(
                (e for e in evenements
                 if e["intHomeScore"] is not None and e["intAwayScore"] is not None and e["dateEvent"]),
                key=lambda e: (e["dateEvent"], e["idEvent"]))
            for e in joues:
                dom, ext = e["idHomeTeam"], e["idAwayTeam"]
                buts_dom, buts_ext = int(e["intHomeScore"]), int(e["intAwayScore"])
                x = etat.features(dom, ext)
                if x is not None:
                    lignes.append([league_id, saison, e["dateEvent"], e["strHomeTeam"], e["strAwayTeam"]]
                                  + [round(v, 4) for v in x] + [buts_dom, buts_ext])
                etat.enregistrer(dom, ext, buts_dom, buts_ext)

    with open(FICHIER_DATASET, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(colonnes)
        writer.writerows(lignes)
    print(f"{len(lignes)} matchs ecrits dans {FICHIER_DATASET}")


if __name__ == "__main__":
    main_build()
