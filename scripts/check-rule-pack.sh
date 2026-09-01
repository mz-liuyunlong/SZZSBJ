#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "AGENTS.md"
  "AI_DAILY_RULES.md"
  "RULE_PACK_FILE_INDEX.md"
  "docs/00_RULE_PACK_V2_OVERVIEW.md"
  "docs/01_PROJECT_DECISIONS.md"
  "docs/architecture/frontend.md"
  "docs/architecture/backend.md"
  "docs/architecture/api.md"
  "docs/architecture/database.md"
  "docs/architecture/security-secrets-integrations.md"
  "docs/business-rules/navigation-spec.md"
  "docs/business-rules/permission-model.md"
  "docs/business-rules/organization-and-data-scope.md"
  "docs/business-rules/fee-rules-versioning.md"
  "docs/delivery/api-documentation-standard.md"
  "docs/delivery/sop-help-standard.md"
  "docs/tasks/FIRST_30_CODEX_TASKS.md"
)

for f in "${required_files[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required file: $f" >&2
    exit 1
  fi
done

echo "Rule pack required files OK"
