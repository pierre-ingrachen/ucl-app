# Démo statique (GitHub Pages)

Le site complet (`main.py` + Angular) est trop lourd à héberger simplement : calculs et
appels API à la demande, plusieurs Mo de caches (voir la mémoire *hébergement-tentative-
annulée*). Cette démo contourne le problème en figeant **10 matchs représentatifs**
(fiches complètes : cotes, prédictions rating/ML/ensemble, classement, historique) + le
**bilan de paris complet** des 3 modèles dans des fichiers JSON statiques, servis sans
aucun backend.

## Comment ça marche

- `export_demo.py` interroge le backend local (déjà démarré, caches déjà chauds) et écrit
  un instantané dans `ucl-app/public/demo-data/` (~1 Mo au lieu des ~21 Mo de caches
  complets).
- Un environnement Angular dédié (`environment.demo.ts`, activé par la configuration de
  build `demo`) fait lire ces JSON à `SportsApiService` au lieu d'appeler
  `http://localhost:8000/api/...`.
- `ng build --configuration=demo` produit un site 100 % statique (pas de rendu serveur,
  pas de service worker) dans `ucl-app/dist/demo/browser/`.
- Le workflow `.github/workflows/demo-pages.yml` build et déploie ce dossier sur GitHub
  Pages à chaque push sur `master` touchant `ucl-app/`.

Le site complet, lui, continue de tourner normalement en local via `start.command` — rien
n'a changé de ce côté.

## Régénérer l'instantané (nouveaux matchs)

```bash
.venv/bin/python -m uvicorn main:app --port 8000 &
.venv/bin/python export_demo.py
kill %1
```

Modifier `EUROPE_IDS` / `CHAMPIONNAT_IDS` dans `export_demo.py` pour changer les matchs
choisis (identifiants `idEvent` de TheSportsDB). Puis committer les fichiers mis à jour
dans `ucl-app/public/demo-data/` — le déploiement se fait automatiquement au push.

## Activer GitHub Pages (à faire une fois)

Dans les paramètres du repo GitHub : **Settings > Pages > Source = "GitHub Actions"**.
Le site sera ensuite disponible à `https://pierre-ingrachen.github.io/ucl-app/`.

## Tester en local

```bash
cd ucl-app
ng build --configuration=demo --base-href /ucl-app/
cd dist/demo/browser && python3 -m http.server 8123
```
