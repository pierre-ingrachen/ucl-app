import { Routes } from '@angular/router';
import { MatchListComponent } from './match-list/match-list';
import { MatchDetails } from './match-details/match-details';

export const routes: Routes = [
    { path: '', component: MatchListComponent },
    { path: 'match/:id', component: MatchDetails },
    { path: '**', redirectTo: '' }
];
