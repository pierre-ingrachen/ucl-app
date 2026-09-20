import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SportsApiService } from '../services/sports-api';
import { Match } from '../models/match';

@Component({
  selector: 'app-selections',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './selections.html',
  styleUrl: './selections.css'
})
export class Selections implements OnInit {
  isLoading = true;
  matches: Match[] = [];

  /** idEvent du match dont la fiche des 2 sélections est dépliée (un seul à la fois). */
  matchDeplie: string | null = null;
  /** Fiches déjà chargées, indexées par idTeam : évite de recharger au second clic. */
  private fiches = new Map<string, any>();
  /** idTeam en cours de chargement, pour l'indicateur de chargement par équipe. */
  chargementEquipe = new Set<string>();

  constructor(private sportsApi: SportsApiService) {}

  ngOnInit(): void {
    this.sportsApi.getSelectionsSemaine().subscribe({
      next: (data) => {
        this.matches = data;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Erreur de récupération API :', err);
        this.isLoading = false;
      }
    });
  }

  toggleMatch(match: Match): void {
    if (this.matchDeplie === match.idEvent) {
      this.matchDeplie = null;
      return;
    }
    this.matchDeplie = match.idEvent;
    this.chargerFiche(match.idHomeTeam, match.strHomeTeam);
    this.chargerFiche(match.idAwayTeam, match.strAwayTeam);
  }

  private chargerFiche(idTeam: string | undefined, nomTeam: string | undefined): void {
    if (!idTeam || this.fiches.has(idTeam) || this.chargementEquipe.has(idTeam)) return;
    this.chargementEquipe.add(idTeam);
    this.sportsApi.getSelectionEquipe(idTeam).subscribe({
      next: (fiche) => {
        this.fiches.set(idTeam, fiche);
        this.chargementEquipe.delete(idTeam);
      },
      error: (err) => {
        console.error(`Erreur de récupération de la fiche de ${nomTeam} :`, err);
        this.fiches.set(idTeam, null);
        this.chargementEquipe.delete(idTeam);
      }
    });
  }

  ficheEquipe(idTeam: string | undefined): any {
    return idTeam ? this.fiches.get(idTeam) : undefined;
  }

  enChargement(idTeam: string | undefined): boolean {
    return !!idTeam && this.chargementEquipe.has(idTeam);
  }

  /** Regroupement affiché pour une fiche : les 2 dernières éditions de Ligue des Nations,
   * puis CDM 2026 et Euro 2024 (phase finale si qualifiée, sinon parcours de qualification) —
   * même structure "saison / liste de matchs" que l'historique des onglets Championnats et
   * Coupes d'Europe. */
  sections(fiche: any): { titre: string; matchs: any[]; statut?: string }[] {
    return [
      { titre: 'Ligue des Nations 2024-2025', matchs: fiche.historiqueLigueDesNations['2024-2025'] || [] },
      {
        titre: 'Coupe du Monde 2026',
        matchs: fiche.cdm2026.matchs,
        statut: fiche.cdm2026.qualifiee ? undefined : 'Non qualifiée — parcours de qualification',
      },
      {
        titre: 'Euro 2024',
        matchs: fiche.euro2024.matchs,
        statut: fiche.euro2024.qualifiee ? undefined : 'Non qualifiée — parcours de qualification',
      },
    ];
  }

  /** Détermine, pour une ligne d'historique, si le côté donné (domicile ou extérieur)
   * correspond à l'adversaire de l'équipe suivie (et non à l'équipe suivie elle-même).
   * Comparaison par idTeam, comme dans la fiche de match. */
  estAdversaire(hist: any, idEquipeSuivie: string, cote: 'home' | 'away'): boolean {
    const idEquipe = cote === 'home' ? hist.idHomeTeam : hist.idAwayTeam;
    return idEquipe !== idEquipeSuivie;
  }

  /** Résultat (Victoire / Nul / Défaite) d'un match du point de vue de l'équipe suivie. */
  resultatEquipe(hist: any, idEquipeSuivie: string): 'V' | 'N' | 'D' | null {
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

  private static readonly COULEUR_RESULTAT: { [key: string]: string } = {
    'V': '#16a34a',
    'N': '#9ca3af',
    'D': '#dc2626'
  };

  couleurResultat(resultat: 'V' | 'N' | 'D' | null): string {
    return resultat ? Selections.COULEUR_RESULTAT[resultat] : '#ccc';
  }

  getDateJourMois(dateEvent: string | undefined): string {
    if (!dateEvent) return '';
    const d = new Date(dateEvent);
    if (isNaN(d.getTime())) return '';
    const jour = d.getDate().toString().padStart(2, '0');
    const mois = (d.getMonth() + 1).toString().padStart(2, '0');
    return `${jour}/${mois}`;
  }
}
