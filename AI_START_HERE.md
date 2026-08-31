# AI 从这里开始

## 入口顺序

AI 接手本项目时，先不要直接改代码。

必须先读取：

```text
AI_ONBOARDING.md
AI_DAILY_RULES.md
AGENTS.md
RULE_PACK_FILE_INDEX.md
skills/README.md
docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md
```

如果当前环境尚未确认官方 Ponytail 插件，AI 必须先帮助开发者完成 AI 工具首次配置检查。

有终端能力时，先建议并在用户确认后执行：

```bash
bash scripts/check-ai-tools.sh
bash scripts/setup-ai-tools.sh
```

然后再进入 Skill 自发现和开发计划。

---

## 修改代码前必须输出

1. 当前是否已做 AI 工具首次配置检查。
2. 当前是否检测到官方 Ponytail 插件或已执行安装引导。
3. 如果未安装官方插件，说明正在使用项目内置 Ponytail 默认规则。
4. 本次任务类型。
5. 本次准备读取哪些 Skill。
6. 本次准备读取哪些 docs。
7. Ponytail 最小正确实现检查。
8. 初步开发计划。
9. 风险点和需要用户确认的事项。

用户确认前，不得修改代码。
