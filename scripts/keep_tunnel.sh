#!/usr/bin/env bash
# Держит HTTPS-туннель localhost.run и обновляет MINIAPP_URL + кнопку бота.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENVF="$ROOT/.env"
PORT="${PORT:-8877}"
LOG=/tmp/localhost-run.log
PIDFILE=/tmp/lenormand-tunnel.pid

need_restart() {
  local url
  url=$(grep '^MINIAPP_URL=' "$ENVF" 2>/dev/null | cut -d= -f2- || true)
  if [[ -z "$url" ]]; then return 0; fi
  local code body
  code=$(curl -sS -o /tmp/tuncheck.html -w '%{http_code}' --max-time 12 "$url/" || echo 000)
  body=$(head -c 200 /tmp/tuncheck.html 2>/dev/null || true)
  if [[ "$code" != "200" ]]; then return 0; fi
  if echo "$body" | grep -qi 'no tunnel'; then return 0; fi
  return 1
}

start_tunnel() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    sleep 1
  fi
  # kill any old
  pgrep -f 'nokey@localhost.run' | xargs kill 2>/dev/null || true
  sleep 1
  : >"$LOG"
  nohup ssh -o StrictHostKeyChecking=accept-new \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \
    -o ExitOnForwardFailure=yes \
    -R 80:127.0.0.1:"$PORT" nokey@localhost.run >"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 10
  local url
  url=$(grep -oE 'https://[a-zA-Z0-9]+\.lhr\.life' "$LOG" | tail -1)
  if [[ -z "$url" ]]; then
    echo "Failed to get tunnel URL" >&2
    tail -20 "$LOG" >&2
    return 1
  fi
  # preserve keys
  local bot or
  bot=$(grep '^BOT_TOKEN=' "$ENVF" | cut -d= -f2-)
  or=$(grep '^OPENROUTER_API_KEY=' "$ENVF" | cut -d= -f2- || true)
  {
    echo "BOT_TOKEN=$bot"
    echo "MINIAPP_URL=$url"
    [[ -n "$or" ]] && echo "OPENROUTER_API_KEY=$or"
    echo "LLM_PROVIDER=openrouter"
    echo "LLM_MODEL=google/gemma-4-26b-a4b-it:free"
    echo "ALLOW_INSECURE_WEBAPP=1"
  } >"$ENVF"
  chmod 600 "$ENVF"
  echo "Tunnel OK: $url"
  # restart bot to refresh menu
  pgrep -f "$ROOT/main.py" | xargs kill 2>/dev/null || true
  sleep 1
  cd "$ROOT"
  nohup .venv/bin/python main.py >/tmp/lenormand-bot.log 2>&1 &
  echo "Bot restarted"
}

# ensure local server
if ! curl -s --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  cd "$ROOT"
  nohup .venv/bin/python serve_miniapp.py --port "$PORT" >/tmp/miniapp-serve.log 2>&1 &
  sleep 2
fi

if need_restart; then
  echo "Tunnel down — restarting..."
  start_tunnel
else
  echo "Tunnel OK: $(grep MINIAPP_URL "$ENVF")"
fi
