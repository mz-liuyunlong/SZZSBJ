# AI 新人接手项目启动流程

## 文件用途

本文件给第一次拉取本项目的开发者和 AI 使用。

目标不是让人手动阅读所有规则，而是让 AI 在接手项目时主动完成环境检查、Ponytail 官方插件安装引导、项目规则读取和开发前计划。

---

## 新人拉取项目后的第一条 AI 指令

开发者拉取项目后，可以直接把下面这段发给当前使用的 AI：

```md
你现在第一次接手本项目。

请先读取：

1. `AI_ONBOARDING.md`
2. `AI_DAILY_RULES.md`
3. `AGENTS.md`
4. `RULE_PACK_FILE_INDEX.md`
5. `skills/README.md`
6. `docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md`

然后先不要开发业务代码。

请先帮我完成：

1. 判断当前我使用的 AI 工具类型。
2. 检查本机是否可以安装官方 Ponytail 插件。
3. 如果当前工具支持官方 Ponytail 插件，请帮我执行或给出安装命令。
4. 如果需要我手动信任 hooks，请明确停下来让我确认。
5. 如果当前工具不支持官方 Ponytail 插件，请启用项目内置 Ponytail 默认规则。
6. 输出本项目规则读取顺序和后续开发流程。
```

---

## AI 必须主动做的事

AI 不得假设开发者会自己看文档。

第一次接手本项目时，AI 必须主动：

1. 读取 `docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md`。
2. 检查是否存在 `scripts/setup-ai-tools.sh`。
3. 建议开发者执行：

```bash
bash scripts/setup-ai-tools.sh
```

4. 如果当前 AI 具有终端执行能力，可以在开发者确认后执行该脚本。
5. 执行后提示开发者检查并信任 Codex / Claude Code 等工具的 hooks。

---

## 重要边界

Ponytail 官方插件安装属于开发者本机 AI 工具配置。

AI 可以帮助安装，但不得：

1. 偷偷修改全局工具配置。
2. 偷偷信任 hooks。
3. 把官方插件安装写入 `npm install`、`postinstall`、CI、Vercel 或 Docker 构建流程。
4. 用 Ponytail 简化原则覆盖项目强制规则。

如果官方插件安装失败，AI 仍必须使用项目内置规则：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```
