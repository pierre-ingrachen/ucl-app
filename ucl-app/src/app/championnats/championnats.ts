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

  // Les onglets regroupent les championnats par niveau ; l'ordre des ids fixe aussi l'ordre
  // d'affichage dans la liste déroulante.
  // Top 5 : Premier League, La Liga, Bundesliga, Serie A, Ligue 1.
  private static readonly TOP5_LEAGUE_IDS = ['4328', '4335', '4331', '4332', '4334'];
  // 6-10 : Pro League (Belgique), Eredivisie (Pays-Bas), Primeira Liga (Portugal),
  // Süper Lig (Turquie), Ekstraklasa (Pologne).
  private static readonly G610_LEAGUE_IDS = ['4338', '4337', '4344', '4339', '4422'];
  // 11-20 : Tchéquie, Grèce, Norvège, Danemark, Chypre, Suisse, Autriche, Hongrie, Écosse, Suède.
  private static readonly G1120_LEAGUE_IDS = ['4631', '4336', '4358', '4340', '4630', '4675', '4621', '4690', '4330', '4347'];

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

  get ongletActif(): 'top5' | 'g610' | 'g1120' {
    return this.state.ongletActif;
  }

  changerOnglet(onglet: 'top5' | 'g610' | 'g1120'): void {
    if (this.state.ongletActif === onglet) return;
    this.state.ongletActif = onglet;
    this.state.competitionsSelectionnees = [];
  }

  private get ongletLeagueIds(): string[] {
    switch (this.ongletActif) {
      case 'g610': return Championnats.G610_LEAGUE_IDS;
      case 'g1120': return Championnats.G1120_LEAGUE_IDS;
      default: return Championnats.TOP5_LEAGUE_IDS;
    }
  }

  private get matchesOnglet(): Match[] {
    const ids = this.ongletLeagueIds;
    return this.matches.filter(m => !!m.idLeague && ids.includes(m.idLeague));
  }

  // Liste des championnats disponibles, déduite des matchs reçus, dans l'ordre défini
  // pour l'onglet actif (pas alphabétique).
  get championnats(): { id: string; nom: string }[] {
    const ordre = this.ongletLeagueIds;
    const vus = new Map<string, string>();
    for (const m of this.matchesOnglet) {
      if (m.idLeague && m.strLeague && !vus.has(m.idLeague)) {
        vus.set(m.idLeague, m.strLeague);
      }
    }
    return Array.from(vus, ([id, nom]) => ({ id, nom }))
      .sort((a, b) => ordre.indexOf(a.id) - ordre.indexOf(b.id));
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
    if (this.competitionsSelectionnees.length === 0) return this.matchesOnglet;
    return this.matchesOnglet.filter(m => m.idLeague && this.competitionsSelectionnees.includes(m.idLeague));
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
