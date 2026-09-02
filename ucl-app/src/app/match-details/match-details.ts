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
  // Historique complet, toutes phases confondues (y compris qualifications) : sert à
  // déterminer si un club a été exempté de qualifications lors d'une campagne passée.
  private historiqueComplet: any[] = [];

  predictionsRevelees = false;

  /** Cote calculee a partir de la probabilite du modele (0.9 / probabilite, marge de
   * 10% comme un bookmaker). Plafonnee pour eviter un affichage a l'infini quand la
   * probabilite est quasi nulle. */
  cote(probabilite: number | undefined | null): string {
    if (!probabilite || probabilite <= 0) return '—';
    return Math.min(0.9 / probabilite, 99).toFixed(2);
  }

  /** Probabilites implicites des cotes du bookmaker (1 / cote, normalisees pour retirer sa
   * marge) : sert a afficher les cotes dans le meme format que les prédictions du modele,
   * pour une comparaison directe. */
  get probasBookmaker(): { domicile: number; nul: number; exterieure: number } | null {
    const d = this.match?.coteDomicile;
    const n = this.match?.coteNul;
    const e = this.match?.coteExterieure;
    if (!d || !n || !e) return null;

    const invD = 1 / d, invN = 1 / n, invE = 1 / e;
    const somme = invD + invN + invE;
    return { domicile: invD / somme, nul: invN / somme, exterieure: invE / somme };
  }

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

  private static readonly DOMESTIC_LEAGUE_IDS = [
    '4344', '4337', '4338', '4328', '4334', '4335', '4332', '4331', '4339', '4422', // Primeira Liga, Eredivisie, Pro League, Premier League, Ligue 1, La Liga, Serie A, Bundesliga, Süper Lig, Ekstraklasa
    '4631', '4336', '4358', '4340', '4630', '4675', '4621', '4690', '4330', '4347', // Tchéquie, Grèce, Norvège, Danemark, Chypre, Suisse, Autriche, Hongrie, Écosse, Suède
  ];

  get estChampionnatNational(): boolean {
    return !!this.match && MatchDetails.DOMESTIC_LEAGUE_IDS.includes(this.match.idLeague);
  }

  classement: any = null;
  isLoadingClassement = false;
  saisonClassementAffichee: 'actuelle' | 'precedente' = 'actuelle';

  ngOnInit(): void {
    const matchId = this.route.snapshot.paramMap.get('id');

    if (matchId) {
      this.sportsApi.getMatchDetails(matchId).subscribe({
        next: (data) => {
          this.match = data;
          if (this.estChampionnatNational) {
            // Le backend a déjà rempli match.historiqueDomicile / historiqueExterieur
            // (5 derniers matchs de championnat) : pas besoin de l'historique des qualifs.
            this.isLoading = false;
            this.chargerClassement();
            return;
          }
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

  chargerClassement(): void {
    this.isLoadingClassement = true;
    this.sportsApi.getClassementChampionnat(this.match.idLeague).subscribe({
      next: (data) => {
        this.classement = data;
        this.isLoadingClassement = false;
      },
      error: (err) => {
        console.error(err);
        this.isLoadingClassement = false;
      }
    });
  }

  get classementAffiche(): any[] {
    if (!this.classement) return [];
    const cle = this.saisonClassementAffichee === 'actuelle' ? 'saisonActuelle' : 'saisonPrecedente';
    return this.classement[cle]?.classement || [];
  }

  get saisonClassementLibelle(): string {
    if (!this.classement) return '';
    const cle = this.saisonClassementAffichee === 'actuelle' ? 'saisonActuelle' : 'saisonPrecedente';
    return this.classement[cle]?.saison || '';
  }

  /** Couleur de la pastille de zone (Ligue des champions, Europa, relégation...) déduite de la
   * description fournie par l'API pour la ligne du classement. */
  couleurZone(description: string | null | undefined): string {
    const d = (description || '').toLowerCase();
    if (d.includes('champions league')) return '#1e3a8a';
    if (d.includes('europa')) return '#ea580c';
    if (d.includes('conference')) return '#16a34a';
    if (d.includes('relegation')) return '#dc2626';
    return 'transparent';
  }

  /** Détermine, pour une ligne d'historique de championnat, si le côté donné (domicile ou
   * extérieur) correspond à l'adversaire de l'équipe suivie (et non à l'équipe suivie elle-même).
   * Comparaison par idTeam (et non par nom) : le nom d'une équipe peut différer d'une saison à
   * l'autre dans les données de l'API (ex : "Porto" vs "FC Porto"). */
  estAdversaire(hist: any, idEquipeSuivie: string, cote: 'home' | 'away'): boolean {
    const idEquipe = cote === 'home' ? hist.idHomeTeam : hist.idAwayTeam;
    return idEquipe !== idEquipeSuivie;
  }

  /** Résultat (Victoire / Nul / Défaite) d'un match d'historique du point de vue de l'équipe suivie. */
  resultatEquipe(hist: any, idEquipeSuivie: string): 'V' | 'N' | 'D' | null {
    const estDomicile = hist.idHomeTeam === idEquipeSuivie;
    const estExterieur = hist.idAwayTeam === idEquipeSuivie;
    if (!estDomicile && !estExterieur) return null;

    const scoreEquipe = estDomicile ? hist.intHomeScore : hist.intAwayScore;
    const scoreAdversaire = estDomicile ? hist.intAwayScore : hist.intHomeScore;
    if (scoreEquipe === null || scoreEquipe === undefined || scoreAdversaire === null || scoreAdversaire === undefined) {
      return null;
    }

    if (Number(scoreEquipe) > Number(scoreAdversaire)) return 'V';
    if (Number(scoreEquipe) < Number(scoreAdversaire)) return 'D';
    return 'N';
  }

  private static readonly COULEUR_RESULTAT: { [key: string]: string } = {
    'V': '#16a34a',
    'N': '#9ca3af',
    'D': '#dc2626'
  };

  couleurResultat(resultat: 'V' | 'N' | 'D' | null): string {
    return resultat ? MatchDetails.COULEUR_RESULTAT[resultat] : '#ccc';
  }

  chargerHistorique(): void {
    this.sportsApi.getHistoriqueQualifications().subscribe({
      next: (historiqueComplet) => {
        this.historiqueComplet = historiqueComplet;
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
  // On compare par idTeam (et non par nom) : le nom d'un club peut différer d'une saison à
  // l'autre dans les données de l'API (ex : "Porto" vs "FC Porto"), ce qui faisait manquer
  // des matchs de l'historique si on comparait par nom.
  get historiqueDomicile(): any[] {
    return this.historiqueMemePhase.filter(m =>
      m.idHomeTeam === this.match.idHomeTeam || m.idAwayTeam === this.match.idHomeTeam
    );
  }

  get historiqueExterieur(): any[] {
    return this.historiqueMemePhase.filter(m =>
      m.idHomeTeam === this.match.idAwayTeam || m.idAwayTeam === this.match.idAwayTeam
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

  get groupedDomicile(): { annee: string; equipes: { nom: string; idEquipe: string; matchs: any[] }[]; directes: string[] }[] {
    const idEquipe = this.match?.idHomeTeam;
    if (this.modeDomicile === 'national') {
      // "Qualifié directement" ne concerne que les parcours de club en coupe d'Europe :
      // ce libellé n'a pas de sens pour une sélection nationale, on ne le fusionne donc pas ici.
      return this.fusionnerAvecDirectes(
        this.grouperNational(idEquipe, this.match.strHomeCountry, this.filtreNationalDomicile),
        new Map()
      );
    }
    // Mode club : toutes compétitions confondues, on précise donc dans quelle compétition
    // se déroulait chaque partie du parcours.
    const competitionMatchAffiche = this.nomCompetitionCanonique(this.match.strLeague);
    return this.fusionnerAvecDirectes(
      this.grouperParAnnee(
        this.historiqueDomicile, m => this.nomCompetitionCanonique(m.strLeague),
        m => this.nomCompetitionCanonique(m.strLeague) === competitionMatchAffiche, () => idEquipe,
        nom => this.rangCompetition(nom)
      ),
      this.campagnesDirectesParAnnee(idEquipe)
    );
  }

  get groupedExterieur(): { annee: string; equipes: { nom: string; idEquipe: string; matchs: any[] }[]; directes: string[] }[] {
    const idEquipe = this.match?.idAwayTeam;
    if (this.modeExterieur === 'national') {
      // "Qualifié directement" ne concerne que les parcours de club en coupe d'Europe :
      // ce libellé n'a pas de sens pour une sélection nationale, on ne le fusionne donc pas ici.
      return this.fusionnerAvecDirectes(
        this.grouperNational(idEquipe, this.match.strAwayCountry, this.filtreNationalExterieur),
        new Map()
      );
    }
    const competitionMatchAffiche = this.nomCompetitionCanonique(this.match.strLeague);
    return this.fusionnerAvecDirectes(
      this.grouperParAnnee(
        this.historiqueExterieur, m => this.nomCompetitionCanonique(m.strLeague),
        m => this.nomCompetitionCanonique(m.strLeague) === competitionMatchAffiche, () => idEquipe,
        nom => this.rangCompetition(nom)
      ),
      this.campagnesDirectesParAnnee(idEquipe)
    );
  }

  /** Nom affiche pour une competition europeenne, normalise entre les variantes utilisees
   * selon la saison par TheSportsDB (ex: la Conference League s'appelait "UEFA Conference
   * League" avant le rebranding UEFA en "UEFA Europa Conference League") : sans ca, les matchs
   * d'une meme competition se retrouvent scindes en deux groupes distincts dans l'historique. */
  private nomCompetitionCanonique(nom: string | undefined): string {
    const alias: { [nom: string]: string } = {
      'UEFA Conference League': 'UEFA Europa Conference League',
    };
    const brut = nom || 'Compétition inconnue';
    return alias[brut] || brut;
  }

  /** Ordre d'affichage fixe des competitions europeennes dans l'historique club (Champions
   * League, puis Europa League, puis Conference League), independant de la chronologie : une
   * equipe reversee de C1 en C3 la meme annee civile doit quand meme apparaitre C1 avant C3.
   * Attend un nom deja normalise via `nomCompetitionCanonique`. */
  private rangCompetition(nomCompetition: string): number {
    const rangs: { [nom: string]: number } = {
      'UEFA Champions League': 0,
      'UEFA Europa League': 1,
      'UEFA Europa Conference League': 2,
    };
    return rangs[nomCompetition] ?? 99;
  }

  /** Historique national : l'équipe suivie ET les autres équipes du pays sont puisées dans
   * la MÊME source (restreinte à la compétition du match, ou toutes selon le bouton choisi) —
   * sinon l'équipe suivie affichait ses matchs toutes compétitions confondues même en mode
   * "compétition du match". On identifie l'équipe suivie par idTeam (et non par nom) : son nom
   * peut différer d'une saison à l'autre dans les données de l'API. */
  private grouperNational(
    idEquipeRef: string,
    paysRef: string | null | undefined,
    filtre: 'match' | 'toutes'
  ): { annee: string; equipes: { nom: string; idEquipe: string; matchs: any[] }[] }[] {
    const source = filtre === 'toutes' ? this.historiqueMemePhase : this.historiqueMemePhaseMemeCompetition;

    const matchsEquipe = source.filter(m =>
      m.idHomeTeam === idEquipeRef || m.idAwayTeam === idEquipeRef
    );
    const matchsAutresEquipesDuPays = paysRef ? source.filter(m =>
      (m.strHomeCountry === paysRef || m.strAwayCountry === paysRef)
      && m.idHomeTeam !== idEquipeRef && m.idAwayTeam !== idEquipeRef
    ) : [];

    return this.grouperParAnnee(
      [...matchsEquipe, ...matchsAutresEquipesDuPays],
      m => this.getEquipeConcernee(m, idEquipeRef, paysRef),
      m => m.idHomeTeam === idEquipeRef || m.idAwayTeam === idEquipeRef,
      m => this.getIdEquipeConcernee(m, idEquipeRef, paysRef)
    );
  }

  /** Détermine, pour un match d'historique, quelle équipe est "concernée"
   * (l'équipe du club suivi, ou l'équipe du pays en mode national). Le nom affiché est
   * celui du match lui-même, donc toujours celui utilisé par l'API pour cette saison-là. */
  private getEquipeConcernee(hist: any, idEquipeRef: string, paysRef: string | null | undefined): string {
    if (hist.idHomeTeam === idEquipeRef) return hist.strHomeTeam;
    if (hist.idAwayTeam === idEquipeRef) return hist.strAwayTeam;
    if (paysRef) {
      if (hist.strHomeCountry === paysRef) return hist.strHomeTeam;
      if (hist.strAwayCountry === paysRef) return hist.strAwayTeam;
    }
    return hist.strHomeTeam;
  }

  /** Équivalent de `getEquipeConcernee` mais retourne l'idTeam au lieu du nom : sert à
   * identifier la campagne (année + compétition + équipe) pour laquelle on cherche à savoir
   * si l'équipe est passée par les qualifications. */
  private getIdEquipeConcernee(hist: any, idEquipeRef: string, paysRef: string | null | undefined): string {
    if (hist.idHomeTeam === idEquipeRef) return idEquipeRef;
    if (hist.idAwayTeam === idEquipeRef) return idEquipeRef;
    if (paysRef) {
      if (hist.strHomeCountry === paysRef) return hist.idHomeTeam;
      if (hist.strAwayCountry === paysRef) return hist.idAwayTeam;
    }
    return hist.idHomeTeam;
  }

  /** Pour l'équipe donnée, liste par année (la même étiquette d'année que celle utilisée pour
   * grouper les matchs affichés, ex: "2025") les compétitions où elle s'est qualifiée
   * directement, sans passer par les tours préliminaires. On se base sur l'historique COMPLET,
   * toutes phases confondues (contrairement à `historiqueDomicile`/`historiqueExterieur`, qui
   * ne retiennent que les matchs de la même phase que le match affiché — une campagne sans
   * qualifications peut donc être totalement absente de ces listes si le match affiché est
   * lui-même un match de qualifications). Les campagnes sont regroupées par `strSeason`
   * (ex: "2025-2026") car une même campagne s'étale sur deux années civiles (qualifs/poules à
   * l'été-automne, phase finale l'année suivante) : grouper par année civile romprait
   * artificiellement une campagne démarrée en qualifications en deux entrées distinctes. Une
   * fois la campagne validée comme "directe" (au moins un match de phase de groupe/finale cette
   * saison, aucun match de qualifications), on l'étiquette avec l'année civile de son premier
   * match hors qualifications, pour qu'elle s'insère à la bonne place chronologique dans la
   * liste des années affichées.
   *
   * L'absence de qualifications s'apprécie saison par saison, TOUTES compétitions confondues
   * (et non compétition par compétition) : une équipe éliminée en qualifications de C1 peut
   * être repêchée directement en poules de C3 la même saison sans y disputer le moindre match
   * de qualifications — elle n'est pourtant pas passée "directement", puisqu'elle a bien joué
   * des qualifications (celles de C1) cette saison-là. */
  private campagnesDirectesParAnnee(idEquipe: string | undefined): Map<string, string[]> {
    const resultat = new Map<string, string[]>();
    if (!idEquipe) return resultat;

    const saisonsAvecQualifs = new Set<string>();
    for (const m of this.historiqueComplet) {
      if (m.idHomeTeam !== idEquipe && m.idAwayTeam !== idEquipe) continue;
      if (m.strPhase !== 'qualifications') continue;
      const saison = m.strSeason || (m.dateEvent ? m.dateEvent.substring(0, 4) : null);
      if (saison) saisonsAvecQualifs.add(saison);
    }

    const parCampagne = new Map<string, { competition: string; saison: string; anneeAffichee: string | null; aJoueGroupe: boolean }>();
    for (const m of this.historiqueComplet) {
      if (m.idHomeTeam !== idEquipe && m.idAwayTeam !== idEquipe) continue;
      if (m.strPhase === 'qualifications') continue;
      const saison = m.strSeason || (m.dateEvent ? m.dateEvent.substring(0, 4) : null);
      if (!saison) continue;
      const clef = `${m.idLeague}-${saison}`;
      if (!parCampagne.has(clef)) {
        parCampagne.set(clef, { competition: m.strLeague || '', saison, anneeAffichee: null, aJoueGroupe: false });
      }
      const entree = parCampagne.get(clef)!;
      entree.aJoueGroupe = true;
      const annee = m.dateEvent ? m.dateEvent.substring(0, 4) : null;
      if (annee && (!entree.anneeAffichee || annee < entree.anneeAffichee)) {
        entree.anneeAffichee = annee;
      }
    }

    for (const c of parCampagne.values()) {
      if (c.aJoueGroupe && c.anneeAffichee && !saisonsAvecQualifs.has(c.saison)) {
        const liste = resultat.get(c.anneeAffichee) || [];
        if (!liste.includes(c.competition)) liste.push(c.competition);
        resultat.set(c.anneeAffichee, liste);
      }
    }
    return resultat;
  }

  /** Fusionne les groupes par année (matchs réels) avec les campagnes qualifiées directement :
   * ces dernières sont insérées à leur place chronologique, sous forme d'une année sans match
   * si elle est absente des groupes existants (cas d'un match de qualifications affiché : la
   * campagne sans qualifs de l'année précédente n'a alors aucun match de la même phase à
   * montrer), ou ajoutées à l'année existante sinon. */
  private fusionnerAvecDirectes(
    groupes: { annee: string; equipes: { nom: string; idEquipe: string; matchs: any[] }[] }[],
    directesParAnnee: Map<string, string[]>
  ): { annee: string; equipes: { nom: string; idEquipe: string; matchs: any[] }[]; directes: string[] }[] {
    const parAnnee = new Map<string, { annee: string; equipes: { nom: string; idEquipe: string; matchs: any[] }[]; directes: string[] }>();

    for (const g of groupes) {
      parAnnee.set(g.annee, { annee: g.annee, equipes: g.equipes, directes: directesParAnnee.get(g.annee) || [] });
    }
    for (const [annee, competitions] of directesParAnnee.entries()) {
      if (!parAnnee.has(annee)) {
        parAnnee.set(annee, { annee, equipes: [], directes: competitions });
      }
    }

    return Array.from(parAnnee.values()).sort((a, b) => b.annee.localeCompare(a.annee));
  }

  /** Groupe une liste de matchs par année (la plus récente d'abord), puis par sous-clé
   * (équipe concernée en mode national, compétition en mode club). Le sous-groupe prioritaire
   * (équipe suivie / compétition du match affiché) est toujours affiché en premier : déterminé
   * via `estPrioritaire` plutôt qu'une comparaison de nom, qui peut différer d'une saison à
   * l'autre (mode national). */
  private grouperParAnnee(
    matchs: any[],
    resolverClef: (hist: any) => string,
    estPrioritaire: (hist: any) => boolean,
    resolverId: (hist: any) => string,
    resolverRang?: (clef: string) => number
  ): { annee: string; equipes: { nom: string; idEquipe: string; matchs: any[] }[] }[] {
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
        // Si un ordre fixe est fourni (mode club : Champions League puis Europa League puis
        // Conference League), il prime toujours sur la chronologie — une équipe reversée de C1
        // en C3 la même année civile doit quand même afficher C1 avant C3. Sans ordre fixe
        // (mode national : équipes du pays), le groupe prioritaire est remonté en tête et le
        // reste garde l'ordre chronologique d'apparition dans `sousGroupes` (tri stable, cf. le
        // tri de `tries` en début de fonction) plutôt qu'un tri alphabétique.
        equipes: Array.from(sousGroupes.entries())
          .sort((a, b) => {
            if (resolverRang) {
              const diff = resolverRang(a[0]) - resolverRang(b[0]);
              if (diff !== 0) return diff;
            }
            const aPrioritaire = a[1].some(estPrioritaire);
            const bPrioritaire = b[1].some(estPrioritaire);
            return aPrioritaire === bPrioritaire ? 0 : (aPrioritaire ? -1 : 1);
          })
          .map(([nom, matchs]) => ({ nom, idEquipe: resolverId(matchs[0]), matchs }))
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