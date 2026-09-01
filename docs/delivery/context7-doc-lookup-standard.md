# Context7 文档查询规则

## 1. 定位

Context7 是 AI 开发辅助工具，用于查询第三方库、框架、SDK、CLI 的最新文档和版本相关示例。

它不是 本项目 的生产运行依赖，也不是前端或后端业务依赖。

```text
Context7 = 帮 AI 查最新库文档
Playwright = 浏览器级 E2E 页面验收
AGENTS.md = 项目最高规则
```

## 2. 什么时候必须使用 Context7 或官方文档

当任务涉及以下内容时，AI 必须先核对 Context7 或官方文档，再写代码：

```text
第三方库 API 用法
第三方库配置
依赖升级
脚手架初始化
测试工具配置
框架新版本迁移
SDK 调用方式
CLI 命令参数
```

适用库包括但不限于：

```text
FastAPI
Pydantic
SQLAlchemy
Alembic
Celery
Redis
React
Vite
Ant Design
ProComponents
React Router
TanStack Query
Zustand
ECharts
Playwright
OpenAI SDK
任何新引入依赖
```

## 3. 禁止事项

未经项目负责人明确授权，AI 不允许：

```text
把 Context7 加入 frontend/package.json
把 Context7 加入 backend/pyproject.toml
把 Context7 加入生产 Dockerfile
把 Context7 加入 CI 必跑依赖
通过 postinstall 自动安装 Context7
把 Context7 API Key / MCP Token / OAuth 信息写入仓库
把 Context7 查询结果当成项目规则的上位规则
```

## 4. 推荐使用方式

第一阶段推荐开发者本机使用 CLI + Skills：

```bash
npx ctx7 setup
```

可选 MCP 模式仅在对应 AI 工具明确支持、并由项目负责人批准后配置。

MCP / API Key 必须只存在于本机安全配置或受控密钥系统中，不得提交到 Git。

## 5. 完成报告要求

如果本次任务使用了 Context7，AI 完成报告必须写明：

```text
查询了哪个库
查询了哪个版本
查询了什么问题
采用了哪些文档结论
是否仍有不确定点
```

示例：

```text
Context7 checked:
- library: /microsoft/playwright
- query: Playwright config for Vite React app
- conclusion: use @playwright/test under frontend, E2E runs separately from Vitest
- uncertainty: none
```

## 6. 可信度与冲突处理

Context7 查询结果只能作为开发参考。

如出现冲突，优先级如下：

```text
1. 项目负责人明确指令
2. AGENTS.md / AI_DAILY_RULES.md
3. 项目 docs/architecture、business-rules、delivery
4. 官方文档
5. Context7 查询结果
6. AI 自身记忆
```

如果 Context7 文档与项目规则冲突，必须停止并询问，不得自行选择。

如果 Context7 文档与官方文档冲突，以官方文档为准。

## 7. 安全规则

```text
Context7 不得绕过 old-system 只读规则。
Context7 不得绕过密钥保护规则。
Context7 不得绕过 PostgreSQL / FastAPI / React 技术选型。
Context7 不得作为理由引入未批准的新依赖。
Context7 不得作为理由跳过测试、类型检查、CI、Code Review。
```

## 8. Codex 任务提示模板

当任务涉及第三方库时，可以要求 AI：

```text
本任务涉及第三方库，请先使用 Context7 或官方文档核对当前版本用法。
完成报告中必须写明查询过的库、版本、结论和不确定点。
不得把 Context7 加入生产依赖、CI 必跑依赖或前后端业务依赖。
```
