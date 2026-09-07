# Codex Start Here — Project Rule Pack V1.0

Codex 每次进入项目必须先执行这份阅读顺序。

## 1. 必读文件

```text
1. AGENTS.md
2. AI_DAILY_RULES.md
3. RULE_PACK_FILE_INDEX.md
4. docs/00_RULE_PACK_V1_0_OVERVIEW.md
5. docs/tools/AI_SKILL_REGISTRY.md
6. docs/tools/AI_TOOL_PRIORITY_RULES.md
7. docs/tasks/FIRST_40_CODEX_TASKS.md
```

## 2. 任务判断

开始前先判断任务类型：

```text
普通小任务：按任务说明执行
复杂功能：先写 INITIAL_FEATURE.md，再生成 PRP
长任务：建立 .planning/current/task_plan.md / findings.md / progress.md
第三方库：先查 Context7 或官方文档
Ponytail 兼容：按 docs/PONYTAIL_COMPATIBILITY_RULES.md 做规则守卫，不作为运行依赖
页面 ready：必须补 Playwright E2E
```

任务涉及指定 Agent Skill 时，先阅读 `docs/delivery/agent-role-skill-routing.md`。后端接口或数据源调查任务还必须阅读 `docs/delivery/backend-data-source-decision-gate.md`。

新数据表、同步任务、API PRP、mart/read model、AI 数据使用或文档知识索引必须先检查 `docs/data-sources/database-layering-standard.md`；新字段、API response 字段、清洗任务或数据映射必须先检查 `docs/data-sources/field-standardization-standard.md`。

## 3. 禁止动作

默认禁止：

```text
修改 old-system
修改生产数据库
修改真实 .env / Token / Secret
运行同步任务
部署 / 重启服务
创建第二套后台系统
自动使用 vercel-deploy-claimable
让外部 Skill 覆盖 Project Rule Pack
```

## 4. PRP 流程

后端业务接口任务不能直接进入实现，必须先按 `docs/delivery/backend-data-source-decision-gate.md` 完成数据源决策，再编写并批准接口 PRP，最后才可实现。

复杂功能必须：

```text
templates/INITIAL_FEATURE.md
  ↓
PRPs/templates/prp_base.md
  ↓
用户确认
  ↓
.planning/current/
  ↓
开发和验证
```

PRP 未确认，不得动代码。
