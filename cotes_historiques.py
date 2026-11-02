"""Cotes historiques de football-data.co.uk : telechargement (cache + retries), lecture
normalisee en un schema unique pour toutes les ligues, probabilites implicites sans marge.

Deux familles de fichiers :
- saisonniers (`mmz4281/{saison}/{code}.csv`) : cotes d'ouverture ET de cloture, nombreux bookmakers ;
- "extra" (`new/{code}.csv`, une ligne par match, toutes saisons) : uniquement des cotes de cloture.

Usage : .venv/bin/python cotes_historiques.py [--refresh]   (ecrit data/odds_2020_2027.csv)
"""
import logging
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

log = logging.getLogger("cotes")

BASE_URL = "https://football-data.co.uk"  # le domaine en www. redirige vers celui-ci
DOSSIER_BRUT = os.path.join("data", "raw")
FICHIER_SORTIE = os.path.join("data", "odds_2020_2027.csv")

SAISONS = ["2021", "2122", "2223", "2324", "2425", "2526", "2627"]
SAISON_COURANTE = SAISONS[-1]
AGE_MAX_COURANT_H = 20  # le fichier de la saison en cours est retelecharge s'il date de plus de 20 h
DATE_MIN = "2020-08-01"  # debut de la premiere saison couverte (2020-21) (filtre des fichiers "extra")

# code football-data -> (id TheSportsDB, nom) pour les championnats saisonniers
LIGUES_SAISONNIERES = {
    "E0": "4328", "SC0": "4330", "D1": "4331", "I1": "4332", "SP1": "4335", "F1": "4334",
    "N1": "4337", "B1": "4338", "P1": "4344", "T1": "4339", "G1": "4336",
}
# fichiers "extra" -> id TheSportsDB
LIGUES_EXTRA = {"AUT": "4621", "DNK": "4340", "POL": "4422", "SWZ": "4675", "NOR": "4358", "SWE": "4347"}

# colonne source -> colonne du schema commun. Les colonnes absentes d'une ligue donnent NaN.
COLONNES_COTES = {
    # 1X2 : ouverture / cloture, par bookmaker
    "B365H": "b365_h", "B365D": "b365_d", "B365A": "b365_a",
    "B365CH": "b365c_h", "B365CD": "b365c_d", "B365CA": "b365c_a",
    "PSH": "ps_h", "PSD": "ps_d", "PSA": "ps_a",
    "PSCH": "psc_h", "PSCD": "psc_d", "PSCA": "psc_a",
    "MaxH": "max_h", "MaxD": "max_d", "MaxA": "max_a",
    "MaxCH": "maxc_h", "MaxCD": "maxc_d", "MaxCA": "maxc_a",
    "AvgH": "avg_h", "AvgD": "avg_d", "AvgA": "avg_a",
    "AvgCH": "avgc_h", "AvgCD": "avgc_d", "AvgCA": "avgc_a",
    # plus / moins de 2,5 buts
    "B365>2.5": "b365_o25", "B365<2.5": "b365_u25", "B365C>2.5": "b365c_o25", "B365C<2.5": "b365c_u25",
    "P>2.5": "ps_o25", "P<2.5": "ps_u25", "PC>2.5": "psc_o25", "PC<2.5": "psc_u25",
    "Max>2.5": "max_o25", "Max<2.5": "max_u25", "MaxC>2.5": "maxc_o25", "MaxC<2.5": "maxc_u25",
    "Avg>2.5": "avg_o25", "Avg<2.5": "avg_u25", "AvgC>2.5": "avgc_o25", "AvgC<2.5": "avgc_u25",
}
COLONNES_BASE = ["div", "saison_fd", "date", "equipe_dom", "equipe_ext", "buts_dom", "buts_ext", "resultat"]
COLONNES_SCHEMA = COLONNES_BASE + list(COLONNES_COTES.values())
COLS_1X2 = ["b365", "b365c", "ps", "psc", "max", "maxc", "avg", "avgc"]


# --- Telechargement -------------------------------------------------------------------

def download(url, destination, max_age_h=None, tentatives=4, force=False):
    """Telecharge `url` vers `destination` sauf si le fichier existe deja (et, si `max_age_h`
    est fourni, n'est pas trop ancien). Retries avec attente croissante sur erreur reseau ou
    code 5xx/429 ; un 404 n'est pas retente. Renvoie le chemin, ou None si introuvable."""
    if not force and os.path.exists(destination) and os.path.getsize(destination) > 0:
        age_h = (time.time() - os.path.getmtime(destination)) / 3600
        if max_age_h is None or age_h < max_age_h:
            log.info("cache   %s", destination)
            return destination
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    for essai in range(1, tentatives + 1):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 404:
                log.warning("absent  %s (404)", url)
                return None
            if resp.status_code in (429,) or resp.status_code >= 500:
                raise requests.exceptions.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            if not resp.content.strip():
                raise ValueError("reponse vide")
            with open(destination, "wb") as f:
                f.write(resp.content)
            log.info("telecharge %s (%d o)", url, len(resp.content))
            return destination
        except (requests.exceptions.RequestException, ValueError) as exc:
            attente = 2 ** essai
            log.warning("echec %d/%d %s : %s%s", essai, tentatives, url, exc,
                        f" -> nouvel essai dans {attente}s" if essai < tentatives else "")
            if essai < tentatives:
                time.sleep(attente)
    if os.path.exists(destination):  # mieux vaut un cache ancien que rien
        log.warning("utilisation du cache ancien %s", destination)
        return destination
    return None


# --- Lecture --------------------------------------------------------------------------

def _lire_csv(chemin):
    """Lit un CSV football-data : BOM possible, encodage utf-8 ou latin-1, lignes vides ou
    mal formees ignorees (certains fichiers ont des lignes plus longues que l'en-tete)."""
    for encodage in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(chemin, encoding=encodage, on_bad_lines="skip", skip_blank_lines=True,
                               low_memory=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"encodage illisible : {chemin}")


def parse(chemin, code, saison_fd=None):
    """Fichier football-data -> DataFrame au schema commun `COLONNES_SCHEMA`.
    `saison_fd` ("2526") pour les fichiers saisonniers ; pour les fichiers "extra" la saison
    vient de la colonne Season du fichier."""
    brut = _lire_csv(chemin)
    brut = brut.loc[:, ~brut.columns.astype(str).str.startswith("Unnamed")]
    extra = "Home" in brut.columns  # fichiers "extra" : autres noms de colonnes
    if extra:
        brut = brut.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG",
                                    "Res": "FTR"})
    manquantes = {"Date", "HomeTeam", "AwayTeam"} - set(brut.columns)
    if manquantes:
        raise ValueError(f"{chemin} : colonnes manquantes {sorted(manquantes)}")
    brut = brut.dropna(subset=["Date", "HomeTeam", "AwayTeam"], how="any")

    sortie = pd.DataFrame({
        "div": code,
        "saison_fd": brut["Season"].astype(str) if extra and "Season" in brut else saison_fd,
        "date": _parser_dates(brut["Date"]),
        "equipe_dom": brut["HomeTeam"].astype(str).str.strip(),
        "equipe_ext": brut["AwayTeam"].astype(str).str.strip(),
        "buts_dom": pd.to_numeric(brut.get("FTHG"), errors="coerce"),
        "buts_ext": pd.to_numeric(brut.get("FTAG"), errors="coerce"),
        "resultat": brut.get("FTR"),
    })
    for source, cible in COLONNES_COTES.items():
        sortie[cible] = pd.to_numeric(brut[source], errors="coerce") if source in brut else np.nan
    nb = len(sortie)
    sortie = sortie.dropna(subset=["date"])
    if len(sortie) < nb:
        log.warning("%s : %d lignes sans date valide ignorees", code, nb - len(sortie))
    if extra:
        sortie = sortie[sortie["date"] >= DATE_MIN]
    return sortie[COLONNES_SCHEMA].reset_index(drop=True)


def _parser_dates(serie):
    """dd/mm/yy ou dd/mm/yyyy (formats parfois melanges dans un meme fichier) -> datetime."""
    s = serie.astype(str).str.strip()
    long = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    court = pd.to_datetime(s, format="%d/%m/%y", errors="coerce")
    return long.fillna(court)


# --- Probabilites implicites ----------------------------------------------------------

def compute_probs(df, prefixe="psc"):
    """Probabilites implicites sans marge (1/cote divisee par la somme des 1/cote) a partir
    des colonnes `{prefixe}_h/_d/_a`. Ajoute `p_{prefixe}_h/_d/_a` (NaN si une cote manque)
    et `marge_{prefixe}` (surronde du bookmaker, ex. 0.03 = 3 %)."""
    df = df.copy()
    cotes = df[[f"{prefixe}_h", f"{prefixe}_d", f"{prefixe}_a"]].where(lambda c: c > 1.0)  # cote <= 1 : invalide
    inverses = 1.0 / cotes
    somme = inverses.sum(axis=1, skipna=False)
    for col, issue in zip(inverses.columns, ("h", "d", "a")):
        df[f"p_{prefixe}_{issue}"] = inverses[col] / somme
    df[f"marge_{prefixe}"] = somme - 1.0
    return df


# --- Chargement complet ---------------------------------------------------------------

def charger_toutes_les_cotes(force=False):
    """Telecharge (avec cache) et assemble toutes les ligues/saisons. Renvoie un DataFrame
    au schema commun, avec la colonne `ligue_id` (id TheSportsDB)."""
    morceaux = []
    for saison in SAISONS:
        for code, ligue_id in LIGUES_SAISONNIERES.items():
            chemin = download(f"{BASE_URL}/mmz4281/{saison}/{code}.csv",
                              os.path.join(DOSSIER_BRUT, f"{saison}_{code}.csv"),
                              max_age_h=AGE_MAX_COURANT_H if saison == SAISON_COURANTE else None, force=force)
            if chemin:
                df = parse(chemin, code, saison)
                df["ligue_id"] = ligue_id
                morceaux.append(df)
    for code, ligue_id in LIGUES_EXTRA.items():
        chemin = download(f"{BASE_URL}/new/{code}.csv", os.path.join(DOSSIER_BRUT, f"extra_{code}.csv"),
                          max_age_h=AGE_MAX_COURANT_H, force=force)
        if chemin:
            df = parse(chemin, code)
            df["ligue_id"] = ligue_id
            morceaux.append(df)
    cotes = pd.concat(morceaux, ignore_index=True)
    for prefixe in COLS_1X2:
        cotes = compute_probs(cotes, prefixe)
    return cotes


def resume(df):
    """Matchs par ligue et % de valeurs manquantes par colonne."""
    print("\nMatchs par ligue :")
    print(df.groupby("div").size().to_string())
    print("\n% de valeurs manquantes par colonne :")
    print((df.isna().mean() * 100).round(1).to_string())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    cotes = charger_toutes_les_cotes(force="--refresh" in sys.argv)
    os.makedirs(os.path.dirname(FICHIER_SORTIE), exist_ok=True)
    cotes.to_csv(FICHIER_SORTIE, index=False, date_format="%Y-%m-%d")
    log.info("%d matchs ecrits dans %s", len(cotes), FICHIER_SORTIE)
    resume(cotes)
