"""Annuaire des clubs : rapprochement des noms de clubs d'un fournisseur (ESPN, The Odds API)
avec les identifiants TheSportsDB utilises partout dans le depot (historiques, journaux), et
logos.

L'annuaire (`ressources/annuaire.json`, versionne : la CI n'a pas les caches locaux) est
construit une fois a partir des donnees locales :

    .venv/bin/python -m calendrier.equipes construire

Il contient pour chaque club son id TheSportsDB, son nom, son logo TheSportsDB et ses ligues, et
pour chaque ligue son logo. `ressources/pont_espn.json` memorise les correspondances
id ESPN -> id TheSportsDB deja resolues (ou forcees a la main : une valeur ecrite ici l'emporte
toujours sur le rapprochement par nom).
"""
import json
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher

RESSOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources")
FICHIER_ANNUAIRE = os.path.join(RESSOURCES, "annuaire.json")
FICHIER_PONT_ESPN = os.path.join(RESSOURCES, "pont_espn.json")
RACINE = os.path.dirname(os.path.dirname(RESSOURCES))

SEUIL_SIMILARITE = 0.82  # plus strict que odds.py (0.6) : ici il n'y a pas la date pour verifier
SEUIL_MEMORISATION = 0.95  # en dessous, le rapprochement est refait a chaque run (jamais memorise dans le pont)
MARGE_AMBIGUITE = 0.04   # le meilleur candidat doit battre le deuxieme d'au moins cette marge

# Sigles de club qui varient d'un fournisseur a l'autre (« FC Porto », « Porto »).
MOTS_IGNORES = {"fc", "cf", "sc", "ac", "afc", "cfc", "club", "cd", "ss", "us", "ud", "sk", "fk", "if", "bk",
                "ff", "fbc", "sv", "vfl", "vfb", "tsg", "fsv", "rb", "ks", "kv", "kvc", "krc", "sporting", "de", "the"}
# Noms differents d'un fournisseur a l'autre : nom du fournisseur -> nom TheSportsDB. A completer
# quand `python -m calendrier.source diagnostic` signale un club non rapproche. (Un rapprochement
# force par identifiant se fait plutot dans ressources/pont_espn.json.)
ALIAS_NOMS = {
    "Olympiakos Piraeus": "Olympiacos", "Red Star Belgrade": "Crvena Zvezda", "Hearts": "Heart of Midlothian",
    "FC Cologne": "Köln", "Internazionale": "Inter Milan", "Stade Rennais": "Rennes",
    "Deportivo": "Deportivo de A Coruña", "OFI Crete": "OFI", "OH Leuven": "Oud-Heverlee Leuven",
    "Erzurum BB": "Erzurumspor", "AGF": "AGF Aarhus", "F.C. København": "FC Copenhagen",
    "C.D. Nacional": "Nacional de Madeira", "KFUM Oslo": "KFUM-Kameratene Oslo",
    "CSU Craiova": "Universitatea Craiova", "SC Rheindorf Altach": "SCR Altach", "SV Josko Ried": "SV Ried", "WSG Swarovski Tirol": "WSG Tirol",
}


# Lettres que NFKD ne decompose pas (« Lillestrøm », « Wisła », « Þór ») : sans cela elles disparaissent.
_TRANSLITTERATION = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ð": "d",
                                   "þ": "th", "æ": "ae", "Æ": "AE", "œ": "oe", "ß": "ss", "ı": "i"})


def _cle(nom):
    nom = unicodedata.normalize("NFKD", (nom or "").translate(_TRANSLITTERATION)).encode("ascii", "ignore").decode("ascii").lower()
    nom = nom.replace("&", " and ").replace("'", "")
    return "".join(m for m in re.split(r"[^a-z0-9]+", nom) if m and m not in MOTS_IGNORES)


_ALIAS = {_cle(a): _cle(b) for a, b in ALIAS_NOMS.items()}


def normaliser(nom):
    """Cle de comparaison : sans accents, casse, ponctuation ni sigles de club."""
    cle = _cle(nom)
    return _ALIAS.get(cle, cle)


def _score(a, b):
    """Similarite de deux cles normalisees : 1 si l'une commence par l'autre (« PAOK » /
    « PAOK Thessaloniki »), sinon rapport de SequenceMatcher."""
    if a == b:
        return 1.0
    court, long_ = sorted((a, b), key=len)
    if len(court) >= 4 and (long_.startswith(court) or long_.endswith(court)):
        return 0.97
    if len(court) >= 5 and court in long_:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def _lire(fichier, defaut):
    if not os.path.exists(fichier):
        return defaut
    with open(fichier, encoding="utf-8") as f:
        return json.load(f)


class Annuaire:
    """Rapprochement nom -> id TheSportsDB et logos. `donnees` = contenu d'annuaire.json."""

    def __init__(self, donnees=None, pont=None):
        donnees = donnees if donnees is not None else _lire(FICHIER_ANNUAIRE, {"equipes": {}, "ligues": {}})
        self.equipes = donnees.get("equipes", {})       # id -> {"nom", "badge", "ligues": [...]}
        self.badges_ligue = donnees.get("ligues", {})    # id ligue -> logo
        self.fichier_pont = FICHIER_PONT_ESPN if pont is None else None  # pont fourni (tests) : jamais ecrit
        self.pont = pont if pont is not None else _lire(FICHIER_PONT_ESPN, {})
        self.pont_modifie = False
        self.inconnus = {}                               # (ligue, nom) -> raison, pour le diagnostic
        self._index = {}

    def _candidats(self, id_ligue):
        """{id club -> cle normalisee} des clubs de la ligue (tous les clubs connus pour une coupe
        d'Europe, dont les participants viennent de partout)."""
        if id_ligue not in self._index:
            from .ligues import LIGUES
            europe = LIGUES.get(id_ligue, {}).get("europe", False)
            self._index[id_ligue] = {i: normaliser(e["nom"]) for i, e in self.equipes.items()
                                     if europe or id_ligue in e.get("ligues", [])}
        return self._index[id_ligue]

    def resoudre(self, nom, id_ligue, id_externe=None):
        """Id TheSportsDB du club `nom` (ou None si inconnu / ambigu). `id_externe` = id chez le
        fournisseur (ESPN) : sa correspondance est memorisee apres un premier rapprochement."""
        cle_pont = f"espn:{id_externe}" if id_externe else None
        if cle_pont and cle_pont in self.pont:
            return self.pont[cle_pont]
        cle = normaliser(nom)
        notes = sorted(((_score(cle, c), i) for i, c in self._candidats(id_ligue).items()), reverse=True)
        if not notes or notes[0][0] < SEUIL_SIMILARITE:
            self.inconnus[(id_ligue, nom)] = "aucun club assez proche"
            return None
        if len(notes) > 1 and notes[0][0] < 1.0 and notes[0][0] - notes[1][0] < MARGE_AMBIGUITE:
            self.inconnus[(id_ligue, nom)] = f"ambigu : {self.equipes[notes[0][1]]['nom']} / {self.equipes[notes[1][1]]['nom']}"
            return None
        if cle_pont and notes[0][0] >= SEUIL_MEMORISATION:  # un rapprochement douteux n'est jamais fige
            self.pont[cle_pont] = notes[0][1]
            self.pont_modifie = True
        return notes[0][1]

    def resoudre_ou_provisoire(self, nom, id_ligue, id_externe=None):
        """Comme `resoudre`, mais un club inconnu (promu, nouveau) recoit un id provisoire stable,
        identique quel que soit le fournisseur (« inconnu-<nom normalise> ») : il n'a aucun
        historique, donc aucune prediction, mais ses matchs restent coherents d'un run a l'autre."""
        return self.resoudre(nom, id_ligue, id_externe) or f"inconnu-{normaliser(nom)}"

    def nom(self, id_club, defaut=""):
        return self.equipes.get(id_club, {}).get("nom", defaut)

    def logo(self, id_club, logo_fournisseur=None):
        """Logo TheSportsDB du club s'il est connu (meme image que l'ancien site), sinon celui du
        fournisseur (ESPN), sinon vide."""
        return self.equipes.get(id_club, {}).get("badge") or logo_fournisseur or ""

    def logo_ligue(self, id_ligue):
        return self.badges_ligue.get(id_ligue, "")

    def sauvegarder_pont(self):
        if self.pont_modifie and self.fichier_pont:
            os.makedirs(RESSOURCES, exist_ok=True)
            with open(self.fichier_pont, "w", encoding="utf-8") as f:
                json.dump(dict(sorted(self.pont.items())), f, ensure_ascii=False, indent=1)
            self.pont_modifie = False


def construire(racine=None):
    """Construit annuaire.json (ids, noms et logos servant a rapprocher les noms des fournisseurs) depuis les
    historiques locaux (2020 -> aujourd'hui) et la base locale (`calendrier/base/`) : plus aucune dependance
    aux caches non versionnes."""
    racine = racine or RACINE
    equipes, ligues_logos = {}, {}

    def club(id_club, nom, id_ligue=None, badge=None):
        if not id_club or not nom:
            return
        e = equipes.setdefault(str(id_club), {"nom": nom, "badge": "", "ligues": []})
        e["nom"] = nom
        if badge:
            e["badge"] = badge
        if id_ligue and id_ligue not in e["ligues"]:
            e["ligues"].append(id_ligue)

    # 1. Historiques (ids et noms de tous les matchs), du plus ancien au plus recent : le nom retenu est le dernier.
    for fichier in (os.path.join(racine, "modele_d", "ressources", "matchs_reseau_bruts_ext.json"),
                    os.path.join(racine, "matchs_reseau_bruts.json")):
        for id_ligue, saisons in _lire(fichier, {}).items():
            for saison in sorted(saisons):
                for e in saisons[saison]:
                    club(e.get("idHomeTeam"), e.get("strHomeTeam"), id_ligue)
                    club(e.get("idAwayTeam"), e.get("strAwayTeam"), id_ligue)
    # 2. Base locale : noms et logos TheSportsDB les plus recents, logos de ligue.
    from .base import Base
    base = Base(os.path.join(racine, "calendrier", "base"))
    for id_club, fiche in base.equipes().items():
        club(id_club, fiche.get("nom"), (fiche.get("ligue") or {}).get("id"), fiche.get("badge"))
    dossier = os.path.join(base.racine, "evenements")
    for f in sorted(os.listdir(dossier)) if os.path.isdir(dossier) else []:
        for e in base._lire(os.path.join(dossier, f), []):
            if e.get("strLeagueBadge"):
                ligues_logos[e["idLeague"]] = e["strLeagueBadge"]
            for cote in ("Home", "Away"):
                club(e.get(f"id{cote}Team"), e.get(f"str{cote}Team"), None, e.get(f"str{cote}TeamBadge"))
    return {"equipes": equipes, "ligues": ligues_logos}


if __name__ == "__main__":
    if sys.argv[1:] == ["construire"]:
        donnees = construire()
        os.makedirs(RESSOURCES, exist_ok=True)
        with open(FICHIER_ANNUAIRE, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=0)
        avec_logo = sum(1 for e in donnees["equipes"].values() if e["badge"])
        print(f"{len(donnees['equipes'])} clubs ({avec_logo} avec logo), {len(donnees['ligues'])} logos de ligue "
              f"-> {FICHIER_ANNUAIRE}")
    else:
        print("usage : python -m calendrier.equipes construire")
