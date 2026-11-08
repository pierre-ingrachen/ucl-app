import { Routes } from '@angular/router';
import { MatchListComponent } from './match-list/match-list';
import { MatchDetails } from './match-details/match-details';
import { Championnats } from './championnats/championnats';
import { Selections } from './selections/selections';
import { SelectionMatch } from './selection-match/selection-match';
import { Bilan } from './bilan/bilan';
import { MesParis } from './mes-paris/mes-paris';

export const routes: Routes = [
    { path: '', component: MatchListComponent },
    { path: 'championnats', component: Championnats },
    { path: 'selections', component: Selections },
    { path: 'selections/:idEvent', component: SelectionMatch },
    { path: 'bilan', component: Bilan },
    { path: 'mes-notes', component: MesParis },
    { path: 'match/:id', component: MatchDetails },
    { path: '**', redirectTo: '' }
];
