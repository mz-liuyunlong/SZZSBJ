# 数据库规则

## 文件用途

本文件用于约束 AI 如何设计和修改数据库结构。

## 总原则

1. 数据库结构变更必须使用 Alembic migration。
2. 不允许手工修改生产数据库结构。
3. 新增表必须说明业务用途。
4. 新增字段必须说明业务含义。
5. 金额字段必须明确币种。
6. 时间字段必须明确时区语义。
7. 大表查询必须分页。
8. 常用筛选字段必须考虑索引。

## 字段命名

推荐：`created_at`、`updated_at`、`store_id`、`platform_order_id`、`ad_spend_usd`、`refund_amount_usd`、`cost_cny`。

不推荐：`money`、`amount`、`fee`、`data1`、`temp`。

## Alembic 规则

AI 不允许新增 Model 后忘记 migration；不允许修改 migration 而不说明影响；不允许删除已应用 migration。
