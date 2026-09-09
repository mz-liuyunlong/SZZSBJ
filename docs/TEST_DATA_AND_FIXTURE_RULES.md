# Test Data and Fixture Rules

## Required Rules

- 默认使用最小 synthetic fixture；不得复制真实生产客户、员工、订单、SKU、金额、Token 或 payload。
- Fixture 明确命名为 synthetic/mock/test，不能冒充真实数据或 Source Decision 证据。
- 测试隔离：独立数据库/transaction、确定性时间/ID、无网络、无共享状态泄漏。
- 需要外部契约样例时必须脱敏、最小化并记录来源版本和使用授权；不可逆匿名化仍需 Review。
- 财务/权限/边界测试覆盖舍入、币种、时区、scope 和失败路径，不使用真实凭据。
- 测试完成清理临时资源；不得清理非测试环境。
- Snapshot/fixture 变化必须可 Review，不用批量更新掩盖行为变化。

## Stop Conditions

来源不明、疑似生产数据、需要网络/真实账号或测试可能写非测试环境时停止。
