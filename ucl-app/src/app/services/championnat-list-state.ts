import { Injectable } from '@angular/core';
import { Match } from '../models/match';

@Injectable({
  providedIn: 'root'
})
export class ChampionnatListState {
  // Liste vide = aucun filtre, tous les championnats sont affichés.
  competitionsSelectionnees: string[] = [];

  // Onglet actif : 'top5' (5 grands championnats), 'g610' (Belgique, Pays-Bas, Portugal,
  // Turquie, Pologne) ou 'g1120' (Tchéquie, Grèce, Norvège, Danemark, Chypre, Suisse,
  // Autriche, Hongrie, Écosse, Suède).
  ongletActif: 'top5' | 'g610' | 'g1120' = 'top5';

  // Matchs déjà chargés une fois : on les garde pour un retour instantané sur la page
  // (sans ça, le contenu se recharge et change de hauteur, ce qui casse la restauration du scroll).
  matches: Match[] = [];
  aDejaCharge = false;
}
