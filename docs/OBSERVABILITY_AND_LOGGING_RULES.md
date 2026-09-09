# Observability and Logging Rules

## Required Context

适用时记录 `request_id`、`run_id`、`batch_id`、actor、resource、action、status、duration、error code 和受控 scope 摘要。

## Rules

- 使用结构化日志和稳定事件名；日志不是业务状态或 audit 真源。
- API、task、sync、external client 和 calculation 必须能追踪开始、结束、失败、重试和持续时间。
- 监控至少覆盖错误率、延迟、任务失败/积压、sync lag、外部 API 失败、数据库连接和 DQ/freshness。
- 告警必须有 owner、阈值、去重、冷却、升级和恢复行为。
- 禁止记录 secret、完整 header/URL、密码、Cookie、原始大 payload、敏感金额明细或未脱敏 PII。
- 捕获异常时保留安全上下文，禁止 `except: pass`。

新增关键流程必须在 PRP 说明日志、指标、告警和运行手册边界。
