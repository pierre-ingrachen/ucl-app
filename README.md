# UCL — paris football

## Règles de travail
- **Toujours demander à Pierre avant de commit** les changements (même si les fichiers sont prêts).

## Organisation du dépôt

| Emplacement | Contenu |
|---|---|
| `main.py`, `ucl-app/` | Site : backend FastAPI + frontend Angular (`start.command` sur Mac, `start.bat` sur Windows). Démo statique : `README-demo.md`, `export_demo.py`. |
| `paris_reseau.py`, `odds.py`, `reseau_buts.py` + `reseau_buts.pt` | **Modèle existant** : réseau de buts + loi de Poisson, paris du jour. Entraînement : `entrainer_reseau.py`, `construire_dataset_reseau.py`, `dataset_reseau.csv`. |
| `modele_d/` | **Modèle D** : prédit les cotes du marché à partir des features (forme, Elo, buts, repos), détaillé ci-dessous. |
| `cache_*.json`, `matchs_reseau_bruts.json` | Journaux de paris et caches du modèle existant (lus et écrits par le workflow et le site). |
| `.github/workflows/` | `bilan-paris.yml` (paris quotidiens, modèle existant puis modèle D) et `demo-pages.yml` (démo). |

## Modèle D (`modele_d/`)
Depuis la racine du dépôt, avec `.venv/bin/python -m modele_d.<module>` :

| Module | Rôle |
|---|---|
| `paris` | **Point d'entrée en production** : `entrainer` (réentraîne l'ensemble de 11 modèles), `paris`, `bilan`. Appelé chaque jour par `paris_reseau.py` (mêmes calendrier et cotes, aucun appel API en plus). |
| `entrainement` | Chargement du jeu de données, features, réseau de neurones, comparaison des variantes. |
| `ratings` | Notes Elo, moyennes de buts, repos (calculées sans fuite du futur). |
| `historique` | Télécharge les saisons 2020-21 à 2022-23 de TheSportsDB et construit `dataset_reseau_etendu.csv`. |
| `cotes_historiques`, `dataset_cotes` | Cotes football-data.co.uk, puis rattachement aux matchs : `donnees/dataset_cotes.csv`. |
| `experiences`, `robustesse`, `evaluation` | Banc d'essai (walk-forward), analyses de robustesse, métriques (ROI, IC, CLV, drawdown). |
| `tests/test_cotes.py` | `.venv/bin/python -m unittest modele_d.tests.test_cotes -v` |

Dossiers : `ressources/` (modèle entraîné + saisons brutes, **suivis** car nécessaires au workflow), `journaux/` (paris et analyses du modèle D, mis à jour par le workflow), `resultats/` (comptes rendus des expériences), `donnees/` (CSV, cache football-data, probabilités : **non suivis**, régénérables).

Reconstruire les données depuis zéro, dans l'ordre : `historique` → `ratings` → `dataset_cotes` (télécharge football-data), puis `paris entrainer`. Le modèle est **figé dans le workflow** (`MODELE_D_FIGE`) : le réentraîner en local (`paris entrainer`) puis commiter `modele_d/ressources/modele.pkl`.

## Fichiers non suivis par git
`.env` (clés d'API), `.venv` (lien vers `~/.ucl-dev-cache`), `CLAUDE.md` (notes de travail locales), `modele_d/donnees/`, caches volumineux (`cache_season.json`, etc.).
