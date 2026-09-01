# AI Tool Install Guide — Project Rule Pack V1.0

## 1. Default rule

外部 AI Skill / Plugin / MCP 默认只做本地开发辅助，不进入项目运行依赖。

禁止自动写入：

```text
frontend/package.json
backend/pyproject.toml
Dockerfile
CI 必跑步骤
postinstall
生产服务器
```

除非项目负责人明确批准。

## 2. Secret rule

以下内容不得提交：

```text
Context7 API Key
MCP Token
OAuth 信息
OpenAI / Claude / Decodo / 飞书 Token
Webhook Secret
数据库连接串
SSH 私钥
```

## 3. Recommended local setup

可以在开发者本机安装：

```text
Context7: 用于查库文档
planning-with-files: 用于长任务计划持久化
Superpowers: 用于流程增强
Vercel Agent Skills: 用于 React/UI/文档审查
Ponytail: 用于项目规则持续生效与 AI 工作流守卫
```

但安装与否不能影响项目本身能否运行。


## 4. Ponytail boundary

Ponytail-compatible rules are included in the project rule pack, but Ponytail is not a runtime dependency. Local installation is separate from repository setup.
