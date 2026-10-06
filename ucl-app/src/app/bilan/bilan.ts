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
  bilan: any = null;

  constructor(private sportsApi: SportsApiService) {}

  ngOnInit(): void {
    this.sportsApi.getBilanParis().subscribe({
      next: (data) => {
        this.bilan = data;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Erreur de récupération API :', err);
        this.erreur = true;
        this.isLoading = false;
      }
    });
  }

  get parisResolus(): number {
    return this.bilan.parisGagnes + this.bilan.parisPerdus;
  }
}
