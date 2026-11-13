"""Calendrier des matchs a venir (et resultats recents) sans TheSportsDB.

Deux fournisseurs gratuits, au meme format que les evenements TheSportsDB (`idEvent`,
`idHomeTeam`, `strHomeTeamBadge`, ...) pour que le reste du depot n'ait rien a changer :

- `espn`      : API publique ESPN (source principale : matchs a venir ET scores, sans cle) ;
- `odds_api`  : point `/events` de The Odds API (secours : matchs a venir seulement, gratuit,
                ne consomme aucun credit de quota).

`source.py` les combine ligue par ligue (ESPN, puis The Odds API pour les ligues qu'ESPN ne
couvre pas ou en cas de panne), rattache chaque match a l'identifiant TheSportsDB deja connu en
local et complete les logos. Voir README.md.
"""
