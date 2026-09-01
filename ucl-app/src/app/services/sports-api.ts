import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { map, Observable } from 'rxjs';
import { Match, ApiResponse } from '../models/match';

@Injectable({
  providedIn: 'root'
})
export class SportsApiService {
  // On pointe désormais vers notre propre API Python locale !
  private apiUrl = 'http://localhost:8000/api/matchs/a-venir';

  constructor(private http: HttpClient) {}

  getUpcomingMatches(): Observable<Match[]> {
    return this.http.get<ApiResponse>(this.apiUrl).pipe(
      map(response => this.trierMatchsAVenir(response.events))
    );
  }

  getUpcomingChampionnatMatches(): Observable<Match[]> {
    return this.http.get<ApiResponse>('http://localhost:8000/api/championnats/matchs/a-venir').pipe(
      map(response => this.trierMatchsAVenir(response.events))
    );
  }

  getClassementChampionnat(idLigue: string): Observable<any> {
    return this.http.get<any>(`http://localhost:8000/api/championnats/classement/${idLigue}`);
  }

  private trierMatchsAVenir(events: Match[] | undefined): Match[] {
    if (!events) return [];

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const nextWeek = new Date(today);
    nextWeek.setDate(today.getDate() + 7);

    return events
      .filter(match => {
        if (!match.dateEvent) return false;
        const matchDate = new Date(match.dateEvent);
        return matchDate >= today && matchDate <= nextWeek;
      })
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
    return this.http.get<any>(`http://localhost:8000/api/match/${id}`);
  }

  getHistoriqueQualifications(): Observable<any[]> {
    return this.http.get<any>('http://localhost:8000/api/matchs/historique-qualifications').pipe(
      map(response => response.events || [])
    );
  }

  getParis(): Observable<any[]> {
    return this.http.get<any>('http://localhost:8000/api/paris').pipe(
      map(response => response.paris || [])
    );
  }
}