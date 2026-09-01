# FIRST 40 CODEX TASKS — Project Rule Pack V1.0

这些任务用于新项目初始化阶段。Codex 必须按顺序、小步执行，不允许一次性生成整个系统。

## Phase 0 — Rule pack landing

1. 复制规则包到新项目根目录。
2. 读取 `AGENTS.md`、`AI_DAILY_RULES.md`、`CODEX_START_HERE.md`。
3. 检查 `.gitignore.ai-recommended`，合并必要规则到 `.gitignore`。
4. 确认 `old-system/README.md` 只读边界。
5. 建立 `docs/DECISION_LOG.md`。
6. 建立 `CODEX_HANDOFF.md`。
7. 建立 `docs/tools/AI_SKILL_REGISTRY.md` 检查表。
8. 建立 `.planning/current/` 本地计划目录。
9. 用 `templates/planning/` 初始化当前任务计划。
10. 输出 Phase 0 验收报告。

## Phase 1 — Frontend shell

11. 初始化 `frontend/` Vite React TS。
12. 安装 AntD、ProComponents、React Router、Zustand、ECharts、TanStack Query。
13. 建立 `frontend/src/config/navigation.ts`。
14. 建立 `MainLayout`。
15. 建立 `PageShell`。
16. 建立 `ComingSoonPage`。
17. 建立 `LegacyPageWrapper` 占位。
18. 建立基础 routes。
19. 建立页面右上角 `?` 帮助入口。
20. 建立第一批 Playwright 导航壳测试。

## Phase 2 — Backend shell

21. 初始化 `backend/` FastAPI + uv。
22. 建立 `app/main.py`。
23. 建立统一响应格式。
24. 建立 config / logging / request_id。
25. 建立 permission helper。
26. 建立 legacy MySQL readonly 连接占位。
27. 建立 PostgreSQL 连接占位。
28. 建立 Alembic。
29. 建立 OpenAPI metadata 规则。
30. 建立 pytest 基础测试。

## Phase 3 — Database and governance

31. 建立 PostgreSQL 初始核心表 migration 草稿。
32. 建立用户、角色、权限、菜单、组织架构表。
33. 建立集成配置、密钥、通知渠道表草稿。
34. 建立费用规则版本化表草稿。
35. 建立审计日志表草稿。
36. 建立 AI task / usage log 表草稿。
37. 建立 API 文档页面 PRP。
38. 建立 设置 > 系统配置 > 集成配置 PRP。
39. 建立 费用规则页面 PRP。
40. 输出阶段 CODEX_HANDOFF，并等待下一阶段批准。
