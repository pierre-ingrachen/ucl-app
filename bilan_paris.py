"""Bilan quotidien des paris "value" sur les matchs du jour, en deux etapes distinctes
(deux appels separes dans le workflow GitHub Actions, cf. `python bilan_paris.py <etape>`) :

1. `cotes`  : recupere les cotes de la semaine (n'appelle reellement The Odds API que le
   lundi, ou en relance ciblee - cf. main.obtenir_cotes_semaine).
2. `paris`  : resout les paris "en_attente" des jours precedents des que le resultat du
   match est connu (gain net calcule), puis repere parmi les matchs du jour les cas ou la
   cote du bookmaker (Winamax, sinon Betclic, sinon Unibet - cf. odds.py) depasse d'au
   moins 15% la cote implicite du modele (0.9 / probabilite, meme formule que le frontend) :
   un tel ecart est enregistre comme un pari pris, mise = 1 / cote du bookmaker.

`tout` (par defaut, pratique en local) enchaine les deux etapes. Le journal complet est
persiste dans cache_paris.json (commit automatique par le workflow). Ce script s'appuie sur
les fonctions deja existantes de main.py/rating.py/odds.py : il ne reimplemente aucune
logique de recuperation de donnees ou de calcul de probabilite.
"""

import sys
from datetime import date

from main import (
    obtenir_matchs_a_venir, obtenir_matchs_championnats_a_venir,
    obtenir_modele_rating, obtenir_modele_championnat, obtenir_cotes_semaine,
    obtenir_pays_equipe, charger_cache_permanent, sauvegarder_cache_permanent,
    charger_historique_championnat, charger_cache,
    LEAGUE_IDS, DOMESTIC_LEAGUES, CACHE_TEAMS_FILE, CACHE_CHAMPIONNAT_HISTORIQUE_FILE,
    CACHE_COTES_FILE, CACHE_PARIS_FILE,
)
from rating import predire_resultat

SEUIL_VALUE = 1.15  # cote bookmaker >= 15% au-dessus de la cote du modele


def cote_modele(probabilite):
    if not probabilite or probabilite <= 0:
        return None
    return 0.9 / probabilite


def _tous_les_matchs():
    return obtenir_matchs_a_venir() + obtenir_matchs_championnats_a_venir()


def matchs_du_jour():
    aujourd_hui = str(date.today())
    return [m for m in _tous_les_matchs() if m.get("dateEvent") == aujourd_hui]


def resultat_reel(match):
    """'domicile' | 'nul' | 'exterieure' | None (match pas encore joue ou score inconnu)."""
    hs, aws = match.get("intHomeScore"), match.get("intAwayScore")
    if hs is None or aws is None:
        return None
    hs, aws = int(hs), int(aws)
    if hs > aws:
        return "domicile"
    if hs < aws:
        return "exterieure"
    return "nul"


def resoudre_paris_en_attente(bilan):
    matchs_par_id = {m["idEvent"]: m for m in _tous_les_matchs()}
    for pari in bilan:
        if pari["statut"] != "en_attente":
            continue
        match = matchs_par_id.get(pari["idEvent"])
        if not match:
            continue
        resultat = resultat_reel(match)
        if resultat is None:
            continue
        if resultat == pari["issue"]:
            pari["statut"] = "gagne"
            pari["gain"] = round(pari["mise"] * (pari["coteBookmaker"] - 1), 4)
        else:
            pari["statut"] = "perdu"
            pari["gain"] = round(-pari["mise"], 4)


def predictions_du_match(match, cache_teams, cache_championnat_historique):
    id_ligue = match.get("idLeague")
    if id_ligue in LEAGUE_IDS:
        home_pays = obtenir_pays_equipe(match.get("idHomeTeam"), cache_teams)
        away_pays = obtenir_pays_equipe(match.get("idAwayTeam"), cache_teams)
        modele = obtenir_modele_rating()
        return predire_resultat(modele, match.get("idHomeTeam"), match.get("idAwayTeam"), home_pays, away_pays)
    if id_ligue in DOMESTIC_LEAGUES:
        matchs_ligue = charger_historique_championnat(id_ligue, cache_championnat_historique)
        modele = obtenir_modele_championnat(id_ligue, matchs_ligue)
        return predire_resultat(modele, match.get("idHomeTeam"), match.get("idAwayTeam"), "", "")
    return None


def chercher_nouveaux_paris(bilan, cotes_semaine):
    deja_paries = {(p["idEvent"], p["issue"]) for p in bilan}
    cache_teams = charger_cache_permanent(CACHE_TEAMS_FILE)
    cache_championnat_historique = charger_cache(CACHE_CHAMPIONNAT_HISTORIQUE_FILE) or {}

    issues = [
        ("domicile", "probaVictoireDomicile", "domicile"),
        ("nul", "probaNul", "nul"),
        ("exterieure", "probaVictoireExterieure", "exterieure"),
    ]

    for match in matchs_du_jour():
        cotes = cotes_semaine.get(match["idEvent"])
        if not cotes or not cotes.get("bookmaker"):
            continue

        predictions = predictions_du_match(match, cache_teams, cache_championnat_historique)
        if not predictions:
            continue

        for issue, cle_proba, cle_cote in issues:
            if (match["idEvent"], issue) in deja_paries:
                continue
            c_modele = cote_modele(predictions.get(cle_proba))
            c_bookmaker = cotes.get(cle_cote)
            if not c_modele or not c_bookmaker or c_bookmaker < SEUIL_VALUE * c_modele:
                continue

            bilan.append({
                "idEvent": match["idEvent"],
                "date": match.get("dateEvent"),
                "equipeDomicile": match.get("strHomeTeam"),
                "equipeExterieur": match.get("strAwayTeam"),
                "issue": issue,
                "coteBookmaker": c_bookmaker,
                "bookmaker": cotes.get("bookmaker"),
                "coteModele": round(c_modele, 3),
                "mise": round(1 / c_bookmaker, 4),
                "statut": "en_attente",
                "gain": None,
            })

    sauvegarder_cache_permanent(CACHE_TEAMS_FILE, cache_teams)
    sauvegarder_cache_permanent(CACHE_CHAMPIONNAT_HISTORIQUE_FILE, cache_championnat_historique)


def afficher_bilan(bilan):
    resolus = [p for p in bilan if p["statut"] != "en_attente"]
    gain_total = sum(p["gain"] for p in resolus)
    gagnes = sum(1 for p in resolus if p["statut"] == "gagne")
    en_attente = sum(1 for p in bilan if p["statut"] == "en_attente")

    print(f"## Bilan des paris — {date.today()}\n")
    print(f"- Paris resolus : {len(resolus)} ({gagnes} gagnes, {len(resolus) - gagnes} perdus)")
    print(f"- Gain net cumule : {gain_total:+.2f} unites")
    print(f"- Paris en attente : {en_attente}\n")

    nouveaux = [p for p in bilan if p["date"] == str(date.today())]
    if nouveaux:
        print("### Nouveaux paris du jour\n")
        for p in nouveaux:
            print(f"- {p['equipeDomicile']} vs {p['equipeExterieur']} ({p['issue']}) "
                  f"— cote {p['bookmaker']} {p['coteBookmaker']} vs cote modele {p['coteModele']}, "
                  f"mise {p['mise']}")


def etape_cotes():
    """Etape 1 : recupere (ou relit) les cotes de la semaine. N'appelle reellement The Odds
    API que le lundi (releve complet) ou pour une relance ciblee sur un match du lendemain
    encore sans cote (cf. main.obtenir_cotes_semaine) — les autres jours, relit juste le
    cache local sans consommer de quota."""
    cotes = obtenir_cotes_semaine()
    quota = charger_cache_permanent(CACHE_COTES_FILE).get("quota") or {}
    avec_cote = sum(1 for c in cotes.values() if c.get("bookmaker"))

    print(f"## Cotes — {date.today()}\n")
    print(f"- Matchs suivis avec une cote trouvee : {avec_cote}/{len(cotes)}")
    print(f"- Quota The Odds API restant : {quota.get('restant', 'inconnu')}\n")
    return cotes


def etape_paris(cotes_semaine):
    """Etape 2 : resout les paris en attente puis choisit les paris du jour, a partir des
    cotes deja recuperees a l'etape precedente (aucun nouvel appel a The Odds API ici)."""
    bilan = charger_cache_permanent(CACHE_PARIS_FILE)
    if not isinstance(bilan, list):
        bilan = []

    resoudre_paris_en_attente(bilan)
    chercher_nouveaux_paris(bilan, cotes_semaine)

    sauvegarder_cache_permanent(CACHE_PARIS_FILE, bilan)
    afficher_bilan(bilan)


if __name__ == "__main__":
    etape = sys.argv[1] if len(sys.argv) > 1 else "tout"

    if etape == "cotes":
        etape_cotes()
    elif etape == "paris":
        etape_paris(obtenir_cotes_semaine())
    elif etape == "tout":
        etape_paris(etape_cotes())
    else:
        print(f"Etape inconnue : {etape!r} (attendu : cotes, paris, ou tout)")
        sys.exit(1)
