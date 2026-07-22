import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class MatchListState {
  competitionSelectionnee: 'toutes' | '4480' | '5071' = 'toutes';
}
