# Le second modèle de prédiction : régression par apprentissage

En complément du modèle de rating ([`rating.py`](rating.py), décrit dans
[`ALGORITHME_PARIS.md`](ALGORITHME_PARIS.md)), un second modèle apprend la
**mécanique d'un match** à partir de features d'historique de chaque équipe.
Il alimente son propre journal de paris, comparé à celui du rating et à celui
de l'ensemble des deux.

## Vue d'ensemble

| Étape | Fichier | Rôle |
|---|---|---|
| Historique profond | [`construire_cache_ml.py`](construire_cache_ml.py) | `cache_ml_matchs.json` : ~27 000 matchs terminés (5 saisons, Europe + 20 championnats). Régénérable, reconstruit **une fois par semaine** (lundi) via l'API. |
| Features | [`dataset_ml.py`](dataset_ml.py) | Passe chronologique unique → features **strictement pré-match** + Elo par équipe. Complète les résultats récents à partir des caches quotidiens du site (aucun appel réseau). |
| Modèle | [`modele_ml.py`](modele_ml.py) | Double régression de Poisson (gradient boosting) → matrice des scores → probas. |
| Accès applicatif | [`predictions_ml.py`](predictions_ml.py) | Modèle du jour (pickle `cache_modele_ml.pkl`), probas d'un match à venir, ensemble. |
| Validation | [`backtest_ml.py`](backtest_ml.py) | Backtest temporel glissant vs `rating.py`. |

Aucun de ces fichiers de cache n'est envoyé au navigateur : ils ne servent
qu'au backend, une fois par jour.

## 1. Données et anti-fuite

`cache_ml_matchs.json` contient uniquement des matchs **terminés**. `dataset_ml.py`
les rejoue **dans l'ordre chronologique** ; pour chaque match, les features sont
calculées à partir du seul état des équipes **avant le coup d'envoi**. L'état de
chaque équipe (Elo, liste des derniers matchs, head-to-head) n'est mis à jour
qu'**après** avoir émis la ligne du match. Aucune information postérieure ne peut
donc entrer dans la prédiction de ce match.

Chaque match d'entraînement est pondéré par une **décroissance exponentielle**
selon son ancienneté (demi-vie 365 jours, comme `rating.py`).

## 2. Features (`dataset_ml.py`)

### Par équipe (mêmes champs pour le camp qui marque `t_` et l'adversaire `o_`)

| Feature | Description |
|---|---|
| `nb_matchs` | Nombre de matchs d'historique connus (indicateur de *cold start*). |
| `gf_5`, `ga_5`, `gd_5`, `ppg_5` | Buts marqués / encaissés / différentiel / points par match sur les **5** derniers matchs. |
| `gf_10`, `ga_10`, `gd_10`, `ppg_10` | Idem sur les **10** derniers. |
| `gf_lieu`, `ga_lieu` | Buts marqués / encaissés sur les 8 derniers matchs **joués au même endroit** (domicile pour l'équipe à domicile, extérieur pour l'autre). |
| `gf_ewm`, `ga_ewm` | Moyennes de buts pondérées exponentiellement (demi-vie 180 j), toutes compétitions. |
| `serie` | Série en cours, signée (+3 = 3 victoires d'affilée, −2 = 2 défaites ; un nul remet à zéro). |
| `jours_repos` | Jours depuis le dernier match (borné à 30). |
| `matchs_14j` | Nombre de matchs joués sur les 14 derniers jours (fatigue / calendrier). |

### Rating Elo

Un Elo **à pool unique** par équipe (init 1500, avantage du terrain 65 points,
K = 20·√(1+|écart de buts|)). Un seul pool pour toutes les compétitions : les
championnats se retrouvent implicitement reliés entre eux par les matchs
européens, où des clubs de pays différents s'affrontent. Le contexte reçoit
`eloHome`, `eloAway` et `eloDiff = eloHome + 65 − eloAway`.

### Contexte du match

`leagueId` (catégoriel), `phase` (catégoriel : qualifications / groupe / finale /
championnat), `mois` civil, `estEurope`, head-to-head (`h2hGdHome` = écart de buts
moyen des 6 dernières confrontations, vu du domicile).

## 3. Modèle (`modele_ml.py`)

- **Un** régresseur `HistGradientBoostingRegressor(loss="poisson")` prédit le
  nombre de buts d'un camp. Chaque match fournit **deux lignes** (perspective
  domicile puis extérieur), ce qui rend le modèle symétrique et double
  l'échantillon (~55 000 lignes).
- Les colonnes catégorielles sont gérées nativement ; les valeurs manquantes
  (équipe sans historique) aussi — pas d'imputation artificielle.
- Sortie : `λ_domicile`, `λ_extérieur` (buts attendus).

### De λ aux probabilités

Matrice des scores jusqu'à 10-10 : produit de deux lois de Poisson, corrigé par
le terme de **Dixon-Coles** sur les petits scores (0-0, 1-0, 0-1, 1-1), dont le
paramètre `rho` est calibré par maximum de vraisemblance pondéré sur les issues
1X2 des 6 000 matchs les plus récents (`rho ≈ −0,1`). On en tire :

- `probaVictoireDomicile`, `probaNul`, `probaVictoireExterieure` ;
- `over25`, `btts` (calculés mais non encore exploités pour les paris).

## 4. Le modèle « ensemble »

Moyenne **géométrique** renormalisée des probabilités de `rating.py` et du
modèle ML (`predictions_ml.ensemble_probas`). C'est la combinaison la plus
performante au backtest.

## 5. Résultats du backtest (`backtest_ml.py`)

Protocole : 9 coupures trimestrielles de 2024‑08 à 2026‑09, entraînement sur
tout le passé, test sur les 3 mois suivants. n = 13 871 matchs hors échantillon.

| Modèle | Log‑loss 1X2 | Brier 1X2 | Précision | MAE buts |
|---|---|---|---|---|
| `rating.py` | 0,995 | 0,593 | 0,520 | — |
| ML | 0,996 | 0,595 | 0,520 | 0,94 |
| **Ensemble** | **0,988** | **0,589** | **0,524** | — |
| Taux de base | 1,067 | 0,646 | — | — |

Lecture : sur le **1X2 pur**, le ML fait **jeu égal** avec le rating sans le
battre (résultat classique : un bon modèle Poisson/Elo est difficile à dépasser
sans features riches — xG, compositions — indisponibles via l'API gratuite). Le
ML apporte des **prédictions de buts calibrées** et une diversité de signal ;
**l'ensemble des deux bat les deux modèles isolés** sur toutes les métriques.
La calibration du ML est excellente (probabilité prédite ≈ fréquence observée).

Pas de ROI dans le backtest : il n'existe pas d'historique de cotes bookmaker.
La comparaison de rentabilité se fait en conditions réelles via les trois
journaux de paris (`cache_paris.json`, `cache_paris_ml.json`,
`cache_paris_ensemble.json`), affichés dans l'onglet **Bilan** du front.

## 6. Reconstruction et coût

| Élément | Fréquence | Coût |
|---|---|---|
| `cache_ml_matchs.json` | 1×/semaine (lundi, workflow) | ~120 requêtes TheSportsDB |
| Mise à jour des résultats récents | chaque run | 0 (caches du site déjà chargés) |
| `cache_modele_ml.pkl` (entraînement) | 1×/jour, au 1ᵉʳ appel | ~10 s CPU |
| Prédiction d'un match | à la volée | négligeable (pickle déjà chargé) |

## Constantes de réglage

| Constante | Fichier | Valeur | Effet |
|---|---|---|---|
| `HALF_LIFE_DAYS` | `dataset_ml.py` | `365` | poids temporel d'entraînement |
| `HALF_LIFE_FORME_DAYS` | `dataset_ml.py` | `180` | demi-vie des moyennes `*_ewm` |
| `ELO_INIT` / `ELO_HOME_ADVANTAGE` / `ELO_K` | `dataset_ml.py` | `1500` / `65` / `20` | rating Elo |
| `MAX_BUTS` | `modele_ml.py` | `10` | troncature de la matrice des scores |
| `learning_rate` / `max_iter` / `min_samples_leaf` | `modele_ml.py` | `0.05` / `500` / `60` | gradient boosting |
| `SAISONS_EUROPE` / `SAISONS_DOMESTIQUES` | `construire_cache_ml.py` | 5 saisons | profondeur d'historique |
