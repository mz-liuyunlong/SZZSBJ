# SZZSBJ Rule Pack v2.0 使用说明

## 这是什么

这是 SKYC V2 新系统重建项目的 AI 开发规则包。它不是业务系统代码，而是用于约束 Codex、Cursor、Claude Code、GitHub Copilot、其他 AI 开发助手以及人类开发者的工程制度包。

本版本已经按 2026-09-01 的讨论重新优化，重点补齐：

- PostgreSQL 新库架构
- FastAPI 后端框架规则
- React + Ant Design 前端框架规则
- API 文档页面
- 页面右上角帮助 / SOP 入口
- 动态权限、角色、页面权限、动作权限、数据权限
- 组织架构、小组长、组员、产品负责人归属
- 费用规则版本化、生效日期、历史重算、月结锁账
- AI Token、飞书群、Webhook、外部密钥安全管理
- 数据中心 API 文档入口
- 不新增第二套后台管理系统
- CI 质量门禁与 Codex 任务验收格式

## 最重要的原则

```text
不要让 AI 快速堆代码。
要让 AI 在固定规则、固定目录、固定接口契约、固定验收标准下做小任务。
```

## 新项目定位

- 新系统是 greenfield 重建项目。
- 旧系统代码只能放在 `old-system/` 只读参考。
- 新系统代码只能写在 `frontend/`、`backend/`、`docs/`、`scripts/`、`.github/` 等明确目录中。
- 不允许在旧系统里继续开发。
- 不允许把旧系统混乱架构复制到新系统。

## 日常开发先读顺序

AI 每次接手任务时，先读：

```text
1. AI_DAILY_RULES.md
2. AGENTS.md
3. RULE_PACK_FILE_INDEX.md
4. docs/00_RULE_PACK_V2_OVERVIEW.md
5. skills/README.md
```

然后按任务类型选择性读取相关 docs 与 skills，不要一次性读取全部文件。

## 规则冲突处理

如果旧规则和 v2 新规则冲突，以这些文件优先：

```text
AGENTS.md
AI_DAILY_RULES.md
docs/00_RULE_PACK_V2_OVERVIEW.md
docs/01_PROJECT_DECISIONS.md
docs/architecture/*
docs/business-rules/*
docs/delivery/*
```

AI 不允许自行选择更方便的规则。遇到冲突必须停止并问项目负责人。

## 推荐给 Codex 的启动提示词

```md
你现在参与 SKYC V2 新系统重建项目。请先读取：

1. AI_DAILY_RULES.md
2. AGENTS.md
3. RULE_PACK_FILE_INDEX.md
4. docs/00_RULE_PACK_V2_OVERVIEW.md
5. skills/README.md

然后根据任务类型选择相关 docs 与 skills。不要一次性读取全部文件。不要修改 old-system。不要连接生产数据库。不要调用真实外部 API。不要部署。不要自行更换技术栈。

本次任务是：{填写任务}

请先输出：
1. 本次任务类型判断
2. 需要读取的 docs / skills
3. 不需要读取的 docs / skills
4. 允许修改范围
5. 禁止事项
6. 开发计划
7. 验收标准

等我确认后再修改代码。
```
