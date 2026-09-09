# Sync Task Boundary Rules

## Required Rules

- 同步任务只负责获批来源的采集、标准化和发布编排；不得直接修改权威业务表，除非 PRP 明确批准发布边界。
- 每次执行必须有 `run_id`、`batch_id`、幂等键、重试策略、失败记录、开始/结束时间和计数。
- 失败不得静默吞掉；重试必须有上限、退避和停止条件。
- 外部 API 成功不等于业务发布成功；采集成功不等于清洗成功；清洗成功不等于前端可见。
- RAW、DQ、lineage、watermark、分页、限流和 schema drift 必须按 Source Decision/PRP 处理。
- 前端同步按钮只创建后端任务或查询状态，不得直接调用外部平台。

## Forbidden Patterns

Route 内批量同步、无幂等 upsert、同步覆盖 manual value、凭据进入参数/日志、失败仍标记成功、任务直接发布未通过 DQ 的数据。

新增同步任务必须同 PR 更新 Data Interface 与 Task registries。
