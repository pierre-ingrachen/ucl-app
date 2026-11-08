import { Injectable } from '@angular/core';

export interface PariManuel {
  idMatch: string;
  equipe: '' | 'home' | 'away';
  cote: number | null;
  coteAttendue: number | null;
  note: string;
  // Copie des infos du match, pour pouvoir lister les paris sans recharger l'API.
  domicile: string;
  exterieur: string;
  badgeDomicile?: string;
  badgeExterieur?: string;
  ligue?: string;
  dateEvent?: string;
  heure?: string;
}

// Les paris saisis à la main restent dans le navigateur (localStorage) : ils ne sont ni
// envoyés au serveur ni dans le dépôt git.
const CLE = 'paris-manuels';

@Injectable({ providedIn: 'root' })
export class ParisManuelsService {
  private lireTout(): Record<string, PariManuel> {
    try {
      return JSON.parse(localStorage.getItem(CLE) || '{}');
    } catch {
      return {};
    }
  }

  get(idMatch: string): PariManuel | null {
    return this.lireTout()[idMatch] ?? null;
  }

  liste(): PariManuel[] {
    return Object.values(this.lireTout()).sort((a, b) =>
      ((a.dateEvent ?? '') + (a.heure ?? '')).localeCompare((b.dateEvent ?? '') + (b.heure ?? ''))
    );
  }

  enregistrer(pari: PariManuel): void {
    const tout = this.lireTout();
    if (!pari.equipe && pari.cote == null && pari.coteAttendue == null && !pari.note.trim()) {
      delete tout[pari.idMatch];
    } else {
      tout[pari.idMatch] = pari;
    }
    try {
      localStorage.setItem(CLE, JSON.stringify(tout));
    } catch { /* stockage indisponible */ }
  }

  supprimer(idMatch: string): void {
    const tout = this.lireTout();
    delete tout[idMatch];
    try {
      localStorage.setItem(CLE, JSON.stringify(tout));
    } catch { /* stockage indisponible */ }
  }
}
