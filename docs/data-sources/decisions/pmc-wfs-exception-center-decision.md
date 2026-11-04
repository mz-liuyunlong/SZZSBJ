# WFS 异常中心 M1 接口数据源决策

状态：M1 本地实施授权（2026-10-29 对话 Q1–Q7 确认）；领星履约与设置规则 **NEED_OWNER_DECISION** 至专项 PRP 前不得填造正式同步/配置读模型。

## M1 范围

| 数据组 | 分类 | M1 来源 |
|---|---|---|
| 异常案件、处理时间线、检测事件 | NEW_SYSTEM_OWNED | `ops_wfs_exception_cases`、`evt_wfs_exception_detections`、`evt_wfs_exception_actions` |
| 货件身份、店铺、PK/商品展示字段 | NEW_SYSTEM_OWNED（关联） | 案件写入时冗余；可关联 `ops_wfs_creation_*` / 看板 `row_id` |
| 履约事实（到仓/收货/短少判定） | REBUILD_SYNC | **不读取**；自动规则引擎 M1 为 STUB，返回「无法判断」 |
| 规则版本与阈值 | NEW_SYSTEM_OWNED（配置） | `rule_version=M1_STUB`；设置 Tab PRP 前不读版本化配置表 |
| 旧 HTML/demo 异常 | ARCHIVE_ONLY | 禁止作为检测输入 |
| `warehouse_wfs` 费用异常 | 独立领域 | 禁止复用其案件表或规则 |

## 门禁

- 不调用领星/Walmart 实时 API；不自动提交平台申诉。
- M1 不做 Celery 全量重算、通知、附件存储。
- 检测与案件去重键：`source_account_ref + store_id + shipment_id + rule_family + item_key`。

## 联调数据

- 生产路径不 seed 假案件。
- pytest 与隔离 schema 写入样例案件；本地空列表为正常态。
