# Data Quality and Freshness Rules

## Required Rules

- 每个数据集声明 grain、必填、唯一性、类型、枚举、范围、关系、freshness/SLA 和 owner。
- DQ 结果使用明确动作：pass、warn、reject、quarantine、owner review；不得静默丢弃或猜测补值。
- Freshness 必须区分 source event time、business date、ingested/processed/published time。
- “任务刚运行”不等于来源新鲜；read model 更新时间不等于源数据时间。
- DQ/freshness 阈值必须版本化并有适用范围，不得散落在前端。
- 财务、库存、广告等高风险数据在 DQ 未通过时不得发布权威结果。
- API/UI 必须明确 partial/stale/warning 行为。

新增检查或 freshness contract 必须更新 Data Interface Registry 和相关 PRP/metric contract。
