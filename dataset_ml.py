"""Construction du jeu d'entraînement du modèle de prédiction par apprentissage,
et calcul de l'état courant des équipes pour prédire un match à venir.

Une passe chronologique unique. Pour chaque match, features *strictement
pré-match* (uniquement à partir des matchs DÉJÀ joués au coup d'envoi) : aucune
fuite du futur.

Chaque équipe entretient un état mis à jour APRÈS chaque match :
  - un rating Elo (pool unique : les championnats se relient entre eux via les
    matchs européens, où des clubs de pays différents se rencontrent) ;
  - la liste de ses derniers matchs (moyennes glissantes, forme, fatigue, séries).

Sources de matchs :
  - `cache_ml_matchs.json` : historique profond (5 saisons), reconstruit une fois
    par semaine par `construire_cache_ml.py` ;
  - fusion des caches quotidiens du site (`cache_history_qualifs.json`,
    `cache_season.json`, `cache_championnat_season.json`) pour rester à jour des
    tout derniers résultats sans appel réseau supplémentaire.

API principale :
  - `construire_dataset()` -> lignes d'entraînement (features + cible + poids) ;
  - `Historique.depuis_caches()` puis `.ligne_pour(fixture)` -> features d'un
    match à venir, au même format (sans cible).
"""

import json
import math
import os
from collections import defaultdict, deque
from datetime import date, datetime

CACHE_ML_FILE = "cache_ml_matchs.json"
CACHES_SITE = ["cache_ml_matchs.json", "cache_history_qualifs.json",
               "cache_season.json", "cache_championnat_season.json"]

# Ligues européennes (mêmes ids que main.LEAGUE_IDS) : sert à typer les matchs
# issus des caches du site, qui ne portent pas le champ `typeCompetition`.
LIGUES_EUROPE = {"4480", "4481", "5071"}

HALF_LIFE_DAYS = 365.0
HALF_LIFE_FORME_DAYS = 180.0
ELO_INIT = 1500.0
ELO_HOME_ADVANTAGE = 65.0
ELO_K = 20.0
JOURS_REPOS_MAX = 30
FENETRE_CONGESTION_JOURS = 14


def _ordinal(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").date().toordinal()


def _poids_temporel(date_str, ref_ordinal):
    age = max(0, ref_ordinal - _ordinal(date_str))
    return 0.5 ** (age / HALF_LIFE_DAYS)


def _esperance_elo(elo, elo_adv, home):
    ecart = elo_adv - (elo + (ELO_HOME_ADVANTAGE if home else -ELO_HOME_ADVANTAGE))
    return 1.0 / (1.0 + 10.0 ** (ecart / 400.0))


def _maj_elo(elo_home, elo_away, gd):
    resultat = 1.0 if gd > 0 else (0.0 if gd < 0 else 0.5)
    attendu = _esperance_elo(elo_home, elo_away, home=True)
    k = ELO_K * math.sqrt(1 + abs(gd))
    delta = k * (resultat - attendu)
    return elo_home + delta, elo_away - delta


# ---------------------------------------------------------------------------
# Normalisation des matchs (cache ML profond + caches quotidiens du site).
# ---------------------------------------------------------------------------
def _int_ou_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _normaliser_brut(m):
    """Match TheSportsDB brut -> schéma commun, ou None si inexploitable / non terminé."""
    hs, aws = _int_ou_none(m.get("intHomeScore")), _int_ou_none(m.get("intAwayScore"))
    hid, aid = m.get("idHomeTeam"), m.get("idAwayTeam")
    d = m.get("dateEvent")
    if hs is None or aws is None or not hid or not aid or not d:
        return None
    europe = m.get("idLeague") in LIGUES_EUROPE
    return {
        "idEvent": m.get("idEvent"),
        "date": d,
        "timestamp": m.get("strTimestamp") or f"{d}T00:00:00",
        "leagueId": m.get("idLeague"),
        "typeCompetition": "europe" if europe else "championnat",
        "phase": m.get("strPhase") or ("" if europe else "championnat"),
        "saison": m.get("strSeason") or "",
        "homeId": hid, "awayId": aid,
        "homeName": m.get("strHomeTeam"), "awayName": m.get("strAwayTeam"),
        "homePays": m.get("strHomeCountry") or "", "awayPays": m.get("strAwayCountry") or "",
        "homeGoals": hs, "awayGoals": aws,
    }


def _charger_matchs():
    """Union dédupliquée des matchs terminés. `cache_ml_matchs.json` (déjà
    normalisé, avec phase et pays) est prioritaire ; les caches du site ne font
    que compléter les résultats récents."""
    par_id = {}
    for chemin in CACHES_SITE:
        if not os.path.exists(chemin):
            continue
        with open(chemin, "r", encoding="utf-8") as fh:
            contenu = json.load(fh)
        matchs = contenu.get("data", contenu) if isinstance(contenu, dict) else contenu
        deja_normalise = chemin == CACHE_ML_FILE
        for m in matchs:
            norm = m if deja_normalise else _normaliser_brut(m)
            if norm and norm["idEvent"] and norm["idEvent"] not in par_id:
                par_id[norm["idEvent"]] = norm
    return sorted(par_id.values(), key=lambda m: (m["timestamp"], m["idEvent"]))


# ---------------------------------------------------------------------------
class _EtatEquipe:
    __slots__ = ("elo", "matchs")

    def __init__(self):
        self.elo = ELO_INIT
        self.matchs = deque(maxlen=40)  # (ordinal, is_home, gf, ga, points)

    def _fenetre(self, k, filtre=None):
        src = [m for m in self.matchs if filtre is None or filtre(m)]
        return src[-k:]

    def features(self, ref_ord, joue_domicile):
        n = len(self.matchs)
        f = {"nb_matchs": float(n)}
        for k in (5, 10):
            w = self._fenetre(k)
            if w:
                f[f"gf_{k}"] = sum(m[2] for m in w) / len(w)
                f[f"ga_{k}"] = sum(m[3] for m in w) / len(w)
                f[f"gd_{k}"] = sum(m[2] - m[3] for m in w) / len(w)
                f[f"ppg_{k}"] = sum(m[4] for m in w) / len(w)
            else:
                f[f"gf_{k}"] = f[f"ga_{k}"] = f[f"gd_{k}"] = f[f"ppg_{k}"] = math.nan

        w_lieu = self._fenetre(8, lambda m: m[1] == joue_domicile)
        if w_lieu:
            f["gf_lieu"] = sum(m[2] for m in w_lieu) / len(w_lieu)
            f["ga_lieu"] = sum(m[3] for m in w_lieu) / len(w_lieu)
        else:
            f["gf_lieu"] = f["ga_lieu"] = math.nan

        if n:
            poids = [0.5 ** ((ref_ord - m[0]) / HALF_LIFE_FORME_DAYS) for m in self.matchs]
            s = sum(poids) or 1.0
            f["gf_ewm"] = sum(p * m[2] for p, m in zip(poids, self.matchs)) / s
            f["ga_ewm"] = sum(p * m[3] for p, m in zip(poids, self.matchs)) / s
        else:
            f["gf_ewm"] = f["ga_ewm"] = math.nan

        serie = 0
        for m in reversed(self.matchs):
            r = 1 if m[4] == 3 else (-1 if m[4] == 0 else 0)
            if r == 0:
                break
            if serie == 0 or (serie > 0) == (r > 0):
                serie += r
            else:
                break
        f["serie"] = float(serie)

        if self.matchs:
            f["jours_repos"] = float(min(JOURS_REPOS_MAX, ref_ord - self.matchs[-1][0]))
            f["matchs_14j"] = float(sum(1 for m in self.matchs
                                        if ref_ord - m[0] <= FENETRE_CONGESTION_JOURS))
        else:
            f["jours_repos"] = float(JOURS_REPOS_MAX)
            f["matchs_14j"] = 0.0
        return f

    def enregistrer(self, ord_, is_home, gf, ga):
        points = 3 if gf > ga else (1 if gf == ga else 0)
        self.matchs.append((ord_, is_home, gf, ga, points))


def _cle_h2h(hid, aid):
    return (hid, aid) if hid < aid else (aid, hid)


class Historique:
    """État Elo + historique par équipe après rejeu chronologique des matchs.
    Sert autant à construire le dataset qu'à figer les features d'un match à venir."""

    def __init__(self):
        self.etats = defaultdict(_EtatEquipe)
        self.h2h = defaultdict(lambda: deque(maxlen=6))  # (min_id, max_id) -> écarts (perspective min_id)

    @classmethod
    def depuis_caches(cls):
        h = cls()
        h.rejouer(_charger_matchs())
        return h

    def rejouer(self, matchs):
        for m in matchs:
            self.appliquer(m)

    def appliquer(self, m):
        hid, aid = m["homeId"], m["awayId"]
        try:
            ord_ = _ordinal(m["date"])
        except (ValueError, KeyError):
            return
        yh, ya = m["homeGoals"], m["awayGoals"]
        eh, ea = self.etats[hid], self.etats[aid]
        elo_h, elo_a = eh.elo, ea.elo
        eh.enregistrer(ord_, True, yh, ya)
        ea.enregistrer(ord_, False, ya, yh)
        eh.elo, ea.elo = _maj_elo(elo_h, elo_a, yh - ya)
        cle = _cle_h2h(hid, aid)
        self.h2h[cle].append((yh - ya) if hid < aid else (ya - yh))

    def ligne_pour(self, fixture, ref_ordinal=None):
        """`fixture` : dict avec homeId, awayId, leagueId, typeCompetition,
        phase, date. Retourne une ligne au format `construire_dataset` (sans cible)."""
        hid, aid = fixture["homeId"], fixture["awayId"]
        try:
            ord_ = _ordinal(fixture["date"])
        except (ValueError, KeyError):
            ord_ = date.today().toordinal()
        ref_ordinal = ref_ordinal or ord_

        eh = self.etats.get(hid) or _EtatEquipe()
        ea = self.etats.get(aid) or _EtatEquipe()
        feat_home = eh.features(ref_ordinal, joue_domicile=True)
        feat_away = ea.features(ref_ordinal, joue_domicile=False)

        precedents = list(self.h2h.get(_cle_h2h(hid, aid), []))
        if precedents:
            moy = sum(precedents) / len(precedents)
            h2h_gd_home = moy if hid < aid else -moy
        else:
            h2h_gd_home = math.nan

        try:
            mois = float(datetime.strptime(fixture["date"], "%Y-%m-%d").month)
        except (ValueError, KeyError):
            mois = float(date.today().month)

        est_europe = 1.0 if fixture.get("typeCompetition") == "europe" else 0.0
        return {
            "idEvent": fixture.get("idEvent"),
            "date": fixture.get("date"),
            "leagueId": fixture.get("leagueId"),
            "typeCompetition": fixture.get("typeCompetition"),
            "phase": fixture.get("phase") or "",
            "homeId": hid, "awayId": aid,
            "homeName": fixture.get("homeName"), "awayName": fixture.get("awayName"),
            "featHome": feat_home,
            "featAway": feat_away,
            "ctx": {
                "leagueId": fixture.get("leagueId"),
                "typeCompetition": fixture.get("typeCompetition"),
                "phase": fixture.get("phase") or "",
                "mois": mois,
                "estEurope": est_europe,
                "eloHome": eh.elo,
                "eloAway": ea.elo,
                "eloDiff": eh.elo + ELO_HOME_ADVANTAGE - ea.elo,
                "h2hGdHome": h2h_gd_home,
            },
        }


def construire_dataset(ref_ordinal=None, min_matchs=0):
    """Table d'entraînement : une ligne par match terminé, features pré-match,
    cible (yHome/yAway) et poids temporel (`ref_ordinal` = date de référence,
    aujourd'hui par défaut)."""
    if ref_ordinal is None:
        ref_ordinal = date.today().toordinal()

    hist = Historique()
    lignes = []
    for m in _charger_matchs():
        ligne = hist.ligne_pour(m, ref_ordinal=ref_ordinal)
        if (ligne["featHome"]["nb_matchs"] >= min_matchs
                and ligne["featAway"]["nb_matchs"] >= min_matchs):
            ligne["yHome"] = m["homeGoals"]
            ligne["yAway"] = m["awayGoals"]
            ligne["saison"] = m.get("saison") or ""
            ligne["poids"] = _poids_temporel(m["date"], ref_ordinal)
            lignes.append(ligne)
        hist.appliquer(m)
    return lignes


if __name__ == "__main__":
    lignes = construire_dataset()
    print(f"{len(lignes)} matchs dans le dataset")
    if lignes:
        import statistics
        print("buts domicile moyen :",
              round(statistics.mean(l["yHome"] for l in lignes), 3),
              "| extérieur :", round(statistics.mean(l["yAway"] for l in lignes), 3))
        froids = sum(1 for l in lignes if l["featHome"]["nb_matchs"] < 5
                     or l["featAway"]["nb_matchs"] < 5)
        print(f"au moins une équipe < 5 matchs : {froids}/{len(lignes)}")
