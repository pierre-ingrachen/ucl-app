"""Paris automatiques bases sur le reseau de neurones (reseau_buts.pt), en deux etapes
(deux appels separes dans le workflow GitHub Actions, cf. `python paris_reseau.py <etape>`) :

1. `cotes` : recupere les cotes bookmaker de la semaine via The Odds API (releve complet le
   mardi et le vendredi, relance ciblee les autres jours pour les matchs du lendemain sans
   cote : meme rythme qu'avant, pour rester sous le quota gratuit). Cache : cache_cotes_winamax.json.
2. `paris` : resout les paris en attente, puis pour chaque match du jour :
   buts attendus du reseau -> loi de Poisson -> cotes justes (1 / probabilite) -> pari pris si
   la cote du bookmaker est superieure a COTE_MIN ET si la cote du modele est au moins
   ECART_MIN inferieure a celle du bookmaker (ex. bookmaker 5.00, modele 3.75).
   Journal : cache_paris_reseau.json (mise = 1 / cote : un pari gagne rapporte 1 unite brute).

`tout` (defaut, pratique en local) enchaine les deux. Variables d'environnement :
SPORTSDB_API_KEY et ODDS_API_KEY.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np

import main  # requete_api_avec_retry, API_KEY, ligues et saisons
from construire_dataset_reseau import FICHIER_BRUTS, saisons_ligue
from odds import recuperer_toutes_les_cotes
from reseau_buts import EtatChampionnat, charger_modele, cotes_match, predire_lambdas

COTE_MIN = 4.00  # cote bookmaker strictement superieure a ce seuil
ECART_MIN = 0.15  # cote du modele au moins 15 % sous la cote du bookmaker
FICHIER_COTES = "cache_cotes_winamax.json"
FICHIER_PARIS = "cache_paris_reseau.json"
JOURS_RELEVE_COMPLET = {1, 4}  # mardi, vendredi (lundi = 0)
# Identifiants de ligue -> cles The Odds API (pas de cotes publiees pour Tchequie, Chypre, Hongrie).
ODDS_API_SPORT_KEYS = {
    "4344": ["soccer_portugal_primeira_liga"], "4337": ["soccer_netherlands_eredivisie"],
    "4338": ["soccer_belgium_first_div"], "4328": ["soccer_epl"],
    "4334": ["soccer_france_ligue_one"], "4335": ["soccer_spain_la_liga"],
    "4332": ["soccer_italy_serie_a"], "4331": ["soccer_germany_bundesliga"],
    "4339": ["soccer_turkey_super_league"], "4422": ["soccer_poland_ekstraklasa"],
    "4336": ["soccer_greece_super_league"], "4358": ["soccer_norway_eliteserien"],
    "4340": ["soccer_denmark_superliga"], "4675": ["soccer_switzerland_superleague"],
    "4621": ["soccer_austria_bundesliga"], "4330": ["soccer_spl"],
    "4347": ["soccer_sweden_allsvenskan"],
}
ISSUES = [("domicile", "1", "domicile"), ("nul", "N", "nul"), ("exterieure", "2", "exterieure")]


def _lire_json(fichier, defaut):
    if not os.path.exists(fichier):
        return defaut
    with open(fichier, encoding="utf-8") as f:
        return json.load(f)


def _ecrire_json(fichier, data):
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def charger_calendrier():
    """{ligue -> {saison -> evenements}} : historique fige (matchs_reseau_bruts.json) dont la
    saison en cours est rechargee depuis TheSportsDB (resultats et calendrier a jour)."""
    brut = _lire_json(FICHIER_BRUTS, {})
    for league_id in main.DOMESTIC_LEAGUES:
        saison = main.saison_actuelle_ligue(league_id)
        url = (f"https://www.thesportsdb.com/api/v1/json/{main.API_KEY}/"
               f"eventsseason.php?id={league_id}&s={saison}")
        resp = main.requete_api_avec_retry(url)
        resp.raise_for_status()
        brut.setdefault(league_id, {})[saison] = [
            {k: e.get(k) for k in ("idEvent", "dateEvent", "idHomeTeam", "idAwayTeam",
                                   "strHomeTeam", "strAwayTeam", "intHomeScore", "intAwayScore")}
            for e in (resp.json().get("events") or [])
        ]
    return brut


def est_joue(e):
    return e["intHomeScore"] is not None and e["intAwayScore"] is not None


def matchs_a_venir(calendrier, debut, fin):
    """Matchs non joues de la saison en cours dont la date est dans [debut, fin] (ISO)."""
    resultat = []
    for league_id in main.DOMESTIC_LEAGUES:
        evenements = calendrier.get(league_id, {}).get(main.saison_actuelle_ligue(league_id), [])
        resultat += [dict(e, idLeague=league_id) for e in evenements
                     if not est_joue(e) and e["dateEvent"] and debut <= e["dateEvent"] <= fin]
    return resultat


def etape_cotes(calendrier):
    """Cotes de la semaine : relit le cache, ou interroge The Odds API les jours de releve."""
    cache = _lire_json(FICHIER_COTES, {})
    if "data" not in cache:
        cache = {"data": {}, "quota": None, "dernier_releve_complet": None, "relances_faites": []}
    aujourd_hui = date.today()
    cle_jour = str(aujourd_hui)
    releve_complet = (aujourd_hui.weekday() in JOURS_RELEVE_COMPLET
                      and cache.get("dernier_releve_complet") != cle_jour)
    peut_relancer = not releve_complet and bool(cache.get("dernier_releve_complet"))

    a_interroger, par_ligue = {}, {}
    if releve_complet or peut_relancer:
        semaine = matchs_a_venir(calendrier, cle_jour, str(aujourd_hui + timedelta(days=7)))
        for m in semaine:
            par_ligue.setdefault(m["idLeague"], []).append(m)
    if releve_complet:
        a_interroger = ODDS_API_SPORT_KEYS
        cache.update(dernier_releve_complet=cle_jour, data={}, relances_faites=[])
    elif peut_relancer:
        demain = str(aujourd_hui + timedelta(days=1))
        for league_id, cles in ODDS_API_SPORT_KEYS.items():
            cle_relance = f"{league_id}:{cle_jour}"
            sans_cote = any(m["dateEvent"] == demain and not cache["data"].get(m["idEvent"], {}).get("bookmaker")
                            for m in par_ligue.get(league_id, []))
            if sans_cote and cle_relance not in cache["relances_faites"]:
                a_interroger[league_id] = cles
                cache["relances_faites"].append(cle_relance)

    if a_interroger:
        nouvelles, quota = recuperer_toutes_les_cotes(a_interroger, par_ligue, os.environ["ODDS_API_KEY"])
        cache["data"].update(nouvelles)
        if quota:
            cache["quota"] = quota
        _ecrire_json(FICHIER_COTES, cache)

    cotes = cache.get("data", {})
    quota = (cache.get("quota") or {}).get("restant", "inconnu")
    print(f"## Cotes — {cle_jour}\n")
    print(f"- Matchs avec une cote trouvee : {sum(1 for c in cotes.values() if c.get('bookmaker'))}/{len(cotes)}")
    print(f"- Quota The Odds API restant : {quota}\n")
    return cotes


def rejouer_championnats(calendrier):
    """Rejoue chaque championnat jusqu'a aujourd'hui : etat final (classement + 5 derniers
    matchs de chaque equipe) utilise pour les features des matchs a venir."""
    etats, joues = {}, {}
    for league_id in main.DOMESTIC_LEAGUES:
        etat = EtatChampionnat()
        for saison in saisons_ligue(league_id):
            etat.changer_saison(saison)
            matchs = sorted((e for e in calendrier.get(league_id, {}).get(saison, [])
                             if est_joue(e) and e["dateEvent"]), key=lambda e: (e["dateEvent"], e["idEvent"]))
            for e in matchs:
                etat.enregistrer(e["idHomeTeam"], e["idAwayTeam"], int(e["intHomeScore"]), int(e["intAwayScore"]))
                joues[e["idEvent"]] = e
        etats[league_id] = etat
    return etats, joues


def resoudre_paris(journal, joues):
    for pari in journal:
        e = joues.get(pari["idEvent"])
        if pari["statut"] != "en_attente" or not e:
            continue
        dom, ext = int(e["intHomeScore"]), int(e["intAwayScore"])
        reel = "domicile" if dom > ext else "exterieure" if dom < ext else "nul"
        gagne = reel == pari["issue"]
        pari["statut"] = "gagne" if gagne else "perdu"
        pari["gain"] = round(pari["mise"] * (pari["coteBookmaker"] - 1), 4) if gagne else -pari["mise"]


def pari_value(cote_bookmaker, cote_modele):
    return cote_bookmaker > COTE_MIN and cote_modele <= cote_bookmaker * (1 - ECART_MIN)


def etape_paris(calendrier, cotes):
    journal = _lire_json(FICHIER_PARIS, [])
    etats, joues = rejouer_championnats(calendrier)
    resoudre_paris(journal, joues)

    modeles, ck = charger_modele()
    deja = {(p["idEvent"], p["issue"]) for p in journal}
    aujourd_hui = str(date.today())
    nb_analyses = 0
    for m in matchs_a_venir(calendrier, aujourd_hui, aujourd_hui):
        cotes_book = cotes.get(m["idEvent"])
        if not cotes_book or not cotes_book.get("bookmaker"):
            continue
        x = etats[m["idLeague"]].features(m["idHomeTeam"], m["idAwayTeam"])
        if x is None:  # une equipe sans 5 matchs d'historique
            continue
        lam = predire_lambdas(modeles, ck, [x])[0]
        modele = cotes_match(lam[0], lam[1])
        nb_analyses += 1
        for issue, cle, cle_cote in ISSUES:
            c_book, c_modele = cotes_book.get(cle_cote), modele["cotes"][cle]
            if (m["idEvent"], issue) in deja or not c_book or not pari_value(c_book, c_modele):
                continue
            journal.append({
                "idEvent": m["idEvent"], "date": m["dateEvent"], "ligue": main.DOMESTIC_LEAGUES[m["idLeague"]],
                "equipeDomicile": m["strHomeTeam"], "equipeExterieur": m["strAwayTeam"],
                "issue": issue, "coteBookmaker": c_book, "bookmaker": cotes_book["bookmaker"],
                "coteModele": c_modele, "butsAttendus": [round(float(lam[0]), 2), round(float(lam[1]), 2)],
                "mise": round(1 / c_book, 4), "statut": "en_attente", "gain": None,
            })
    _ecrire_json(FICHIER_PARIS, journal)
    afficher_bilan(journal, nb_analyses)


def afficher_bilan(journal, nb_analyses):
    resolus = [p for p in journal if p["statut"] != "en_attente"]
    gagnes = sum(p["statut"] == "gagne" for p in resolus)
    gain = sum(p["gain"] for p in resolus)
    mises = sum(p["mise"] for p in resolus)
    print(f"## Bilan des paris du reseau — {date.today()}\n")
    print(f"- Matchs analyses aujourd'hui : {nb_analyses}")
    print(f"- Paris resolus : {len(resolus)} ({gagnes} gagnes, {len(resolus) - gagnes} perdus)")
    print(f"- Gain net cumule : {gain:+.2f} unites" + (f" (ROI {gain / mises:+.1%})" if mises else ""))
    print(f"- Paris en attente : {sum(p['statut'] == 'en_attente' for p in journal)}\n")
    nouveaux = [p for p in journal if p["date"] == str(date.today())]
    if nouveaux:
        print("### Nouveaux paris du jour\n")
        for p in nouveaux:
            print(f"- {p['equipeDomicile']} - {p['equipeExterieur']} ({p['issue']}) : cote {p['bookmaker']} "
                  f"{p['coteBookmaker']} vs modele {p['coteModele']} (buts attendus {p['butsAttendus']}), "
                  f"mise {p['mise']}")


if __name__ == "__main__":
    etape = sys.argv[1] if len(sys.argv) > 1 else "tout"
    if etape not in ("cotes", "paris", "tout"):
        print(f"Etape inconnue : {etape!r} (attendu : cotes, paris ou tout)")
        sys.exit(1)
    calendrier = charger_calendrier()
    cotes = etape_cotes(calendrier) if etape in ("cotes", "tout") else _lire_json(FICHIER_COTES, {}).get("data", {})
    if etape in ("paris", "tout"):
        etape_paris(calendrier, cotes)
