# Data Interface Registry Rules

## Authority

`docs/data-registry/DATA_INTERFACE_REGISTRY.md` 是正式 GitHub 真源。飞书表格只能是人工查看副本或同步镜像，不得反向覆盖仓库决定。

## Update Triggers

任何新增或变更的外部接口、内部 API、同步任务、导入导出、数据库表、read model、通知/Webhook 或前端数据依赖，必须在同一 PR 更新 registry。

Registry 必须回答：使用哪个接口、RAW 存哪里、进入哪一清洗层、Core 表、read model、后端 API、前端页面、permission key、批准/实现 PRP 与 PR。

## Required Rules

- 未合并或未实现能力不得标记 `implemented`。
- Secret 只记录 `secret_ref`，不记录真值、URL、header 或连接串。
- 每个条目必须有稳定 ID、owner、status、来源/目标、权限和证据。
- 状态至少包括 `planned`、`candidate`、`approved`、`implemented`、`deprecated`、`superseded`、`blocked`。
- External、storage、API、frontend、sync 和 notification 条目必须用 ID 互相引用，不复制互相冲突的契约。

## Stop Conditions

来源、权威、RAW、permission、owner、状态或 PRP 不明确时保持 `candidate/blocked`，不得开始实现或虚构值。
