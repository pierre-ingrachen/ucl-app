// Couleurs associées à chaque compétition (proches des identités visuelles UEFA :
// bleu nuit pour la Champions League, orange pour l'Europa League, vert pour la
// Conference League), utilisées pour teinter dynamiquement l'interface selon le match affiché.
export const COULEUR_COMPETITION: { [idLeague: string]: string } = {
  '4480': '#0c1c38', // UEFA Champions League — bleu nuit
  '4481': '#ff5a00', // UEFA Europa League — orange
  '5071': '#00a650', // UEFA Europa Conference League — vert
};

export const COULEUR_DEFAUT = '#0c1c38';

export function getCouleurCompetition(idLeague: string | undefined | null): string {
  return (idLeague && COULEUR_COMPETITION[idLeague]) || COULEUR_DEFAUT;
}

/** Dégradé prononcé (bandeau) pour teinter fortement le haut de la page avec la couleur
 * d'une compétition donnée, en s'estompant vers le bas. */
export function getDegradeFond(couleur: string): string {
  return `radial-gradient(1400px circle at 50% -5%, ${couleur}cc 0%, ${couleur}80 25%, ${couleur}26 55%, transparent 80%)`;
}
