import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { SportsApiService } from '../services/sports-api';
import { SelectionsState } from '../services/selections-state';
import { Match } from '../models/match';

@Component({
  selector: 'app-selections',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './selections.html',
  styleUrl: './selections.css'
})
export class Selections implements OnInit {
  isLoading = true;

  constructor(
    private sportsApi: SportsApiService,
    private state: SelectionsState
  ) {}

  get matches(): Match[] {
    return this.state.matches;
  }

  ngOnInit(): void {
    // Si on revient sur la page (retour depuis un match), on réutilise les données déjà
    // chargées : sinon le contenu se recharge et change de hauteur, ce qui empêche
    // la restauration de la position de scroll.
    if (this.state.aDejaCharge) {
      this.isLoading = false;
      return;
    }

    this.sportsApi.getSelectionsSemaine().subscribe({
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
