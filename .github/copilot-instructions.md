# GitHub Copilot Repository Instructions

Follow the project rules in:

- `AGENTS.md`
- `AI_DAILY_RULES.md`
- `RULE_PACK_FILE_INDEX.md`
- `docs/TECH_STACK.md`
- `docs/FEATURE_SLICE_DEVELOPMENT_RULES.md`
- `docs/OLD_SYSTEM_READONLY_RULES.md`
- `docs/COMPONENT_AND_MODULE_RULES.md`
- `docs/CODE_COMMENT_RULES.md`
- `docs/DATA_SOURCE_AND_LINEAGE_RULES.md`
- `docs/FINANCIAL_CALCULATION_RULES.md`

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

## Context7 documentation lookup

When working with third-party library APIs, configuration, SDKs, CLIs, or upgrades, verify current usage through Context7 or official documentation first.

Context7 is documentation lookup only. Do not add it to production dependencies, CI, Dockerfile, or postinstall. Do not commit Context7 API keys, MCP tokens, or OAuth data.
