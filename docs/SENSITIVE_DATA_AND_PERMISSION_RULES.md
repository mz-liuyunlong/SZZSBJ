# Sensitive Data and Permission Rules

## Required Rules

- 数据按 public/internal/confidential/secret 及适用业务敏感级别分类。
- 后端同时执行 page、action、data scope、field、export 和 high-risk permission；前端隐藏不是安全控制。
- 未知、缺失或 `none` scope 必须 fail closed。
- 财务、成本、利润、员工、客户、店铺凭据、身份和审计数据最小化返回、脱敏记录并限制导出。
- Service/repository 不信任客户端声明的管理员、全店铺或字段可见性。
- 测试、日志、错误、AI 输入和截图不得包含未经授权的真实敏感数据。
- 高风险写入需要二次确认、必要审批、幂等、audit 和可回滚。

新增敏感字段、权限 key 或 data scope 必须有独立 PRP/负责人批准，并更新相应 registry/contract。
