import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SportsApiService } from '../services/sports-api';
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
  matches: Match[] = [];
  isLoading = true;

  competitionSelectionnee: 'toutes' | '4480' | '5071' = 'toutes';

  constructor(private sportsApi: SportsApiService) {}

  ngOnInit(): void {
    this.sportsApi.getUpcomingMatches().subscribe({
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

  get matchesFiltres(): Match[] {
    if (this.competitionSelectionnee === 'toutes') return this.matches;
    return this.matches.filter(m => m.idLeague === this.competitionSelectionnee);
  }
}