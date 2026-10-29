#!/usr/bin/env bash
# Shared, non-destructive checks for local AI development and GitHub Actions.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-all}"
cd "$ROOT"

rules() {
  echo "[preflight] rule pack and diff whitespace"
  git diff --check
  git diff --cached --check
  bash scripts/check-rule-pack.sh
}
backend() {
  echo "[preflight] backend"
  cd "$ROOT/backend"
  uv sync --frozen
  uv run ruff format --check .
  uv run ruff check .
  uv run pytest
  uv run python -c "import app.main"
}
frontend() {
  echo "[preflight] frontend"
  cd "$ROOT/frontend"
  test -f package-lock.json || { echo "Missing frontend/package-lock.json" >&2; exit 1; }
  npm ci
  npm run lint --if-present
  npm run typecheck --if-present
  npm run test --if-present -- --run
  npm run build --if-present
  if node -e "const p=require('./package.json'); process.exit(p.scripts && p.scripts['test:e2e'] ? 0 : 1)"; then
    if [[ "${CI:-}" == "true" ]]; then
      npx playwright install --with-deps
    else
      npx playwright install
    fi
    npm run test:e2e
  fi
}
case "$MODE" in
  rules) rules ;;
  backend) backend ;;
  frontend) frontend ;;
  all)
    rules
    [[ ! -f backend/pyproject.toml ]] || backend
    [[ ! -f frontend/package.json ]] || frontend
    ;;
  *) echo "Usage: bash scripts/ci-preflight.sh [rules|backend|frontend|all]" >&2; exit 2 ;;
esac
echo "[preflight] PASS: $MODE"
