import { Routes } from '@angular/router';
import { MatchListComponent } from './match-list/match-list';
import { MatchDetails } from './match-details/match-details';
import { Championnats } from './championnats/championnats';
import { Bilan } from './bilan/bilan';
import { MesParis } from './mes-paris/mes-paris';

export const routes: Routes = [
    { path: '', component: MatchListComponent },
    { path: 'championnats', component: Championnats },
    { path: 'bilan', component: Bilan },
    { path: 'mes-notes', component: MesParis },
    { path: 'match/:id', component: MatchDetails },
    { path: '**', redirectTo: '' }
];
