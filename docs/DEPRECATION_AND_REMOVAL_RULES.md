# Deprecation and Removal Rules

## Required Rules

- 弃用先标记 `deprecated`，记录 replacement、owner、消费者、截止条件和迁移计划。
- 替代决定使用 `superseded` 并链接新条目；不得改写历史证据。
- 删除前搜索代码、API、registry、page、task、数据、文档和外部消费者。
- API/字段删除需要兼容窗口、通知、监控和 version strategy。
- 数据表/列删除需要独立 migration PRP、备份/恢复和数据保留决定。
- 旧系统、历史文档、audit/RAW/财务证据不得因“看似无用”直接删除。
- 删除是写操作，由独立任务和负责人批准；不得在无关 PR 顺手清理。

## Completion

移除后同步更新 Interface/Page/Task/Module/Component registry，并验证无死链接和无运行消费者。
