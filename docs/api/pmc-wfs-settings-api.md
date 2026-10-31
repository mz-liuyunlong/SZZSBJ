# WFS 设置 API（店铺 Walmart 创建设置，2026-10-31）

前缀 `/api/pmc/wfs/settings`。读 `page:pmc:wfs:view`，写 `action:pmc:wfs-settings:manage`；来源账号与店铺数据范围同看板。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /stores | 当前范围内全部领星店铺 + 设置：`store_id`、`store_name`、`suggested_code`（店铺名前缀推断，仅建议）、`walmart_store_code`、`reviewed_code`（服务器 `SZZSBJ_WALMART_SCF_STORE_ID_MAP` 审核映射）、`mapping_state`（unset / ok / unreviewed / conflict）、`its_enabled`、`creation_enabled`、`note`、`actor_uid`、`updated_at` |
| PUT | /stores/{store_id} | upsert：`source_account_ref`、`walmart_store_code`（`^(HK|CN)\d{4}$`）、`its_enabled`、`creation_enabled`、`note?`。同账号内代码重复 → 409 `WFS_STORE_CODE_TAKEN`；店铺不在账号内 → 404；记录操作人与时间 |

表：`ops_wfs_store_settings`（迁移 0072）。创建适配器在「确认创建」前读取：无行或代码非法 → 409 `WFS_STORE_NOT_CONFIGURED`；`creation_enabled=false` → 409 `WFS_STORE_CREATION_DISABLED`；选 ITS 但 `its_enabled=false` → 409 `WFS_ITS_NOT_AVAILABLE`；与服务器审核映射不一致 → 409 `WFS_STORE_MAPPING_CONFLICT`。

负责人 2026-10-31：八店（HK2612/2613/2614/2615、CN2501/2601/2602/2603）均有 ITS；CN2502 不参与。
