# Context7 本机配置指南

## 1. 用途

Context7 用于让 Codex、Cursor、Claude Code、其他 AI 在开发时查询最新第三方库文档。

它不属于 本项目 生产系统，不需要部署到服务器。

## 2. 推荐安装

在开发者本机执行：

```bash
npx ctx7 setup
```

按提示选择适合当前 AI 工具的模式。

## 3. 不允许提交的内容

```text
Context7 API Key
MCP Token
OAuth 缓存
本机 MCP 配置中的密钥
任何 Authorization Header
```

## 4. 项目规则

- 不要把 Context7 加进 `frontend/package.json`。
- 不要把 Context7 加进 `backend/pyproject.toml`。
- 不要在 CI、Docker、postinstall 中自动安装 Context7。
- AI 只能把 Context7 当作文档查询工具。

## 5. 使用建议

当 AI 要写第三方库相关代码时，在任务中加入：

```text
涉及第三方库用法时，请先使用 Context7 或官方文档核对，不要凭记忆写。
```
