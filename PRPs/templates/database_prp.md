# 本项目 Database PRP Template — Project Rule Pack V1.0

## 1. Goal

[本次要建设什么功能，最终完成状态是什么]

## 2. Why

[业务价值、用户影响、解决的问题]

## 3. Scope

### In scope

- [ ] ...

### Out of scope

- [ ] ...

## 4. Navigation / Page

```text
一级导航：
二级导航：
页面路径：
页面状态：planned / building / testing / ready / disabled / hidden
```

## 5. Permissions

```text
page permissionKey:
action permissionKeys:
data scope resource:
field permissions:
high-risk actions:
```

## 6. Data Source

```text
old-system reference: yes/no
legacy MySQL readonly tables:
new PostgreSQL tables:
cache / mart tables:
```

## 7. API Contract

```text
method:
path:
request schema:
response schema:
error codes:
meta.source:
meta.source_tables:
request_id:
```

## 8. UI Requirements

```text
layout:
table columns:
filters:
actions:
empty state:
loading state:
error state:
helpUrl:
```

## 9. SOP / API Docs

- [ ] Markdown API doc required
- [ ] OpenAPI metadata required
- [ ] SOP help page required
- [ ] PageShell help entry required

## 10. Implementation Plan

```text
Task 1:
Task 2:
Task 3:
```

## 11. Validation Gates

```bash
# frontend
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e

# backend
uv run ruff check .
uv run pytest
uv run alembic check
```

## 12. Forbidden Actions

```text
不修改 old-system
不连接生产数据库
不修改 .env
不调用真实外部 API
不部署
不重启服务
```

## 13. Rollback Plan

[如何回滚代码、数据库、配置、feature flag]

## 14. Acceptance Checklist

- [ ] 页面 / API 完成
- [ ] 权限生效
- [ ] 数据权限生效
- [ ] API 文档完成
- [ ] SOP 完成
- [ ] 测试通过
- [ ] Playwright 通过，如适用
- [ ] CODEX_HANDOFF 更新

## Database Special Checks

- PostgreSQL only for new writes
- legacy MySQL readonly only
- Alembic migration draft
- no raw huge legacy copy
- rollback or compensation plan
