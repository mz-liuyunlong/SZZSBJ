# Planning with Files Standard — Project Rule Pack V1.0

## 1. Purpose

长任务必须把计划、发现、进度写到磁盘，避免模型上下文满、`/clear`、压缩失败或换会话后丢方向。

## 2. When required

以下任务必须使用文件化计划：

```text
超过 30 分钟
超过 5 个文件
跨前后端
跨数据库
跨权限
跨 old-system 分析
涉及费用规则、AI Token、导入导出、审批、数据权限
```

## 3. File location

默认写入：

```text
.planning/current/task_plan.md
.planning/current/findings.md
.planning/current/progress.md
```

## 4. File purpose

| File | Purpose |
|---|---|
| task_plan.md | 阶段、任务、勾选项、验收标准 |
| findings.md | 调查发现、旧系统读取结果、风险、证据 |
| progress.md | 操作记录、命令、测试、失败原因、下一步 |

## 5. Git rule

`.planning/` 默认不提交 Git。阶段结束后，把重要信息整理到：

```text
CODEX_HANDOFF.md
docs/DECISION_LOG.md
```

## 6. Resume rule

AI 恢复任务时，必须先读：

```text
AGENTS.md
AI_DAILY_RULES.md
.planning/current/task_plan.md
.planning/current/progress.md
CODEX_HANDOFF.md
```

## 7. Boundary

planning files 不能覆盖用户最新指令，也不能覆盖 Project Rule Pack 安全边界。
