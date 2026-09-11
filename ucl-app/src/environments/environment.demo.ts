// Build "démo" (ng build --configuration=demo) : site 100% statique, sans backend.
// SportsApiService lit alors des fichiers JSON figés (public/demo-data/) au lieu d'appeler
// l'API Python — voir README-demo.md.
export const environment = {
  demo: true,
  apiUrl: '', // non utilisé en mode démo
};
