#!/usr/bin/env bash
# Sobe o decision-wizard localmente + tunnel gratis (cloudflared, sem conta/signup).
# Uso: start.sh <pasta-de-trabalho> [porta]
#   <pasta-de-trabalho> precisa ter docs/<slug>.html gerado (generate_wizard.py).
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="${1:?uso: start.sh <pasta-de-trabalho-com-docs/> [porta]}"
PORT="${2:-$(( (RANDOM % 5000) + 20000 ))}"

command -v cloudflared >/dev/null 2>&1 || {
  echo "cloudflared nao encontrado no PATH." >&2
  echo "Instale: brew install cloudflared (mac) ou veja https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
  exit 1
}

mkdir -p "$WORKDIR/docs" "$WORKDIR/diagrams" "$WORKDIR/audio"
cp "$SKILL_DIR/server.py" "$WORKDIR/server.py"
cp "$SKILL_DIR/answers.js" "$WORKDIR/answers.js"
cp "$SKILL_DIR/wizard.css" "$WORKDIR/wizard.css"
cp "$SKILL_DIR/wizard-core.js" "$WORKDIR/wizard-core.js"

PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')"
HASH="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "$PASSWORD")"
SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

ARTIFACT_PASSWORD_SHA256="$HASH" ARTIFACT_SESSION_SECRET="$SECRET" PORT="$PORT" \
  python3 "$WORKDIR/server.py" > "$WORKDIR/server.log" 2>&1 &
SERVER_PID=$!

TUNNEL_LOG="$WORKDIR/tunnel.log"
cloudflared tunnel --url "http://localhost:$PORT" > "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

URL=""
for _ in $(seq 1 30); do
  URL=$(grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done

if [ -z "$URL" ]; then
  echo "tunnel nao respondeu em 30s. Veja $TUNNEL_LOG" >&2
  kill "$SERVER_PID" "$TUNNEL_PID" 2>/dev/null || true
  exit 1
fi

echo "$SERVER_PID" > "$WORKDIR/server.pid"
echo "$TUNNEL_PID" > "$WORKDIR/tunnel.pid"
echo "URL=$URL"
echo "PASSWORD=$PASSWORD"
