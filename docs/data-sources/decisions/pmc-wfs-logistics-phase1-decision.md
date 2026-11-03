# PMC WFS · 物流组第一期数据源决策

- Status: Approved for implementation (phase 1, read-only)
- Decision date: 2026-11-03
- Owner authorization: Rocky 2026-11-02 / 2026-11-03（WFS 物流板块上线；按 8088 业务逻辑上线；Walmart 数据用已校验文件，不新增 Walmart 调用）；PRP #298 由 Rocky 2026-11-03 批准（刘云龙授权 Rocky 为 PRP 负责人）：一期 a + b，D-1=A、S8 只读已校验文件、D-2 维持、D-3 开放、D-4 手工一次性运行、物流页一期用 `page:pmc:wfs:view`
- Plan: `PRPs/pmc-wfs-logistics-group.md`（§6.2 D-1 方案 A、§6.4 归属规则）

## Purpose

确定 WFS 货件看板、异常中心、待发货打包单、物流看板第一期的数据来源和写入边界。第一期全部只读：不写 Walmart、不写领星、不改生产数据。

## Authoritative sources

| Data | Authoritative source | Lineage |
| --- | --- | --- |
| WFS 货件、商品行 | 领星 `wfsCargoPage` 经 Integration Sync RAW/ODS，发布到 `mart_wfs_shipment_board` | run id、RAW request ref、发布版本 |
| SP 发货单 | 领星 `wfsShippingListPage`，同上 | 同上 |
| Walmart 签收日、逐 Item 签收与破损、Receipt 上架流水 | 一店一服务器采集并校验过的文件 `walmart/<store_id>/{shipments,items,inventory_log}.csv`，经 `raw_pmc_wfs_source_files` → `ods_walmart_wfs_*` | 文件 sha256、路径、行数、批次 |
| 物流商轨迹（众壹） | 已采集文件 `zhongyi/{orders_summary,orders_track}.csv` → `ods_carrier_zhongyi_*` | 同上 |
| 物流渠道名称 | 领星渠道字典文件 `lingxing/logistics_channels.csv` → `ods_lingxing_logistics_channels` | 同上 |
| Item ID | `dim_walmart_listings`（店铺 × MSKU） | 已有维表 |
| 产品负责人 | `dwd_lingxing_sku_product_info_current`（按 SKU） | 已有维表 |

## Required rules

1. 到仓 / 可售 / 分段 / 异常全部按 8088 口径（到仓链路、可售 = 首批上架或到仓 + 10 天、规则版本 `WFS-RULES-20261010`）；用 2026-11-02 数据回放核对：897 张货件到仓结果、84 条异常（含描述）、635 个产品行与 8088 逐条一致。
2. 文件加载只接受已校验的采集产物；同一文件 sha256 重复加载直接跳过；新文件成为该店铺该接口的当前文件，旧文件保留可追溯。加载不调用任何外部接口。
3. 缺失的数据源保持空（页面显示“—”），不得补 0 或编造；Walmart 未覆盖的店铺照常显示领星数据。
4. 与“今天”相关的字段（已过天数、分段、申诉剩余天数）按 8088 口径用**数据日**计算（8088：`TODAY = 数据日`），即当前发布版本记录的 `as_of`；还没有发布版本时用上海时间当天。每天刷新时数据日就是当天。
5. 异常中心：规则命中建单或刷新；不再命中由系统自动解决（留动作记录）；人工解决 / 关闭的案件系统不重开；测试货件（`PMC-TEST-`）不建单。
6. 打包完成满 3 天仍有箱子未安排到货件标红；天数后续由 WFS 设置 `wfs.pending_packing_overdue_days` 修改，第一期固定 3。
7. PK 与 OWS 关联对账不恢复；操作人不写死，由权限控制。
8. 物流看板按 8088 `pmc-logistics`（`build_from_daily.py` + `app-a.jsx enrich`）：只看 2026-07-01 起的 SP，排除 `PMC-TEST-` 货件及其 SP；读当前发布版本的领星发货单 / 货件 + 当前已加载的渠道、众壹、Walmart 文件；数据日同规则 4。2026-11-02 回放：393 张 SP 全部派生字段与 8088 一致（异常 580 条、可索赔合计 350,938.2）。
9. 物流渠道文件加载保留 `raw_json` 中的 `method_name` / `remark` / `enabled`（仓库代码 / 渠道代码）；此前加载的同一文件再次加载时只就地补这几个字段，不删不重建。
10. D-2：#282 写入代码维持现状（`DisabledGateway`、`guard_write`、人工书面批准）；D-3：异常中心处理状态 / 负责人 / 记录开放，只写本系统；D-4：领星数据手工一次性运行。

## Approved implementation scope

- 迁移 0076（文件登记 + 6 张 ODS 表，#302 占用），文件加载、看板事实、8088 规则移植、异常检测、看板 / 异常中心 / 待发货页面改造、本地回放脚本和测试。
- 物流看板 `pmc_logistics`（`/api/pmc/logistics/board`、`/shipping-lists/{code}`，只读、按店铺数据范围过滤）与 5173 页面；无新迁移、无新权限键。

## Explicitly not approved

- 任何 Walmart / 领星 / 众壹真实调用，生产迁移、生产数据加载、调度启用、部署或重启（由部署流程另行批准）；服务器入库定时、领星定时同步另行出票。
- 写回 Walmart（建货件、取消、改数量）与箱规写回领星：第二期，单独立项。

## Stop conditions

- 文件校验不通过、sha256 与采集记录不一致、店铺身份不明。
- 回放结果与 8088 不一致且原因不明。
- 需要扩大到生产写入或未批准的数据源。
