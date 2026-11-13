"""Paris automatiques bases sur le reseau de neurones (reseau_buts.pt), en deux etapes
(deux appels separes dans le workflow GitHub Actions, cf. `python paris_reseau.py <etape>`) :

1. `cotes` : recupere les cotes bookmaker de la semaine via The Odds API (releve complet le
   mardi, jeudi, samedi et dimanche, relance ciblee les autres jours pour les matchs du lendemain sans
   cote : meme rythme qu'avant, pour rester sous le quota gratuit). Cache : cache_cotes_winamax.json.
2. `paris` : resout les paris en attente, puis pour chaque match du jour :
   buts attendus du reseau -> loi de Poisson -> cotes justes (1 / probabilite) -> pari pris si
   la cote du bookmaker est superieure a COTE_MIN ET si la cote du modele est au moins
   ECART_MIN inferieure a celle du bookmaker (ex. bookmaker 5.00, modele 3.75).
   Journal : cache_paris_reseau.json (mise = 1 / cote : un pari gagne rapporte 1 unite brute).

`tout` (defaut, pratique en local) enchaine les deux. Variables d'environnement :
ODDS_API_KEY (plus aucune cle TheSportsDB).
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np

import main  # ligues et saisons
from construire_dataset_reseau import FICHIER_BRUTS, saisons_ligue
from calendrier.ligues import LIGUES
from odds import recuperer_toutes_les_cotes
from reseau_buts import EtatChampionnat, charger_modele, cotes_match, predire_lambdas

COTE_MIN = 4.00  # cote bookmaker strictement superieure a ce seuil
ECART_MIN = 0.15  # cote du modele au moins 15 % sous la cote du bookmaker
FICHIER_COTES = "cache_cotes_winamax.json"
FICHIER_PARIS = "cache_paris_reseau.json"
FICHIER_ANALYSES = "cache_analyses_reseau.json"  # {idEvent: date} des matchs passes au reseau
JOURS_RELEVE_COMPLET = {1, 3, 5, 6}  # mardi, jeudi, samedi, dimanche (lundi = 0) : 20 requetes par releve
# Identifiants de ligue -> cles The Odds API (pas de cotes publiees pour Tchequie, Chypre, Hongrie).
# Coupes d'Europe : cotes affichees sur le site uniquement (le modele ne parie que sur les championnats).
ODDS_API_SPORT_KEYS = {i: l["odds"] for i, l in LIGUES.items() if l["odds"]}
# Pas de pari "match nul" : cette issue est volontairement exclue.
ISSUES = [("domicile", "1", "domicile"), ("exterieure", "2", "exterieure")]


def _lire_json(fichier, defaut):
    if not os.path.exists(fichier):
        return defaut
    with open(fichier, encoding="utf-8") as f:
        return json.load(f)


def _ecrire_json(fichier, data):
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def charger_calendrier():
    """{ligue -> {saison -> evenements}} : historique fige (matchs_reseau_bruts.json) complete avec les
    resultats recents et les matchs a venir, via le package `calendrier/` (AUCUN appel TheSportsDB) : ESPN
    (resultats et a venir), football-data (resultats Pologne et Suisse), The Odds API (secours a venir).
    Met aussi a jour la base locale du site (`calendrier/base/` : evenements, clubs, logos).
    Tchequie, Chypre et Hongrie n'ont aucun fournisseur gratuit : leurs resultats restent figes (sans cotes,
    donc sans paris)."""
    from calendrier import source
    from calendrier.base import Base
    brut, rapport = source.completer_calendrier(_lire_json(FICHIER_BRUTS, {}), ids_ligues=list(main.DOMESTIC_LEAGUES),
                                                base=Base())
    par_source = {}
    for id_ligue, src in rapport["sources"].items():
        if id_ligue in main.DOMESTIC_LEAGUES:
            par_source.setdefault(src or "aucune", []).append(main.DOMESTIC_LEAGUES[id_ligue])
    modifies, ajoutes, logos_manquants = rapport["base_modifiee"]
    print(f"## Calendrier — {rapport['resultats_nouveaux']} resultats ESPN, {rapport['resultats_footballdata']} "
          f"resultats football-data ; a venir : "
          + ", ".join(f"{src} : {len(noms)} ligues" for src, noms in sorted(par_source.items())))
    print(f"- Base locale : {modifies} matchs mis a jour, {ajoutes} ajoutes, {logos_manquants} logos non telecharges")
    if rapport["ligues_sans_resultats"] or rapport["ligues_espn_en_panne"]:
        gelees = [main.DOMESTIC_LEAGUES[i] for i in rapport["ligues_sans_resultats"]]
        panne = [main.DOMESTIC_LEAGUES[i] for i in rapport["ligues_espn_en_panne"]]
        print(f"- Resultats figes (aucune source gratuite) : {', '.join(gelees) or 'aucune'} ; "
              f"ESPN en panne (rattrapage au prochain run) : {', '.join(panne) or 'aucune'}")
    try:  # coupes d'Europe : base du site uniquement (jamais l'historique des modeles), erreurs isolees
        europe = source.mettre_a_jour_europe(Base())
        print(f"- Coupes d'Europe : {europe['resultats']} resultats, base {europe['base_modifiee'][0]} mis a jour / "
              f"{europe['base_modifiee'][1]} ajoutes" + (f", ESPN en panne : {europe['ligues_espn_en_panne']}"
                                                         if europe["ligues_espn_en_panne"] else ""))
    except Exception as exc:  # noqa: BLE001
        print(f"- Coupes d'Europe : mise a jour impossible ({type(exc).__name__}: {exc}), base inchangee")
    print()
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
        fin_semaine = str(aujourd_hui + timedelta(days=7))
        semaine = matchs_a_venir(calendrier, cle_jour, fin_semaine) + matchs_europe_a_venir(cle_jour, fin_semaine)
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


def matchs_europe_a_venir(debut, fin):
    """Matchs non joues des coupes d'Europe dans [debut, fin] : utilises pour relever leurs cotes (affichage
    sur le site), jamais pour les paris du reseau. Identifiants et tours viennent de la base locale."""
    from calendrier import source
    from calendrier.base import Base
    base = Base()
    locaux = [e for i in main.COMPETITIONS_EUROPE for e in base.evenements_saison(i, main.SEASON)]
    try:
        evenements, _ = source.a_venir(date.fromisoformat(debut), date.fromisoformat(fin), locaux,
                                       ids_ligues=list(main.COMPETITIONS_EUROPE))
        return evenements
    except Exception as exc:  # noqa: BLE001
        print(f"- Calendrier europeen ESPN/Odds API indisponible ({type(exc).__name__}) : base locale")
        return [e for e in locaux if not est_joue(e) and e.get("dateEvent") and debut <= e["dateEvent"] <= fin]


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
    analyses = _lire_json(FICHIER_ANALYSES, {})
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
        analyses[m["idEvent"]] = m["dateEvent"]
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
    _ecrire_json(FICHIER_ANALYSES, analyses)
    afficher_bilan(journal, nb_analyses)


def afficher_bilan(journal, nb_analyses):
    # Plusieurs issues d'un meme match (ex. exterieure + nul) comptent comme un seul pari.
    par_match = {}
    for p in journal:
        par_match.setdefault(p["idEvent"], []).append(p)
    attente = sum(any(l["statut"] == "en_attente" for l in legs) for legs in par_match.values())
    resolus_m = [legs for legs in par_match.values() if all(l["statut"] != "en_attente" for l in legs)]
    gagnes = sum(any(l["statut"] == "gagne" for l in legs) for legs in resolus_m)
    resolus = [p for p in journal if p["statut"] != "en_attente"]
    gain = sum(p["gain"] for p in resolus)
    mises = sum(p["mise"] for p in resolus)
    print(f"## Bilan des paris du reseau — {date.today()}\n")
    print(f"- Matchs analyses aujourd'hui : {nb_analyses}")
    print(f"- Paris resolus : {len(resolus_m)} ({gagnes} gagnes, {len(resolus_m) - gagnes} perdus)")
    print(f"- Gain net cumule : {gain:+.2f} unites" + (f" (ROI {gain / mises:+.1%})" if mises else ""))
    print(f"- Paris en attente : {attente}\n")
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
        # Modele D (modele_d/paris.py) : memes calendrier et cotes, aucun appel API en plus. Isole du
        # reseau existant : une erreur ici ne doit jamais faire echouer l'etape ni perdre son journal.
        try:
            from modele_d import paris as paris_modele_d
            print()
            paris_modele_d.etape_paris_d(calendrier, cotes)
        except Exception as exc:  # noqa: BLE001
            print(f"\n## Modele D indisponible : {type(exc).__name__}: {exc}")
        # IA-optimisee : meme principe (journaux separes, memes cotes, erreurs isolees).
        try:
            from ia_optimisee import paris as paris_ia
            print()
            paris_ia.etape_paris_ia(calendrier, cotes)
        except Exception as exc:  # noqa: BLE001
            print(f"\n## IA-optimisee indisponible : {type(exc).__name__}: {exc}")
