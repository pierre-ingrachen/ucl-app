import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { map, Observable } from 'rxjs';
import { Match, ApiResponse } from '../models/match';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class SportsApiService {
  private apiUrl = `${environment.apiUrl}/api/matchs/a-venir`;

  constructor(private http: HttpClient) {}

  /** Résout un chemin de fichier JSON démo (public/demo-data/...) en URL absolue via le
   * <base href> de la page : indispensable pour fonctionner sous un sous-chemin (GitHub
   * Pages de projet, ex. /mon-repo/) et depuis une route imbriquée (/match/:id). */
  private demoUrl(path: string): string {
    if (typeof document !== 'undefined') {
      return new URL(path, document.baseURI).href;
    }
    return path;
  }

  getUpcomingMatches(): Observable<Match[]> {
    const source = environment.demo
      ? this.http.get<ApiResponse>(this.demoUrl('demo-data/matchs-a-venir.json'))
      : this.http.get<ApiResponse>(this.apiUrl);
    return source.pipe(map(response => this.trierMatchsAVenir(response.events)));
  }

  getUpcomingChampionnatMatches(): Observable<Match[]> {
    const source = environment.demo
      ? this.http.get<ApiResponse>(this.demoUrl('demo-data/championnats-a-venir.json'))
      : this.http.get<ApiResponse>(`${environment.apiUrl}/api/championnats/matchs/a-venir`);
    return source.pipe(map(response => this.trierMatchsAVenir(response.events)));
  }

  getClassementChampionnat(idLigue: string): Observable<any> {
    if (environment.demo) {
      return this.http.get<any>(this.demoUrl(`demo-data/classements/${idLigue}.json`));
    }
    return this.http.get<any>(`${environment.apiUrl}/api/championnats/classement/${idLigue}`);
  }

  /** Classement de la phase de ligue d'une compétition européenne (C1 / C3 / C4). */
  getClassementCompetition(idLigue: string): Observable<any> {
    if (environment.demo) {
      return this.http.get<any>(this.demoUrl(`demo-data/classements/${idLigue}.json`));
    }
    return this.http.get<any>(`${environment.apiUrl}/api/competitions/classement/${idLigue}`);
  }

  private trierMatchsAVenir(events: Match[] | undefined): Match[] {
    if (!events) return [];

    // Mode démo : les matchs sont un instantané figé (certains déjà joués au moment de la
    // consultation) — on les affiche tous plutôt que de les filtrer sur la date du jour.
    let candidats = events;
    if (!environment.demo) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      const nextWeek = new Date(today);
      nextWeek.setDate(today.getDate() + 7);

      candidats = events.filter(match => {
        if (!match.dateEvent) return false;
        const matchDate = new Date(match.dateEvent);
        return matchDate >= today && matchDate <= nextWeek;
      });
    }

    return candidats
      .map(match => {
        const timeString = match.strTime ? match.strTime : '00:00:00';
        match.localDateTime = new Date(`${match.dateEvent}T${timeString}Z`);

        return match;
      })
      .sort((a, b) => {
        if (a.localDateTime && b.localDateTime) {
          return a.localDateTime.getTime() - b.localDateTime.getTime();
        }
        return 0;
      });
  }

  getMatchDetails(id: string): Observable<any> {
    if (environment.demo) {
      return this.http.get<any>(this.demoUrl(`demo-data/matches/${id}.json`));
    }
    return this.http.get<any>(`${environment.apiUrl}/api/match/${id}`);
  }

  getHistoriqueQualifications(): Observable<any[]> {
    const source = environment.demo
      ? this.http.get<any>(this.demoUrl('demo-data/historique-qualifs.json'))
      : this.http.get<any>(`${environment.apiUrl}/api/matchs/historique-qualifications`);
    return source.pipe(map(response => response.events || []));
  }

  /** Journal des paris d'un modèle : 'rating' (défaut), 'ml' ou 'ensemble'. */
  getParis(modele: 'rating' | 'ml' | 'ensemble' = 'rating'): Observable<{ paris: any[]; matchsAnalyses: number }> {
    const source = environment.demo
      ? this.http.get<any>(this.demoUrl(`demo-data/paris-${modele}.json`))
      : this.http.get<any>(`${environment.apiUrl}/api/paris?modele=${modele}`);
    return source.pipe(
      map(response => ({
        paris: response.paris || [],
        matchsAnalyses: response.matchsAnalyses || 0,
      }))
    );
  }
}
