#!/bin/bash
set -e

ROOT="/Users/pierre/Library/CloudStorage/OneDrive-FondationEPF/F/UCL"
export PATH="/opt/homebrew/bin:$PATH"
export NG_CLI_ANALYTICS=false

cd "$ROOT"

echo "Recuperation des dernieres mises a jour (git pull)..."
if ! git pull; then
    echo "Attention : la mise a jour Git a echoue (pas de connexion, modifications locales en conflit, etc.)."
    echo "Demarrage avec les fichiers actuels."
fi

echo "Demarrage du backend (FastAPI)..."
(cd "$ROOT" && "$ROOT/.venv/bin/python" -m uvicorn main:app --reload) &
BACKEND_PID=$!

echo "Demarrage du frontend (Angular)..."
(cd "$ROOT/ucl-app" && ./node_modules/.bin/ng serve) &
FRONTEND_PID=$!

cleanup() {
    echo "Arret des serveurs..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
    echo "Termine."
}
trap cleanup EXIT

echo "Attente que le frontend soit pret sur http://localhost:4200 ..."
until curl -s -o /dev/null "http://localhost:4200"; do
    sleep 2
done

echo "Ouverture de Chrome..."
open -na "Google Chrome" --args --new-window "http://localhost:4200"

echo "Site ouvert dans Chrome."
echo "Les serveurs s'arreteront automatiquement a la fermeture de Chrome."

while pgrep -x "Google Chrome" >/dev/null; do
    sleep 3
done

echo "Chrome ferme. Arret des serveurs..."
