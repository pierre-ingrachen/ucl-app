"""Met a jour les jeux du modele D jusqu'aux derniers matchs joues : recharge la saison en cours de
TheSportsDB (paris_reseau.charger_calendrier), reconstruit dataset_reseau_etendu.csv et
ratings_matchs.csv (sans fuite du futur), puis rattache les cotes football-data (dataset_cotes.py).
matchs_reseau_bruts.json (modele existant) n'est jamais modifie.

Usage : .venv/bin/python -m modele_d.rafraichir_donnees
"""
import csv

import construire_dataset_reseau as base
import paris_reseau as pr
from modele_d import dataset_cotes, historique as ext, ratings


def main():
    calendrier = pr.charger_calendrier()
    etendu = ext._lire(ext.FICHIER_BRUTS_EXT)
    brut = {lid: {**etendu.get(lid, {}), **saisons} for lid, saisons in calendrier.items()}
    colonnes, lignes = base.rejouer_matchs(brut)
    with open(ext.FICHIER_DATASET_ETENDU, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(colonnes)
        w.writerows(lignes)
    print(f"{len(lignes)} matchs dans {ext.FICHIER_DATASET_ETENDU}")
    lignes_r = ratings.rejouer(brut)
    with open(ratings.FICHIER_RATINGS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ratings.COLONNES)
        w.writerows(lignes_r)
    print(f"{len(lignes_r)} matchs dans {ratings.FICHIER_RATINGS}")
    dataset_cotes.main()


if __name__ == "__main__":
    main()
