# 数据同步规则

## 文件用途

本文件用于约束平台数据同步任务的设计。Celery 规则管后台任务怎么写，本文件管数据同步业务怎么设计。

## 适用场景

- 同步订单
- 同步广告
- 同步库存
- 同步退款
- 同步结算
- 同步 Review
- 同步 Listing
- 同步 old-system 可读数据快照

## 同步任务必须记录

- sync_batch_id
- source_platform
- store_id
- task_id
- started_at
- finished_at
- status
- total_count
- success_count
- failed_count
- error_message

## 设计要求

1. 同步任务必须走 Celery。
2. 同步必须支持失败重试。
3. 同步必须防止重复写入。
4. 同步必须有增量策略。
5. 同步必须记录来源平台和同步批次。
6. 同步必须说明全量同步和增量同步边界。
7. 同步失败必须可追踪。
8. 大批量同步必须考虑限流。
