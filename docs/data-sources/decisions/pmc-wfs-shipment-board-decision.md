# WFS 货件看板 M1 接口数据源决策

状态：M1 本地实施授权（2026-10-29 对话确认）；领星履约段 **NEED_OWNER_DECISION** 至专项核实前不得填造正式同步表。

## M1 范围

| 数据组 | 分类 | M1 来源 |
|---|---|---|
| 实际货件 identity、标签状态、关联 PK/店铺/商品 | NEW_SYSTEM_OWNED | `ops_wfs_creation_operations`、`ops_wfs_creation_tickets.result.labels`、快照内 `order`/`orders` |
| 店铺筛选项 | REBUILD_SYNC（维度） | `dim_lingxing_stores` + 账号/店铺数据范围 |
| 领星 SP/运输/到仓/Received/规范状态 | REBUILD_SYNC | **不读取**；API 返回 `lingxing_sync_status=PENDING`，数量字段 `null` |
| 旧 Walmart Receipt / 众壹混合 | ARCHIVE_ONLY | 禁止作为正式主链 |

## 行粒度

仅 `ticket.result.labels` 中已有 `shipment_id` 的货件进入看板；无货件号的创建过程仅在待发货「创建记录」跟进。

## 门禁

- 不调用领星/Walmart 实时 API。
- M1 不新增 MART/Alembic 表。
- 完整领星读模型与同步任务需后续决策与 PRP。
