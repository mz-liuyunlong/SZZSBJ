# SZZSBJ v2 优化报告

## 已完成

- 已清理原 ZIP 中的 macOS 垃圾文件：`__MACOSX/`、`.DS_Store`、`._*`。
- 已移除原 ZIP 中的 `.git/` 目录，避免把本地 Git 历史带入新项目。
- 已保留原有规则、docs、skills、.cursor、.github 适配文件。
- 已按讨论新增 v2 规则目录和模板。

## 新增重点

```text
docs/00_RULE_PACK_V2_OVERVIEW.md
docs/01_PROJECT_DECISIONS.md
docs/architecture/
docs/business-rules/
docs/delivery/
docs/operations/
docs/database/
docs/tasks/FIRST_30_CODEX_TASKS.md
templates/frontend/src/config/navigation.ts
templates/backend/app/core/response.py
templates/backend/app/core/permissions.py
templates/backend/alembic/versions/0001_initial_skyc_v2_core_tables.py
```

## 关键定稿

```text
数据库：PostgreSQL
Python：3.13
Node：24
前端包管理器：npm
后端依赖管理：uv
API返回：{ success, data, error, meta, request_id }
API文档：数据中心 > API文档
帮助文档：页面右上角 ? 新标签页打开
权限：角色动态配置，代码只认 permissionKey
数据权限：每个页面独立配置
组织架构：支持部门、小组、组长、组员
费用规则：版本化 + 生效日期 + 失效日期 + 审计
集成配置：AI Token / 飞书 / Webhook 加密存储、脱敏展示
后台管理：不新增第二套独立后台系统
```

## 使用建议

将本 ZIP 解压到新项目根目录后，先让 Codex 读取：

```text
AI_DAILY_RULES.md
AGENTS.md
RULE_PACK_FILE_INDEX.md
docs/00_RULE_PACK_V2_OVERVIEW.md
docs/tasks/FIRST_30_CODEX_TASKS.md
```

然后按第一批 30 个任务逐步执行。
