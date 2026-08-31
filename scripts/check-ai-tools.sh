#!/usr/bin/env bash
set -u

printf '\nAI tool check for this project\n'
printf '================================\n\n'

has() { command -v "$1" >/dev/null 2>&1; }

if has node; then
  printf '[ok] node: %s\n' "$(node -v 2>/dev/null)"
else
  printf '[warn] node not found. Ponytail Codex/Claude hooks may not run without Node on PATH.\n'
fi

if has codex; then
  printf '[ok] codex found: %s\n' "$(command -v codex)"
else
  printf '[info] codex not found. Skip Codex Ponytail plugin install.\n'
fi

if has claude; then
  printf '[ok] claude found: %s\n' "$(command -v claude)"
else
  printf '[info] claude command not found. Claude Code plugin install may need slash commands inside Claude Code.\n'
fi

if has copilot; then
  printf '[ok] copilot found: %s\n' "$(command -v copilot)"
else
  printf '[info] copilot CLI not found. Skip Copilot Ponytail plugin install.\n'
fi

if has gemini; then
  printf '[ok] gemini found: %s\n' "$(command -v gemini)"
else
  printf '[info] gemini CLI not found. Skip Gemini Ponytail extension install.\n'
fi

printf '\nProject fallback rule is always available:\n'
printf '  docs/PONYTAIL_COMPATIBILITY_RULES.md\n\n'
printf 'To install supported official plugins, run:\n'
printf '  bash scripts/setup-ai-tools.sh\n\n'
