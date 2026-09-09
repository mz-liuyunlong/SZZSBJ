# Financial Time and Currency Boundary Rules

## Canonical Contract

- 金额使用 Decimal / PostgreSQL Numeric，禁止 float。
- 金额必须有 `amount`、`currency_code`、`precision`、`scale`、`rounding_rule`。
- 换汇必须有实际 `fx_rate`、适用日期 `fx_date` 和来源 `fx_source`；来源别名 `rate_source/rate_date` 必须映射为 canonical 字段，不建立第二套契约。
- 时间必须区分 timezone-aware UTC system timestamp、业务 timezone 和来源时间。
- 日报/指标必须明确 `business_date`、grain、cutoff 和迟到数据规则。
- 历史订单和锁定期间不得使用最新规则或汇率静默重算；例外需要版本化重算任务和审批。

财务、利润、费用、佣金、广告、库存估值、结算和退款必须有专项 Source Decision/PRP、control totals、lineage、权限和 audit。

Canonical 字段以本文件及 Data Governance 金额契约为准；旧文档中的币种后缀字段示例只能作为来源/展示示例，不得创建第二套 canonical contract。
