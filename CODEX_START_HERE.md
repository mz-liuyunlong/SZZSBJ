# Codex 启动入口

## 必读文件

Codex 接手本项目时，先读取：

```text
AI_ONBOARDING.md
AI_DAILY_RULES.md
AGENTS.md
RULE_PACK_FILE_INDEX.md
skills/README.md
docs/tools/AI_TOOLS_FIRST_RUN_SETUP.md
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

---

## 官方 Ponytail 插件要求

Codex 支持官方 Ponytail 插件时，应优先安装官方插件。

如果当前 Codex 环境尚未确认 Ponytail 插件，Codex 必须先建议并在用户确认后执行：

```bash
bash scripts/check-ai-tools.sh
bash scripts/setup-ai-tools.sh
```

或者直接执行：

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

安装后必须提醒用户：

```text
进入 Codex 后输入 /hooks，审查并信任 Ponytail hooks。
```

Codex 不得自动替用户信任 hooks。

如果官方插件不可用，Codex 必须继续按项目内置规则执行：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

---

## 进入开发前输出

Codex 修改代码前必须先输出：

1. 是否已检查官方 Ponytail 插件。
2. 当前使用官方 Ponytail 插件，还是项目内置 Ponytail 默认规则。
3. 本次任务类型。
4. 本次选择的 Skill 和 docs。
5. Ponytail 最小正确实现检查。
6. 实施计划。
7. 等用户确认。
