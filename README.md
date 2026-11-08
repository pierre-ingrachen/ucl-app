# UCL — paris football

Application de paris sportifs football : un site (backend FastAPI, front Angular) et quatre algorithmes de paris qui tournent chaque jour en parallèle, sur les 20 championnats nationaux couverts et les coupes d'Europe. Le projet cherche, avec une méthode rigoureuse (aucune fuite du futur, évaluation en walk-forward, intervalles de confiance), s'il existe un avantage mesurable sur les cotes élevées (> 4,00), et suit chaque algorithme sur de vraies cotes bookmaker.

## Organisation du dépôt

| Emplacement | Contenu |
|---|---|
| `main.py`, `ucl-app/` | Site : backend FastAPI + frontend Angular (`start.command` sur Mac, `start.bat` sur Windows). Démo statique : `README-demo.md`, `export_demo.py`. |
| `paris_reseau.py`, `odds.py`, `reseau_buts.py` + `reseau_buts.pt` | **Modèle existant** : réseau de buts + loi de Poisson, paris du jour. Entraînement : `entrainer_reseau.py`, `construire_dataset_reseau.py`, `dataset_reseau.csv`. |
| `modele_d/` | **Modèle D** et **Règles** : prédit les cotes du marché (forme, Elo, buts, repos) / règle simple sans IA, détaillés ci-dessous. |
| `ia_optimisee/` | **IA-optimisée** : modèle dédié aux outsiders (cote > 4), détaillé ci-dessous. |
| `cache_*.json`, `matchs_reseau_bruts.json` | Journaux de paris et caches du modèle existant (lus et écrits par le workflow et le site). |
| `.github/workflows/` | `bilan-paris.yml` (paris quotidiens des 4 algorithmes) et `demo-pages.yml` (démo). |

## Les 4 algorithmes de paris

Les quatre algorithmes cherchent la même chose : **des paris à cote élevée (> 4,00) dont l'espérance de gain serait positive**. Ils tournent chaque jour en parallèle dans le workflow `bilan-paris.yml` (`python paris_reseau.py paris`), sur les mêmes matchs et les mêmes cotes, avec chacun son journal. L'onglet **Bilan** du site affiche les quatre (`/api/paris/bilans`).

**Règles communes**
- **Cotes** : The Odds API (`odds.py`), bookmaker français dans cet ordre de priorité : Winamax, Betclic, Unibet. Relevé complet (20 requêtes : 17 championnats + 3 coupes d'Europe) le mardi, jeudi, samedi et dimanche ; relances ciblées les autres jours pour les matchs du lendemain sans cote. Quota gratuit : 500 requêtes par mois (environ 350 utilisées).
- **Mise = 1 / cote** : un pari gagné rapporte 1 unité brute, donc **ROI = profit / total misé**. Pas de pari sur le match nul (sauf mention contraire).
- **Aucune fuite du futur** : les caractéristiques d'un match ne viennent que de matchs antérieurs (`EtatChampionnat`, `EtatRatings`, rejoués dans l'ordre chronologique). Les évaluations se font en **walk-forward** (entraînement sur le passé, test sur la saison suivante), jamais en découpage aléatoire.
- **Les cotes ne sont jamais des entrées** des modèles : elles servent uniquement à décider si on parie et à calculer le gain.
- **Données d'entraînement** : 42 caractéristiques « matchs précédents » par match (pour chaque équipe, les 5 derniers matchs : buts pour, buts contre, rang de l'adversaire, à domicile ou non ; plus le rang des deux équipes), `dataset_reseau.csv` (2023-24 à aujourd'hui) et, avec les cotes de football-data.co.uk, `modele_d/donnees/dataset_cotes.csv` (2020-21 à aujourd'hui, ~29 000 matchs, 17 championnats).

### 1. Réseau de buts (le premier algorithme)
Fichiers : `reseau_buts.py` (réseau et probabilités), `entrainer_reseau.py`, `construire_dataset_reseau.py`, `paris_reseau.py` (paris), `reseau_buts.pt` (modèle), journal `cache_paris_reseau.json`.

1. **Prédire les buts.** Les 42 caractéristiques entrent dans un perceptron multicouche (4 couches de 32 neurones, dropout 0,2, weight decay 0,01). Il sort deux nombres : les buts attendus de l'équipe à domicile et de l'équipe à l'extérieur, entraînés par vraisemblance de Poisson. L'ensemble est la moyenne de 5 réseaux (graines différentes).
2. **Passer aux probabilités.** On suppose que chaque équipe marque selon une loi de Poisson de ce paramètre, indépendamment de l'autre ; on somme la grille de scores (0 à 10 buts) pour obtenir P(1), P(N) et P(2). La **cote du modèle** est 1 / probabilité.
3. **Décider.** On parie sur la victoire domicile ou extérieure si la **cote du bookmaker est > 4,00** ET si la **cote du modèle est au moins 15 % sous celle du bookmaker** (ex. bookmaker 5,00, modèle 3,75 : le modèle juge l'issue plus probable que le bookmaker).

Entraînement : `dataset_reseau.csv`, découpage aléatoire 80/20, hyperparamètres choisis par validation croisée. Attention : ce modèle a donc **vu des matchs de 2026-27** ; pour tout test sur le passé, le réentraîner sur les matchs antérieurs (c'est ce que fait `modele_d/rejeu_2627.py`).

Résultats (28 665 matchs, une saison laissée de côté à la fois) : ROI de **−20,1 %** avec les cotes de clôture Bet365, −23,1 % à −5 %, −16,6 % avec la moyenne du marché, **−7,6 %** avec la meilleure cote du marché. Il fait moins bien que le pari à l'aveugle sur les mêmes cotes : exiger un écart plus grand n'améliore pas le ROI (signal nul).

### 2. Modèle D (`modele_d/`)
Fichiers : `paris.py` (production), `entrainement.py`, `ratings.py`, `experiences.py`, `ressources/modele.pkl`, journaux `journaux/paris.json` et `analyses.json`.

1. **Cadrage : le marché est la cible, pas une entrée.** Le modèle apprend à prédire les probabilités 1/N/2 du marché (cotes moyennes de clôture, marge retirée) à partir des seules caractéristiques du match. On parie quand sa probabilité est nettement plus haute que celle sous-entendue par la cote du bookmaker.
2. **Caractéristiques.** Les 42 + dérivées (moyennes de buts, points, écarts, ligue) + **ratings** calculés sans fuite du futur (`ratings.py`) : note Elo avec avantage du terrain et marge de victoire, moyennes mobiles de buts marqués et encaissés, jours de repos, nombre de matchs joués, et probabilités d'un modèle de Poisson (xG) bâti sur ces forces.
3. **Ensemble de 11 modèles** (régression logistique, gradient boosting, petits réseaux), qui diffèrent par le jeu de caractéristiques, la cible (moyenne du marché ou Pinnacle) et le mélange α entre le résultat réel et la probabilité du marché. Probabilités moyennées. Réentraîné **en local** (`python -m modele_d.paris entrainer`, ~2 min) puis commité : le workflow ne le réentraîne jamais (`MODELE_D_FIGE`).
4. **Décider.** Règle unique : **victoire extérieure**, cote du bookmaker dans ]4 ; 6], et `1 − 1/(p × cote) ≥ 20 %`. Elle a été choisie sur les saisons 2023-24 à 2026-27 parmi 381 règles testées : **elle n'est pas confirmée statistiquement**, ce paper-trading sert à la tester sur de vraies cotes. Il journalise aussi **tous** les matchs analysés (probabilités, cotes, résultat) dans `analyses.json` pour évaluer d'autres règles.

Résultats : meilleure piste à environ +12 % sur 257 paris (Bet365 −5 %), mais aucune règle positive sur les 4 saisons à Bet365 −10 %, et un intervalle de confiance très large.


### 3. IA-optimisée (`ia_optimisee/`)
Fichiers : `modele.py` (variables, modèle, évaluation), `paris.py` (entraînement et paris du jour), `resultats.md` (compte rendu), `modele.pkl` (modèle figé), journaux `journaux/paris.json` et `analyses.json`. Conçue pour la finalité **maximiser le ROI sur les outsiders à cote > 4**.

1. **Un candidat = un (match, issue)**, vu du côté de l'équipe sur laquelle on parie (A) contre l'adversaire (B). Variables sans cote : buts des 5 derniers matchs de chaque équipe, moyennes, points, matchs sans défaite, rangs, Elo, forces offensive et défensive, repos, nombre de matchs, écarts A − B, indicateur « à domicile », probabilité Elo.
2. **Apprentissage direct de P(victoire de A)** sur les candidats dont la cote moyenne du marché est ≥ 3,3 (~20 000 lignes), par un ensemble de deux modèles : gradient boosting régularisé (profondeur 3, feuilles ≥ 200 lignes) et régression logistique, probabilités moyennées. Pas de Poisson ni de ligne « nul » : on optimise directement la probabilité utile au pari.
3. **Décider par valeur espérée** : on parie si **cote du bookmaker > 4,00**, **cote ≤ plafond**, et **p × cote − 1 > marge**. La **marge** (0 % aujourd'hui) et le **plafond de cote** (6,0) sont choisis sur les saisons **précédentes** (walk-forward, critère ROI − 1 écart-type, au moins 150 paris), jamais sur la saison testée. Le plafond écarte les très grosses cotes, les moins rentables.
4. Réentraînement en local : `python -m ia_optimisee.paris entrainer`, puis commit de `modele.pkl` (le workflow ne le réentraîne pas). Évaluation complète : `python -m ia_optimisee.modele`.

Résultats : la qualité de ses probabilités est **moins bonne que 1/cote du marché** (log-loss 0,4499 contre 0,4435) : aucun avantage de prédiction démontré. Walk-forward 2023-24 à 2026-27 : environ **−18 %** (540 paris, Bet365 −5 %), contre environ −19 % pour le pari à l'aveugle à ces cotes ; le gain vient surtout du plafond de cote.

## Évaluation et comparaison

- **Rejeu de 2026-27** : `python -m modele_d.rafraichir_donnees` met les données à jour (dernier match joué), puis `python -m modele_d.rejeu_2627` rejoue les quatre algorithmes sur la saison en cours (modèles réentraînés sur les matchs d'avant le 1er juillet, règle de l'IA-optimisée choisie sur le passé). Cotes : Bet365 clôture −5 %, **arrondies à la décimale inférieure comme sur Winamax** (Winamax n'existe pas dans l'historique). Compte rendu : `modele_d/resultats/rejeu_2627.md`, journaux `modele_d/journaux/rejeu_2627_*.json` (affichés dans l'onglet Bilan, puis relayés par les paris réels).
- **Résultats du rejeu** (1 286 matchs, 1er juillet au 29 octobre 2026) : Réseau de buts −11,8 % (337 paris), Modèle D +14,4 % (30), Règles −28,3 % (302), IA-optimisée +22,0 % (73), pari à l'aveugle (cote > 4) −19,3 % (547). **Ces ROI positifs ne sont pas des résultats** : 30 à 73 paris, intervalles de confiance à 95 % qui contiennent 0, résultat qui change de signe selon la cote supposée, et la règle du Modèle D a été choisie en voyant ces saisons. Seul le suivi en direct, avec les vraies cotes, tranchera.
- **Statistique** : avec des cotes > 4, l'écart-type du ROI par pari est d'environ 200 % ; détecter un ROI de +12 % exige environ 1 100 paris.

## Outils du Modèle D (`modele_d/`)
Depuis la racine du dépôt, avec `.venv/bin/python -m modele_d.<module>` :

| Module | Rôle |
|---|---|
| `paris` | **Point d'entrée en production** : `entrainer` (réentraîne l'ensemble de 11 modèles), `paris`, `bilan`. Appelé chaque jour par `paris_reseau.py` (mêmes calendrier et cotes, aucun appel API en plus). |
| `entrainement` | Chargement du jeu de données, features, réseau de neurones, comparaison des variantes. |
| `ratings` | Notes Elo, moyennes de buts, repos (calculées sans fuite du futur). |
| `historique` | Télécharge les saisons 2020-21 à 2022-23 de TheSportsDB et construit `dataset_reseau_etendu.csv`. |
| `cotes_historiques`, `dataset_cotes` | Cotes football-data.co.uk, puis rattachement aux matchs : `donnees/dataset_cotes.csv`. |
| `experiences`, `robustesse`, `evaluation` | Banc d'essai (walk-forward), analyses de robustesse, métriques (ROI, IC, CLV, drawdown). |
| `rafraichir_donnees`, `rejeu_2627` | Mise à jour des jeux jusqu'aux derniers matchs joués ; rejeu des algorithmes sur 2026-27. |
| `tests/test_cotes.py` | `.venv/bin/python -m unittest modele_d.tests.test_cotes -v` |

Dossiers : `ressources/` (modèle entraîné + saisons brutes, **suivis** car nécessaires au workflow), `journaux/` (paris et analyses du modèle D, mis à jour par le workflow), `resultats/` (comptes rendus des expériences), `donnees/` (CSV, cache football-data, probabilités : **non suivis**, régénérables).

Reconstruire les données depuis zéro, dans l'ordre : `historique` → `ratings` → `dataset_cotes` (télécharge football-data), puis `paris entrainer`. Le modèle est **figé dans le workflow** (`MODELE_D_FIGE`) : le réentraîner en local (`paris entrainer`) puis commiter `modele_d/ressources/modele.pkl`.
