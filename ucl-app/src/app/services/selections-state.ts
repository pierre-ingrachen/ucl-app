import { Injectable } from '@angular/core';
import { Match } from '../models/match';

@Injectable({
  providedIn: 'root'
})
export class SelectionsState {
  // Matchs déjà chargés une fois : on les garde pour un retour instantané sur la page
  // (sans ça, le contenu se recharge et change de hauteur, ce qui casse la restauration du scroll).
  matches: Match[] = [];
  aDejaCharge = false;
}
