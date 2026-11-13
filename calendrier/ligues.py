"""Table unique des competitions suivies : identifiants TheSportsDB (ceux des journaux et des
historiques locaux), slug ESPN et cles The Odds API. Aucune dependance a `main.py` (qui exige la
cle TheSportsDB) : ce paquet doit tourner sans TheSportsDB."""
from datetime import date

# id TheSportsDB -> infos. `espn` = None : ESPN ne couvre pas cette ligue (verifie le 2026-11-13
# dans le catalogue sports.core.api.espn.com : ni Pologne, ni Suisse, ni Tchequie, ni Chypre, ni
# Hongrie). `odds` = None : The Odds API ne publie rien pour cette ligue.
LIGUES = {
    "4344": {"nom": "Primeira Liga", "pays": "Portugal", "espn": "por.1", "odds": ["soccer_portugal_primeira_liga"]},
    "4337": {"nom": "Eredivisie", "pays": "Pays-Bas", "espn": "ned.1", "odds": ["soccer_netherlands_eredivisie"]},
    "4338": {"nom": "Pro League", "pays": "Belgique", "espn": "bel.1", "odds": ["soccer_belgium_first_div"]},
    "4328": {"nom": "Premier League", "pays": "Angleterre", "espn": "eng.1", "odds": ["soccer_epl"]},
    "4334": {"nom": "Ligue 1", "pays": "France", "espn": "fra.1", "odds": ["soccer_france_ligue_one"]},
    "4335": {"nom": "La Liga", "pays": "Espagne", "espn": "esp.1", "odds": ["soccer_spain_la_liga"]},
    "4332": {"nom": "Serie A", "pays": "Italie", "espn": "ita.1", "odds": ["soccer_italy_serie_a"]},
    "4331": {"nom": "Bundesliga", "pays": "Allemagne", "espn": "ger.1", "odds": ["soccer_germany_bundesliga"]},
    "4339": {"nom": "Süper Lig", "pays": "Turquie", "espn": "tur.1", "odds": ["soccer_turkey_super_league"]},
    "4422": {"nom": "Ekstraklasa", "pays": "Pologne", "espn": None, "odds": ["soccer_poland_ekstraklasa"]},
    "4631": {"nom": "Czech First League", "pays": "Tchéquie", "espn": None, "odds": None},
    "4336": {"nom": "Super League", "pays": "Grèce", "espn": "gre.1", "odds": ["soccer_greece_super_league"]},
    "4358": {"nom": "Eliteserien", "pays": "Norvège", "espn": "nor.1", "odds": ["soccer_norway_eliteserien"], "civile": True},
    "4340": {"nom": "Superliga", "pays": "Danemark", "espn": "den.1", "odds": ["soccer_denmark_superliga"]},
    "4630": {"nom": "First Division", "pays": "Chypre", "espn": None, "odds": None},
    "4675": {"nom": "Super League", "pays": "Suisse", "espn": None, "odds": ["soccer_switzerland_superleague"]},
    "4621": {"nom": "Bundesliga", "pays": "Autriche", "espn": "aut.1", "odds": ["soccer_austria_bundesliga"]},
    "4690": {"nom": "NB I", "pays": "Hongrie", "espn": None, "odds": None},
    "4330": {"nom": "Premiership", "pays": "Écosse", "espn": "sco.1", "odds": ["soccer_spl"]},
    "4347": {"nom": "Allsvenskan", "pays": "Suède", "espn": "swe.1", "odds": ["soccer_sweden_allsvenskan"], "civile": True},
    # Coupes d'Europe
    "4480": {"nom": "UEFA Champions League", "pays": None, "espn": "uefa.champions", "odds": ["soccer_uefa_champs_league"], "europe": True},
    "4481": {"nom": "UEFA Europa League", "pays": None, "espn": "uefa.europa", "odds": ["soccer_uefa_europa_league"], "europe": True},
    "5071": {"nom": "UEFA Conference League", "pays": None, "espn": "uefa.europa.conf",
             "odds": ["soccer_uefa_europa_conference_league"], "europe": True},
}
CHAMPIONNATS = [i for i, l in LIGUES.items() if not l.get("europe")]
COUPES_EUROPE = [i for i, l in LIGUES.items() if l.get("europe")]
ID_PAR_SLUG_ESPN = {l["espn"]: i for i, l in LIGUES.items() if l["espn"]}


def saison(id_ligue, jour):
    """Saison TheSportsDB d'un match joue le `jour` (date ou 'AAAA-MM-JJ') : annee civile pour la
    Norvege et la Suede ("2026"), sinon "AAAA-AAAA" avec bascule en juillet (les tours
    preliminaires europeens de juillet appartiennent deja a la nouvelle saison)."""
    d = jour if isinstance(jour, date) else date.fromisoformat(str(jour)[:10])
    if LIGUES[id_ligue].get("civile"):
        return str(d.year)
    debut = d.year if d.month >= 7 else d.year - 1
    return f"{debut}-{debut + 1}"
