"""Prepare le mode hors ligne (commande `ucl-1510`) : a lancer AVEC connexion internet.

Precharge uniquement l'onglet Championnats (Top 5 + 6-10) pour les matchs des dates visees :
liste des matchs, fiche detaillee de chacun (5 derniers matchs des deux equipes, classements
nationaux), classements general / domicile / exterieur des championnats concernes, et logos
des clubs (telecharges dans cache_badges/).

    .venv/bin/python preparer_hors_ligne.py [AAAA-MM-JJ ...]

Sans argument, les dates sont celles de main.DATES_HORS_LIGNE (weekend du 16 au 18/10/2026).
Le script est reprenable : relance-le s'il s'arrete, ce qui est deja en cache n'est pas
redemande. Les appels a l'API sont espaces de DELAI secondes, et le script S'ARRETE des qu'un
429 (limite de debit) persiste, plutot que d'ecrire des caches incomplets."""
import json
import os
import sys
import time

import requests

import main

DELAI = 1.5  # secondes entre deux appels TheSportsDB (limite gratuite : ~30/min)
DATES = sys.argv[1:] or main.DATES_HORS_LIGNE
main.DELAI_MIN_ENTRE_APPELS_SPORTSDB = DELAI

appels = [0]
_requete_originale = main.requete_api_avec_retry


class LimiteAtteinte(BaseException):
    """BaseException pour traverser les `except Exception` du backend sans etre avalee."""


class ApiIndisponible(BaseException):
    """Timeout / erreur reseau / 5xx persistants. BaseException pour que le backend ne la
    transforme pas en valeur vide mise en cache (ex. pays "" d'une equipe)."""


def requete_surveillee(url, *args, **kwargs):
    appels[0] += 1
    reponse = None
    for pause in (5, 15, 30, None):  # 5xx / timeout : l'API est momentanement indisponible
        try:
            reponse = _requete_originale(url, *args, **kwargs)
            if reponse.status_code < 500:
                break
            erreur = f"HTTP {reponse.status_code}"
        except requests.exceptions.RequestException as e:
            erreur = type(e).__name__
        if pause is None:
            raise ApiIndisponible(f"{erreur} sur {url}")
        print(f"  {erreur}, nouvelle tentative dans {pause}s", flush=True)
        time.sleep(pause)
    if reponse.status_code == 429:
        raise LimiteAtteinte(url)
    return reponse


main.requete_api_avec_retry = requete_surveillee


def etape(msg):
    print(f"\n== {msg}", flush=True)


try:
    etape("Liste des matchs de championnat de la saison (10 championnats)")
    cache_saison = main.charger_cache(main.CACHE_CHAMPIONNAT_SEASON_FILE)
    if cache_saison is None:
        # Cache du jour absent : on repart de l'ancien (autres championnats) et on remplace
        # les 10 championnats cibles par des donnees fraiches.
        try:
            with open(main.CACHE_CHAMPIONNAT_SEASON_FILE, encoding="utf-8") as f:
                cache_saison = json.load(f).get("data", [])
        except (OSError, ValueError):
            cache_saison = []
    ligues_ok, ligues_ko = [], []
    for league_id in main.LIGUES_HORS_LIGNE:
        nom = main.DOMESTIC_LEAGUES[league_id]
        url = (f"https://www.thesportsdb.com/api/v1/json/{main.API_KEY}/eventsseason.php"
               f"?id={league_id}&s={main.saison_actuelle_ligue(league_id)}")
        try:
            r = main.requete_api_avec_retry(url)
            r.raise_for_status()
            events = r.json().get("events") or []
        except (ApiIndisponible, requests.exceptions.RequestException) as e:
            print(f"  {nom}: INDISPONIBLE ({e})", flush=True)
            ligues_ko.append(league_id)
            continue
        cache_saison = [m for m in cache_saison if m.get("idLeague") != league_id] + events
        ligues_ok.append(league_id)
        print(f"  {nom}: {len(events)} matchs", flush=True)
    main.sauvegarder_cache(main.CACHE_CHAMPIONNAT_SEASON_FILE, cache_saison)
    matchs = cache_saison
    cibles = sorted(
        (m for m in matchs if m.get("dateEvent") in DATES and m.get("idLeague") in ligues_ok),
        key=lambda m: (m["dateEvent"], m.get("strTime") or ""),
    )
    print(f"{len(cibles)} matchs retenus ({', '.join(DATES)})")

    # Les caches permanents gardent parfois une valeur vide issue d'un echec passe : on les
    # retire pour les equipes visees afin qu'elles soient redemandees (une seule fois).
    equipes = {t for m in cibles for t in (m.get("idHomeTeam"), m.get("idAwayTeam")) if t}
    cache_teams = main.charger_cache_permanent(main.CACHE_TEAMS_FILE)
    cache_classement = main.charger_cache_permanent(main.CACHE_CLASSEMENT_FILE)
    for t in equipes:
        if not cache_teams.get(t):
            cache_teams.pop(t, None)
        if cache_classement.get(t) is None:
            cache_classement.pop(t, None)
    main.sauvegarder_cache_permanent(main.CACHE_TEAMS_FILE, cache_teams)
    main.sauvegarder_cache_permanent(main.CACHE_CLASSEMENT_FILE, cache_classement)

    etape("Classements des championnats (historique 2 saisons)")
    ligues = sorted({m["idLeague"] for m in cibles}, key=main.LIGUES_HORS_LIGNE.index)
    classements = {}
    for league_id in ligues:
        nom = main.DOMESTIC_LEAGUES[league_id]
        try:
            classements[league_id] = main.get_classement_championnat(league_id)
        except ApiIndisponible as e:
            print(f"{nom}: INDISPONIBLE ({e}) -> championnat ignore", flush=True)
            ligues_ko.append(league_id)
            continue
        n_actuelle = len(classements[league_id]["saisonActuelle"]["general"])
        n_prec = len(classements[league_id]["saisonPrecedente"]["general"])
        print(f"{nom}: {n_actuelle} equipes (saison en cours), "
              f"{n_prec} (precedente) - {appels[0]} appels", flush=True)
    cibles = [m for m in cibles if m["idLeague"] in classements]

    etape(f"Fiches detaillees ({len(cibles)} matchs)")
    fiches = {}
    echecs = []
    for i, m in enumerate(cibles, 1):
        try:
            fiches[m["idEvent"]] = main.get_match_details(m["idEvent"])
            statut = "ok"
        except (Exception, ApiIndisponible) as e:  # noqa: BLE001 - on continue pour les autres matchs
            statut = f"ECHEC ({e})"
            echecs.append(m["idEvent"])
        print(f"[{i}/{len(cibles)}] {m['dateEvent']} {m.get('strHomeTeam')} - {m.get('strAwayTeam')} : {statut}"
              f" ({appels[0]} appels)", flush=True)

    etape("Logos des clubs")
    os.makedirs(main.DOSSIER_BADGES, exist_ok=True)
    urls = set()
    for obj in (*cibles, *fiches.values(), *classements.values()):
        urls.update(main.RE_URL_BADGE.findall(json.dumps(obj)))
    deja, nouveaux, rates = 0, 0, []
    for url in sorted(urls):
        chemin = os.path.join(main.DOSSIER_BADGES, main.nom_fichier_badge(url))
        if os.path.exists(chemin):
            deja += 1
            continue
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            with open(chemin, "wb") as f:
                f.write(r.content)
            nouveaux += 1
        except requests.exceptions.RequestException as e:
            rates.append(url)
            print(f"  logo manquant : {url} ({e})")
        time.sleep(0.2)
    print(f"{len(urls)} logos : {nouveaux} telecharges, {deja} deja presents, {len(rates)} manquants")
except LimiteAtteinte as e:
    print(f"\nLIMITE DE DEBIT (429) atteinte sur {e}.\n"
          f"Arret apres {appels[0]} appels. Attends quelques minutes puis relance le script : "
          "ce qui est deja en cache ne sera pas redemande.")
    sys.exit(2)

etape("Resume")
sans_hist = [m for m in cibles if m["idEvent"] in fiches and not (
    fiches[m["idEvent"]].get("historiqueDomicile") and fiches[m["idEvent"]].get("historiqueExterieur"))]
for m in cibles:
    print(f"  {m['dateEvent']} {m.get('strLeague')}: {m.get('strHomeTeam')} - {m.get('strAwayTeam')}")
print(f"\n{appels[0]} appels TheSportsDB au total.")
if ligues_ko:
    print("Championnats NON disponibles (relancer plus tard) : "
          + ", ".join(main.DOMESTIC_LEAGUES[l] for l in dict.fromkeys(ligues_ko)))
if sans_hist:
    print(f"Note : {len(sans_hist)} match(s) sans historique complet d'une des equipes (promu ?) :")
    for m in sans_hist:
        print(f"  {m.get('strHomeTeam')} - {m.get('strAwayTeam')}")
if echecs:
    print(f"\nATTENTION : {len(echecs)} fiche(s) en echec : {echecs} -> relancer le script.")
    sys.exit(1)
print("\nPret pour le hors ligne.")
