# GitHub Copilot Repository Instructions

Follow the project rules in:

- `AGENTS.md`
- `RULE_PACK_FILE_INDEX.md`
- `docs/TECH_STACK.md`
- `docs/FEATURE_SLICE_DEVELOPMENT_RULES.md`
- `docs/OLD_SYSTEM_READONLY_RULES.md`
- `docs/COMPONENT_AND_MODULE_RULES.md`
- `docs/CODE_COMMENT_RULES.md`
- `docs/DATA_SOURCE_AND_LINEAGE_RULES.md`
- `docs/FINANCIAL_CALCULATION_RULES.md`
- `docs/PONYTAIL_COMPATIBILITY_RULES.md`

## Core requirements

- This is a greenfield rebuild.
- `old-system/` is read-only reference only.
- Do not copy old-system code into the new system.
- One task should handle one feature/page only.
- Frontend uses React + TypeScript + Vite + Ant Design + ProComponents.
- Backend uses Python + FastAPI + Pydantic + SQLAlchemy + Alembic + Redis + Celery.
- Business logic belongs in services.
- Database access belongs in repositories.
- Background tasks use Celery only.
- Add maintainability comments for business logic.
- Do not commit secrets.


## Skill self-discovery

Before suggesting or generating code, read `skills/README.md`, infer the task type, and use only the relevant Skill instructions. Do not assume the user will manually specify the right Skill.

## Ponytail default-on development

Apply `docs/PONYTAIL_COMPATIBILITY_RULES.md` by default for all coding suggestions. Do not wait for the user to mention Ponytail.

Ponytail is not an optional skill in this repository. It is a default coding principle.

Prefer reuse, standard library, native platform capabilities, and existing dependencies. Avoid unrequested abstractions, duplicate code, and new dependencies.

Do not use minimalism to skip validation, permissions, audit logs, API contracts, database migrations, Celery idempotency, tests, maintainability comments, or `old-system/` read-only rules.


## First-run setup behavior

When helping a developer who just cloned this repository, first point them to `AI_ONBOARDING.md` and `docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md`.
If they use GitHub Copilot CLI, help install official Ponytail with:

```bash
copilot plugin marketplace add DietrichGebert/ponytail
copilot plugin install ponytail@ponytail
```

Never suggest adding Ponytail plugin installation to npm postinstall or CI.
