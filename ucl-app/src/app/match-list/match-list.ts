import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SportsApiService } from '../services/sports-api';
import { MatchListState } from '../services/match-list-state';
import { Match } from '../models/match';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-match-list',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './match-list.html',
  styleUrl: './match-list.css'
})
export class MatchListComponent implements OnInit {
  isLoading = true;

  constructor(
    private sportsApi: SportsApiService,
    private state: MatchListState
  ) {}

  get matches(): Match[] {
    return this.state.matches;
  }

  get competitionSelectionnee(): 'toutes' | '4480' | '4481' | '5071' {
    return this.state.competitionSelectionnee;
  }

  set competitionSelectionnee(valeur: 'toutes' | '4480' | '4481' | '5071') {
    this.state.competitionSelectionnee = valeur;
  }

  ngOnInit(): void {
    // Si on revient sur la page (retour depuis un match), on réutilise les données déjà
    // chargées : sinon le contenu se recharge et change de hauteur, ce qui empêche
    // la restauration de la position de scroll.
    if (this.state.aDejaCharge) {
      this.isLoading = false;
      return;
    }

    this.sportsApi.getUpcomingMatches().subscribe({
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

  get matchesFiltres(): Match[] {
    if (this.competitionSelectionnee === 'toutes') return this.matches;
    return this.matches.filter(m => m.idLeague === this.competitionSelectionnee);
  }
}