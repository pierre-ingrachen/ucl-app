"""Tests hors ligne du paquet `calendrier` (fausses reponses ESPN / The Odds API, aucun reseau).

    .venv/bin/python -m unittest calendrier.tests.test_calendrier -v

Test en ligne facultatif (ESPN reel) : CALENDRIER_LIVE=1 .venv/bin/python -m unittest calendrier.tests.test_calendrier
"""
import os
import tempfile
import unittest
import zlib
from datetime import date

import requests

from calendrier import espn, footballdata, odds_api, source
from calendrier.equipes import Annuaire, normaliser
from calendrier.ligues import LIGUES, saison

ANNUAIRE = {
    "equipes": {
        "1": {"nom": "Paris Saint-Germain", "badge": "https://tsdb/psg.png", "ligues": ["4334"]},
        "2": {"nom": "Marseille", "badge": "", "ligues": ["4334"]},
        "3": {"nom": "Union Berlin", "badge": "", "ligues": ["4331"]},
        "4": {"nom": "Union Saint-Gilloise", "badge": "", "ligues": ["4338"]},
        "5": {"nom": "Köln", "badge": "", "ligues": ["4331"]},
        "6": {"nom": "Lille", "badge": "", "ligues": ["4334"]},
        "7": {"nom": "Lillestrøm", "badge": "", "ligues": ["4358"]},
        "8": {"nom": "Piast Gliwice", "badge": "", "ligues": ["4422"]},
        "9": {"nom": "Korona Kielce", "badge": "", "ligues": ["4422"]},
    },
    "ligues": {"4334": "https://tsdb/l1.png"},
}


def annuaire():
    return Annuaire(donnees=ANNUAIRE, pont={})


class Reponse:
    def __init__(self, donnees, code=200, entetes=None):
        self.status_code, self._donnees, self.headers = code, donnees, entetes or {}

    def json(self):
        return self._donnees

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(str(self.status_code))


class FausseSession:
    """get(url, params, timeout) -> Reponse, selon une fonction de routage."""

    def __init__(self, routeur):
        self.routeur, self.appels = routeur, []

    def get(self, url, params=None, timeout=None):
        self.appels.append((url, dict(params or {})))
        return self.routeur(url, params or {})


def evenement_espn(id_, dom, ext, dt="2026-11-21T20:00Z", score=("2", "1"), statut="STATUS_FULL_TIME",
                   id_dom=None, id_ext=None):
    id_dom, id_ext = id_dom or str(zlib.crc32(dom.encode())), id_ext or str(zlib.crc32(ext.encode()))
    termine = statut == "STATUS_FULL_TIME"
    return {
        "id": id_, "date": dt, "venue": {"fullName": "Stade X"},
        "status": {"type": {"name": statut, "state": "post" if termine else "pre", "completed": termine}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": score[0], "team": {"id": id_dom, "displayName": dom, "logo": "https://espn/dom.png"}},
            {"homeAway": "away", "score": score[1], "team": {"id": id_ext, "displayName": ext, "logo": "https://espn/ext.png"}},
        ]}],
    }


class TestNormalisation(unittest.TestCase):
    def test_noms_equivalents(self):
        self.assertEqual(normaliser("FC Köln"), normaliser("Koln"))
        self.assertEqual(normaliser("Paris Saint-Germain"), normaliser("paris saint germain"))
        self.assertEqual(normaliser("FC Cologne"), normaliser("Köln"))  # alias
        self.assertEqual(normaliser("Lillestrom"), normaliser("Lillestrøm"))  # lettre non decomposable par NFKD
        self.assertEqual(normaliser("Wisla Krakow"), normaliser("Wisła Kraków"))

    def test_resolution_exacte_prefixe_et_inconnu(self):
        a = annuaire()
        self.assertEqual(a.resoudre("Marseille", "4334"), "2")
        self.assertEqual(a.resoudre("Olympique de Marseille", "4334"), "2")  # nom plus long que l'annuaire
        self.assertIsNone(a.resoudre("Clermont Foot", "4334"))
        self.assertIn(("4334", "Clermont Foot"), a.inconnus)

    def test_candidats_limites_a_la_ligue(self):
        # « Lillestrom » (Norvege) ne doit pas se rabattre sur Lille (France).
        a = annuaire()
        self.assertEqual(a.resoudre("Lillestrom", "4358"), "7")
        self.assertEqual(a.resoudre("Lille", "4334"), "6")

    def test_ambiguite_refusee(self):
        # En coupe d'Europe tous les clubs sont candidats : « Union » seul est ambigu.
        a = annuaire()
        self.assertIsNone(a.resoudre("Union", "4480"))
        self.assertEqual(a.resoudre("Union Berlin", "4480"), "3")

    def test_pont_espn_prioritaire_et_memorise(self):
        a = annuaire()
        a.pont["espn:99"] = "6"
        self.assertEqual(a.resoudre("Nom completement different", "4334", "99"), "6")
        self.assertEqual(a.resoudre("Marseille", "4334", "55"), "2")
        self.assertEqual(a.pont["espn:55"], "2")
        self.assertTrue(a.pont_modifie)

    def test_rapprochement_douteux_non_memorise(self):
        a = annuaire()
        self.assertEqual(a.resoudre("Olympique Marseille", "4334", "55"), "2")  # prefixe : sur
        self.assertIn("espn:55", a.pont)
        a2 = annuaire()
        a2.equipes["10"] = {"nom": "Stade Brestois", "badge": "", "ligues": ["4334"]}
        self.assertEqual(a2.resoudre("Stade Brestoix", "4334", "66"), "10")  # similarite moyenne : accepte...
        self.assertNotIn("espn:66", a2.pont)                              # ...mais non fige

    def test_pont_fourni_jamais_ecrit_sur_disque(self):
        a = annuaire()
        a.resoudre("Marseille", "4334", "55")
        self.assertIsNone(a.fichier_pont)
        a.sauvegarder_pont()  # ne doit rien ecrire

    def test_id_provisoire_identique_entre_fournisseurs(self):
        a = annuaire()
        self.assertEqual(a.resoudre_ou_provisoire("Clermont Foot", "4334", "7"),
                         a.resoudre_ou_provisoire("Clermont Foot", "4334"))

    def test_logo_tsdb_prefere_puis_fournisseur(self):
        a = annuaire()
        self.assertEqual(a.logo("1", "https://espn/x.png"), "https://tsdb/psg.png")
        self.assertEqual(a.logo("2", "https://espn/x.png"), "https://espn/x.png")
        self.assertEqual(a.logo("2"), "")


class TestLigues(unittest.TestCase):
    def test_saison(self):
        self.assertEqual(saison("4328", date(2026, 11, 13)), "2026-2027")
        self.assertEqual(saison("4328", date(2027, 5, 20)), "2026-2027")
        self.assertEqual(saison("4480", date(2026, 7, 7)), "2026-2027")   # tour preliminaire de juillet
        self.assertEqual(saison("4358", date(2026, 11, 1)), "2026")        # annee civile
        self.assertEqual(saison("4328", "2026-06-30"), "2025-2026")

    def test_coherence_avec_main(self):
        os.environ.setdefault("SPORTSDB_API_KEY", "test")
        import main
        self.assertEqual({i: n for i, n in main.DOMESTIC_LEAGUES.items()}, {i: LIGUES[i]["nom"] for i in main.DOMESTIC_LEAGUES})
        self.assertEqual(set(main.COMPETITIONS_EUROPE), {i for i, l in LIGUES.items() if l.get("europe")})
        self.assertEqual({i for i, l in LIGUES.items() if l.get("civile")}, main.DOMESTIC_LEAGUES_ANNEE_CIVILE)
        self.assertEqual(set(LIGUES), set(main.DOMESTIC_LEAGUES) | set(main.COMPETITIONS_EUROPE))


class TestEspn(unittest.TestCase):
    def test_match_termine(self):
        e = espn.convertir(evenement_espn("1", "Paris Saint-Germain", "Marseille"), "4334", annuaire())
        self.assertEqual((e["idHomeTeam"], e["idAwayTeam"]), ("1", "2"))
        self.assertEqual((e["intHomeScore"], e["intAwayScore"], e["strStatus"]), ("2", "1", "FT"))
        self.assertEqual((e["dateEvent"], e["strTime"], e["strSeason"]), ("2026-11-21", "20:00:00", "2026-2027"))
        self.assertEqual(e["strHomeTeam"], "Paris Saint-Germain")  # nom canonique TheSportsDB
        self.assertEqual(e["strHomeTeamBadge"], "https://tsdb/psg.png")
        self.assertEqual(e["strAwayTeamBadge"], "https://espn/ext.png")  # pas de logo TheSportsDB : logo ESPN
        self.assertEqual(e["strLeagueBadge"], "https://tsdb/l1.png")

    def test_match_a_venir_sans_score(self):
        e = espn.convertir(evenement_espn("1", "Paris Saint-Germain", "Marseille", score=("0", "0"),
                                          statut="STATUS_SCHEDULED"), "4334", annuaire())
        self.assertIsNone(e["intHomeScore"])
        self.assertEqual((e["strStatus"], e["strPostponed"]), ("NS", "no"))

    def test_match_reporte_ou_abandonne_sans_score(self):
        for statut in ("STATUS_POSTPONED", "STATUS_ABANDONED"):
            e = espn.convertir(evenement_espn("1", "Marseille", "Lille", score=("0", "0"), statut=statut), "4334", annuaire())
            self.assertIsNone(e["intHomeScore"], statut)
            self.assertEqual(e["strPostponed"], "yes")

    def test_score_illisible_ne_devine_pas(self):
        e = espn.convertir(evenement_espn("1", "Marseille", "Lille", score=("?", "1")), "4334", annuaire())
        self.assertIsNone(e["intHomeScore"])

    def test_evenement_mal_forme_ignore(self):
        self.assertIsNone(espn.convertir({"id": "1"}, "4334", annuaire()))
        self.assertIsNone(espn.convertir({"id": "1", "date": "pas une date", "competitions": []}, "4334", annuaire()))

    def test_club_inconnu_id_provisoire(self):
        e = espn.convertir(evenement_espn("1", "Clermont Foot", "Marseille"), "4334", annuaire())
        self.assertEqual(e["idHomeTeam"], "inconnu-clermontfoot")
        self.assertEqual(e["strHomeTeam"], "Clermont Foot")

    def test_telecharger_jour_400_vide_et_erreur_apres_essais(self):
        self.assertEqual(espn.telecharger_jour("fra.1", date(2026, 11, 14), FausseSession(lambda u, p: Reponse({}, 400))), [])
        espn.time.sleep = lambda s: None  # pas d'attente reelle dans les tests
        with self.assertRaises(espn.ErreurEspn):
            espn.telecharger_jour("fra.1", date(2026, 11, 14), FausseSession(lambda u, p: Reponse({}, 503)), tentatives=2)
        with self.assertRaises(espn.ErreurEspn):  # JSON sans `events`
            espn.telecharger_jour("fra.1", date(2026, 11, 14), FausseSession(lambda u, p: Reponse({"x": 1})), tentatives=1)

    def test_une_requete_par_ligue_et_par_jour(self):
        session = FausseSession(lambda u, p: Reponse({"events": []}))
        espn.evenements([("4334", date(2026, 11, 14)), ("4334", date(2026, 11, 15)), ("4422", date(2026, 11, 14))],
                        annuaire(), session)  # 4422 (Pologne) n'a pas de slug ESPN : aucune requete
        self.assertEqual(sorted(p["dates"] for _, p in session.appels), ["20261114", "20261115"])
        self.assertTrue(all("fra.1" in u for u, _ in session.appels))


class TestOddsApi(unittest.TestCase):
    EVENEMENT = {"id": "abc", "sport_key": "soccer_poland_ekstraklasa", "commence_time": "2026-11-20T17:00:00Z",
                 "home_team": "Piast Gliwice", "away_team": "Korona Kielce"}

    def test_conversion(self):
        e = odds_api.convertir(self.EVENEMENT, "4422", annuaire())
        self.assertEqual((e["idHomeTeam"], e["idAwayTeam"], e["dateEvent"], e["strTime"]), ("8", "9", "2026-11-20", "17:00:00"))
        self.assertEqual((e["intHomeScore"], e["source"]), (None, "odds_api"))
        self.assertIsNone(odds_api.convertir({"id": "x"}, "4422", annuaire()))

    def test_erreurs_http_et_cle_absente(self):
        with self.assertRaises(odds_api.ErreurOddsApi):
            odds_api.telecharger_sport("soccer_epl", "cle", FausseSession(lambda u, p: Reponse([], 401)))
        os.environ.pop("ODDS_API_KEY", None)
        evs, panne, _ = odds_api.evenements(["4422"], annuaire(), cle_api=None)
        self.assertEqual((evs, panne), ([], {"4422"}))

    def test_ligue_sans_publication_ignoree(self):
        evs, panne, _ = odds_api.evenements(["4631"], annuaire(), cle_api="cle")  # Tchequie : pas de cle sport
        self.assertEqual((evs, panne), ([], set()))

    def test_appel_gratuit_attendu(self):
        session = FausseSession(lambda u, p: Reponse([self.EVENEMENT], entetes={"x-requests-last": "0"}))
        evs, panne, _ = odds_api.evenements(["4422"], annuaire(), cle_api="cle", session=session)
        self.assertEqual((len(evs), panne), (1, set()))
        self.assertTrue(session.appels[0][0].endswith("/soccer_poland_ekstraklasa/events"))


def local(id_, dom, ext, jour, ligue="4334", saison_="2026-2027", **plus):
    return dict(idEvent=id_, idLeague=ligue, strSeason=saison_, idHomeTeam=dom, idAwayTeam=ext, dateEvent=jour,
                strHomeTeam=f"D{dom}", strAwayTeam=f"E{ext}", intHomeScore=None, intAwayScore=None, **plus)


def brut_evt(dom, ext, jour, ligue="4334"):
    e = espn.convertir(evenement_espn("9", dom, ext, f"{jour}T20:00Z", statut="STATUS_SCHEDULED"), ligue, annuaire())
    return e


class TestRattachement(unittest.TestCase):
    def test_reprend_id_et_champs_statiques_du_local(self):
        loc = local("555", "1", "2", "2026-11-21", intRound="13", strVenue="Parc")
        res, nb = source.rattacher([brut_evt("Paris Saint-Germain", "Marseille", "2026-11-22")], [loc])
        self.assertEqual((nb, res[0]["idEvent"], res[0]["intRound"], res[0]["dateEvent"]), (1, "555", "13", "2026-11-22"))

    def test_deux_confrontations_la_plus_proche_et_une_seule_fois(self):
        locs = [local("A", "1", "2", "2026-08-30"), local("B", "1", "2", "2027-02-20")]
        evs = [brut_evt("Paris Saint-Germain", "Marseille", "2026-08-30"),
               brut_evt("Paris Saint-Germain", "Marseille", "2027-02-21")]
        res, nb = source.rattacher(evs, locs)
        self.assertEqual((nb, sorted(r["idEvent"] for r in res)), (2, ["A", "B"]))

    def test_sans_local_id_stable_et_independant_du_fournisseur(self):
        e1, _ = source.rattacher([brut_evt("Paris Saint-Germain", "Marseille", "2026-11-22")], [])
        o = odds_api.convertir({"id": "z", "commence_time": "2026-11-22T20:00:00Z", "home_team": "Paris Saint-Germain",
                                "away_team": "Marseille"}, "4334", annuaire())
        e2, _ = source.rattacher([o], [])
        self.assertEqual(e1[0]["idEvent"], e2[0]["idEvent"])
        self.assertEqual(e1[0]["idEvent"], "x4334-1-2-2026-11-22")

    def test_saison_differente_non_rattachee(self):
        loc = local("OLD", "1", "2", "2026-11-22", saison_="2025-2026")
        res, nb = source.rattacher([brut_evt("Paris Saint-Germain", "Marseille", "2026-11-22")], [loc])
        self.assertEqual(nb, 0)


def routeur_espn(par_slug_jour):
    """{(slug, 'AAAAMMJJ'): [evenements]} ; slug en panne si la valeur est une exception."""
    def route(url, params):
        slug = url.split("/soccer/")[1].split("/")[0]
        v = par_slug_jour.get((slug, params["dates"]), [])
        return Reponse({"events": v}) if not isinstance(v, Exception) else Reponse({}, 503)
    return route


class TestFacade(unittest.TestCase):
    def setUp(self):
        espn.time.sleep = lambda s: None
        self.odds = FausseSession(lambda u, p: Reponse([TestOddsApi.EVENEMENT], entetes={"x-requests-last": "0"}))

    def lancer(self, par_slug_jour, locaux=(), ids=("4334", "4422"), **kw):
        return source.a_venir(date(2026, 11, 20), date(2026, 11, 21), list(locaux), list(ids), annuaire(),
                              session_espn=FausseSession(routeur_espn(par_slug_jour)), session_odds=self.odds,
                              cle_odds="cle", **kw)

    def test_espn_principal_et_odds_pour_ligue_non_couverte(self):
        evs, rap = self.lancer({("fra.1", "20261121"): [evenement_espn("1", "Paris Saint-Germain", "Marseille", "2026-11-21T20:00Z",
                                                                    statut="STATUS_SCHEDULED")]})
        self.assertEqual(rap["sources"], {"4334": "espn", "4422": "odds_api"})
        self.assertEqual(sorted(e["source"] for e in evs), ["espn", "odds_api"])

    def test_espn_en_panne_bascule_sur_odds(self):
        espn.time.sleep = lambda s: None
        evs, rap = self.lancer({("fra.1", "20261120"): Exception()}, ids=("4334",))
        # La Ligue 1 n'a pas d'evenement Odds API ici (fixture = Pologne) : la ligue reste sans fournisseur utile.
        self.assertEqual(rap["sources"]["4334"], "odds_api")

    def test_espn_muet_alors_que_le_calendrier_local_annonce_un_match(self):
        locaux = [local("77", "8", "9", "2026-11-20", ligue="4422")]
        evs, rap = self.lancer({}, locaux=locaux, ids=("4422",))
        self.assertEqual(rap["sources"]["4422"], "odds_api")
        self.assertEqual(evs[0]["idEvent"], "77")  # rattache au calendrier local

    def test_reportes_et_joues_exclus_sauf_demande(self):
        j = {("fra.1", "20261120"): [evenement_espn("1", "Marseille", "Lille", "2026-11-20T20:00Z"),
                                      evenement_espn("2", "Paris Saint-Germain", "Lille", "2026-11-20T18:00Z", statut="STATUS_POSTPONED"),
                                      evenement_espn("3", "Paris Saint-Germain", "Marseille", "2026-11-20T19:00Z", statut="STATUS_SCHEDULED")]}
        evs, _ = self.lancer(j, ids=("4334",))
        self.assertEqual([e["strHomeTeam"] for e in evs], ["Paris Saint-Germain"])
        evs, _ = self.lancer(j, ids=("4334",), inclure_joues=True)
        self.assertEqual(len(evs), 2)

    def test_sans_secours_pas_d_appel_odds(self):
        self.lancer({}, ids=("4334",), secours=False)
        self.assertEqual(self.odds.appels, [])


class TestCompleterCalendrier(unittest.TestCase):
    def setUp(self):  # jamais le vrai cache de resultats du depot
        self.dossier = tempfile.TemporaryDirectory()
        self.ancien = source.FICHIER_RECENTS
        source.FICHIER_RECENTS = os.path.join(self.dossier.name, "recents.json")

    def tearDown(self):
        source.FICHIER_RECENTS = self.ancien
        self.dossier.cleanup()

    def test_resultats_fusionnes_et_incrementaux(self):
        espn.time.sleep = lambda s: None
        brut = {"4334": {"2026-2027": [
            dict(idEvent="10", dateEvent="2026-11-10", idHomeTeam="1", idAwayTeam="2", strHomeTeam="Paris Saint-Germain",
                 strAwayTeam="Marseille", intHomeScore=None, intAwayScore=None),
            dict(idEvent="11", dateEvent="2026-11-20", idHomeTeam="2", idAwayTeam="6", strHomeTeam="Marseille",
                 strAwayTeam="Lille", intHomeScore=None, intAwayScore=None)]}}
        j = {("fra.1", "20261110"): [evenement_espn("1", "Paris Saint-Germain", "Marseille", "2026-11-10T20:00Z", ("3", "0"))],
             ("fra.1", "20261121"): [evenement_espn("2", "Marseille", "Lille", "2026-11-21T20:00Z", statut="STATUS_SCHEDULED")]}
        ann = annuaire()
        res, rap = source.completer_calendrier(brut, aujourd_hui=date(2026, 11, 13), ids_ligues=["4334"], annuaire=ann,
                                               persister=False, session_espn=FausseSession(routeur_espn(j)), secours=False)
        evs = {e["idEvent"]: e for e in res["4334"]["2026-2027"]}
        self.assertEqual((evs["10"]["intHomeScore"], evs["10"]["intAwayScore"]), ("3", "0"))  # resultat integre
        self.assertEqual((evs["11"]["dateEvent"], evs["11"]["intHomeScore"]), ("2026-11-21", None))  # match deplace
        self.assertEqual(len(evs), 2)  # aucun doublon
        self.assertEqual(rap["resultats_nouveaux"], 1)
        self.assertEqual(rap["ligues_sans_resultats"], [])

    def test_ligues_sans_resultats_gratuits_signalees(self):
        # Tchequie et Chypre : ni ESPN ni football-data. Pologne : football-data en panne -> signalee aussi.
        _, rap = source.completer_calendrier({}, aujourd_hui=date(2026, 11, 13), ids_ligues=["4631", "4630", "4422"],
                                             annuaire=annuaire(), persister=False, secours=False,
                                             session_espn=FausseSession(routeur_espn({})),
                                             session_fd=FausseSession(lambda u, p: Reponse(None, 503)))
        self.assertEqual(rap["ligues_sans_resultats"], ["4631", "4630", "4422"])


CSV_POL = ("Country,League,Season,Date,Time,Home,Away,HG,AG,Res\n"
           "Poland,Ekstraklasa,2026/2027,08/11/2026,15:00,Piast Gliwice,Korona Kielce,2,1,H\n"
           "Poland,Ekstraklasa,2026/2027,09/11/2026,15:00,Piast Gliwice,Club Inconnu,1,1,D\n"
           "Poland,Ekstraklasa,2026/2027,10/11/2026,15:00,Piast Gliwice,Korona Kielce,,,\n"
           "Poland,Ekstraklasa,2025/2026,01/03/2026,15:00,Piast Gliwice,Korona Kielce,0,0,D\n")


class FausseReponseCsv(Reponse):
    def __init__(self, texte, code=200):
        super().__init__(None, code)
        self.content = texte.encode("utf-8")


class TestFootballData(unittest.TestCase):
    def setUp(self):
        footballdata.time.sleep = lambda s: None

    def test_resultats_filtres_et_clubs_inconnus_ignores(self):
        session = FausseSession(lambda u, p: FausseReponseCsv(CSV_POL))
        evs, panne = footballdata.resultats(["4422", "4334"], annuaire(), date(2026, 8, 1), session)
        self.assertEqual(panne, set())
        self.assertEqual(len(evs), 1)  # club inconnu, score vide et saison passee ecartes ; 4334 sans fichier
        e = evs[0]
        self.assertEqual((e["idHomeTeam"], e["idAwayTeam"], e["intHomeScore"], e["intAwayScore"], e["dateEvent"],
                          e["strSeason"]), ("8", "9", "2", "1", "2026-11-08", "2026-2027"))
        self.assertTrue(session.appels[0][0].endswith("/new/POL.csv"))

    def test_fichier_invalide_ou_injoignable(self):
        with self.assertRaises(footballdata.ErreurFootballData):
            footballdata.telecharger("POL", FausseSession(lambda u, p: FausseReponseCsv("<html>nope</html>")), tentatives=1)
        _, panne = footballdata.resultats(["4422"], annuaire(), date(2026, 8, 1),
                                          FausseSession(lambda u, p: FausseReponseCsv("", 503)))
        self.assertEqual(panne, {"4422"})

    def test_completer_integre_resultats_pologne_sans_creer_de_match(self):
        dossier = tempfile.TemporaryDirectory()
        ancien, source.FICHIER_RECENTS = source.FICHIER_RECENTS, os.path.join(dossier.name, "r.json")
        try:
            brut = {"4422": {"2026-2027": [dict(idEvent="900", dateEvent="2026-11-08", idHomeTeam="8", idAwayTeam="9",
                                                strHomeTeam="Piast Gliwice", strAwayTeam="Korona Kielce",
                                                intHomeScore=None, intAwayScore=None)]}}
            res, rap = source.completer_calendrier(
                brut, aujourd_hui=date(2026, 11, 13), ids_ligues=["4422"], annuaire=annuaire(), persister=False,
                secours=False, session_espn=FausseSession(routeur_espn({})),
                session_fd=FausseSession(lambda u, p: FausseReponseCsv(CSV_POL)))
            evs = res["4422"]["2026-2027"]
            self.assertEqual(len(evs), 1)  # aucun doublon, aucun match invente
            self.assertEqual((evs[0]["idEvent"], evs[0]["intHomeScore"], evs[0]["intAwayScore"]), ("900", "2", "1"))
            self.assertEqual((rap["resultats_footballdata"], rap["ligues_sans_resultats"]), (1, []))
        finally:
            source.FICHIER_RECENTS = ancien
            dossier.cleanup()


@unittest.skipUnless(os.environ.get("CALENDRIER_LIVE") == "1", "test en ligne : CALENDRIER_LIVE=1")
class TestEnLigne(unittest.TestCase):
    def test_espn_repond_et_les_noms_sont_rapproches(self):
        ann = Annuaire()
        evs, panne, ignores = espn.evenements([("4328", date(2026, 11, 21)), ("4334", date(2026, 11, 21))], ann)
        self.assertFalse(panne)
        self.assertEqual(ignores, 0)
        self.assertTrue(evs)
        self.assertFalse([e for e in evs if str(e["idHomeTeam"]).startswith("inconnu-")], ann.inconnus)


if __name__ == "__main__":
    unittest.main()
