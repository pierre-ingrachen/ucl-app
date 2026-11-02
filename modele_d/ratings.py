"""Features de force des equipes sur le long terme, calculees avant chaque match, sans fuite du futur :
note Elo (avec avantage du terrain et marge de victoire), moyennes mobiles exponentielles des buts
marques / encaisses, jours de repos et nombre de matchs joues. Elles completent les 5 derniers
matchs de dataset_reseau*.csv, qui ne voient que la forme recente.

Rejoue tous les matchs joues de matchs_reseau_bruts_ext.json (2020-23) puis matchs_reseau_bruts.json,
championnat par championnat, et ecrit ratings_matchs.csv (cle : ligue, date, equipe_dom, equipe_ext).

Usage : .venv/bin/python -m modele_d.ratings
"""
import csv
import json
import math
from datetime import date

from modele_d import historique as ext
import construire_dataset_reseau as base

FICHIER_RATINGS = "modele_d/donnees/ratings_matchs.csv"
ELO_INITIAL, ELO_PROMU, K, AVANTAGE_TERRAIN, RETOUR_MOYENNE = 1500.0, 1450.0, 20.0, 60.0, 0.25
ALPHA_BUTS, BUTS_INITIAL, REPOS_MAX = 0.08, 1.3, 30
COLONNES = ["ligue", "date", "equipe_dom", "equipe_ext", "elo_dom", "elo_ext", "elo_diff",
            "att_dom", "def_dom", "att_ext", "def_ext", "repos_dom", "repos_ext", "nb_dom", "nb_ext"]


def multiplicateur(ecart):
    return 1.0 if ecart <= 1 else 1.5 if ecart == 2 else (11 + ecart) / 8


class EtatRatings:
    """Etat des notes d'un championnat, rejoue chronologiquement. `ligne` donne les features d'un
    match a venir ou a rejouer (valeurs d'AVANT le match), `enregistrer` integre son resultat."""

    def __init__(self):
        self.elo, self.att, self.dfn, self.dernier, self.nb = {}, {}, {}, {}, {}
        self.n_saison = -1

    def nouvelle_saison(self):
        self.n_saison += 1
        for e in self.elo:  # les notes reviennent un peu vers la moyenne
            self.elo[e] = ELO_INITIAL + (1 - RETOUR_MOYENNE) * (self.elo[e] - ELO_INITIAL)

    def _init(self, t):
        self.elo.setdefault(t, ELO_PROMU if self.n_saison else ELO_INITIAL)  # 1re saison : tout le monde a 1500
        self.att.setdefault(t, BUTS_INITIAL)
        self.dfn.setdefault(t, BUTS_INITIAL)
        self.nb.setdefault(t, 0)

    def ligne(self, dom, ext_, d):
        for t in (dom, ext_):
            self._init(t)
        repos = lambda t: min((d - self.dernier[t]).days, REPOS_MAX) if t in self.dernier else REPOS_MAX
        return [round(self.elo[dom], 1), round(self.elo[ext_], 1),
                round(self.elo[dom] - self.elo[ext_] + AVANTAGE_TERRAIN, 1),
                round(self.att[dom], 3), round(self.dfn[dom], 3), round(self.att[ext_], 3), round(self.dfn[ext_], 3),
                repos(dom), repos(ext_), self.nb[dom], self.nb[ext_]]

    def enregistrer(self, dom, ext_, gd, ge, d):
        self._init(dom)
        self._init(ext_)
        attendu = 1 / (1 + 10 ** (-(self.elo[dom] - self.elo[ext_] + AVANTAGE_TERRAIN) / 400))
        reel = 1.0 if gd > ge else 0.5 if gd == ge else 0.0
        delta = K * multiplicateur(abs(gd - ge)) * (reel - attendu)
        self.elo[dom] += delta
        self.elo[ext_] -= delta
        for t, pour, contre in ((dom, gd, ge), (ext_, ge, gd)):
            self.att[t] += ALPHA_BUTS * (pour - self.att[t])
            self.dfn[t] += ALPHA_BUTS * (contre - self.dfn[t])
            self.nb[t] += 1
            self.dernier[t] = d


def rejouer(brut):
    lignes = []
    for ligue, saisons in brut.items():
        etat = EtatRatings()
        for saison, evenements in saisons.items():
            etat.nouvelle_saison()
            joues = sorted((e for e in evenements if e["intHomeScore"] is not None
                            and e["intAwayScore"] is not None and e["dateEvent"]),
                           key=lambda e: (e["dateEvent"], e["idEvent"]))
            for e in joues:
                dom, ext_, d = e["idHomeTeam"], e["idAwayTeam"], date.fromisoformat(e["dateEvent"])
                lignes.append([ligue, e["dateEvent"], e["strHomeTeam"], e["strAwayTeam"]] + etat.ligne(dom, ext_, d))
                etat.enregistrer(dom, ext_, int(e["intHomeScore"]), int(e["intAwayScore"]), d)
    return lignes


if __name__ == "__main__":
    existant = ext._lire(base.FICHIER_BRUTS)
    complet = ext.brut_etendu(ext._lire(ext.FICHIER_BRUTS_EXT))
    lignes = rejouer({lid: complet[lid] for lid in existant})
    with open(FICHIER_RATINGS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLONNES)
        w.writerows(lignes)
    print(f"{len(lignes)} matchs ecrits dans {FICHIER_RATINGS}")
