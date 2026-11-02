# CLAUDE.md — mémoire du projet et règles fixées par Pierre

Ce fichier est en clair : il résume ce que Claude retient de la conversation. Corrigez-le si quelque chose est faux, il fait foi.

## Contexte du projet
- Application de paris sportifs football (backend Python `main.py`, front Angular `ucl-app/`, données TheSportsDB).
- 20 championnats nationaux couverts (`DOMESTIC_LEAGUES` dans `main.py`) + coupes d'Europe.
- Un réseau de neurones prédit les buts (`reseau_buts.py`, `entrainer_reseau.py`). Son jeu actuel est `dataset_reseau.csv` (16 854 matchs, saisons 2023-24 à 2026-27, 42 features « matchs précédents » reconstruites sans fuite du futur par `EtatChampionnat`). **Ce jeu n'a pas de cotes.**
- Les cotes actuelles (Winamax/Betclic/Unibet) viennent de The Odds API (`odds.py`) et ne couvrent que les matchs à venir.

## Demande en cours (2026-11-02)
Construire un **nouveau jeu d'entraînement et de test** pour l'algorithme de paris, contenant **tous les matchs de championnat couverts** pour lesquels on a à la fois :
1. le **résultat** (buts, 1/N/2),
2. les **cotes** (le maximum possible, issues de football-data.co.uk),
3. les **matchs précédents** (les mêmes features que `dataset_reseau.csv`).

Méthode de récupération des cotes demandée (script Python pandas + requests) :
- CSV `https://www.football-data.co.uk/mmz4281/{SAISON}/{CODE}.csv`, mis en cache dans `data/raw/` (ne pas retélécharger s'il existe), encodage latin-1 possible, lignes vides à ignorer.
- Colonnes gardées : Div, Date (dd/mm/yy ou dd/mm/yyyy), HomeTeam, AwayTeam, FTHG, FTAG, FTR, B365H/D/A, PSH/D/A, PSCH/D/A, AvgH/D/A, AvgCH/D/A ; colonnes absentes gérées proprement (NaN), schéma unique pour toutes les ligues.
- Probabilités implicites à partir des cotes de clôture Pinnacle, normalisées sans marge (1/cote ÷ somme des 1/cote).
- Export `data/odds_2025_26.csv` (à adapter si on élargit les saisons), résumé affiché : matchs par ligue, % de valeurs manquantes par colonne.
- Contraintes : fonctions modulaires `download`, `parse`, `compute_probs` ; logs clairs ; retries sur erreurs réseau ; un petit test vérifiant que les probabilités de chaque match somment à 1.

## Décisions de Pierre (réponses du 2026-11-02)
- Saisons : **2023-24 à 2026-27** (même période que `dataset_reseau.csv`).
- Ligues : **toutes celles disponibles** sur football-data.co.uk.
- Un match **sans cote est exclu** du nouveau jeu. On a donc **deux jeux de données distincts** : `dataset_reseau.csv` (inchangé, sans cotes) et `dataset_cotes.csv` (nouveau, avec cotes).

## Règles que Pierre m'a fixées
- Poser des questions si nécessaire et **confirmer ma compréhension avant de foncer**.
- Maximiser le nombre de cotes récupérées, sans inventer de données : un match sans résultat, sans cote ou sans historique est exclu du jeu (et compté dans le résumé).
- Garder ce CLAUDE.md lisible et à jour de ce que je retiens.
- Style du dépôt : code et commentaires en français, sans fuite du futur (les features d'un match n'utilisent que des matchs antérieurs).
- **Toujours demander à Pierre avant de commit** (règle notée aussi dans README.md). Il a autorisé le commit du 2026-11-02 pour les jeux de cotes.

## Ce qui a été construit
- `cotes_historiques.py` : `download` (cache `data/raw/`, retries), `parse` (schéma unique), `compute_probs` (probas sans marge ; calculées pour B365, B365C, PS, PSC, Max, MaxC, Avg, AvgC). Écrit `data/odds_2023_2027.csv` (16 028 matchs, 17 ligues, cotes 1X2 + plus/moins 2,5).
- `construire_dataset_cotes.py` : rattache ces cotes aux matchs de `dataset_reseau.csv` (même ligue, date ±1 jour, noms de clubs proches + `ALIAS`), vérifie que le score est identique dans les deux sources, écrit `dataset_cotes.csv` (14 254 matchs, résultat + 42 features + cotes).
- `test_cotes_historiques.py` : probas somment à 1, au moins une cote par match, résultat cohérent, pas de doublon. Lancer : `.venv/bin/python -m unittest test_cotes_historiques -v`.
- Exclusions normales : clubs à moins de 5 matchs d'historique (début 2023-24, promus), 8 matchs au score différent entre sources, et les ligues sans cotes (Chypre, Tchéquie, Hongrie : 0 match).
- Les cotes Pinnacle de clôture (`psc_*`) existent pour ~75 % des matchs ; `maxc_*` et `avgc_*` pour 100 %. Les cotes d'ouverture (`*_h/d/a` sans « c ») n'existent que pour les 11 ligues principales.

## Constats techniques (vérifiés le 2026-11-02)
- `www.football-data.co.uk` redirige (302) vers `football-data.co.uk` ; `requests` suit la redirection.
- Fichiers saisonniers existants pour 2324, 2425, 2526, 2627 : E0, SC0, D1, I1, SP1, F1, N1, B1, P1, T1, G1 (Angleterre, Écosse, Allemagne, Italie, Espagne, France, Pays-Bas, Belgique, Portugal, Turquie, Grèce).
- Fichiers « extra » (une ligne par match, toutes saisons) : AUT, DNK, POL, SWZ, NOR, SWE. Ils n'ont que les cotes de **clôture** (PSC, Max, Avg, B365C), pas B365H/PSH/AvgH.
- Pas de fichier pour la Tchéquie, la Hongrie et Chypre sur football-data.co.uk.
- La saison en cours est 2026-27 (fichiers 2627 courts, partiels). La demande collée parlait de 2025-26 et de 5 ligues seulement : c'est plus étroit que « tous les championnats couverts ».
- Le rapprochement des noms de clubs (football-data ↔ TheSportsDB) est le point délicat ; `odds.py` a déjà `_normaliser_nom` / `_similaire` et `ALIAS_NOMS_CLUB`.
- Les fichiers téléchargés sont des données non fiables : les lire avec pandas uniquement, jamais les exécuter.
