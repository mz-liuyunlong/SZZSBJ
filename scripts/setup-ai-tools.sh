#!/usr/bin/env bash
set -u

printf '\nProject AI tools setup\n'
printf '======================\n\n'
printf 'This script helps install official Ponytail where the current machine has a supported AI CLI.\n'
printf 'It does not modify project runtime dependencies.\n'
printf 'It does not trust hooks for you. You must review hooks manually.\n\n'

has() { command -v "$1" >/dev/null 2>&1; }
ask() {
  local prompt="$1"
  printf '%s [y/N]: ' "$prompt"
  read -r answer
  case "$answer" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

run_cmd() {
  printf '\n$ %s\n' "$*"
  "$@"
}

printf 'Step 1: checking tools...\n\n'
bash "$(dirname "$0")/check-ai-tools.sh" || true

if ! has node; then
  printf '\n[warn] Node is not on PATH. Official Ponytail hooks for Codex/Claude may not activate.\n'
  printf 'Install Node first if you want full official hook behavior.\n'
fi

if has codex; then
  printf '\nDetected Codex.\n'
  if ask 'Install official Ponytail plugin for Codex now?'; then
    run_cmd codex plugin marketplace add DietrichGebert/ponytail || true
    run_cmd codex plugin add ponytail@ponytail || true
    printf '\nCodex Ponytail install command finished.\n'
    printf 'Next required manual step:\n'
    printf '  1. Run: codex\n'
    printf '  2. In Codex, type: /hooks\n'
    printf '  3. Review and trust Ponytail hooks manually.\n'
  fi
fi

if has copilot; then
  printf '\nDetected GitHub Copilot CLI.\n'
  if ask 'Install official Ponytail plugin for Copilot CLI now?'; then
    run_cmd copilot plugin marketplace add DietrichGebert/ponytail || true
    run_cmd copilot plugin install ponytail@ponytail || true
  fi
fi

if has gemini; then
  printf '\nDetected Gemini CLI.\n'
  if ask 'Install Ponytail Gemini extension now?'; then
    run_cmd gemini extensions install https://github.com/DietrichGebert/ponytail || true
  fi
fi

printf '\nClaude Code note:\n'
printf 'If you use Claude Code, open Claude Code and send these two messages separately:\n'
printf '  /plugin marketplace add DietrichGebert/ponytail\n'
printf '  /plugin install ponytail@ponytail\n\n'

printf 'Setup complete.\n'
printf 'Even if no official plugin was installed, this project still enforces:\n'
printf '  docs/PONYTAIL_COMPATIBILITY_RULES.md\n\n'
