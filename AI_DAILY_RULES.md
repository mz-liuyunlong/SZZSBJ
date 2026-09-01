# AI 日常开发规则 v2.0

## 1. 每次任务默认先读

```text
AGENTS.md
AI_DAILY_RULES.md
RULE_PACK_FILE_INDEX.md
docs/00_RULE_PACK_V2_OVERVIEW.md
skills/README.md
```

然后按任务类型选择性读取对应 docs / skills。不要一次性全文读取所有文档。

---

## 2. 项目定位

- 这是 SKYC V2 新系统重建项目。
- `old-system/` 只能只读参考。
- 新系统代码只能写入 `frontend/`、`backend/`、`docs/`、`scripts/`、`.github/`、`.cursor/`、`skills/`。
- 不允许复制旧系统架构。
- 不允许新增第二套独立后台管理系统。

---

## 3. 固定技术栈

```text
Frontend: React + TypeScript + Vite + Ant Design + ProComponents + React Router + Zustand + ECharts
Backend: Python 3.13 + FastAPI + Pydantic + SQLAlchemy 2 + Alembic + Redis + Celery
Database: PostgreSQL
Package: frontend npm；backend uv
API: { success, data, error, meta, request_id }
```

---

## 4. 任务开始前必须输出

AI 修改代码前必须先输出：

```text
1. 本次任务类型
2. 需要读取哪些 docs / skills
3. 哪些 docs / skills 本次不需要
4. 允许修改范围
5. 禁止事项
6. 开发计划
7. 验收标准
```

用户确认前不得修改代码。

---

## 5. 关键硬规则

```text
不改 old-system
不连接生产数据库
不调用真实外部 API
不修改 .env 真实密钥
不部署
不重启服务
不一次性生成整个系统
不新增独立 admin 系统
不硬编码角色
不覆盖历史费用规则
不把 Token 明文返回前端
```

---

## 6. 按任务类型追加读取

### 前端导航 / 页面壳

```text
docs/business-rules/navigation-spec.md
docs/architecture/frontend.md
docs/delivery/sop-help-standard.md
docs/delivery/acceptance-checklist.md
```

### 后端接口

```text
docs/architecture/backend.md
docs/architecture/api.md
docs/delivery/api-documentation-standard.md
docs/business-rules/permission-model.md
```

### 数据库 / Alembic

```text
docs/architecture/database.md
docs/database/INITIAL_SCHEMA_PLAN.md
docs/database/LEGACY_DB_READONLY_PLAN.md
docs/business-rules/fee-rules-versioning.md
```

### 权限 / 组织架构 / 数据范围

```text
docs/business-rules/permission-model.md
docs/business-rules/organization-and-data-scope.md
```

### 费用 / 利润 / 汇率

```text
docs/business-rules/fee-rules-versioning.md
docs/business-rules/time-money-metric-rules.md
docs/operations/release-rollback-backup.md
```

### AI Token / 飞书 / Webhook / 外部 API

```text
docs/architecture/security-secrets-integrations.md
docs/architecture/backend.md
docs/business-rules/permission-model.md
```

### API 文档页面

```text
docs/delivery/api-documentation-standard.md
docs/business-rules/navigation-spec.md
docs/architecture/api.md
```

### SOP / 帮助中心

```text
docs/delivery/sop-help-standard.md
docs/business-rules/navigation-spec.md
```

---

## 7. 完成报告格式

每个任务完成后必须输出：

```text
## Done
## Files changed
## Commands run
## Tests run
## Risk check
## Acceptance checklist
## Next step
```

如果没有运行测试，必须诚实说明原因，不能声称测试通过。
