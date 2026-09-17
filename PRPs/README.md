# PRPs — 本项目 Product Requirements Prompts

PRP 是 AI 开发前的施工图。复杂功能必须先写 PRP，经项目负责人确认后才能开发。

## Structure

```text
PRPs/templates/prp_base.md
PRPs/templates/frontend_page_prp.md
PRPs/templates/backend_api_prp.md
PRPs/templates/database_prp.md
PRPs/templates/ai_task_prp.md
```

## Rule

PRP 不等于批准开发。PRP 与 `AGENTS.md` 冲突时，以 `AGENTS.md` 为准。

## Current Drafts

- `pmc-purchase-board.md`：PMC 采购看板（采购计划 / 采购单 / 收货单只读同步 + 看板）；状态 Draft，关联 `docs/data-sources/decisions/pmc-purchase-board-decision.md`（BLOCKED_BY_OWNER_DECISION，单项：收货单接口重评）。
- `lingxing-raw-foundation.md`：领星 L2 RAW 留痕、脱敏、hash、分页和审计边界；当前状态以文件正文为准。
