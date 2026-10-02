import { RenderMode, ServerRoute } from '@angular/ssr';

export const serverRoutes: ServerRoute[] = [
  {
    // Contenu chargé côté client (via l'API) : pas de prérendu possible pour un id dynamique
    path: 'match/:id',
    renderMode: RenderMode.Client
  },
  {
    // Idem pour la fiche détaillée d'un match de Ligue des Nations.
    path: 'selections/:idEvent',
    renderMode: RenderMode.Client
  },
  {
    path: '**',
    renderMode: RenderMode.Prerender
  }
];
