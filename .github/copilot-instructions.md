# GitHub Copilot Repository Instructions

Follow the project rules in:

- `AGENTS.md`
- `docs/TECH_STACK.md`
- `docs/FEATURE_SLICE_DEVELOPMENT_RULES.md`
- `docs/OLD_SYSTEM_READONLY_RULES.md`
- `docs/COMPONENT_AND_MODULE_RULES.md`
- `docs/CODE_COMMENT_RULES.md`

## Core requirements

- This is a greenfield rebuild.
- `old-system/` is read-only reference only.
- Do not copy old-system code into the new system.
- One task should handle one feature/page only.
- Frontend uses React + TypeScript + Vite + Ant Design + ProComponents.
- Backend uses Python + FastAPI + Pydantic + SQLAlchemy + Alembic + Redis + Celery.
- Business logic belongs in services, not frontend pages or route handlers.
- Database access belongs in repositories.
- Background tasks use Celery only.
- Add maintainability comments for business logic.
- Do not commit secrets.
