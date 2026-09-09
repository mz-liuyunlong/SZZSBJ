# External API Client Rules

## Required Rules

- 外部客户端位于 `backend/app/integrations/` 的 provider 边界；route、repository 和 frontend 不直接调用外部平台。
- 每个 endpoint 先有 Source Decision、Data Interface Registry 条目、PRP 和负责人批准。
- 客户端统一处理认证引用、timeout、限流、重试/backoff、分页、错误映射、schema drift 和脱敏日志。
- 凭据只通过 `secret_ref` 解析，不进入参数、任务消息、RAW 或日志。
- 批量采集走批准的后台任务；业务 API request path 不实时批量拉取。
- 外部成功只表示 transport/provider 成功，不表示 RAW、清洗、DQ 或发布成功。
- 响应在发布前保留获批 RAW/lineage 并标准化；不得直接作为权威 API 返回。

## Stop Conditions

官方契约、授权、费用、限流、重试安全、RAW 或 secret boundary 未确认时不得调用真实 API。
