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

  modeDomicile: 'club' | 'national' = 'club';
  modeExterieur: 'club' | 'national' = 'club';

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
      next: (historiqueComplet) => {
        // On ne compare le match qu'à des confrontations de la même phase
        // (qualifications / phase de groupe-poule-championnat / phase finale)
        const phaseActuelle = this.getPhase(this.match.intRound, this.match.strEvent, this.match.strFilename);
        const historique = historiqueComplet.filter(m =>
          this.getPhase(m.intRound, m.strEvent, m.strFilename) === phaseActuelle
        );

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

  /** Classe un match dans l'une des 3 phases équivalentes d'une campagne de C1 :
   * qualifications, phase de groupe/poule/championnat, ou phase finale (à partir des 8es). */
  private getPhase(intRound: string | undefined, strEvent?: string, strFilename?: string): 'qualifications' | 'groupe' | 'finale' {
    const eventName = (strEvent || '').toLowerCase();
    const filename = (strFilename || '').toLowerCase();

    if (intRound === '400' || eventName.includes('qual') || filename.includes('qual')) {
      return 'qualifications';
    }

    const r = Number(intRound);
    if (isNaN(r)) return 'qualifications';
    if ([16, 32, 125, 150, 160, 200].includes(r)) return 'finale';
    if (r >= 1 && r <= 15) return 'groupe';
    return 'qualifications';
  }

  getFlagUrl(country: string | undefined | null): string | null {
    if (!country) return null;
    const code = COUNTRY_TO_ISO[country];
    return code ? `https://flagcdn.com/w40/${code}.png` : null;
  }

  get groupedDomicile(): { annee: string; matchs: any[] }[] {
    const source = this.modeDomicile === 'national'
      ? [...this.historiqueDomicile, ...this.historiquePaysDomicile]
      : this.historiqueDomicile;
    return this.groupParAnnee(source);
  }

  get groupedExterieur(): { annee: string; matchs: any[] }[] {
    const source = this.modeExterieur === 'national'
      ? [...this.historiqueExterieur, ...this.historiquePaysExterieur]
      : this.historiqueExterieur;
    return this.groupParAnnee(source);
  }

  private groupParAnnee(matchs: any[]): { annee: string; matchs: any[] }[] {
    const tries = [...matchs].sort((a, b) =>
      new Date(a.dateEvent).getTime() - new Date(b.dateEvent).getTime()
    );

    const groupes = new Map<string, any[]>();
    for (const m of tries) {
      const annee = m.dateEvent ? m.dateEvent.substring(0, 4) : '?';
      if (!groupes.has(annee)) groupes.set(annee, []);
      groupes.get(annee)!.push(m);
    }

    return Array.from(groupes.entries())
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([annee, matchs]) => ({ annee, matchs }));
  }

  getDateJourMois(dateEvent: string | undefined): string {
    if (!dateEvent) return '';
    const d = new Date(dateEvent);
    if (isNaN(d.getTime())) return '';
    const jour = d.getDate().toString().padStart(2, '0');
    const mois = (d.getMonth() + 1).toString().padStart(2, '0');
    return `${jour}/${mois}`;
  }

}