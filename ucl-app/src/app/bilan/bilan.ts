import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SportsApiService } from '../services/sports-api';

type ModeleParis = 'rating' | 'ml' | 'ensemble';

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
  matchsAnalyses = 0;

  readonly modeles: { cle: ModeleParis; libelle: string }[] = [
    { cle: 'rating', libelle: 'Rating' },
    { cle: 'ml', libelle: 'IA' },
    { cle: 'ensemble', libelle: 'Ensemble' },
  ];
  modeleActif: ModeleParis = 'rating';

  constructor(private sportsApi: SportsApiService) {}

  ngOnInit(): void {
    this.charger();
  }

  changerModele(modele: ModeleParis): void {
    if (modele === this.modeleActif) return;
    this.modeleActif = modele;
    this.charger();
  }

  private charger(): void {
    this.isLoading = true;
    this.sportsApi.getParis(this.modeleActif).subscribe({
      next: (data) => {
        this.paris = data.paris;
        this.matchsAnalyses = data.matchsAnalyses;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Erreur de récupération API :', err);
        this.paris = [];
        this.matchsAnalyses = 0;
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

  /** Gain net cumulé, en unités (une unité = une mise de 1/cote), sur les paris déjà résolus. */
  get gainTotal(): number {
    return this.resolus.reduce((somme, p) => somme + (p.gain || 0), 0);
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
