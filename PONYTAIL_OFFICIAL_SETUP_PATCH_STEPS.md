# Ponytail 官方安装辅助补丁 v1.4.4 使用步骤

## 适用场景

你已经安装了 v1.4.3 规则包，现在希望：

- 其他开发者拉取项目后，不需要自己看说明。
- AI 第一次接手项目时，主动帮开发者检查并安装官方 Ponytail 插件。
- 支持官方插件的工具优先安装官方插件；不支持时使用项目内置规则兜底。

---

## 安装补丁

把补丁 ZIP 解压到项目根目录，覆盖同名文件。

项目根目录是 `.git/` 所在目录。

---

## 安装后新增文件

```text
AI_ONBOARDING.md
docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md
scripts/check-ai-tools.sh
scripts/setup-ai-tools.sh
```

---

## 新开发者第一次拉取项目后

把这段发给 AI：

```md
你现在第一次接手本项目。请先读取 AI_ONBOARDING.md、AI_DAILY_RULES.md、AGENTS.md、RULE_PACK_FILE_INDEX.md、skills/README.md、docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md。

先不要开发业务代码。请先检查并帮助安装当前工具支持的官方 Ponytail 插件；如果需要 hooks 信任，请停下来让我确认。安装失败时，使用项目内置 Ponytail 默认规则。
```

AI 有终端能力时，会建议执行：

```bash
bash scripts/check-ai-tools.sh
bash scripts/setup-ai-tools.sh
```

---

## 提交 Git

```bash
git add AI_ONBOARDING.md AI_DAILY_RULES.md AGENTS.md AI_START_HERE.md CODEX_START_HERE.md CLAUDE.md README_AI_RULES.md RULE_PACK_FILE_INDEX.md INSTALL_TO_PROJECT.md RULE_PACK_CHANGELOG.md docs tools scripts skills .cursor .github
git commit -m "docs(ai): add first-run official Ponytail setup"
```

如果没有 `tools/` 目录，忽略该项。
