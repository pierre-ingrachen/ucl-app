"""Base locale des matchs et des clubs : tout ce que le site affichait grace a TheSportsDB, stocke
dans le depot (aucun appel externe pour le lire).

    calendrier/base/
      evenements/<id_ligue>_<saison>.json   evenements au format TheSportsDB (champs utiles, voir CHAMPS)
      equipes.json                          id club -> {nom, pays, ligue:{id,nom}, badge}
      classements_nationaux.json            tables gelees des ligues que nous ne suivons pas
      badges/ + badges.json                 logos reduits, url d'origine -> fichier local

Les saisons terminees ne sont plus jamais reecrites. La saison en cours est mise a jour par
`upsert` (resultats ESPN / football-data, nouveaux matchs) sans jamais ecraser un champ statique
(tour, stade, logos) par une valeur vide. Le snapshot initial vient de `migration_tsdb.py`.
"""
import json
import logging
import os
import threading

journal = logging.getLogger("calendrier.base")
RACINE_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base")

# Champs conserves par evenement (ceux que le site, les modeles et l'API utilisent).
CHAMPS = ("idEvent", "idLeague", "strLeague", "strLeagueBadge", "strSeason", "intRound", "strEvent",
          "idHomeTeam", "idAwayTeam", "strHomeTeam", "strAwayTeam", "strHomeTeamBadge", "strAwayTeamBadge",
          "dateEvent", "strTime", "strTimestamp", "intHomeScore", "intAwayScore", "strStatus", "strPostponed",
          "strVenue", "strCountry", "strFilename")
# Champs qui changent d'un match a l'autre en cours de saison : ceux-la sont toujours remplaces.
CHAMPS_DYNAMIQUES = ("dateEvent", "strTime", "strTimestamp", "intHomeScore", "intAwayScore", "strStatus",
                     "strPostponed")


def _joue(e):
    return e.get("intHomeScore") not in (None, "") and e.get("intAwayScore") not in (None, "")


def reduire(evenement):
    """Evenement fournisseur -> evenement de la base (champs utiles seulement). Garantit `strFilename`
    (utilise par le front pour reperer les qualifications) meme pour un evenement ESPN."""
    e = {k: evenement.get(k) for k in CHAMPS}
    if not e["strFilename"] and e["strLeague"] and e["strEvent"]:
        e["strFilename"] = f"{e['strLeague']} {e['dateEvent']} {e['strEvent']}"
    return e


class Base:
    """Acces en lecture/ecriture a la base locale. `racine` : dossier de la base (tests : dossier temporaire)."""

    def __init__(self, racine=None):
        self.racine = racine or RACINE_BASE
        self._cache = {}        # fichier -> (signature, donnees)
        self._verrou = threading.Lock()
        self._index = None      # idEvent -> (ligue, saison), reconstruit si les fichiers changent
        self._signature_index = None

    # --- lecture / ecriture brutes -------------------------------------------------------------------------------
    def _chemin(self, *morceaux):
        return os.path.join(self.racine, *morceaux)

    def _lire(self, chemin, defaut):
        try:
            st = os.stat(chemin)
        except OSError:
            return defaut
        signature = (st.st_mtime_ns, st.st_size)
        with self._verrou:
            en_cache = self._cache.get(chemin)
            if en_cache and en_cache[0] == signature:
                return en_cache[1]
        try:
            with open(chemin, encoding="utf-8") as f:
                donnees = json.load(f)
        except (OSError, ValueError):
            return defaut
        with self._verrou:
            self._cache[chemin] = (signature, donnees)
        return donnees

    def _ecrire(self, chemin, donnees):
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        temporaire = chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporaire, chemin)  # ecriture atomique : un lecteur ne voit jamais un fichier a moitie ecrit
        with self._verrou:
            self._cache.pop(chemin, None)

    # --- evenements ---------------------------------------------------------------------------------------------
    def chemin_saison(self, id_ligue, saison):
        return self._chemin("evenements", f"{id_ligue}_{saison}.json")

    def saisons(self, id_ligue):
        """Saisons stockees d'une ligue, de la plus ancienne a la plus recente."""
        dossier = self._chemin("evenements")
        if not os.path.isdir(dossier):
            return []
        return sorted(f[len(id_ligue) + 1:-5] for f in os.listdir(dossier)
                      if f.startswith(f"{id_ligue}_") and f.endswith(".json"))

    def evenements_saison(self, id_ligue, saison):
        """Evenements d'une ligue pour une saison (liste vide si absente). Ne pas modifier la liste renvoyee."""
        return self._lire(self.chemin_saison(id_ligue, saison), [])

    def evenements_ligue(self, id_ligue, saisons=None):
        """Tous les evenements d'une ligue (saisons demandees, sinon toutes)."""
        return [e for s in (saisons or self.saisons(id_ligue)) for e in self.evenements_saison(id_ligue, s)]

    def ecrire_saison(self, id_ligue, saison, evenements):
        tries = sorted((reduire(e) for e in evenements), key=lambda e: (e["dateEvent"] or "", str(e["idEvent"])))
        self._ecrire(self.chemin_saison(id_ligue, saison), tries)
        self._index = None

    def evenement(self, id_event):
        """Evenement par identifiant (toutes ligues et saisons), ou None."""
        dossier = self._chemin("evenements")
        if not os.path.isdir(dossier):
            return None
        signature = tuple(sorted((f, os.stat(os.path.join(dossier, f)).st_mtime_ns) for f in os.listdir(dossier)))
        if self._index is None or self._signature_index != signature:
            index = {}
            for f in os.listdir(dossier):
                if f.endswith(".json"):
                    for e in self._lire(os.path.join(dossier, f), []):
                        index[str(e["idEvent"])] = e
            self._index, self._signature_index = index, signature
        return self._index.get(str(id_event))

    def upsert(self, evenements):
        """Ajoute ou met a jour des evenements (format TheSportsDB, champs en plus ignores). Un evenement
        connu voit ses champs dynamiques remplaces et ses champs statiques completes seulement s'ils
        etaient vides ; un evenement inconnu est ajoute. Renvoie (nb_mis_a_jour, nb_ajoutes)."""
        par_fichier = {}
        for e in evenements:
            par_fichier.setdefault((e["idLeague"], e["strSeason"]), []).append(e)
        modifies = ajoutes = 0
        for (id_ligue, saison), nouveaux in par_fichier.items():
            existants = {str(x["idEvent"]): dict(x) for x in self.evenements_saison(id_ligue, saison)}
            avant = json.dumps(existants, sort_keys=True)
            for e in nouveaux:
                e = reduire(e)
                cle = str(e["idEvent"])
                if cle in existants:
                    courant = existants[cle]
                    if _joue(courant) and not _joue(e) and e.get("dateEvent") != courant.get("dateEvent"):
                        # Un match joue ne perd jamais son score ni sa date (evenement fournisseur mal rattache).
                        journal.warning("Mise a jour refusee pour %s (%s - %s, joue le %s) : date %s sans score",
                                        cle, courant.get("strHomeTeam"), courant.get("strAwayTeam"),
                                        courant.get("dateEvent"), e.get("dateEvent"))
                        continue
                    for champ, valeur in e.items():
                        if champ in CHAMPS_DYNAMIQUES:
                            courant[champ] = valeur
                        elif valeur not in (None, "") and courant.get(champ) in (None, ""):
                            courant[champ] = valeur
                    modifies += 1
                else:
                    existants[cle] = e
                    ajoutes += 1
            if json.dumps(existants, sort_keys=True) != avant:
                self.ecrire_saison(id_ligue, saison, list(existants.values()))
        return modifies, ajoutes

    # --- clubs --------------------------------------------------------------------------------------------------
    def equipes(self):
        return self._lire(self._chemin("equipes.json"), {})

    def ecrire_equipes(self, equipes):
        self._ecrire(self._chemin("equipes.json"), equipes)

    def completer_equipes(self, evenements):
        """Cree la fiche des clubs presents dans `evenements` mais absents de equipes.json (promus, nouveaux
        clubs, ids provisoires) : pays = pays majoritaire des clubs de la meme ligue, ligue = celle du match,
        logo du match. Renvoie le nombre de fiches ajoutees."""
        equipes = self.equipes()
        pays_par_ligue = {}
        for fiche in equipes.values():
            if fiche.get("ligue") and fiche.get("pays"):
                pays_par_ligue.setdefault(fiche["ligue"]["id"], []).append(fiche["pays"])
        ajoutes = 0
        for e in evenements:
            for cote in ("Home", "Away"):
                id_club = str(e.get(f"id{cote}Team") or "")
                if not id_club or id_club in equipes:
                    continue
                pays = pays_par_ligue.get(e["idLeague"])
                equipes[id_club] = {
                    "nom": e.get(f"str{cote}Team") or id_club,
                    "pays": max(set(pays), key=pays.count) if pays else "",
                    "ligue": {"id": e["idLeague"], "nom": e.get("strLeague") or ""},
                    "badge": e.get(f"str{cote}TeamBadge") or "",
                }
                ajoutes += 1
        if ajoutes:
            self.ecrire_equipes(equipes)
        return ajoutes

    def pays(self, id_equipe):
        return (self.equipes().get(str(id_equipe)) or {}).get("pays") or ""

    def ligue_nationale(self, id_equipe):
        """{"id", "nom"} du championnat national du club (selon le dernier releve TheSportsDB), ou None."""
        return (self.equipes().get(str(id_equipe)) or {}).get("ligue") or None

    # --- classements nationaux gelés (ligues non suivies) ---------------------------------------------------------
    def classements_nationaux(self):
        return self._lire(self._chemin("classements_nationaux.json"), {})

    def ecrire_classements_nationaux(self, donnees):
        self._ecrire(self._chemin("classements_nationaux.json"), donnees)

    def classement_national_gele(self, id_equipe):
        """Position du club dans une ligue que nous ne suivons pas (table figee au dernier releve) :
        {"position", "total", "saison", "ligue", "maj"} ou None."""
        id_equipe = str(id_equipe)
        for id_ligue, table in self.classements_nationaux().items():
            for ligne in table.get("lignes", []):
                if ligne["idTeam"] == id_equipe:
                    return {"position": int(ligne["intRank"]), "total": len(table["lignes"]),
                            "saison": table["saison"], "ligue": table["ligue"], "maj": table["maj"]}
        return None
