import { Routes } from '@angular/router';
import { MatchListComponent } from './match-list/match-list';
import { MatchDetails } from './match-details/match-details';
import { Championnats } from './championnats/championnats';
import { Bilan } from './bilan/bilan';

export const routes: Routes = [
    { path: '', component: MatchListComponent },
    { path: 'championnats', component: Championnats },
    { path: 'bilan', component: Bilan },
    { path: 'match/:id', component: MatchDetails },
    { path: '**', redirectTo: '' }
];
