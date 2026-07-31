import { Component, OnInit } from '@angular/core';
import { CommonModule, Location } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
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
  imports: [CommonModule],
  templateUrl: './match-details.html',
  styleUrls: ['./match-details.css']
})
export class MatchDetails implements OnInit {
  match: any;
  isLoading = true;

  // Historique de toutes les compétitions confondues (mais restreint à la même phase
  // équivalente que le match affiché) : sert de base au mode "club" et au mode "national"
  // quand on choisit "toutes compétitions".
  private historiqueMemePhase: any[] = [];
  // Sous-ensemble ci-dessus, restreint à la compétition du match affiché : sert de base
  // au mode "national" quand on choisit "compétition du match".
  private historiqueMemePhaseMemeCompetition: any[] = [];

  modeDomicile: 'club' | 'national' = 'club';
  modeExterieur: 'club' | 'national' = 'club';

  // Uniquement pertinent en mode "national" : périmètre des compétitions comparées.
  filtreNationalDomicile: 'match' | 'toutes' = 'match';
  filtreNationalExterieur: 'match' | 'toutes' = 'match';

  constructor(
    private route: ActivatedRoute,
    private sportsApi: SportsApiService,
    private location: Location
  ) {}

  retourAuxMatchs(): void {
    this.location.back();
  }

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
        // On ne compare le match qu'à des confrontations de la même phase équivalente
        // (qualifications / phase de groupe-poule-championnat / phase finale)
        const phaseActuelle = this.getPhase(this.match.intRound, this.match.strEvent, this.match.strFilename);
        this.historiqueMemePhase = historiqueComplet.filter(m =>
          this.getPhase(m.intRound, m.strEvent, m.strFilename) === phaseActuelle
        );
        this.historiqueMemePhaseMemeCompetition = this.historiqueMemePhase.filter(m =>
          m.idLeague === this.match.idLeague
        );

        this.isLoading = false;
      },
      error: (err) => {
        console.error(err);
        this.isLoading = false;
      }
    });
  }

  // Historique club : toutes compétitions confondues, même phase équivalente.
  get historiqueDomicile(): any[] {
    return this.historiqueMemePhase.filter(m =>
      m.strHomeTeam === this.match.strHomeTeam || m.strAwayTeam === this.match.strHomeTeam
    );
  }

  get historiqueExterieur(): any[] {
    return this.historiqueMemePhase.filter(m =>
      m.strHomeTeam === this.match.strAwayTeam || m.strAwayTeam === this.match.strAwayTeam
    );
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

  private static readonly ABREGE_COMPETITION: { [idLeague: string]: string } = {
    '4480': 'UCL',
    '4481': 'UEL',
    '5071': 'UECL'
  };

  getAbregeCompetition(hist: any): string {
    return MatchDetails.ABREGE_COMPETITION[hist.idLeague] || hist.strLeague || '';
  }

  get groupedDomicile(): { annee: string; equipes: { nom: string; matchs: any[] }[] }[] {
    if (this.modeDomicile === 'national') {
      return this.grouperNational(this.match.strHomeTeam, this.match.strHomeCountry, this.filtreNationalDomicile);
    }
    // Mode club : toutes compétitions confondues, on précise donc dans quelle compétition
    // se déroulait chaque partie du parcours.
    return this.grouperParAnnee(this.historiqueDomicile, m => m.strLeague || 'Compétition inconnue', this.match.strLeague);
  }

  get groupedExterieur(): { annee: string; equipes: { nom: string; matchs: any[] }[] }[] {
    if (this.modeExterieur === 'national') {
      return this.grouperNational(this.match.strAwayTeam, this.match.strAwayCountry, this.filtreNationalExterieur);
    }
    return this.grouperParAnnee(this.historiqueExterieur, m => m.strLeague || 'Compétition inconnue', this.match.strLeague);
  }

  /** Historique national : l'équipe suivie ET les autres équipes du pays sont puisées dans
   * la MÊME source (restreinte à la compétition du match, ou toutes selon le bouton choisi) —
   * sinon l'équipe suivie affichait ses matchs toutes compétitions confondues même en mode
   * "compétition du match". */
  private grouperNational(
    equipeRef: string,
    paysRef: string | null | undefined,
    filtre: 'match' | 'toutes'
  ): { annee: string; equipes: { nom: string; matchs: any[] }[] }[] {
    const source = filtre === 'toutes' ? this.historiqueMemePhase : this.historiqueMemePhaseMemeCompetition;

    const matchsEquipe = source.filter(m =>
      m.strHomeTeam === equipeRef || m.strAwayTeam === equipeRef
    );
    const matchsAutresEquipesDuPays = paysRef ? source.filter(m =>
      (m.strHomeCountry === paysRef || m.strAwayCountry === paysRef)
      && m.strHomeTeam !== equipeRef && m.strAwayTeam !== equipeRef
    ) : [];

    return this.grouperParAnnee(
      [...matchsEquipe, ...matchsAutresEquipesDuPays],
      m => this.getEquipeConcernee(m, equipeRef, paysRef),
      equipeRef
    );
  }

  /** Détermine, pour un match d'historique, quelle équipe est "concernée"
   * (l'équipe du club suivi, ou l'équipe du pays en mode national). */
  private getEquipeConcernee(hist: any, equipeRef: string, paysRef: string | null | undefined): string {
    if (hist.strHomeTeam === equipeRef || hist.strAwayTeam === equipeRef) return equipeRef;
    if (paysRef) {
      if (hist.strHomeCountry === paysRef) return hist.strHomeTeam;
      if (hist.strAwayCountry === paysRef) return hist.strAwayTeam;
    }
    return hist.strHomeTeam;
  }

  /** Groupe une liste de matchs par année (la plus récente d'abord), puis par sous-clé
   * (équipe concernée en mode national, compétition en mode club). La sous-clé prioritaire
   * (équipe suivie / compétition du match affiché) est toujours affichée en premier. */
  private grouperParAnnee(
    matchs: any[],
    resolverClef: (hist: any) => string,
    clefPrioritaire: string
  ): { annee: string; equipes: { nom: string; matchs: any[] }[] }[] {
    const tries = [...matchs].sort((a, b) =>
      new Date(a.dateEvent).getTime() - new Date(b.dateEvent).getTime()
    );

    const groupesAnnee = new Map<string, Map<string, any[]>>();
    for (const m of tries) {
      const annee = m.dateEvent ? m.dateEvent.substring(0, 4) : '?';
      const clef = resolverClef(m);
      if (!groupesAnnee.has(annee)) groupesAnnee.set(annee, new Map<string, any[]>());
      const sousGroupes = groupesAnnee.get(annee)!;
      if (!sousGroupes.has(clef)) sousGroupes.set(clef, []);
      sousGroupes.get(clef)!.push(m);
    }

    return Array.from(groupesAnnee.entries())
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([annee, sousGroupes]) => ({
        annee,
        equipes: Array.from(sousGroupes.entries())
          .sort((a, b) => (a[0] === clefPrioritaire ? -1 : b[0] === clefPrioritaire ? 1 : a[0].localeCompare(b[0])))
          .map(([nom, matchs]) => ({ nom, matchs }))
      }));
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