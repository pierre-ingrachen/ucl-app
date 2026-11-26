"""Tests de la base locale (calendrier/base.py), des logos et de `main.py` sans TheSportsDB.

    .venv/bin/python -m unittest calendrier.tests.test_base -v
"""
import os
import re
import tempfile
import unittest

from calendrier import espn, logos
from calendrier.base import Base
from calendrier.tests.test_calendrier import FausseSession, Reponse, annuaire, evenement_espn

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def evt(id_, dom="1", ext="2", jour="2026-11-20", ligue="4334", saison="2026-2027", **plus):
    base = dict(idEvent=id_, idLeague=ligue, strLeague="Ligue 1", strSeason=saison, idHomeTeam=dom, idAwayTeam=ext,
                strHomeTeam=f"D{dom}", strAwayTeam=f"E{ext}", strEvent=f"D{dom} vs E{ext}", dateEvent=jour,
                strTime="19:45:00", strTimestamp=f"{jour}T19:45:00", intHomeScore=None, intAwayScore=None,
                strStatus="NS", strPostponed="no", intRound="13", strVenue="Parc", strHomeTeamBadge="https://x/d.png")
    base.update(plus)
    return base


class TestBase(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.base = Base(self.dossier.name)

    def tearDown(self):
        self.dossier.cleanup()

    def test_ecriture_lecture_et_champs_reduits(self):
        self.base.ecrire_saison("4334", "2026-2027", [evt("2", jour="2026-11-21", strThumb="x", strVideo="y"), evt("1")])
        evs = self.base.evenements_saison("4334", "2026-2027")
        self.assertEqual([e["idEvent"] for e in evs], ["1", "2"])        # trie par date
        self.assertNotIn("strThumb", evs[0])                              # champs inutiles ecartes
        self.assertEqual(evs[0]["strFilename"], "Ligue 1 2026-11-20 D1 vs E2")
        self.assertEqual(self.base.saisons("4334"), ["2026-2027"])
        self.assertEqual(self.base.evenement("2")["dateEvent"], "2026-11-21")
        self.assertIsNone(self.base.evenement("999"))
        self.assertEqual(self.base.evenements_saison("4334", "1999"), [])

    def test_upsert_dynamique_remplace_statique_conserve(self):
        self.base.ecrire_saison("4334", "2026-2027", [evt("1")])
        # resultat : score/statut remplaces ; stade vide et tour vide ne doivent pas effacer l'existant
        modifies, ajoutes = self.base.upsert([evt("1", intHomeScore="2", intAwayScore="0", strStatus="FT",
                                                  strVenue="", intRound=None, strTime="20:00:00")])
        self.assertEqual((modifies, ajoutes), (1, 0))
        e = self.base.evenement("1")
        self.assertEqual((e["intHomeScore"], e["strStatus"], e["strTime"]), ("2", "FT", "20:00:00"))
        self.assertEqual((e["strVenue"], e["intRound"]), ("Parc", "13"))

    def test_upsert_ne_deplace_jamais_un_match_joue(self):
        self.base.ecrire_saison("4334", "2026-2027", [evt("1", jour="2026-08-22", intHomeScore="1", intAwayScore="2",
                                                          strStatus="FT")])
        self.base.upsert([evt("1", jour="2026-11-28")])  # evenement a venir mal rattache : refuse
        e = self.base.evenement("1")
        self.assertEqual((e["dateEvent"], e["intHomeScore"], e["intAwayScore"], e["strStatus"]),
                         ("2026-08-22", "1", "2", "FT"))
        self.base.upsert([evt("1", jour="2026-08-22", intHomeScore="2", intAwayScore="2", strStatus="FT")])
        self.assertEqual(self.base.evenement("1")["intHomeScore"], "2")  # une correction de score passe toujours

    def test_upsert_ajoute_un_match_inconnu_et_reste_idempotent(self):
        self.assertEqual(self.base.upsert([evt("7")]), (0, 1))
        chemin = self.base.chemin_saison("4334", "2026-2027")
        avant = os.stat(chemin).st_mtime_ns
        self.assertEqual(self.base.upsert([evt("7")]), (1, 0))
        self.assertEqual(os.stat(chemin).st_mtime_ns, avant)  # rien de change : fichier non reecrit (pas de commit inutile)

    def test_completer_equipes_pays_majoritaire_de_la_ligue(self):
        self.base.ecrire_equipes({"1": {"nom": "A", "pays": "France", "ligue": {"id": "4334", "nom": "L1"}, "badge": ""},
                                  "2": {"nom": "B", "pays": "France", "ligue": {"id": "4334", "nom": "L1"}, "badge": ""},
                                  "3": {"nom": "C", "pays": "Monaco", "ligue": {"id": "4334", "nom": "L1"}, "badge": ""}})
        self.assertEqual(self.base.completer_equipes([evt("1", dom="1", ext="9")]), 1)
        self.assertEqual(self.base.pays("9"), "France")
        self.assertEqual(self.base.ligue_nationale("9")["id"], "4334")
        self.assertEqual(self.base.completer_equipes([evt("1", dom="1", ext="9")]), 0)  # deja connu

    def test_classement_national_gele(self):
        self.base.ecrire_classements_nationaux({"4001": {"ligue": "Kazakhstan Premier League", "saison": "2026",
                                                         "maj": "2026-11-13",
                                                         "lignes": [{"idTeam": "55", "intRank": "2", "strTeam": "X"},
                                                                    {"idTeam": "56", "intRank": "1", "strTeam": "Y"}]}})
        self.assertEqual(self.base.classement_national_gele("55"),
                         {"position": 2, "total": 2, "saison": "2026", "ligue": "Kazakhstan Premier League",
                          "maj": "2026-11-13"})
        self.assertIsNone(self.base.classement_national_gele("999"))

    def test_phase_europe_deduite_d_espn(self):
        a = annuaire()
        brut = evenement_espn("1", "Marseille", "Lille", "2026-02-18T20:00Z", statut="STATUS_SCHEDULED")
        for slug, tour in (("round-of-16", "16"), ("knockout-round-playoffs", "32"), ("quarterfinals", "125"),
                           ("semifinals", "150"), ("final", "200"), ("league-phase", None)):
            brut["season"] = {"slug": slug}
            self.assertEqual(espn.convertir(brut, "4480", a)["intRound"], tour, slug)
        self.assertEqual(espn.convertir(brut, "4480", a, qualification=True)["intRound"], "400")

    def test_qualifications_europeennes_interrogent_les_ligues_extra(self):
        session = FausseSession(lambda u, p: Reponse({"events": []}))
        from datetime import date
        espn.evenements([("4480", date(2026, 7, 14))], annuaire(), session)
        self.assertEqual(sorted(u.split("/soccer/")[1].split("/")[0] for u, _ in session.appels),
                         ["uefa.champions", "uefa.champions_qual"])


class TestMiseAJourEurope(unittest.TestCase):
    def test_resultats_et_a_venir_ecrits_dans_la_base_sans_brut(self):
        from datetime import date
        from calendrier import source
        dossier = tempfile.TemporaryDirectory()
        ancien, source.FICHIER_RECENTS = source.FICHIER_RECENTS, os.path.join(dossier.name, "r.json")
        try:
            base = Base(os.path.join(dossier.name, "base"))
            base.ecrire_saison("4480", "2026-2027", [evt("50", dom="1", ext="2", jour="2026-11-10", ligue="4480",
                                                       strLeague="UEFA Champions League", intRound="3")])
            session = FausseSession(lambda u, p: Reponse({"events": [
                evenement_espn("1", "Paris Saint-Germain", "Marseille", "2026-11-10T20:00Z", ("3", "1"))]
                if p["dates"] == "20261110" and u.endswith("/uefa.champions/scoreboard") else []}))
            rap = source.mettre_a_jour_europe(base, aujourd_hui=date(2026, 11, 13), annuaire=annuaire(),
                                              session_espn=session, secours=False)
            e = base.evenement("50")
            self.assertEqual((e["intHomeScore"], e["intAwayScore"], e["intRound"]), ("3", "1", "3"))  # tour conserve
            self.assertEqual(rap["resultats"], 1)
            self.assertEqual(base.evenements_saison("4480", "2026-2027").__len__(), 1)   # pas de doublon
        finally:
            source.FICHIER_RECENTS = ancien
            dossier.cleanup()


class TestLogos(unittest.TestCase):
    def test_nom_et_variante_reduite(self):
        url = "https://r2.thesportsdb.com/images/media/team/badge/abc.png"
        self.assertTrue(logos.nom_fichier_badge(url).endswith(".png"))
        self.assertEqual(logos.url_a_telecharger(url), url + "/small")
        espn_url = "https://a.espncdn.com/i/teamlogos/soccer/500/364.png"
        self.assertEqual(logos.url_a_telecharger(espn_url), espn_url)

    def test_telecharge_seulement_les_manquants(self):
        with tempfile.TemporaryDirectory() as d:
            base = Base(d)
            u1, u2 = "https://r2.thesportsdb.com/images/media/team/badge/a.png", "https://a.espncdn.com/i/teamlogos/soccer/500/1.png"
            base.ecrire_saison("4334", "2026-2027", [evt("1", strHomeTeamBadge=u1, strAwayTeamBadge=u2)])

            class Img(Reponse):
                content = b"\x89PNG..."

            session = FausseSession(lambda u, p: Img(None, 200, {"content-type": "image/png"}))
            self.assertEqual(logos.telecharger_manquants(base, session), (2, [], 0))
            self.assertTrue(os.path.exists(os.path.join(d, "badges", logos.nom_fichier_badge(u1))))
            self.assertIn(u1 + "/small", [u for u, _ in session.appels])
            self.assertEqual(logos.telecharger_manquants(base, session), (0, [], 2))  # deja la : aucun appel de plus


class TestSansTheSportsDB(unittest.TestCase):
    """La base du depot est complete et main.py / paris_reseau.py n'appellent plus TheSportsDB."""

    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def test_aucun_appel_thesportsdb_dans_le_code_de_production(self):
        for fichier in ("main.py", "paris_reseau.py", "construire_dataset_reseau.py", "modele_d/historique.py",
                        "calendrier/source.py", "calendrier/espn.py", "calendrier/odds_api.py"):
            with open(os.path.join(RACINE, fichier), encoding="utf-8") as f:
                code = f.read()
            self.assertNotRegex(code, r"thesportsdb\.com/api", fichier)
            self.assertNotIn("requete_api_avec_retry", code, fichier)
            self.assertNotIn("SPORTSDB_API_KEY", code, fichier)

    def test_base_du_depot_complete(self):
        base = self.main.BASE
        for id_ligue in self.main.DOMESTIC_LEAGUES:
            for saison in self.main.saisons_passees_ligue(id_ligue) + [self.main.saison_actuelle_ligue(id_ligue)]:
                self.assertTrue(base.evenements_saison(id_ligue, saison), f"{id_ligue} {saison} absent")
        for id_ligue in self.main.COMPETITIONS_EUROPE:
            for saison in self.main.PAST_SEASONS + [self.main.SEASON]:
                self.assertTrue(base.evenements_saison(id_ligue, saison), f"{id_ligue} {saison} absent")
        # chaque club d'un match a un pays, une ligue et un logo local
        manquants = set()
        for id_ligue in list(self.main.DOMESTIC_LEAGUES) + list(self.main.COMPETITIONS_EUROPE):
            for e in base.evenements_ligue(id_ligue):
                for cote in ("Home", "Away"):
                    if not base.pays(e[f"id{cote}Team"]) and e[f"id{cote}Team"] not in self.main.CORRECTIONS_PAYS:
                        manquants.add(e[f"id{cote}Team"])
        self.assertEqual(len(manquants), 0, f"clubs sans pays : {sorted(manquants)[:10]}")
        urls = logos.urls_de_la_base(base)
        sans_logo = [u for u in urls if not os.path.exists(os.path.join(logos.dossier(base), logos.nom_fichier_badge(u)))]
        self.assertEqual(sans_logo, [])

    def test_classement_national_calcule_ou_gele(self):
        main = self.main
        club = next(e["idHomeTeam"] for e in main.BASE.evenements_saison("4328", main.saison_actuelle_ligue("4328")))
        c = main.obtenir_classement_national(club)
        self.assertEqual((c["total"], c["saison"]), (20, main.saison_actuelle_ligue("4328")))
        self.assertTrue(1 <= c["position"] <= 20)
        # un club d'une ligue non suivie (Kazakhstan) : table gelee du snapshot
        gele = next((i for i, f in main.BASE.equipes().items()
                     if f.get("ligue") and f["ligue"]["id"] not in main.DOMESTIC_LEAGUES
                     and main.BASE.classement_national_gele(i)), None)
        self.assertIsNotNone(gele)
        self.assertIn("position", main.obtenir_classement_national(gele))
        self.assertIsNone(main.obtenir_classement_national("inconnu-xyz"))

    def test_endpoints_du_site_sans_cle(self):
        from fastapi.testclient import TestClient
        main = self.main
        client = TestClient(main.app)
        for url in ("/api/championnats/classement/4328", "/api/competitions/classement/4480",
                    "/api/matchs/historique-qualifications"):
            self.assertEqual(client.get(url).status_code, 200, url)
        match = next(e for e in main.BASE.evenements_saison("4328", main.saison_actuelle_ligue("4328"))
                     if e["intHomeScore"] is not None)
        fiche = client.get(f"/api/match/{match['idEvent']}").json()
        self.assertEqual(fiche["idEvent"], match["idEvent"])
        self.assertEqual(len(fiche["historiqueDomicile"]), 5)
        self.assertTrue(fiche["strHomeCountry"])
        self.assertEqual(client.get("/api/match/0000").status_code, 404)

    def test_ligues_sans_fournisseur_restent_affichees(self):
        from fastapi.testclient import TestClient
        main = self.main
        main._cache_source.clear()
        ancien, main.JOURS_AFFICHES = main.JOURS_AFFICHES, 15
        try:
            ligues = {e["idLeague"] for e in TestClient(main.app).get("/api/championnats/matchs/a-venir").json()["events"]}
        finally:
            main.JOURS_AFFICHES = ancien
            main._cache_source.clear()
        for id_ligue in ("4631", "4630", "4690"):  # Tchequie, Chypre, Hongrie : base locale
            self.assertIn(id_ligue, ligues)

    def test_logos_reecrits_vers_la_copie_locale(self):
        from fastapi.testclient import TestClient
        main = self.main
        corps = TestClient(main.app).get("/api/championnats/classement/4328").text
        self.assertNotRegex(corps, r"thesportsdb\.com/images")
        self.assertRegex(corps, r"http://[^/\"]+/badges/[0-9a-f]{16}\.png")


if __name__ == "__main__":
    unittest.main()
