# Context Engineering / PRP Standard — Project Rule Pack V1.0

## 1. Purpose

复杂功能不得直接开发。必须先把需求、上下文、边界、实现步骤、测试命令、验收标准写成 PRP。

PRP 是施工图，不是批准开发。

## 2. Required for

```text
新页面
新 API
新数据库表
新权限模型
新费用规则
新 AI 任务
新导入导出流程
涉及 old-system 的迁移/读取
涉及生产数据或历史财务口径的功能
```

## 3. Workflow

```text
templates/INITIAL_FEATURE.md
  ↓
PRPs/templates/prp_base.md
  ↓
项目负责人确认 PRP
  ↓
.planning/current/
  ↓
开发、测试、验收
```

## 4. Required PRP fields

PRP 必须包含：

```text
功能目标
业务价值
所属导航
页面路径
permissionKey
数据权限范围
old-system 是否读取
旧库只读表
新库写入表
API 契约
API 文档要求
SOP 帮助入口
UI 验收标准
pytest / vitest / Playwright 验收
禁止动作
回滚方案
完成报告格式
```

## 5. Validation gates

PRP 必须写清楚可以执行的验证命令：

```text
frontend lint / typecheck / vitest / build / Playwright
backend ruff / pyright or mypy / pytest / alembic check
OpenAPI generation
secret scan
old-system protection check
```

## 6. Boundary

PRP 不能覆盖 `AGENTS.md`。如果 PRP 需要高危操作，必须等待项目负责人单独批准。
