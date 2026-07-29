import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class ConnectiviteService {
  // navigator n'existe pas côté serveur (SSR) : on suppose "en ligne" dans ce cas.
  horsLigne = signal(typeof navigator !== 'undefined' ? !navigator.onLine : false);

  constructor() {
    if (typeof window === 'undefined') return;
    window.addEventListener('online', () => this.horsLigne.set(false));
    window.addEventListener('offline', () => this.horsLigne.set(true));
  }
}
