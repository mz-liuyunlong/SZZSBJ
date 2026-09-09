# Performance and Pagination Rules

## Required Rules

- 列表和大表查询默认服务端分页、筛选和排序；禁止全表加载后在前端筛选。
- 分页 contract 使用项目既有 `page/page_size`，并设边界和最大值；改变方式需 API contract 批准。
- 查询必须声明 grain、data scope、稳定排序和适用索引；禁止无界 `SELECT *`。
- 批量、报表、导入导出和外部 API 调用必须限定规模、并发、速率、timeout 和取消/失败策略。
- 前端高密度表格使用统一内部滚动，不渲染无限数据。
- 优化必须基于测量证据，不得为假设流量预建 cache/read model。

## Stop Conditions

查询可能影响生产、缺少过滤/索引证据、计划全量载入或需要新增 read model 时停止并单独评估。
