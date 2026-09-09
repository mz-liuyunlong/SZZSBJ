# Business Calculation Authority Rules

## Required Rules

- 前端只展示后端批准结果，不计算权威利润、费用、佣金、库存、补货或广告指标。
- AI 输出只能是 `candidate/suggestion`，不得写入权威计算结果。
- 只有获批 backend service 或可追溯 read model 可发布权威计算。
- 每个利润、广告指标、库存预警、补货建议和财务结果必须有 authority、rule version、calculation grain、输入 lineage、业务时间、审计和负责人批准。
- 公式、阈值、包含/排除、舍入和历史锁定必须版本化。
- 已锁定历史不因新规则自动重算；重算需要独立任务、审批、对账和回滚。

## Stop Conditions

来源、grain、公式、版本、币种、时区或 owner 任一不明确时，禁止发布权威结果。
