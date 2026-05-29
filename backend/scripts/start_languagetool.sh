#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAVA_BIN="${JAVA_BIN:-/home/newuser/.local/opt/jdk-21.0.11+10-jre/bin/java}"
LT_HOME="${LT_HOME:-}"
LT_PORT="${LT_PORT:-8010}"
LT_HOST="${LT_HOST:-127.0.0.1}"
LT_WAIT_SEC="${LT_WAIT_SEC:-30}"
LT_UNIT_NAME="${LT_UNIT_NAME:-piap-languagetool}"
LT_LOG_DIR="${LT_LOG_DIR:-/home/newuser/.local/var/log}"
LT_LOG_FILE="${LT_LOG_FILE:-$LT_LOG_DIR/languagetool.log}"
LT_PID_FILE="${LT_PID_FILE:-$LT_LOG_DIR/languagetool.pid}"

mkdir -p "$LT_LOG_DIR"

if [[ ! -x "$JAVA_BIN" ]]; then
  echo "java binary not found: $JAVA_BIN" >&2
  exit 1
fi

if [[ -z "$LT_HOME" ]]; then
  LT_HOME="$(find /home/newuser/.local/share/languagetool -maxdepth 1 -mindepth 1 -type d -name 'LanguageTool-*' | sort | tail -n 1)"
fi

if [[ ! -d "$LT_HOME" ]]; then
  echo "LanguageTool home not found: $LT_HOME" >&2
  exit 1
fi

if [[ -f "$LT_PID_FILE" ]]; then
  old_pid="$(cat "$LT_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "LanguageTool already running on pid $old_pid"
    exit 0
  fi
  rm -f "$LT_PID_FILE"
fi

cd "$LT_HOME"
systemctl --user stop "${LT_UNIT_NAME}.service" >/dev/null 2>&1 || true
systemd-run --user \
  --unit="$LT_UNIT_NAME" \
  --working-directory="$LT_HOME" \
  --setenv=JAVA_HOME="$(dirname "$(dirname "$JAVA_BIN")")" \
  --property=StandardOutput=append:"$LT_LOG_FILE" \
  --property=StandardError=append:"$LT_LOG_FILE" \
  "$JAVA_BIN" -cp "languagetool-server.jar:libs/*" org.languagetool.server.HTTPServer \
  --port "$LT_PORT" \
  --public \
  --allow-origin >/dev/null

main_pid="$(systemctl --user show -p MainPID --value "${LT_UNIT_NAME}.service" | tr -d '\n')"
echo "$main_pid" >"$LT_PID_FILE"
for _ in $(seq 1 "$LT_WAIT_SEC"); do
  if curl -fsS "http://$LT_HOST:$LT_PORT/v2/languages" >/dev/null 2>&1; then
    echo "LanguageTool started on http://$LT_HOST:$LT_PORT with pid $(cat "$LT_PID_FILE")"
    exit 0
  fi
  if ! kill -0 "$(cat "$LT_PID_FILE")" 2>/dev/null; then
    echo "LanguageTool exited during startup. Log:" >&2
    tail -n 40 "$LT_LOG_FILE" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "LanguageTool did not become ready within ${LT_WAIT_SEC}s. Log:" >&2
tail -n 40 "$LT_LOG_FILE" >&2 || true
exit 1
