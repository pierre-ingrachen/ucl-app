"""Exporte un instantané figé de ~10 matchs (+ classements, historique H2H, bilan de paris)
depuis le backend local vers ucl-app/public/demo-data/, pour un build Angular 100% statique
(mode démo, sans backend). À exécuter depuis la racine du repo, backend déjà démarré :

    .venv/bin/python -m uvicorn main:app --port 8000 &
    .venv/bin/python export_demo.py

Puis : cd ucl-app && ng build --configuration=demo --base-href /ucl-app/
Voir README-demo.md."""
import json
import requests

BASE = "http://localhost:8000"
OUT = "ucl-app/public/demo-data"

# 7 matchs européens (5 terminés Ligue des champions + 2 à venir Europa League)
# + 3 matchs de championnat national (2 terminés + 1 à venir).
EUROPE_IDS = ["2594617", "2594591", "2594538", "2594568", "2594652", "2594868", "2594892"]
CHAMPIONNAT_IDS = ["2494023", "2489085", "2513981"]
MATCH_IDS = EUROPE_IDS + CHAMPIONNAT_IDS

COMPETITIONS_EUROPE = {"4480", "4481"}


def get(path):
    r = requests.get(f"{BASE}{path}", timeout=60)
    r.raise_for_status()
    return r.json()


def save(relpath, data):
    with open(f"{OUT}/{relpath}", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"  -> {relpath} ({len(json.dumps(data))} octets)")


print("Fiches match...")
matchs = {}
for mid in MATCH_IDS:
    data = get(f"/api/match/{mid}")
    matchs[mid] = data
    save(f"matches/{mid}.json", data)

leagues = {m.get("idLeague") for m in matchs.values() if m.get("idLeague")}
print(f"Classements ({leagues})...")
for league_id in leagues:
    path = (f"/api/competitions/classement/{league_id}" if league_id in COMPETITIONS_EUROPE
            else f"/api/championnats/classement/{league_id}")
    save(f"classements/{league_id}.json", get(path))

print("Historique qualifications (filtré sur les équipes des 10 matchs)...")
equipes = set()
for m in matchs.values():
    equipes.add(m.get("idHomeTeam"))
    equipes.add(m.get("idAwayTeam"))
historique = get("/api/matchs/historique-qualifications")["events"]
filtre = [e for e in historique if e.get("idHomeTeam") in equipes or e.get("idAwayTeam") in equipes]
save("historique-qualifs.json", {"events": filtre})
print(f"  ({len(historique)} -> {len(filtre)} evenements)")

print("Listes 'a venir' figees...")
save("matchs-a-venir.json", {"events": [matchs[i] for i in EUROPE_IDS]})
save("championnats-a-venir.json", {"events": [matchs[i] for i in CHAMPIONNAT_IDS]})

print("Bilan de paris (3 modeles)...")
for modele in ("rating", "ml", "ensemble"):
    save(f"paris-{modele}.json", get(f"/api/paris?modele={modele}"))

print("Termine.")
