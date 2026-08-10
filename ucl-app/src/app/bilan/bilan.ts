import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SportsApiService } from '../services/sports-api';

@Component({
  selector: 'app-bilan',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './bilan.html',
  styleUrl: './bilan.css'
})
export class Bilan implements OnInit {
  isLoading = true;
  paris: any[] = [];

  constructor(private sportsApi: SportsApiService) {}

  ngOnInit(): void {
    this.sportsApi.getParis().subscribe({
      next: (data) => {
        this.paris = data;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Erreur de récupération API :', err);
        this.isLoading = false;
      }
    });
  }

  get resolus(): any[] {
    return this.paris.filter(p => p.statut !== 'en_attente');
  }

  get gagnes(): number {
    return this.resolus.filter(p => p.statut === 'gagne').length;
  }

  get enAttente(): number {
    return this.paris.length - this.resolus.length;
  }

  /** ROI = gain net cumulé / mise totale, uniquement sur les paris déjà résolus
   * (un pari en attente n'a pas encore de gain connu). */
  get roi(): number | null {
    const miseResolue = this.resolus.reduce((somme, p) => somme + (p.mise || 0), 0);
    if (miseResolue === 0) return null;
    const gainTotal = this.resolus.reduce((somme, p) => somme + (p.gain || 0), 0);
    return (gainTotal / miseResolue) * 100;
  }

  couleurStatut(statut: string): string {
    if (statut === 'gagne') return '#16a34a';
    if (statut === 'perdu') return '#dc2626';
    return '#999';
  }

  libelleStatut(statut: string): string {
    if (statut === 'gagne') return 'Gagné';
    if (statut === 'perdu') return 'Perdu';
    return 'En attente';
  }

  libelleIssue(issue: string): string {
    if (issue === 'domicile') return 'Victoire domicile';
    if (issue === 'exterieure') return 'Victoire extérieure';
    return 'Match nul';
  }
}
