import { Injectable } from '@angular/core';
import { Match } from '../models/match';

@Injectable({
  providedIn: 'root'
})
export class MatchListState {
  competitionSelectionnee: 'toutes' | '4480' | '4481' | '5071' = 'toutes';

  // Ne garder que les matchs avec une cote élevée sur une victoire (équipe 1 ou 2).
  coteElevee = false;

  // Matchs déjà chargés une fois : on les garde pour un retour instantané sur la page
  // (sans ça, le contenu se recharge et change de hauteur, ce qui casse la restauration du scroll).
  matches: Match[] = [];
  aDejaCharge = false;
}
