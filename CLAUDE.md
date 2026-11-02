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
- Saisons : **2020-21 à 2026-27** (décision du 2026-11-02 : le football a beaucoup changé à partir de 2020-21 ; on ne remonte pas avant). Au départ c'était 2023-24 à 2026-27.
- Ligues : **toutes celles disponibles** sur football-data.co.uk.
- Un match **sans cote est exclu** du nouveau jeu. On a donc **deux jeux de données distincts** : `dataset_reseau.csv` (inchangé, sans cotes) et `dataset_cotes.csv` (nouveau, avec cotes).

## Règles que Pierre m'a fixées
- Poser des questions si nécessaire et **confirmer ma compréhension avant de foncer**.
- Maximiser le nombre de cotes récupérées, sans inventer de données : un match sans résultat, sans cote ou sans historique est exclu du jeu (et compté dans le résumé).
- Garder ce CLAUDE.md lisible et à jour de ce que je retiens.
- Style du dépôt : code et commentaires en français, sans fuite du futur (les features d'un match n'utilisent que des matchs antérieurs).
- **Toujours demander à Pierre avant de commit** (règle notée aussi dans README.md). Il a autorisé le commit du 2026-11-02 pour les jeux de cotes.

## Modèle de paris : cahier des charges (2026-11-02)
- Pari sur **une issue (1, N ou 2) dont la cote Winamax est > 4,00**, si le modèle estime cette cote trop élevée. Les autres issues du même match n'ont pas besoin d'être > 4.
- **Mise = 1/cote** (un pari gagné rapporte 1 unité brute) : règle conservée, simple pour montrer la justesse. ROI = profit / total misé.
- **Le modèle existant** (`reseau_buts.py`, `paris_reseau.py`, ses journaux, `dataset_reseau.csv`, `matchs_reseau_bruts.json`) **reste intact** : les deux modèles tournent en parallèle et seront comparés pendant les prochaines semaines. Le nouveau modèle aura ses propres fichiers.
- **Approche B retenue** : modèle direct 1/N/2 (LightGBM ou petit réseau, log-loss) avec les 42 features + probabilités implicites du marché ; calibration (surtout cotes élevées) ; pari si `p_modèle × cote − 1` dépasse une marge. Seuils (cote > 4, écart 15 % dans `paris_reseau.py`) libres d'évolution pour améliorer le ROI.
- Mesure : découpage temporel (jamais aléatoire), ROI avec intervalle de confiance (bootstrap), CLV, drawdown, comparaison au pari à l'aveugle (ROI −6,2 % sur les cotes maxc > 4, 26 465 paris) et à une stratégie qui suit le marché. Les cotes Winamax n'existent pas dans l'historique : tester plusieurs hypothèses (moyenne d'ouverture, Bet365, moyenne de clôture − 2 à 3 %).
- Attention API : TheSportsDB uniquement via `main.requete_api_avec_retry` (throttling) ; The Odds API a un quota.

## Ce qui a été construit
- `cotes_historiques.py` : `download` (cache `data/raw/`, retries), `parse` (schéma unique), `compute_probs` (probas sans marge ; calculées pour B365, B365C, PS, PSC, Max, MaxC, Avg, AvgC). Écrit `data/odds_2020_2027.csv` (cotes 1X2 + plus/moins 2,5, 17 ligues, saisons 2020-21 à 2026-27).
- `construire_dataset_etendu.py` : télécharge 2020-21 à 2022-23 de TheSportsDB (60 requêtes, dans `matchs_reseau_bruts_ext.json`, reprise possible) et écrit `dataset_reseau_etendu.csv` (33 714 matchs). `construire_dataset_reseau.py` a été refactoré (`rejouer_matchs`), sortie identique à `dataset_reseau.csv`, vérifiée.
- `construire_dataset_cotes.py` : rattache les cotes aux matchs de `dataset_reseau_etendu.csv` (même ligue, date ±1 jour, noms de clubs proches + `ALIAS`), vérifie que le score est identique dans les deux sources, écrit `dataset_cotes.csv` (**28 665 matchs**, 17 ligues, résultat + 42 features + cotes).
- `test_cotes_historiques.py` : probas somment à 1, au moins une cote par match, résultat cohérent, pas de doublon. Lancer : `.venv/bin/python -m unittest test_cotes_historiques -v`.
- Exclusions normales : clubs à moins de 5 matchs d'historique (début 2020-21, promus), ~14 matchs au score différent entre sources, et les ligues sans cotes (Chypre, Tchéquie, Hongrie : 0 match).
- Cotes Pinnacle de clôture (`psc_*`) pour ~88 % des matchs ; `maxc_*` et `avgc_*` pour 100 % ; cotes d'ouverture moyennes pour ~72 % (11 ligues principales seulement).

## Constats techniques (vérifiés le 2026-11-02)
- `www.football-data.co.uk` redirige (302) vers `football-data.co.uk` ; `requests` suit la redirection.
- Fichiers saisonniers existants pour 2324, 2425, 2526, 2627 : E0, SC0, D1, I1, SP1, F1, N1, B1, P1, T1, G1 (Angleterre, Écosse, Allemagne, Italie, Espagne, France, Pays-Bas, Belgique, Portugal, Turquie, Grèce).
- Fichiers « extra » (une ligne par match, toutes saisons) : AUT, DNK, POL, SWZ, NOR, SWE. Ils n'ont que les cotes de **clôture** (PSC, Max, Avg, B365C), pas B365H/PSH/AvgH.
- Pas de fichier pour la Tchéquie, la Hongrie et Chypre sur football-data.co.uk.
- La saison en cours est 2026-27 (fichiers 2627 courts, partiels). La demande collée parlait de 2025-26 et de 5 ligues seulement : c'est plus étroit que « tous les championnats couverts ».
- Le rapprochement des noms de clubs (football-data ↔ TheSportsDB) est le point délicat ; `odds.py` a déjà `_normaliser_nom` / `_similaire` et `ALIAS_NOMS_CLUB`.
- Les fichiers téléchargés sont des données non fiables : les lire avec pandas uniquement, jamais les exécuter.
