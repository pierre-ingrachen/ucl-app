import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { SportsApiService } from '../services/sports-api';
import { ChampionnatListState } from '../services/championnat-list-state';
import { Match } from '../models/match';

@Component({
  selector: 'app-championnats',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './championnats.html',
  styleUrl: './championnats.css'
})
export class Championnats implements OnInit {
  isLoading = true;

  constructor(
    private sportsApi: SportsApiService,
    private state: ChampionnatListState
  ) {}

  get matches(): Match[] {
    return this.state.matches;
  }

  get competitionsSelectionnees(): string[] {
    return this.state.competitionsSelectionnees;
  }

  // Liste des championnats disponibles, déduite des matchs reçus (triée par nom)
  // pour éviter de dupliquer côté front la liste des championnats gérés par l'API.
  get championnats(): { id: string; nom: string }[] {
    const vus = new Map<string, string>();
    for (const m of this.matches) {
      if (m.idLeague && m.strLeague && !vus.has(m.idLeague)) {
        vus.set(m.idLeague, m.strLeague);
      }
    }
    return Array.from(vus, ([id, nom]) => ({ id, nom })).sort((a, b) => a.nom.localeCompare(b.nom));
  }

  get libelleSelection(): string {
    const nb = this.competitionsSelectionnees.length;
    if (nb === 0) return 'Tous les championnats';
    if (nb === 1) return this.championnats.find(c => c.id === this.competitionsSelectionnees[0])?.nom ?? '1 championnat';
    return `${nb} championnats sélectionnés`;
  }

  estSelectionne(id: string): boolean {
    return this.competitionsSelectionnees.includes(id);
  }

  toggleChampionnat(id: string): void {
    const selection = this.competitionsSelectionnees;
    this.state.competitionsSelectionnees = this.estSelectionne(id)
      ? selection.filter(c => c !== id)
      : [...selection, id];
  }

  toutSelectionner(): void {
    this.state.competitionsSelectionnees = [];
  }

  get matchesFiltres(): Match[] {
    if (this.competitionsSelectionnees.length === 0) return this.matches;
    return this.matches.filter(m => m.idLeague && this.competitionsSelectionnees.includes(m.idLeague));
  }

  ngOnInit(): void {
    // Si on revient sur la page (retour depuis un match), on réutilise les données déjà
    // chargées : sinon le contenu se recharge et change de hauteur, ce qui empêche
    // la restauration de la position de scroll.
    if (this.state.aDejaCharge) {
      this.isLoading = false;
      return;
    }

    this.sportsApi.getUpcomingChampionnatMatches().subscribe({
      next: (data) => {
        this.state.matches = data;
        this.state.aDejaCharge = true;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Erreur de récupération API :', err);
        this.isLoading = false;
      }
    });
  }
}
