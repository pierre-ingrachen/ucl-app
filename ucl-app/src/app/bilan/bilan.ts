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
  erreur = false;
  algos: any[] = [];
  choix = 'reseau';

  constructor(private sportsApi: SportsApiService) {}

  ngOnInit(): void {
    this.sportsApi.getBilansParis().subscribe({
      next: (data) => {
        this.algos = data.algos;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Erreur de récupération API :', err);
        this.erreur = true;
        this.isLoading = false;
      }
    });
  }

  /** Bilan de l'algorithme sélectionné. */
  get bilan(): any {
    return this.algos.find((a) => a.id === this.choix) ?? this.algos[0];
  }

  get parisResolus(): number {
    return this.bilan.parisGagnes + this.bilan.parisPerdus;
  }
}
