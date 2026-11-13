# calendrier : matchs à venir et résultats récents sans TheSportsDB

Deux fournisseurs gratuits, au format des événements TheSportsDB (`idEvent`, `idHomeTeam`,
`strHomeTeamBadge`, …) : le reste du dépôt (journaux, historiques, front) n'a rien à changer.

| Fournisseur | Rôle | Couvre | Coût |
|---|---|---|---|
| **ESPN** (`espn.py`) | principal : à venir **et** scores | 15 championnats + 3 coupes d'Europe | gratuit, sans clé |
| **The Odds API** (`odds_api.py`, point `/events`) | secours : à venir seulement | 17 championnats + 3 coupes, dont Pologne et Suisse | gratuit, **0 crédit** de quota |

ESPN ne publie ni la Pologne, ni la Suisse, ni la Tchéquie, ni Chypre, ni la Hongrie (catalogue
vérifié le 2026-11-13) ; The Odds API ne publie ni la Tchéquie, ni Chypre, ni la Hongrie : ces trois
ligues restent sans calendrier (elles n'ont de toute façon pas de cotes).

## Comment ça marche

- `source.a_venir` : par ligue, ESPN d'abord ; The Odds API si la ligue n'est pas couverte par ESPN,
  si ESPN est en panne, ou si ESPN renvoie une semaine vide alors que le calendrier local annonce des matchs.
- `source.completer_calendrier(brut)` : met à jour `{ligue: {saison: [événements]}}` (format de
  `matchs_reseau_bruts.json`) avec les résultats ESPN récents et les matchs des 8 prochains jours. Les
  résultats déjà récupérés sont mémorisés dans `ressources/evenements_recents.json` (premier run : ~45 s,
  ensuite quelques secondes).
- **Identifiants** : un match reprend l'`idEvent` TheSportsDB du calendrier local (même ligue, saison,
  domicile, extérieur, date la plus proche) : journaux, cotes et pages de détail restent valides, et les
  champs statiques (tour, stade) sont conservés. Un match absent du calendrier local reçoit
  `x<ligue>-<domicile>-<extérieur>-<date>`, identique quel que soit le fournisseur.
- **Noms de clubs** (`equipes.py`) : normalisation (accents, ø/ł, sigles FC/SC…), comparaison au sein de la ligue
  (tous les clubs pour les coupes d'Europe), seuil 0,82, refus des cas ambigus. `ressources/pont_espn.json`
  mémorise les rapprochements sûrs (id ESPN → id TheSportsDB) et peut être corrigé à la main. Un club
  inconnu (promu) reçoit l'id provisoire `inconnu-<nom>` : il n'a pas d'historique, donc aucune prédiction.
- **Logos** : logo TheSportsDB si le club est dans `ressources/annuaire.json` (639 clubs, 23 logos de ligue,
  construit depuis les historiques et caches locaux), sinon logo ESPN. Le mode hors ligne de `main.py`
  télécharge aussi les logos ESPN.
- **Coupes d'Europe** : `ressources/locaux_europe.json` (instantané de `cache_season.json`) garde les `idEvent`
  et les tours (`intRound`, phase affichée). À régénérer quand un nouveau tirage est connu.

## Branchements

- `paris_reseau.py` : `charger_calendrier` (ESPN + secours, TheSportsDB seulement pour les ligues sans
  résultats : Pologne, Suisse, Tchéquie, Chypre, Hongrie ; repli complet si le paquet échoue) et
  `matchs_europe_a_venir`.
- `main.py` : `/api/matchs/a-venir` et `/api/championnats/matchs/a-venir` (cache de 20 min). Les fiches de
  détail (`/api/match/{id}`), classements et historiques utilisent toujours TheSportsDB.
- Variable `SOURCE_CALENDRIER` : `auto` (défaut) ou `thesportsdb` (ancien comportement partout).
- Workflow : `evenements_recents.json` et `pont_espn.json` sont committés avec les journaux.

## Commandes

```
.venv/bin/python -m calendrier.source prochains 8        # matchs des 8 prochains jours + source de chaque ligue
.venv/bin/python -m calendrier.source diagnostic 14      # clubs non rapprochés, ligues sans fournisseur
.venv/bin/python -m calendrier.equipes construire        # annuaire + instantané européen (après un rafraîchissement TheSportsDB)
.venv/bin/python -m unittest calendrier.tests.test_calendrier -v
CALENDRIER_LIVE=1 .venv/bin/python -m unittest calendrier.tests.test_calendrier   # + test ESPN réel
```

## Limites

- L'API ESPN n'est ni officielle ni documentée : elle peut changer. Les champs sont vérifiés, un match mal
  formé est ignoré et compté, jamais deviné ; un score illisible laisse le match « à jouer ».
- ESPN n'accepte pas de plage de dates (400) : une requête par ligue et par jour.
- Un match abandonné n'a pas de score chez ESPN (TheSportsDB le note 0-0) : il n'entre pas dans l'historique.
- Validation du 2026-11-13 : 560 scores comparés à TheSportsDB depuis le 21/09, 559 identiques ; le seul écart
  (Rizespor–Erzurumspor, 2-1 contre 0-0) est probablement un score TheSportsDB périmé.
