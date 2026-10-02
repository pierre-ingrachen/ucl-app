import { Component, OnInit } from '@angular/core';
import { CommonModule, Location } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { SportsApiService } from '../services/sports-api';
import { Match } from '../models/match';
import { getFlagUrl } from '../services/flags';
import {
  sections as sectionsFiche,
  estAdversaire as estAdversaireFiche,
  resultatEquipe as resultatEquipeFiche,
  couleurResultat as couleurResultatFiche,
  getDateJourMois as getDateJourMoisFiche,
} from '../services/selection-historique';

/** Page dédiée à l'historique des 2 sélections d'un match de Ligue des Nations (accessible
 * en cliquant sur un match de l'onglet "Sélections"), plutôt qu'une fiche dépliée sur place :
 * permet de revenir en arrière et de partager/rafraîchir directement l'URL du match. */
@Component({
  selector: 'app-selection-match',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './selection-match.html',
  styleUrl: './selection-match.css'
})
export class SelectionMatch implements OnInit {
  isLoading = true;
  match: Match | null = null;

  isLoadingHome = true;
  isLoadingAway = true;
  ficheHome: any = null;
  ficheAway: any = null;

  constructor(
    private route: ActivatedRoute,
    private sportsApi: SportsApiService,
    private location: Location
  ) {}

  retour(): void {
    this.location.back();
  }

  ngOnInit(): void {
    const idEvent = this.route.snapshot.paramMap.get('idEvent');
    if (!idEvent) {
      this.isLoading = false;
      return;
    }

    this.sportsApi.getSelectionsSemaine().subscribe({
      next: (matches) => {
        this.match = matches.find(m => m.idEvent === idEvent) || null;
        this.isLoading = false;
        if (this.match) {
          this.chargerFiche(this.match.idHomeTeam, 'home');
          this.chargerFiche(this.match.idAwayTeam, 'away');
        }
      },
      error: (err) => {
        console.error('Erreur de récupération API :', err);
        this.isLoading = false;
      }
    });
  }

  private chargerFiche(idTeam: string | undefined, cote: 'home' | 'away'): void {
    if (!idTeam) {
      if (cote === 'home') this.isLoadingHome = false; else this.isLoadingAway = false;
      return;
    }
    this.sportsApi.getSelectionEquipe(idTeam).subscribe({
      next: (fiche) => {
        if (cote === 'home') { this.ficheHome = fiche; this.isLoadingHome = false; }
        else { this.ficheAway = fiche; this.isLoadingAway = false; }
      },
      error: (err) => {
        console.error(`Erreur de récupération de la fiche de sélection ${idTeam} :`, err);
        if (cote === 'home') this.isLoadingHome = false; else this.isLoadingAway = false;
      }
    });
  }

  sections = sectionsFiche;
  estAdversaire = estAdversaireFiche;
  resultatEquipe = resultatEquipeFiche;
  couleurResultat = couleurResultatFiche;
  getDateJourMois = getDateJourMoisFiche;

  getFlagUrl(country: string | undefined | null): string | null {
    return getFlagUrl(country);
  }
}
