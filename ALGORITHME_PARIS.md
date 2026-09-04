# Comment l'algorithme choisit les paris

Ce document décrit précisément la logique qui, chaque matin, sélectionne les
paris « value » enregistrés dans `cache_paris.json` et affichés par l'onglet
Paris du front. Toute la logique tient dans [`bilan_paris.py`](bilan_paris.py),
qui s'appuie sur le modèle de probabilité de [`rating.py`](rating.py) et sur les
cotes récupérées par [`odds.py`](odds.py) / [`main.py`](main.py).

## Vue d'ensemble

À chaque exécution (workflow GitHub Actions « Bilan quotidien des paris »,
déclenché une fois par jour) :

1. **Étape `cotes`** — on obtient les cotes 1X2 des matchs de la semaine
   (Winamax en priorité, sinon Betclic, sinon Unibet).
2. **Étape `paris`** —
   a. on **résout** les paris `en_attente` des jours précédents dont le match
      est désormais terminé (gagné / perdu + gain net) ;
   b. on **cherche de nouveaux paris** parmi les matchs **du jour** ;
   c. on réécrit `cache_paris.json` et on affiche le bilan.

Le script est idempotent : relancé le même jour, il ne recrée pas un pari déjà
présent (déduplication sur le couple `(idEvent, issue)`).

Depuis 2026-09, l'étape `paris` tient **trois journaux en parallèle**, un par
modèle de probabilité — `rating` (`cache_paris.json`, décrit ici), `ml`
(`cache_paris_ml.json`) et `ensemble` (`cache_paris_ensemble.json`) — afin de
comparer leurs performances dans l'onglet Bilan. Le critère de sélection et la
mise sont identiques ; seule la probabilité (donc la cote du modèle) change. Le
2ᵉ modèle est décrit dans [`ALGORITHME_ML.md`](ALGORITHME_ML.md).

## 1. Estimation de la probabilité de chaque issue

Pour un match donné, le modèle produit trois probabilités qui somment à 1 :
`probaVictoireDomicile`, `probaNul`, `probaVictoireExterieure`
(fonction `predire_resultat` de [`rating.py`](rating.py)).

Deux modèles selon la compétition, tous deux reconstruits une fois par jour :

| Compétition | Modèle | Construction |
|---|---|---|
| C1 / Europa / Conference League | rating **pays** + effet **club** | `construire_modele` |
| Championnats nationaux suivis | rating **club** uniquement | `construire_modele_championnat` |

### Pipeline du modèle (`rating.py`)

1. **Matchs exploitables** — historique des 3 dernières saisons + saison en
   cours déjà jouée. Chaque match est pondéré par une **décroissance
   exponentielle** selon son ancienneté (demi-vie = 365 jours : un match d'il y
   a 3 ans pèse ~8× moins qu'un match récent). L'écart de buts est borné à ±5.
2. **Régression pays pondérée** (`_regression_pays`, compétitions européennes
   seulement) — moindres carrés sur
   `écart_buts = avantage_terrain + rating(pays_dom) − rating(pays_ext)`.
   Permet de comparer des équipes ne s'étant jamais affrontées via des
   adversaires communs.
3. **Effet club** (`_regression_clubs` pour l'Europe, `_regression_ridge_avec_avantage`
   pour les championnats) — régression **ridge** (pénalité L2, λ = 6) sur les
   résidus. Le *shrinkage* ramène vers 0 l'effet des clubs peu représentés
   (ils reviennent alors au simple rating pays).
4. **Calibration logit ordonné** (`_calibrer_logit_ordonne`) — maximum de
   vraisemblance pondéré qui ajuste :
   - `beta` : échelle appliquée à la marge de force ;
   - `c` : demi-largeur de la zone de nul autour de 0.
   Puis, pour un match : `s = beta · marge`,
   `p_ext = σ(−c − s)`, `p_dom = σ(s − c)`, `p_nul = 1 − p_ext − p_dom`,
   le tout renormalisé pour sommer à 1.

## 2. Cote implicite du modèle

```python
cote_modele(p) = 0.9 / p        # bilan_paris.py, identique au frontend
```

Le `0.9` (au lieu de `1 / p`) applique une marge de sécurité de 10 % : on
n'estime « juste » une cote de bookmaker que si elle dépasse la cote équitable
du modèle **d'au moins 10 %**. Le seuil de sélection réel est bien plus élevé
(voir ci-dessous).

## 3. Critère de sélection d'un pari

Pour chaque match **du jour** (`dateEvent == aujourd'hui`) et **chacune** des
trois issues (`domicile`, `nul`, `exterieure`), un pari est pris si **toutes**
ces conditions sont vraies (`chercher_nouveaux_paris`) :

| # | Condition | Constante | Raison |
|---|---|---|---|
| 1 | Une cote bookmaker existe pour ce match | — | Winamax, sinon Betclic, sinon Unibet |
| 2 | Le modèle couvre la compétition | — | sinon pas de probabilité |
| 3 | Le couple `(idEvent, issue)` n'a pas déjà été parié | — | idempotence |
| 4 | `cote_bookmaker ≥ 1.15 × cote_modele` | `SEUIL_VALUE = 1.15` | *value* d'au moins 15 % vs le modèle |
| 5 | `cote_bookmaker > 3.00` | `COTE_MIN = 3.00` | on ne joue que les cotes hautes (issues sous-estimées par le book) |

La condition 4 combinée à `cote_modele = 0.9 / p` revient à exiger :

```
cote_bookmaker ≥ 1.15 × 0.9 / p  =  1.035 / p
```

soit une cote bookmaker au moins ~3,5 % au-dessus de la cote équitable `1/p`,
**et** au-dessus de 3,00 en valeur absolue.

> Note : au rechargement du journal, l'étape `paris` purge aussi les paris
> historiques dont `coteBookmaker < COTE_MIN` (`etape_paris`), pour rester
> cohérent si `COTE_MIN` est modifié.

## 4. Mise et enregistrement

```python
mise = 1 / cote_bookmaker
```

Mise inversement proportionnelle à la cote : le **gain brut potentiel est
constant** (`mise × cote_bookmaker = 1 unité`), donc chaque pari vise le même
gain quelle que soit la cote. Le pari est enregistré avec `statut = "en_attente"`
et les champs : `idEvent`, `date`, équipes, `issue`, `coteBookmaker`,
`bookmaker`, `coteModele`, `mise`, `gain = null`.

## 5. Résolution d'un pari

`resoudre_paris_en_attente` compare l'issue pariée au résultat réel du match
(`resultat_reel` : `domicile` / `nul` / `exterieure` d'après le score final) :

| Cas | `statut` | `gain` |
|---|---|---|
| issue correcte | `gagne` | `+mise × (coteBookmaker − 1)` |
| issue incorrecte | `perdu` | `−mise` |
| match pas encore joué | reste `en_attente` | `null` |

Le bilan affiché cumule le gain net des paris résolus, le nombre de gagnés /
perdus et le nombre de paris encore en attente.

## 6. Quand les cotes sont-elles récupérées ?

`main.obtenir_cotes_semaine` limite fortement les appels à The Odds API (quota
gratuit) :

- **Relevé complet** : uniquement le **mardi** et le **vendredi** matin
  (`JOURS_RELEVE_COMPLET = {1, 4}`), au plus une fois par jour. Le mardi couvre
  C1/Europa/Conference, le vendredi couvre le week-end des championnats.
- **Relance ciblée** les autres jours : seulement pour une compétition ayant un
  match **le lendemain** encore sans cote Winamax, et une seule fois par jour et
  par compétition.
- Sinon : simple relecture du cache `cache_cotes_winamax.json`, aucun appel API.

Une requête par compétition suffit (The Odds API renvoie tous les matchs à venir
d'un coup). L'appariement match interne ↔ match Odds API se fait par **date +
similarité des noms d'équipes** (`odds.py`, seuil 0.6), les identifiants n'étant
pas partagés entre fournisseurs.

## Constantes de réglage

| Constante | Fichier | Valeur | Effet |
|---|---|---|---|
| `SEUIL_VALUE` | `bilan_paris.py` | `1.15` | marge *value* minimale vs modèle |
| `COTE_MIN` | `bilan_paris.py` | `3.00` | cote bookmaker minimale |
| facteur `0.9` | `bilan_paris.py` (`cote_modele`) | `0.9` | marge dans la cote implicite du modèle |
| `HALF_LIFE_DAYS` | `rating.py` | `365` | demi-vie de la pondération temporelle |
| `MAX_GOAL_DIFF` | `rating.py` | `5` | borne de l'écart de buts |
| `LAMBDA_TEAM` / `LAMBDA_CLUB_CHAMPIONNAT` | `rating.py` | `6` | force du *shrinkage* des effets club |
| `JOURS_RELEVE_COMPLET` | `main.py` | `{1, 4}` | jours de relevé complet des cotes |
