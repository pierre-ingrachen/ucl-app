#!/bin/bash
set -e

ROOT="/Users/pierre/Documents/F/UCL"
export PATH="/opt/homebrew/bin:$PATH"
export NG_CLI_ANALYTICS=false

cd "$ROOT"

echo "Recuperation des dernieres mises a jour (git pull)..."
if ! git pull; then
    echo "Attention : la mise a jour Git a echoue (pas de connexion, modifications locales en conflit, etc.)."
    echo "Demarrage avec les fichiers actuels."
fi

# Libere les ports au cas ou un lancement precedent ne se serait pas arrete
# proprement (fermeture brutale du Terminal, veille, etc.).
for port in 8000 4200; do
    lsof -ti tcp:"$port" 2>/dev/null | xargs kill -TERM 2>/dev/null || true
done

echo "Demarrage du backend (FastAPI)..."
(cd "$ROOT" && "$ROOT/.venv/bin/python" -m uvicorn main:app --reload) &
BACKEND_PID=$!

echo "Demarrage du frontend (Angular)..."
(cd "$ROOT/ucl-app" && ./node_modules/.bin/ng serve) &
FRONTEND_PID=$!

CLEANED=0
cleanup() {
    [ "$CLEANED" = "1" ] && return
    CLEANED=1
    echo ""
    echo "Arret des serveurs..."
    # Tue les processus lances ainsi que leurs enfants (uvicorn --reload,
    # ng serve / esbuild, etc.).
    for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
        pkill -TERM -P "$pid" 2>/dev/null || true
        kill -TERM "$pid" 2>/dev/null || true
    done
    # Filet de securite : libere les ports au cas ou des enfants survivraient.
    for port in 8000 4200; do
        lsof -ti tcp:"$port" 2>/dev/null | xargs kill -TERM 2>/dev/null || true
    done
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    echo "Termine."
}
trap cleanup EXIT INT TERM HUP

echo "Attente que le frontend soit pret sur http://localhost:4200 ..."
until curl -s -o /dev/null "http://localhost:4200"; do
    sleep 2
done

echo ""
echo "  Site pret : http://localhost:4200"
echo "  Fermez la fenetre Chrome (ou Ctrl+C) pour arreter les serveurs."
echo ""

# On ouvre le site dans Chrome (profil habituel) puis on surveille l'onglet :
# quand plus aucun onglet Chrome ne pointe vers localhost:4200, on arrete tout.
if [ -d "/Applications/Google Chrome.app" ]; then
    open -a "Google Chrome" "http://localhost:4200"

    # Laisse le temps a l'onglet de s'ouvrir avant de commencer a surveiller.
    sleep 5

    onglet_ouvert() {
        osascript <<'EOF' 2>/dev/null | grep -q "1"
tell application "Google Chrome"
    if not running then return "0"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "localhost:4200" then return "1"
        end repeat
    end repeat
    return "0"
end tell
EOF
    }

    while onglet_ouvert; do
        sleep 2
    done

    echo ""
    echo "Onglet localhost:4200 ferme."
    cleanup
    trap - EXIT INT TERM

    # Fermeture de la fenetre du Terminal.
    osascript -e 'tell application "Terminal" to close (every window whose name contains "start.command")' 2>/dev/null || true
    exit 0
else
    echo "Google Chrome introuvable, ouverture dans le navigateur par defaut."
    open "http://localhost:4200"
    wait
fi
