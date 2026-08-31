# Claude Code 项目规则入口

Claude Code 接手本项目时，必须先读取：

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

Claude Code 支持官方 Ponytail 插件时，应优先安装官方插件。

如果尚未安装，请提示开发者在 Claude Code 中分别发送：

```text
/plugin marketplace add DietrichGebert/ponytail
```

然后发送：

```text
/plugin install ponytail@ponytail
```

如 Claude Code 要求审查或信任 hooks，必须由用户确认。

如果官方插件不可用，Claude Code 必须继续按项目内置规则执行：

```text
docs/PONYTAIL_COMPATIBILITY_RULES.md
```

---

## 强制边界

Ponytail 只能用于减少过度设计、优先复用和最小正确实现。

不得覆盖：

- `old-system/` 只读规则
- 安全和密钥规则
- 权限和操作日志规则
- API 契约
- 数据库迁移
- Celery 幂等性
- 财务计算口径
- 测试与验收
- 维护型注释
