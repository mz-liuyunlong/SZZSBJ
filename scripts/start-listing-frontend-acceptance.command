#!/bin/bash
# Listing local UI acceptance only: no API server, tunnel, migration or database writes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
FRONTEND="$REPO_ROOT/frontend"

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "=== Listing frontend acceptance ==="
echo "Worktree: $REPO_ROOT"
echo "Commit: $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
echo "Mode: UI fixture ONLY; no production database, backend or SSH tunnel."

if [[ ! -f "$REPO_ROOT/backend/app/modules/listing_rule_config/evaluation.py" ]] ||
   [[ ! -f "$REPO_ROOT/backend/app/modules/decodo/service.py" ]] ||
   [[ ! -f "$FRONTEND/src/pages/products/components/ListingRuleConfigPreview.tsx" ]]; then
  echo "ERROR: This worktree does not contain the complete Listing + main acceptance code."
  exit 2
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm was not found; install Node.js 22 and retry."
  exit 2
fi
if [[ ! -d "$FRONTEND/node_modules" ]]; then
  echo "ERROR: Frontend dependencies missing. Run: cd \"$FRONTEND\" && npm ci"
  exit 2
fi
# Do not kill or reuse a previous frontend. Select an unoccupied loopback port.
PORT=""
for candidate in 5173 5174 5175 5176 5177 5178 5179 5180; do
  if ! lsof -nP -iTCP:"$candidate" -sTCP:LISTEN >/dev/null 2>&1; then
    PORT="$candidate"
    break
  fi
done
if [[ -z "$PORT" ]]; then
  echo "ERROR: all acceptance ports 5173-5180 are occupied; no processes were stopped."
  exit 2
fi
URL="http://127.0.0.1:${PORT}/?listing-rule-preview=1"
echo "Selected local frontend port: $PORT"

cd "$FRONTEND"
npm run dev -- --host 127.0.0.1 --port "$PORT" --strictPort &
vite_pid=$!

cleanup() {
  kill "$vite_pid" 2>/dev/null || true
  wait "$vite_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "$vite_pid" 2>/dev/null; then
    echo "ERROR: Vite exited before becoming ready."
    exit 1
  fi
  if curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: Vite readiness check timed out."
  exit 1
fi
echo "Ready: $URL"
open "$URL"
wait "$vite_pid"
