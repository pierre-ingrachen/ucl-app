"""Paris automatiques de l'algorithme a regles (modele_d/regles.py, sans IA), en parallele des autres : memes
calendrier et cotes (Winamax, Betclic ou Unibet, cf. odds.py), journal separe.

Pour chaque match du jour : l'outsider est l'equipe dont la victoire a la cote la plus haute ; on parie sur
sa victoire si regles.parier() l'autorise (cote > 4 et au plus 1 victoire sur ses 5 derniers matchs).
Mise = 1 / cote.

Usage : appele par paris_reseau.py (etape `paris`).
"""
import os
from datetime import date

import paris_reseau as pr
from modele_d import paris as pd_
from modele_d.regles import parier

FICHIER_PARIS = "modele_d/journaux/regles_paris.json"
FICHIER_ANALYSES = "modele_d/journaux/regles_analyses.json"  # {idEvent: date}


def pourcentages_forme(ligne, equipe):
    """(% victoires, % sans defaite, % victoires au meme lieu) sur les 5 derniers matchs de `equipe` ("dom"/"ext")."""
    pour = [ligne[f"{equipe}_m{j}_buts_pour"] for j in range(1, 6)]
    contre = [ligne[f"{equipe}_m{j}_buts_contre"] for j in range(1, 6)]
    lieu = [ligne[f"{equipe}_m{j}_domicile"] == (1 if equipe == "dom" else 0) for j in range(1, 6)]
    gagne = [p > c for p, c in zip(pour, contre)]
    gagne_lieu = [g for g, l in zip(gagne, lieu) if l]
    return (100 * sum(gagne) / 5, 100 * sum(p >= c for p, c in zip(pour, contre)) / 5,
            100 * sum(gagne_lieu) / len(gagne_lieu) if gagne_lieu else 0.0)


def decision(ligne, cote_dom, cote_ext):
    """Issue a parier ("domicile" / "exterieure") ou None. `ligne` : features du match (dict ou Series)."""
    if not cote_dom or not cote_ext:
        return None
    dom_outsider = cote_dom > cote_ext
    dom, ext = pourcentages_forme(ligne, "dom"), pourcentages_forme(ligne, "ext")
    if parier(cote_dom if dom_outsider else cote_ext, dom_outsider, dom[0], ext[0], dom[1], ext[1], dom[2], ext[2]):
        return "domicile" if dom_outsider else "exterieure"
    return None


def etape_paris_regles(calendrier, cotes, aujourd_hui=None):
    aujourd_hui = aujourd_hui or str(date.today())
    journal = pr._lire_json(FICHIER_PARIS, [])
    analyses = pr._lire_json(FICHIER_ANALYSES, {})
    joues = {e["idEvent"]: e for saisons in calendrier.values() for evs in saisons.values() for e in evs if pr.est_joue(e)}
    pr.resoudre_paris(journal, joues)
    deja = {(p["idEvent"], p["issue"]) for p in journal}
    lignes = pd_.lignes_du_jour(calendrier, cotes, aujourd_hui)
    for m, c, ligne in lignes:
        analyses[m["idEvent"]] = m["dateEvent"]
        issue = decision(ligne, c.get("domicile"), c.get("exterieure"))
        if issue and (m["idEvent"], issue) not in deja:
            cote = c[issue]
            journal.append({
                "idEvent": m["idEvent"], "date": m["dateEvent"], "ligue": pr.main.DOMESTIC_LEAGUES[m["idLeague"]],
                "equipeDomicile": m["strHomeTeam"], "equipeExterieur": m["strAwayTeam"],
                "issue": issue, "coteBookmaker": cote, "bookmaker": c["bookmaker"],
                "mise": round(1 / cote, 4), "statut": "en_attente", "gain": None})
    os.makedirs(os.path.dirname(FICHIER_PARIS), exist_ok=True)
    pr._ecrire_json(FICHIER_PARIS, journal)
    pr._ecrire_json(FICHIER_ANALYSES, analyses)
    resolus = [p for p in journal if p["statut"] != "en_attente"]
    gain, mises = sum(p["gain"] for p in resolus), sum(p["mise"] for p in resolus)
    print(f"## Bilan des paris des regles — {aujourd_hui}\n")
    print(f"- Matchs analyses aujourd'hui : {len(lignes)}")
    print(f"- Paris resolus : {len(resolus)} ({sum(p['statut'] == 'gagne' for p in resolus)} gagnes)")
    print(f"- Gain net cumule : {gain:+.2f} unites" + (f" (ROI {gain / mises:+.1%})" if mises else ""))
    print(f"- Paris en attente : {sum(p['statut'] == 'en_attente' for p in journal)}\n")
    for p in [p for p in journal if p["date"] == aujourd_hui]:
        print(f"- {p['equipeDomicile']} - {p['equipeExterieur']} ({p['issue']}) : cote {p['bookmaker']} "
              f"{p['coteBookmaker']}, mise {p['mise']}")
