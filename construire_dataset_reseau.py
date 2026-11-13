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

import main  # constantes (ligues, saisons)
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
    """TheSportsDB n'est plus utilise (abonnement resilie) : matchs_reseau_bruts.json est fige, la saison en
    cours se met a jour par `calendrier/` (paris_reseau.charger_calendrier). Garde-fou explicite."""
    raise SystemExit("--refresh n'existe plus : TheSportsDB est retire. Les saisons passees sont figees dans "
                     "matchs_reseau_bruts.json ; la saison en cours vient de calendrier/ (ESPN, football-data).")


def rejouer_matchs(brut):
    """Rejoue chronologiquement chaque championnat de `brut` ({ligue -> {saison -> evenements}},
    saisons de la plus ancienne a la plus recente) et renvoie (colonnes, lignes) du dataset."""
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
    return colonnes, lignes


def main_build():
    if "--refresh" in sys.argv or not os.path.exists(FICHIER_BRUTS):
        brut = telecharger_matchs()
        with open(FICHIER_BRUTS, "w", encoding="utf-8") as f:
            json.dump(brut, f, ensure_ascii=False)
    else:
        with open(FICHIER_BRUTS, encoding="utf-8") as f:
            brut = json.load(f)

    colonnes, lignes = rejouer_matchs(brut)

    with open(FICHIER_DATASET, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(colonnes)
        writer.writerows(lignes)
    print(f"{len(lignes)} matchs ecrits dans {FICHIER_DATASET}")


if __name__ == "__main__":
    main_build()
