#!/usr/bin/env bash
# Sobe server.py numa porta temporaria, testa /api/followups end-to-end via curl, derruba.
set -euo pipefail
cd "$(dirname "$0")"

PORT=18899
export ARTIFACT_PASSWORD_SHA256=$(printf 'testpass' | shasum -a 256 | cut -d' ' -f1)
export PORT
PASSWORD=testpass
DOC=selfcheck

python3 -c '
import json, os
data = {"f1": {"doc": "selfcheck", "decision": "s1-D1", "about": "resposta livre",
               "turns": [{"role": "agent", "text": "pergunta?", "ts": "2026-01-01T00:00:00"}]}}
open("followups.json", "w", encoding="utf-8").write(json.dumps(data))
'

python3 server.py &
SRV_PID=$!
trap 'kill $SRV_PID 2>/dev/null; rm -f followups.json followups.json.tmp answers.json questions.json questions.log' EXIT
sleep 0.5

JAR=$(mktemp)

# auth-gating: sem cookie, deve recusar
UNAUTH=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/followups?doc=$DOC")
[ "$UNAUTH" = "401" ] && echo "GET /api/followups sem auth: ok (401)" || { echo "GET /api/followups sem auth: FAIL -> $UNAUTH"; exit 1; }

UNAUTH_POST=$(curl -s -o /dev/null -w '%{http_code}' -X POST -d '{"id":"f1","text":"x"}' "http://127.0.0.1:$PORT/api/followups/reply?doc=$DOC")
[ "$UNAUTH_POST" = "401" ] && echo "POST /api/followups/reply sem auth: ok (401)" || { echo "POST /api/followups/reply sem auth: FAIL -> $UNAUTH_POST"; exit 1; }

curl -s -c "$JAR" -o /dev/null -d "password=$PASSWORD" "http://127.0.0.1:$PORT/login?next=/"

OUT=$(curl -s -b "$JAR" "http://127.0.0.1:$PORT/api/followups?doc=$DOC")
echo "$OUT" | grep -q '"id": "f1"' && echo "GET /api/followups: ok" || { echo "GET /api/followups: FAIL -> $OUT"; exit 1; }

# validacao: id inexistente -> 404
BAD=$(curl -s -b "$JAR" -X POST -d '{"id":"nope","text":"x"}' "http://127.0.0.1:$PORT/api/followups/reply?doc=$DOC")
echo "$BAD" | grep -q '"error"' && echo "POST reply id invalido: ok (404)" || { echo "POST reply id invalido: FAIL -> $BAD"; exit 1; }

# validacao: doc nao bate com o registro -> 404
MISMATCH=$(curl -s -b "$JAR" -X POST -d '{"id":"f1","text":"x"}' "http://127.0.0.1:$PORT/api/followups/reply?doc=outrodoc")
echo "$MISMATCH" | grep -q '"error"' && echo "POST reply doc mismatch: ok (404)" || { echo "POST reply doc mismatch: FAIL -> $MISMATCH"; exit 1; }

# validacao: text vazio -> 400
EMPTY=$(curl -s -b "$JAR" -X POST -d '{"id":"f1","text":"  "}' "http://127.0.0.1:$PORT/api/followups/reply?doc=$DOC")
echo "$EMPTY" | grep -q '"error"' && echo "POST reply text vazio: ok (400)" || { echo "POST reply text vazio: FAIL -> $EMPTY"; exit 1; }

REPLY=$(curl -s -b "$JAR" -X POST -d '{"id":"f1","text":"minha resposta"}' "http://127.0.0.1:$PORT/api/followups/reply?doc=$DOC")
echo "$REPLY" | grep -q '"ok": true' && echo "POST /api/followups/reply: ok" || { echo "POST /api/followups/reply: FAIL -> $REPLY"; exit 1; }

OUT2=$(curl -s -b "$JAR" "http://127.0.0.1:$PORT/api/followups?doc=$DOC")
echo "$OUT2" | grep -q '"role": "user"' && echo "turno gravado: ok" || { echo "turno gravado: FAIL -> $OUT2"; exit 1; }

CSS=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "http://127.0.0.1:$PORT/wizard.css")
[ "$CSS" = "200" ] && echo "GET /wizard.css: ok" || { echo "GET /wizard.css: FAIL -> $CSS"; exit 1; }

JS=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "http://127.0.0.1:$PORT/wizard-core.js")
[ "$JS" = "200" ] && echo "GET /wizard-core.js: ok" || { echo "GET /wizard-core.js: FAIL -> $JS"; exit 1; }

rm -f "$JAR"
echo "ok"
