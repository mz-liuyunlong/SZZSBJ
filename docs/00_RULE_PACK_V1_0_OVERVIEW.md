# Project Rule Pack V1.0 Overview

## 1. 定位

Project Rule Pack V1.0 是 新系统重建项目的 AI 工程治理包。

它不是前后端业务代码，也不是生产依赖。它负责约束 Codex、Claude、Cursor、Copilot 等 AI 在项目中的工作方式。

## 2. V1.0 包含什么

```text
AGENTS.md                       项目最高规则
AI_DAILY_RULES.md                AI 每日执行规则
CODEX_START_HERE.md              Codex 入口
docs/architecture/               架构规则
docs/business-rules/             业务口径规则
docs/delivery/                   交付、测试、PRP、SOP、E2E 规则
docs/tools/                      AI 工具治理规则
PRPs/templates/                  项目专用 PRP 模板
templates/planning/              长任务计划模板
templates/frontend/              前端模板
templates/backend/               后端模板
skills/                          项目内 AI Skill 参考
```

## 3. 核心原则

```text
安全边界优先
PRP 先于复杂开发
文件化计划防止上下文丢失
Context7 先查文档再写第三方库代码
Playwright 验收页面真实可用
API 文档和 SOP 是完成标准的一部分
外部 Skill 只能辅助，不能覆盖 Project Rule Pack
Ponytail-compatible rules keep project rules active but are not runtime dependencies
```

## 4. 版本

```text
Rule Pack: Project Rule Pack V1.0
```
