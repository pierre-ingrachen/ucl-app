"""Facade : calendrier a jour (resultats recents + matchs a venir) sans TheSportsDB.

Pour chaque ligue : ESPN d'abord ; The Odds API (`/events`, gratuit) si ESPN ne couvre pas la
ligue, est en panne, ou renvoie une semaine vide alors que le calendrier local annonce des
matchs. Chaque match est rattache a l'`idEvent` TheSportsDB deja connu en local (journaux de
paris, cotes et historiques restent valides) ; un match absent du calendrier local recoit un
identifiant stable `x<ligue>-<domicile>-<exterieur>-<date>`, identique d'un fournisseur a l'autre.

Resultats recents : persistes dans `ressources/evenements_recents.json` (a committer par le
workflow) pour ne retelecharger que les derniers jours. Les ligues sans ESPN (Pologne, Suisse,
Tchequie, Chypre, Hongrie) n'ont pas de resultats ici : l'appelant garde alors sa source de
resultats (voir `completer_calendrier`, liste `ligues_sans_resultats`).

    .venv/bin/python -m calendrier.source prochains [jours]     # matchs des N prochains jours
    .venv/bin/python -m calendrier.source diagnostic [jours]    # clubs non rapproches, ligues muettes
"""
import json
import logging
import os
import sys
from datetime import date, timedelta

from . import espn, footballdata, logos, odds_api
from .base import Base
from .equipes import Annuaire, RESSOURCES
from .ligues import LIGUES, CHAMPIONNATS, COUPES_EUROPE, saison

journal = logging.getLogger("calendrier.source")
FICHIER_RECENTS = os.path.join(RESSOURCES, "evenements_recents.json")
HORIZON_JOURS = 8             # matchs a venir demandes (le site affiche 7 jours)
RECUL_JOURS = 2               # on re-telecharge les 2 derniers jours deja couverts (scores tardifs)
RECUL_MAX_JOURS = 120         # plafond du rattrapage au premier run
TOLERANCE_REPORT_JOURS = 120  # un match deplace de moins de 120 jours reste le meme match
TOLERANCE_MATCH_JOUE_JOURS = 2  # ... sauf s'il est deja joue (score connu) : alors seulement a +/- 2 jours
CHAMPS_RECENTS = ("idEvent", "idLeague", "strSeason", "idHomeTeam", "idAwayTeam", "strHomeTeam", "strAwayTeam",
                  "dateEvent", "intHomeScore", "intAwayScore")  # le cache ne garde que le strict necessaire
CLES_SCORE = ("intHomeScore", "intAwayScore", "strStatus", "strPostponed", "source")
CLES_DYNAMIQUES = ("dateEvent", "strTime", "strTimestamp", "intHomeScore", "intAwayScore", "strStatus",
                   "strPostponed", "source")


def _sans_id(e):
    return e.get("idEvent") is None


def _joue(e):
    return e.get("intHomeScore") not in (None, "") and e.get("intAwayScore") not in (None, "")


def identifiant_stable(e):
    return f"x{e['idLeague']}-{e['idHomeTeam']}-{e['idAwayTeam']}-{e['dateEvent']}"


def rattacher(evenements, locaux):
    """Donne un `idEvent` a chaque evenement fournisseur. `locaux` = evenements TheSportsDB deja
    connus (avec idEvent, idLeague, idHomeTeam, idAwayTeam, dateEvent, strSeason). Un evenement dont
    (ligue, saison, domicile, exterieur) existe en local reprend son idEvent et ses champs
    statiques (tour, stade...), seuls les champs dynamiques (date, heure, score, statut) sont mis a
    jour ; a egalite (plusieurs confrontations dans la saison) c'est la date la plus proche, chaque
    match local n'etant utilise qu'une fois. Renvoie (evenements, nb_rattaches)."""
    par_cle = {}
    for l in locaux:
        par_cle.setdefault((l["idLeague"], l["strSeason"], l["idHomeTeam"], l["idAwayTeam"]), []).append(l)
    utilises, resultat, nb = set(), [], 0
    # Les matchs deja datés chez nous passent d'abord : ils reservent leur match local.
    for e in sorted(evenements, key=lambda x: x["dateEvent"]):
        candidats = [l for l in par_cle.get((e["idLeague"], e["strSeason"], e["idHomeTeam"], e["idAwayTeam"]), [])
                     if l["idEvent"] not in utilises]
        # Un match local deja joue ne peut pas etre « reporte » : un evenement fournisseur a une autre date
        # est un autre match (ex. 2026-11-22 : Grasshoppers-Basel du 28/11 mal nomme avait ecrase Zürich-Basel
        # joue le 22/08).
        candidats = [l for l in candidats
                     if abs((date.fromisoformat(l["dateEvent"]) - date.fromisoformat(e["dateEvent"])).days)
                     <= (TOLERANCE_MATCH_JOUE_JOURS if _joue(l) else TOLERANCE_REPORT_JOURS)] if candidats else []
        if candidats:
            local = min(candidats, key=lambda l: abs((date.fromisoformat(l["dateEvent"])
                                                      - date.fromisoformat(e["dateEvent"])).days))
            utilises.add(local["idEvent"])
            fusion = dict(local)
            cles = CLES_SCORE if e.get("source") == "footballdata" else CLES_DYNAMIQUES  # date locale != date UTC
            fusion.update({k: e.get(k) for k in cles if e.get(k) is not None or k.startswith("int")})
            for cle in ("strHomeTeamBadge", "strAwayTeamBadge", "strLeagueBadge", "strVenue"):
                if not fusion.get(cle):
                    fusion[cle] = e.get(cle)
            resultat.append(fusion)
            nb += 1
        else:
            resultat.append(dict(e, idEvent=identifiant_stable(e)))
    return resultat, nb


def locaux_depuis_fichier(chemin, ids_ligues, aujourd_hui=None):
    """Calendrier local de la saison en cours d'un fichier au format matchs_reseau_bruts.json."""
    aujourd_hui = aujourd_hui or date.today()
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding="utf-8") as f:
        brut = json.load(f)
    return [dict(e, idLeague=i, strSeason=saison(i, aujourd_hui)) for i in ids_ligues
            for e in brut.get(i, {}).get(saison(i, aujourd_hui), []) if e.get("dateEvent")]


def _lire_recents():
    if os.path.exists(FICHIER_RECENTS):
        with open(FICHIER_RECENTS, encoding="utf-8") as f:
            return json.load(f)
    return {"couvert_jusqu_au": {}, "evenements": {}}


def _ecrire_recents(donnees):
    os.makedirs(RESSOURCES, exist_ok=True)
    with open(FICHIER_RECENTS, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=0, sort_keys=True)


def calendrier_attendu(locaux, debut, fin):
    """Ligues pour lesquelles le calendrier local annonce au moins un match dans [debut, fin]."""
    return {l["idLeague"] for l in locaux if str(debut) <= l["dateEvent"] <= str(fin)}


def a_venir(debut, fin, locaux=(), ids_ligues=None, annuaire=None, secours=True, session_espn=None,
            session_odds=None, cle_odds=None, inclure_joues=False):
    """Matchs a venir (non joues ; avec `inclure_joues`, aussi ceux deja termines) dans [debut, fin] pour `ids_ligues` (toutes par defaut).
    Renvoie (evenements, rapport) ; rapport = {"sources": {ligue: "espn"|"odds_api"|None},
    "ignores": n, "rattaches": n}."""
    annuaire = annuaire or Annuaire()
    ids = list(ids_ligues or LIGUES)
    jours = [debut + timedelta(i) for i in range((fin - debut).days + 1)]
    evenements, en_panne, ignores = espn.evenements([(i, j) for i in ids for j in jours], annuaire, session_espn)
    sources = {i: ("espn" if LIGUES[i]["espn"] and i not in en_panne else None) for i in ids}
    par_ligue = {i: [e for e in evenements if e["idLeague"] == i] for i in ids}

    # Secours : ligue sans ESPN, ESPN en panne, ou ESPN muet alors que le calendrier local annonce des matchs.
    attendues = calendrier_attendu(locaux, debut, fin)
    besoin_secours = [i for i in ids if sources[i] is None or (not par_ligue[i] and i in attendues)]
    if secours and besoin_secours:
        sup, panne_odds, ign2 = odds_api.evenements(besoin_secours, annuaire, cle_odds, session_odds)
        ignores += ign2
        for i in besoin_secours:
            if i in panne_odds or not LIGUES[i]["odds"]:
                continue
            venir = [e for e in sup if e["idLeague"] == i and str(debut) <= e["dateEvent"] <= str(fin)]
            deja = {(e["idHomeTeam"], e["idAwayTeam"], e["dateEvent"]) for e in par_ligue[i]}
            nouveaux = [e for e in venir if (e["idHomeTeam"], e["idAwayTeam"], e["dateEvent"]) not in deja]
            if sources[i] is None or nouveaux:
                par_ligue[i] = par_ligue[i] + nouveaux
                sources[i] = "odds_api"
    annuaire.sauvegarder_pont()

    tous = [e for i in ids for e in par_ligue[i]
            if e["strPostponed"] != "yes" and (inclure_joues or e["intHomeScore"] is None)
            and str(debut) <= e["dateEvent"] <= str(fin)]
    tous, rattaches = rattacher(tous, list(locaux))
    return tous, {"sources": sources, "ignores": ignores, "rattaches": rattaches}


def completer_calendrier(brut, aujourd_hui=None, horizon=HORIZON_JOURS, ids_ligues=None, annuaire=None,
                         persister=True, session_espn=None, session_odds=None, cle_odds=None, secours=True,
                         session_fd=None, base=None):
    """Met a jour `brut` ({ligue: {saison: [evenements]}}, format de matchs_reseau_bruts.json) avec
    les resultats recents et les matchs des `horizon` prochains jours, et le renvoie.

    - resultats : ESPN, de la derniere date couverte (memorisee par ligue) jusqu'a aujourd'hui ;
      ajoutes au cache `evenements_recents.json` pour ne pas les retelecharger ;
    - a venir : `a_venir` (ESPN, secours The Odds API) ;
    - Pologne et Suisse : resultats football-data ; les ligues sans aucun fournisseur gratuit (Tchequie,
      Chypre, Hongrie) sont listees dans rapport["ligues_sans_resultats"] (resultats figes) ;
    - `base` (calendrier.base.Base) : base locale du site. Si fournie, elle sert de calendrier local (evenements
      complets : tour, stade, logos) et recoit les resultats, les nouveaux matchs et les nouveaux clubs ; ses
      logos manquants sont telecharges.
    Renvoie (brut, rapport)."""
    aujourd_hui = aujourd_hui or date.today()
    annuaire = annuaire or Annuaire()
    ids = list(ids_ligues or CHAMPIONNATS)
    recents = _lire_recents()

    def saison_courante(i):
        return saison(i, aujourd_hui)

    # Calendrier local de la saison en cours, a plat, pour le rattachement des idEvent.
    locaux = []
    for i in ids:
        de_la_base = base.evenements_saison(i, saison_courante(i)) if base else []
        if de_la_base:
            locaux += [dict(e) for e in de_la_base if e.get("dateEvent")]
            continue
        for e in brut.get(i, {}).get(saison_courante(i), []):
            if e.get("dateEvent"):
                locaux.append(dict(e, idLeague=i, strSeason=saison_courante(i)))
    for e in recents["evenements"].values():  # resultats deja recuperes lors des runs precedents
        if e["idLeague"] in ids and e["strSeason"] == saison_courante(e["idLeague"]):
            locaux = [l for l in locaux if l["idEvent"] != e["idEvent"]] + [e]

    # 1. Resultats recents (ESPN seulement).
    derniere_locale = {i: max((e["dateEvent"] for e in brut.get(i, {}).get(saison_courante(i), [])
                               if e.get("intHomeScore") is not None and e.get("dateEvent")), default=None) for i in ids}
    taches = []
    for i in ids:
        if not LIGUES[i]["espn"]:
            continue
        depart = (recents["couvert_jusqu_au"].get(i) or derniere_locale[i] or str(aujourd_hui - timedelta(RECUL_MAX_JOURS)))
        depart = max(date.fromisoformat(depart) - timedelta(RECUL_JOURS), aujourd_hui - timedelta(RECUL_MAX_JOURS))
        taches += [(i, depart + timedelta(k)) for k in range((aujourd_hui - depart).days + 1)]
    passes, panne, ign1 = espn.evenements(taches, annuaire, session_espn)
    joues = [e for e in passes if e["intHomeScore"] is not None]
    joues, _ = rattacher(joues, locaux)
    for e in joues:
        recents["evenements"][e["idEvent"]] = {k: e.get(k) for k in CHAMPS_RECENTS}
    recents["evenements"] = {k: e for k, e in recents["evenements"].items()   # saisons terminees : inutiles
                             if e["strSeason"] == saison_courante(e["idLeague"])}
    for i in ids:
        if LIGUES[i]["espn"] and i not in panne:
            recents["couvert_jusqu_au"][i] = str(aujourd_hui)

    # 1 bis. Ligues sans ESPN mais avec fichier football-data (Pologne, Suisse) : fichier retelecharge en
    # entier a chaque run (petit), seuls les resultats rattaches a un match du calendrier local sont gardes.
    fd, panne_fd = footballdata.resultats([i for i in ids if not LIGUES[i]["espn"]], annuaire,
                                          aujourd_hui - timedelta(RECUL_MAX_JOURS), session_fd)
    fd_joues, fd_rattaches = [], 0
    if fd:
        fusion, _ = rattacher(fd, locaux)
        fd_joues = [e for e in fusion if not str(e["idEvent"]).startswith("x")]  # « x... » = absent du calendrier local
        fd_rattaches = len(fd_joues)
        for e in fd_joues:
            recents["evenements"][e["idEvent"]] = {k: e.get(k) for k in CHAMPS_RECENTS}

    # 2. A venir.
    venir, rapport_venir = a_venir(aujourd_hui, aujourd_hui + timedelta(horizon), locaux, ids, annuaire, secours,
                                   session_espn, session_odds, cle_odds)

    # 3. Fusion dans `brut` : un evenement remplace celui de meme idEvent, sinon s'ajoute.
    nouveaux = {e["idEvent"]: e for e in list(recents["evenements"].values()) + venir}
    for e in nouveaux.values():
        i, s = e["idLeague"], e["strSeason"]
        liste = brut.setdefault(i, {}).setdefault(s, [])
        champs = ("idEvent", "dateEvent", "idHomeTeam", "idAwayTeam", "strHomeTeam", "strAwayTeam",
                  "intHomeScore", "intAwayScore")
        minimal = {k: e.get(k) for k in champs}
        for k in range(len(liste)):
            if liste[k]["idEvent"] == e["idEvent"]:
                liste[k] = {**liste[k], **minimal}
                break
        else:
            liste.append(minimal)
    if persister:
        _ecrire_recents(recents)
    ajoutes_base = (0, 0, 0)
    if base and persister:
        completes = joues + fd_joues + venir  # evenements COMPLETS de ce run (jamais le cache minimal des runs passes)
        base.completer_equipes(completes)
        modifies, ajoutes = base.upsert(completes)
        ok, echecs, _ = logos.telecharger_manquants(base)
        ajoutes_base = (modifies, ajoutes, len(echecs))

    rapport = dict(rapport_venir, ignores=rapport_venir["ignores"] + ign1,
                   resultats_nouveaux=len(joues), ligues_espn_en_panne=sorted(panne),
                   resultats_footballdata=fd_rattaches, base_modifiee=ajoutes_base,
                   ligues_sans_resultats=[i for i in ids if not LIGUES[i]["espn"]
                                          and (i not in footballdata.CODES or i in panne_fd)])
    return brut, rapport


def mettre_a_jour_europe(base, aujourd_hui=None, horizon=HORIZON_JOURS, annuaire=None, persister=True,
                         session_espn=None, session_odds=None, cle_odds=None, secours=True):
    """Met a jour la base locale pour les 3 coupes d'Europe : resultats ESPN depuis la derniere date couverte
    (memorisee dans le meme fichier que les championnats, cle = id de la competition), matchs a venir (ESPN,
    secours The Odds API), tours de qualification inclus. N'alimente jamais `brut` (historique des modeles :
    championnats seulement). Renvoie un rapport {"resultats", "base_modifiee": (modifies, ajoutes, logos_echecs),
    "ligues_espn_en_panne"}."""
    aujourd_hui = aujourd_hui or date.today()
    annuaire = annuaire or Annuaire()
    ids = list(COUPES_EUROPE)
    recents = _lire_recents()
    locaux = [dict(e) for i in ids for e in base.evenements_saison(i, saison(i, aujourd_hui))]

    taches = []
    for i in ids:
        derniere = max((e["dateEvent"] for e in locaux if e["idLeague"] == i and e.get("intHomeScore") is not None),
                       default=None)
        depart = recents["couvert_jusqu_au"].get(i) or derniere or str(aujourd_hui - timedelta(RECUL_MAX_JOURS))
        depart = max(date.fromisoformat(depart) - timedelta(RECUL_JOURS), aujourd_hui - timedelta(RECUL_MAX_JOURS))
        taches += [(i, depart + timedelta(k)) for k in range((aujourd_hui - depart).days + 1)]
    passes, panne, _ = espn.evenements(taches, annuaire, session_espn)
    joues, _ = rattacher([e for e in passes if e["intHomeScore"] is not None], locaux)
    for i in ids:
        if i not in panne:
            recents["couvert_jusqu_au"][i] = str(aujourd_hui)
    venir, _ = a_venir(aujourd_hui, aujourd_hui + timedelta(horizon), locaux, ids, annuaire, secours,
                       session_espn, session_odds, cle_odds)
    resultat = (0, 0, 0)
    if persister:
        _ecrire_recents(recents)
        completes = joues + venir
        base.completer_equipes(completes)
        modifies, ajoutes = base.upsert(completes)
        _, echecs, _ = logos.telecharger_manquants(base)
        resultat = (modifies, ajoutes, len(echecs))
    annuaire.sauvegarder_pont()
    return {"resultats": len(joues), "base_modifiee": resultat, "ligues_espn_en_panne": sorted(panne)}


def _afficher(evenements, rapport):
    noms = {i: LIGUES[i]["nom"] + (f" ({LIGUES[i]['pays']})" if LIGUES[i]["pays"] else "") for i in LIGUES}
    for e in sorted(evenements, key=lambda x: (x["dateEvent"], x["strTime"])):
        print(f"{e['dateEvent']} {e['strTime'][:5]}  {noms[e['idLeague']]:<28} {e['strHomeTeam']} - {e['strAwayTeam']}"
              f"   [{e['source']}, id {e['idEvent']}]")
    print(f"\n{len(evenements)} matchs ; sources par ligue : "
          + ", ".join(f"{LIGUES[i]['nom'][:12]}={s or '-'}" for i, s in rapport["sources"].items()))
    print(f"rattaches a un idEvent local : {rapport['rattaches']}, ignores (mal formes) : {rapport['ignores']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    commande = sys.argv[1] if len(sys.argv) > 1 else "prochains"
    jours = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    if commande not in ("prochains", "diagnostic"):
        print("usage : python -m calendrier.source prochains|diagnostic [jours]")
        sys.exit(1)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    from construire_dataset_reseau import FICHIER_BRUTS  # noqa: E402 (donne le chemin du calendrier local)
    with open(FICHIER_BRUTS, encoding="utf-8") as f:
        brut = json.load(f)
    locaux = [dict(e, idLeague=i, strSeason=s) for i, ss in brut.items() for s, ev in ss.items()
              for e in ev if s == saison(i, date.today())]
    base_locale = Base()
    locaux += [e for i in COUPES_EUROPE for e in base_locale.evenements_saison(i, saison(i, date.today()))]
    ann = Annuaire()
    evs, rap = a_venir(date.today(), date.today() + timedelta(jours), locaux, annuaire=ann)
    if commande == "prochains":
        _afficher(evs, rap)
    else:
        print(f"{len(evs)} matchs sur {jours} jours.")
        if ann.inconnus:
            print("\nClubs non rapproches (a ajouter dans ALIAS_NOMS de equipes.py ou pont_espn.json) :")
            for (lg, n), raison in sorted(ann.inconnus.items()):
                print(f"  {LIGUES[lg]['nom']} : {n} — {raison}")
        muettes = [LIGUES[i]["nom"] for i, s in rap["sources"].items() if s is None and LIGUES[i]["odds"]]
        print("\nLigues sans fournisseur :", ", ".join(muettes) or "aucune",
              "| non couvertes par aucun fournisseur gratuit :", ", ".join(
                  LIGUES[i]["nom"] for i in LIGUES if not LIGUES[i]["espn"] and not LIGUES[i]["odds"]))
        nouveaux = [e for e in evs if not str(e["idEvent"]).isdigit()]
        print(f"Matchs sans idEvent TheSportsDB (absents du calendrier local) : {len(nouveaux)}")
        for e in nouveaux[:20]:
            print("  ", e["dateEvent"], e["strHomeTeam"], "-", e["strAwayTeam"], e["idEvent"])
