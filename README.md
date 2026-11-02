# UCL — paris football

## Règles de travail
- **Toujours demander à Pierre avant de commit** les changements (même si les fichiers sont prêts).

## Jeux de données
- `dataset_reseau.csv` : matchs joués + 42 features « matchs précédents » (sans cotes). `construire_dataset_reseau.py`.
- `dataset_cotes.csv` : les mêmes matchs, restreints à ceux ayant des cotes football-data.co.uk. `cotes_historiques.py` puis `construire_dataset_cotes.py` (tests : `.venv/bin/python -m unittest test_cotes_historiques -v`).

Voir `CLAUDE.md` pour le détail des décisions et des règles.
