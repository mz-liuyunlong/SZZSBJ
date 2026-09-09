# Error Handling and Safe Message Rules

## Required Rules

- 后端使用 Backend API Foundation 的统一 envelope、稳定 error code 和 `request_id`。
- 用户消息说明可采取的动作，不暴露 stack trace、SQL、表结构、secret、内部主机或外部凭据。
- 详细诊断只进入脱敏日志并通过 request/run ID 关联。
- 已知业务错误、权限拒绝、验证错误、外部依赖失败和未知异常必须分开映射。
- 禁止吞异常、返回虚假成功、用空值掩盖失败或将外部错误原文直传用户。
- 前端必须区分 loading、empty、error、permission denied、stale/partial，并只在安全且幂等时提供 retry。
- 批量任务保留失败记录和 partial-success 语义，不静默丢行。

## Stop Conditions

无法安全分类错误或消息可能泄密时，fail closed 并由负责人/安全 Review。
