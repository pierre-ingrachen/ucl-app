# calendrier : base locale + fournisseurs gratuits (plus aucun appel TheSportsDB)

Tout ce que le site, les paris et le réentraînement tiraient de TheSportsDB est maintenant **dans le dépôt**
(`calendrier/base/`) et mis à jour chaque jour par des sources gratuites. `SPORTSDB_API_KEY` n'existe plus
(sauf pour `migration_tsdb.py`, outil ponctuel).

## La base locale (`calendrier/base/`, versionnée)

| Fichier | Contenu | Taille |
|---|---|---|
| `evenements/<ligue>_<saison>.json` | 52 saisons : 20 championnats (saison précédente + en cours) et 3 coupes d'Europe (2023-24 → en cours), au format TheSportsDB (tour, stade, logos, scores, statut) | 11 Mo |
| `equipes.json` | 599 clubs : nom, **pays**, championnat national, logo | |
| `classements_nationaux.json` | tables figées de 63 ligues non suivies (Kazakhstan, Israël…), pour la position « championnat national » des clubs européens | |
| `badges/` | 736 logos (clubs, ligues, ESPN), version réduite, nommés d'après l'URL d'origine | 25 Mo |

Le backend (`main.py`) lit uniquement cette base : classements (recalculés depuis les résultats), 5 derniers matchs,
fiches de détail, historique européen, pays, position nationale. Les URLs de logos sont réécrites vers
`/badges/<fichier>` (copie locale). Les saisons terminées ne sont plus jamais réécrites ; la saison en cours est
mise à jour par `Base.upsert` sans jamais effacer un champ statique (tour, stade, logo) par une valeur vide.

## Mise à jour quotidienne (workflow, `paris_reseau.charger_calendrier`)

| Fournisseur | Rôle | Couvre | Coût |
|---|---|---|---|
| **ESPN** (`espn.py`) | scores + matchs à venir (+ tours : phase ESPN → `intRound`, qualifications européennes) | 15 championnats, 3 coupes | gratuit, sans clé |
| **football-data.co.uk** (`footballdata.py`) | résultats Pologne, Suisse (~5 jours de retard) | 2 ligues sans ESPN | gratuit |
| **The Odds API** `/events` (`odds_api.py`) | secours : matchs à venir | 17 championnats, 3 coupes | gratuit, **0 crédit** |

Tchéquie, Chypre, Hongrie : aucun fournisseur gratuit, résultats figés (pas de cotes, donc pas de paris).

- `source.completer_calendrier` : championnats → `brut` (historique des modèles) **et** base ; `source.mettre_a_jour_europe` :
  coupes d'Europe → base uniquement. Curseur par ligue dans `ressources/evenements_recents.json` : un run raté est
  rattrapé au suivant.
- **Identifiants** : un match reprend l'`idEvent` TheSportsDB de la base (journaux, cotes, fiches restent valides) ;
  un match inconnu reçoit `x<ligue>-<dom>-<ext>-<date>`, identique d'un fournisseur à l'autre.
- **Noms de clubs** (`equipes.py`) : normalisation + `ALIAS_NOMS` + `ressources/pont_espn.json` ; un club nouveau
  (promu) est ajouté à `equipes.json` avec le pays majoritaire de sa ligue et son logo ESPN, téléchargé dans `badges/`.
- Le workflow committe `calendrier/base/`, `evenements_recents.json` et `pont_espn.json`.

## Commandes

```
.venv/bin/python -m calendrier.source prochains 8        # matchs des 8 prochains jours + source de chaque ligue
.venv/bin/python -m calendrier.source diagnostic 14      # clubs non rapprochés, ligues sans fournisseur
.venv/bin/python -m calendrier.logos                     # télécharge les logos manquants
.venv/bin/python -m calendrier.equipes construire        # régénère ressources/annuaire.json
.venv/bin/python -m unittest calendrier.tests.test_calendrier calendrier.tests.test_base -v
CALENDRIER_LIVE=1 .venv/bin/python -m unittest calendrier.tests.test_calendrier   # + test ESPN réel
```

`python -m calendrier.migration_tsdb` : snapshot ponctuel de TheSportsDB (fait le 2026-11-13, abonnement actif).
À ne relancer que si l'abonnement existe encore ; `--refresh` refait tout.

## Validation (2026-11-13)

- Classements des saisons précédentes et des 3 coupes d'Europe : **identiques** à l'ancien site ; saison en cours :
  identiques à jeu de matchs égal (écarts = 5 jours de résultats en plus). Fiches de détail : pays, phase, 5 derniers
  matchs identiques. Historique européen : 3296 anciens matchs tous présents, +54 récents.
- Scores ESPN vs TheSportsDB : 559/560 identiques ; football-data : 61/61 identiques.
- 53 tests hors ligne ; test garde-fou : aucun appel TheSportsDB dans le code de production.

## Limites

- ESPN n'est ni officielle ni documentée : champs vérifiés, match mal formé ignoré et compté, score illisible → « à jouer ».
- ESPN n'accepte pas de plage de dates : une requête par ligue et par jour.
- Match abandonné : pas de score chez ESPN (TheSportsDB le notait 0-0) : il n'entre pas dans l'historique.
- Classement national d'une ligue non suivie : table figée à la date du snapshot (`maj`).
- Résultats Pologne/Suisse en retard de ~5 jours : un pari n'est résolu qu'une fois football-data à jour.
- Clubs de ligues non suivies sans pays/logo : pays vide, logo ESPN. Poids du dépôt : ~37 Mo (logos 25 Mo).
