#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "AGENTS.md"
  "AI_DAILY_RULES.md"
  "RULE_PACK_FILE_INDEX.md"
  "docs/00_RULE_PACK_V1_0_OVERVIEW.md"
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
  "docs/delivery/e2e-playwright-standard.md"
  "docs/tasks/FIRST_40_CODEX_TASKS.md"
  "docs/ui/ADMIN_LAYOUT_RULES.md"
  "docs/ui/UI_COMPONENT_USAGE_RULES.md"
  "skills/ponytail-compatibility/SKILL.md"
  "docs/tools/PONYTAIL_SETUP_GUIDE.md"
  "docs/PONYTAIL_COMPATIBILITY_RULES.md"
  ".github/workflows/ci.yml"
  ".github/CODEOWNERS"
  ".github/pull_request_template.md"
  ".github/copilot-instructions.md"
  "docs/tools/AI_SKILL_REGISTRY.md"
  ".cursor/rules/00-project-safety.mdc"
  ".cursor/rules/30-frontend-architecture.mdc"
  ".cursor/rules/40-backend-architecture.mdc"
  ".cursor/rules/75-testing-rules.mdc"
  ".cursor/rules/83-ponytail-compatibility.mdc"
)

for f in "${required_files[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required file: $f" >&2
    exit 1
  fi
done

if [[ -f "CLAUDE.md" ]]; then
  echo "CLAUDE.md should not exist in this rule pack. Use AGENTS.md as the single AI entry." >&2
  exit 1
fi

# Removed or deprecated files must not be referenced anywhere in the rule pack.
# Keep this list explicit so deleted documents do not leave dead links in entry files.
removed_references=(
  'docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md'
)

for ref in "${removed_references[@]}"; do
  if grep -RInF "$ref" . \
    --exclude-dir=.git \
    --exclude-dir=node_modules \
    --exclude-dir=dist \
    --exclude='check-rule-pack.sh'; then
    echo "Removed or missing file is still referenced: $ref" >&2
    exit 1
  fi
done

# Critical entry documents may only point to existing fixed rule-pack files.
# This is intentionally conservative: it checks known rule-pack docs, not future app files.
critical_reference_sources=(
  "AGENTS.md"
  "AI_DAILY_RULES.md"
  "CODEX_START_HERE.md"
  "INSTALL_TO_PROJECT.md"
  "README_AI_RULES.md"
  "RULE_PACK_FILE_INDEX.md"
  "docs/00_RULE_PACK_V1_0_OVERVIEW.md"
  "docs/01_PROJECT_DECISIONS.md"
  "docs/README.md"
  "docs/tools/README.md"
  "docs/tools/AI_TOOL_INSTALL_GUIDE.md"
  "docs/tools/AI_SKILL_REGISTRY.md"
)

for source_file in "${critical_reference_sources[@]}"; do
  [[ -f "$source_file" ]] || continue
  while IFS= read -r ref; do
    [[ -z "$ref" ]] && continue
    if [[ ! -e "$ref" ]]; then
      echo "Dead fixed-file reference in $source_file: $ref" >&2
      exit 1
    fi
  done < <(grep -oE 'docs/[A-Za-z0-9_./-]+\.md|PRPs/[A-Za-z0-9_./-]+\.md|templates/[A-Za-z0-9_./-]+\.md|skills/[A-Za-z0-9_./-]+/SKILL\.md|\.cursor/rules/[A-Za-z0-9_./-]+\.mdc' "$source_file" | sort -u)
done

if [[ -f ".github/CODEOWNERS" ]]; then
  if grep -RInE '@your-|real-owner-or-team|your-github-username|@org/|@organization/|TODO_OWNER|OWNER_TO_SET' .github/CODEOWNERS; then
    echo ".github/CODEOWNERS contains placeholder owners. Use only real GitHub users or teams." >&2
    exit 1
  fi
fi

# These terms are not allowed in rule content because they pollute the blank project scope.
# Exclude this script from the search so the check patterns themselves do not trigger failures.
forbidden_patterns=(
  'SZZSBJ|Szzsbj|szzsbj|SKYC|Skyc|skyc'
  'CLAUDE\.md'
  '@your-github-username|@your-|real-owner-or-team'
)

for pattern in "${forbidden_patterns[@]}"; do
  if grep -RInE "$pattern" . \
    --exclude-dir=.git \
    --exclude-dir=node_modules \
    --exclude-dir=dist \
    --exclude='check-rule-pack.sh'; then
    echo "Forbidden or conflicting rule-pack content detected: $pattern" >&2
    exit 1
  fi
done


if ! grep -q "Ponytail" docs/tools/AI_SKILL_REGISTRY.md; then
  echo "Ponytail must be registered in docs/tools/AI_SKILL_REGISTRY.md." >&2
  exit 1
fi

if grep -RInE '\| Ponytail \|.*\| Yes \|' docs/tools/AI_SKILL_REGISTRY.md 2>/dev/null; then
  echo "Ponytail must not be registered as a production dependency." >&2
  exit 1
fi

if grep -RInE '\|\| true' .github/workflows scripts --exclude='check-rule-pack.sh' 2>/dev/null; then
  echo "CI/check scripts must not swallow real failures with || true." >&2
  exit 1
fi

required_nav_terms=(
  "推广中心"
  "测评"
  "刷单"
  "退货分析"
  "销售分析"
  "利润分析"
  "广告分析"
  "库存分析"
)

nav_check_files=(
  "templates/frontend/src/config/navigation.ts"
  "docs/business-rules/navigation-spec.md"
)

for nav_file in "${nav_check_files[@]}"; do
  if [[ ! -f "$nav_file" ]]; then
    echo "Missing navigation check file: $nav_file" >&2
    exit 1
  fi

  for required_nav_term in "${required_nav_terms[@]}"; do
    if ! grep -qF "$required_nav_term" "$nav_file"; then
      echo "Required navigation item missing from $nav_file: $required_nav_term" >&2
      exit 1
    fi
  done
done

node <<'NODE'
const fs = require('fs');

const file = 'templates/frontend/src/config/navigation.ts';

if (!fs.existsSync(file)) {
  process.exit(0);
}

const text = fs.readFileSync(file, 'utf8');
const pageRegex = /page\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]\s*,\s*['"][^'"]+['"]\s*,\s*['"]([^'"]+)['"]/g;

const keys = new Map();
const paths = new Map();

let match;
let failed = false;

while ((match = pageRegex.exec(text)) !== null) {
  const groupKey = match[1];
  const pageKey = match[2];
  const path = match[3];
  const fullKey = `${groupKey}_${pageKey}`;

  if (keys.has(fullKey)) {
    console.error(`Duplicate navigation key: ${fullKey}`);
    failed = true;
  }
  keys.set(fullKey, true);

  if (paths.has(path)) {
    console.error(`Duplicate navigation path: ${path}`);
    failed = true;
  }
  paths.set(path, true);
}

if (failed) {
  process.exit(1);
}
NODE

# Navigation labels must not contain decorative emoji icons. Use semantic text labels only.
for nav_file in "docs/business-rules/navigation-spec.md" "templates/frontend/src/config/navigation.ts"; do
  if [[ -f "$nav_file" ]] && grep -nE "🏠|📦|📈|📢|🧾|🏭|💰|📝|🛒|🤖|🗄|⭐|⚙" "$nav_file"; then
    echo "Navigation file contains decorative emoji icons: $nav_file" >&2
    exit 1
  fi
done


if ! grep -qF "Navigation template." templates/frontend/src/config/navigation.ts; then
  echo "Navigation template must clearly state it is a bootstrap template." >&2
  exit 1
fi

node <<'NODE'
const fs = require('fs');

const file = 'templates/frontend/src/config/navigation.ts';
const text = fs.readFileSync(file, 'utf8');

const statusBlockMatch = text.match(/export type PageStatus =([\s\S]*?);/);
if (!statusBlockMatch) {
  console.error('PageStatus definition is missing from navigation template.');
  process.exit(1);
}

const statusBlock = statusBlockMatch[1];
const invalidStatusValues = ['readonly', 'legacy', 'iframe', 'deprecated'];
let failed = false;

for (const value of invalidStatusValues) {
  if (statusBlock.includes(`'${value}'`)) {
    console.error(`Invalid PageStatus value in navigation template: ${value}`);
    failed = true;
  }
}

for (const value of ['planned', 'building', 'testing', 'ready', 'disabled', 'hidden']) {
  if (!statusBlock.includes(`'${value}'`)) {
    console.error(`Required PageStatus value missing from navigation template: ${value}`);
    failed = true;
  }
}

if (/\breadonly\s*:/.test(text)) {
  console.error('NavigationPage must use readOnly, not readonly.');
  failed = true;
}

if (!/\breadOnly\s*:\s*boolean\s*;/.test(text)) {
  console.error('NavigationPage must include readOnly: boolean.');
  failed = true;
}

if (!/status\s*:\s*'planned'\s+as\s+PageStatus/.test(text)) {
  console.error("Navigation defaults must use status: 'planned' as PageStatus.");
  failed = true;
}

if (!/\breadOnly\s*:\s*false/.test(text)) {
  console.error('Navigation defaults must use readOnly: false.');
  failed = true;
}

if (failed) {
  process.exit(1);
}
NODE

if grep -RInF "页面状态：building / readonly / testing / ready" PRPs/templates docs --exclude='check-rule-pack.sh'; then
  echo "Old readonly PageStatus wording remains in PRP/docs templates." >&2
  exit 1
fi

if grep -RInF "readonly      只读可用" docs/business-rules/navigation-spec.md; then
  echo "Navigation spec still treats readonly as a PageStatus." >&2
  exit 1
fi

if grep -RInF "readonly: boolean;" docs/architecture/frontend.md templates/frontend/src/config/navigation.ts; then
  echo "Navigation page metadata must use readOnly: boolean, not readonly: boolean." >&2
  exit 1
fi

echo "Rule pack required files and conflict checks OK"
