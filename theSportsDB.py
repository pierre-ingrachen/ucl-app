import requests
from datetime import datetime, timedelta

# 1. Paramètres de l'API
API_KEY = "REDACTED_SPORTSDB_API_KEY" 
LEAGUE_ID = "4480"
SEASON = "2026-2027"

url = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsseason.php?id={LEAGUE_ID}&s={SEASON}"

aujourd_hui = datetime.now()
dans_7_jours = aujourd_hui + timedelta(days=7)

print("Récupération des données...")
response = requests.get(url)

if response.status_code == 200:
    matchs = response.json().get("events", [])
    matchs_a_venir = []
    
    # Filtrage des matchs sur 7 jours
    for match in matchs:
        date_str = match.get("dateEvent")
        if date_str:
            try:
                date_match = datetime.strptime(date_str, "%Y-%m-%d")
                if aujourd_hui.date() <= date_match.date() <= dans_7_jours.date():
                    matchs_a_venir.append(match)
            except ValueError:
                pass

    print(f"Génération de la page web pour {len(matchs_a_venir)} match(s)...")

    # 2. Début du code HTML & CSS
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Matchs de Ligue des Champions</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f4f7f6;
                color: #333;
                margin: 0;
                padding: 20px;
            }
            h1 {
                text-align: center;
                color: #0c1c38; /* Bleu Ligue des Champions */
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            .match-card {
                background: white;
                border-radius: 10px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                margin-bottom: 20px;
                padding: 20px;
                text-align: center;
                transition: transform 0.2s;
            }
            .match-card:hover {
                transform: translateY(-5px);
            }
            .date-time {
                font-size: 0.9em;
                color: #777;
                margin-bottom: 15px;
                font-weight: bold;
            }
            .teams {
                display: flex;
                justify-content: space-around;
                align-items: center;
            }
            .team {
                width: 40%;
            }
            .team img {
                width: 80px;
                height: 80px;
                object-fit: contain;
                margin-bottom: 10px;
            }
            .team-name {
                font-size: 1.1em;
                font-weight: bold;
                display: block;
            }
            .vs {
                font-size: 1.5em;
                font-weight: bold;
                color: #ccc;
                width: 20%;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏆 Prochains Matchs - Ligue des Champions</h1>
    """

    # 3. Boucle pour injecter chaque match dans le HTML
    if not matchs_a_venir:
        html_content += "<p style='text-align:center;'>Aucun match prévu dans les 7 prochains jours.</p>"
    else:
        for match in matchs_a_venir:
            equipe_domicile = match.get("strHomeTeam", "Équipe Inconnue")
            equipe_exterieur = match.get("strAwayTeam", "Équipe Inconnue")
            date = match.get("dateEvent", "")
            heure = match.get("strTime", "Heure à définir")[:5] # Garde juste HH:MM
            
            # Récupération des logos (ou logo par défaut si absent)
            logo_domicile = match.get("strHomeTeamBadge", "https://via.placeholder.com/80?text=Logo")
            logo_exterieur = match.get("strAwayTeamBadge", "https://via.placeholder.com/80?text=Logo")

            html_content += f"""
            <div class="match-card">
                <div class="date-time">{date} - {heure}</div>
                <div class="teams">
                    <div class="team">
                        <img src="{logo_domicile}" alt="Logo {equipe_domicile}">
                        <span class="team-name">{equipe_domicile}</span>
                    </div>
                    <div class="vs">VS</div>
                    <div class="team">
                        <img src="{logo_exterieur}" alt="Logo {equipe_exterieur}">
                        <span class="team-name">{equipe_exterieur}</span>
                    </div>
                </div>
            </div>
            """

    # 4. Fermeture des balises HTML
    html_content += """
        </div>
    </body>
    </html>
    """

    # 5. Création et écriture du fichier HTML
    with open("matchs_ldc.html", "w", encoding="utf-8") as file:
        file.write(html_content)
        
    print("✅ Terminé ! Ouvrez le fichier 'matchs_ldc.html' dans votre navigateur.")

else:
    print(f"❌ Erreur HTTP {response.status_code}.")