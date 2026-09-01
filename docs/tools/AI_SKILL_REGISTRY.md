# AI Skill Registry — Project Rule Pack V1.0

本文件统一管理本项目允许参考的外部 AI Skill / 工具。

| Tool / Skill | Priority | Use For | Install Type | Production Dependency | Auto Allowed | Forbidden |
|---|---:|---|---|---:|---:|---|
| planning-with-files | P0 | 长任务计划、发现、进度持久化 | optional local/plugin | No | Yes, for long tasks | 不能覆盖 Project Rule Pack；不能修改 old-system |
| Context Engineering / PRP | P0 | 复杂功能生成施工图 | repo templates | No | Yes, before complex work | PRP 未确认不得开发 |
| Context7 | P0 | 查询第三方库最新文档 | local CLI/MCP | No | Yes, for library docs | 不提交 API Key / MCP Token |
| Playwright | P0 | 前端 E2E 页面验收 | frontend devDependency | No | Yes, for E2E | 不依赖生产库/真实账号 |
| Ponytail | P1 | 项目规则持续生效与工作流守卫 | project rule + local tool | No | Yes, as rule behavior | 不作为运行依赖；不假设 hook 一定存在；不能覆盖 AGENTS.md |
| Superpowers | P1 | AI 工作流增强：讨论、计划、TDD、评审 | plugin | No | Manual | 不得自主生产操作 |
| Vercel Agent Skills | P1 | React/UI/文档审查，Vercel优化分析 | local skill | No | Manual | 默认禁用 deploy-claimable |
| vercel-deploy-claimable | Forbidden | 自动部署 | none | No | No | 未明确批准不得使用 |

## Priority rule

外部 Skill 的优先级低于：

```text
用户最新指令 > AGENTS.md > AI_DAILY_RULES.md > 已确认 PRP > 本地 planning files > 外部 Skill
```

## Installation rule

外部 Skill 默认不进入项目依赖，不进入 Dockerfile，不进入 CI 必跑，不通过 postinstall 安装。

项目必须在未安装任何外部 AI Skill 的情况下仍然可运行。
