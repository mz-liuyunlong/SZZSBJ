# Backend Implementation Prompt

```text
Role: Backend Engineer
Worktree: <absolute path>
Branch: <branch>
Approved PRP: <path>
Allowed files/commands/systems: <exact allowlists>

Preflight and stop on any mismatch or unrelated change. Read AGENTS.md, AI_DAILY_RULES.md, CODEX_START_HERE.md, the Approved PRP, backend/AGENTS.md, data-source decision, DATA_INTERFACE_REGISTRY_RULES.md, database layering/field standards and BACKEND_MODULE_CATALOG.md.

Implement only the Approved PRP. Keep route -> schema -> service -> repository -> model/task/integration boundaries. Do not invent fields, sources, permissions or business rules. Repository does not commit, decide permission, call external APIs or read legacy MySQL runtime. No real DB/API/server/secret/migration/deploy without the prompt's separate explicit authorization.

Update affected Interface/Module/Task registries in the same PR. Use installed dependencies and existing patterns; no unrelated refactor.

Run existing approved formatter/lint/type/test/scaffold checks and report exact results, skipped checks, scope, security, data/migration impact and Explicitly not implemented. Do not perform Git write/upload actions.
```
