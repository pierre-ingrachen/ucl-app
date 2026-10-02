/** Aide partagée entre l'onglet Sélections (liste) et la fiche détaillée d'un match :
 * mise en forme de l'historique d'une sélection nationale (fiche renvoyée par
 * /api/selections/{idTeam}). */

/** Regroupement affiché pour une fiche : l'édition en cours puis la précédente édition de
 * Ligue des Nations, puis pour la CDM 2026 et l'Euro 2024, la phase finale (si qualifiée)
 * et dans tous les cas le parcours de qualification — même structure "saison / liste de
 * matchs" que l'historique des onglets Championnats et Coupes d'Europe. */
export function sections(fiche: any): { titre: string; matchs: any[]; statut?: string }[] {
  const editionsNations = Object.keys(fiche.historiqueLigueDesNations || {}).map(saison => ({
    titre: `Ligue des Nations ${saison}`,
    matchs: fiche.historiqueLigueDesNations[saison] || [],
  }));

  function sectionsCompetition(nom: string, bloc: any): { titre: string; matchs: any[]; statut?: string }[] {
    const sections: { titre: string; matchs: any[]; statut?: string }[] = [];
    if (bloc.qualifiee) {
      sections.push({ titre: nom, matchs: bloc.matchs });
    }
    sections.push({
      titre: `${nom} - Qualifications`,
      matchs: bloc.matchsQualif || [],
      statut: bloc.qualifiee ? undefined : 'Non qualifiée',
    });
    return sections;
  }

  return [
    ...editionsNations,
    ...sectionsCompetition('Coupe du Monde 2026', fiche.cdm2026),
    ...sectionsCompetition('Euro 2024', fiche.euro2024),
  ];
}

/** Détermine, pour une ligne d'historique, si le côté donné (domicile ou extérieur)
 * correspond à l'adversaire de l'équipe suivie (et non à l'équipe suivie elle-même).
 * Comparaison par idTeam, comme dans la fiche de match. */
export function estAdversaire(hist: any, idEquipeSuivie: string, cote: 'home' | 'away'): boolean {
  const idEquipe = cote === 'home' ? hist.idHomeTeam : hist.idAwayTeam;
  return idEquipe !== idEquipeSuivie;
}

/** Résultat (Victoire / Nul / Défaite) d'un match du point de vue de l'équipe suivie. */
export function resultatEquipe(hist: any, idEquipeSuivie: string): 'V' | 'N' | 'D' | null {
  const estDomicile = hist.idHomeTeam === idEquipeSuivie;
  const estExterieur = hist.idAwayTeam === idEquipeSuivie;
  if (!estDomicile && !estExterieur) return null;

  const scoreEquipe = estDomicile ? hist.intHomeScore : hist.intAwayScore;
  const scoreAdversaire = estDomicile ? hist.intAwayScore : hist.intHomeScore;
  if (scoreEquipe === null || scoreEquipe === undefined || scoreAdversaire === null || scoreAdversaire === undefined) {
    return null;
  }

  if (Number(scoreEquipe) > Number(scoreAdversaire)) return 'V';
  if (Number(scoreEquipe) < Number(scoreAdversaire)) return 'D';
  return 'N';
}

const COULEUR_RESULTAT: { [key: string]: string } = {
  'V': '#16a34a',
  'N': '#9ca3af',
  'D': '#dc2626'
};

export function couleurResultat(resultat: 'V' | 'N' | 'D' | null): string {
  return resultat ? COULEUR_RESULTAT[resultat] : '#ccc';
}

export function getDateJourMois(dateEvent: string | undefined): string {
  if (!dateEvent) return '';
  const d = new Date(dateEvent);
  if (isNaN(d.getTime())) return '';
  const jour = d.getDate().toString().padStart(2, '0');
  const mois = (d.getMonth() + 1).toString().padStart(2, '0');
  return `${jour}/${mois}`;
}
