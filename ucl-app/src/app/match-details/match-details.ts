import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { SportsApiService } from '../services/sports-api';

const COUNTRY_TO_ISO: { [key: string]: string } = {
  'Russia': 'ru', 'Ukraine': 'ua', 'Belarus': 'by', 'Denmark': 'dk',
  'Montenegro': 'me', 'Finland': 'fi', 'Croatia': 'hr', 'Kazakhstan': 'kz',
  'Faroe Islands': 'fo', 'Serbia': 'rs', 'Belgium': 'be', 'Macedonia': 'mk',
  'Ireland': 'ie', 'San Marino': 'sm', 'England': 'gb-eng', 'Scotland': 'gb-sct',
  'Northern Ireland': 'gb-nir', 'Wales': 'gb-wls', 'France': 'fr', 'Iceland': 'is',
  'Albania': 'al', 'Greece': 'gr', 'The Netherlands': 'nl', 'Netherlands': 'nl',
  'Lithuania': 'lt', 'Norway': 'no', 'Czechia': 'cz', 'Czech Republic': 'cz',
  'Moldova': 'md', 'Portugal': 'pt', 'Austria': 'at', 'Armenia': 'am',
  'Andorra': 'ad', 'Slovakia': 'sk', 'Turkey': 'tr', 'Slovenia': 'si',
  'Cyprus': 'cy', 'Luxembourg': 'lu', 'Israel': 'il', 'Kosovo': 'xk',
  'Georgia': 'ge', 'Azerbaijan': 'az', 'Sweden': 'se', 'Poland': 'pl',
  'Romania': 'ro', 'Switzerland': 'ch', 'Bosnia and Herzegovina': 'ba',
  'Malta': 'mt', 'Monaco': 'mc', 'Latvia': 'lv', 'Estonia': 'ee',
  'Bulgaria': 'bg', 'Hungary': 'hu', 'Gibraltar': 'gi', 'Germany': 'de',
  'Spain': 'es', 'Italy': 'it'
};

@Component({
  selector: 'app-match-details',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './match-details.html',
  styleUrls: ['./match-details.css']
})
export class MatchDetails implements OnInit {
  match: any;
  isLoading = true;
  historiqueDomicile: any[] = [];
  historiqueExterieur: any[] = [];
  historiquePaysDomicile: any[] = [];
  historiquePaysExterieur: any[] = [];

  constructor(
    private route: ActivatedRoute,
    private sportsApi: SportsApiService
  ) {}

  ngOnInit(): void {
    const matchId = this.route.snapshot.paramMap.get('id');
    
    if (matchId) {
      this.sportsApi.getMatchDetails(matchId).subscribe({
        next: (data) => {
          this.match = data;
          // Une fois le match chargé, on récupère l'historique
          this.chargerHistorique();
        },
        error: (err) => {
          console.error(err);
          this.isLoading = false;
        }
      });
    }
  }

  chargerHistorique(): void {
    this.sportsApi.getHistoriqueQualifications().subscribe({
      next: (historique) => {
        // Filtre pour l'équipe à domicile
        this.historiqueDomicile = historique.filter(m => 
          m.strHomeTeam === this.match.strHomeTeam || m.strAwayTeam === this.match.strHomeTeam
        );
        
        // Filtre pour l'équipe à l'extérieur
        this.historiqueExterieur = historique.filter(m =>
          m.strHomeTeam === this.match.strAwayTeam || m.strAwayTeam === this.match.strAwayTeam
        );

        // Filtre pour les équipes du même pays que l'équipe à domicile (hors historique déjà affiché)
        this.historiquePaysDomicile = !!this.match.strHomeCountry ? historique.filter(m =>
          (m.strHomeCountry === this.match.strHomeCountry || m.strAwayCountry === this.match.strHomeCountry)
          && m.strHomeTeam !== this.match.strHomeTeam && m.strAwayTeam !== this.match.strHomeTeam
        ) : [];

        // Filtre pour les équipes du même pays que l'équipe à l'extérieur (hors historique déjà affiché)
        this.historiquePaysExterieur = !!this.match.strAwayCountry ? historique.filter(m =>
          (m.strHomeCountry === this.match.strAwayCountry || m.strAwayCountry === this.match.strAwayCountry)
          && m.strHomeTeam !== this.match.strAwayTeam && m.strAwayTeam !== this.match.strAwayTeam
        ) : [];

        this.isLoading = false;
      },
      error: (err) => {
        console.error(err);
        this.isLoading = false;
      }
    });
  }

  getFlagUrl(country: string | undefined | null): string | null {
    if (!country) return null;
    const code = COUNTRY_TO_ISO[country];
    return code ? `https://flagcdn.com/w40/${code}.png` : null;
  }

}