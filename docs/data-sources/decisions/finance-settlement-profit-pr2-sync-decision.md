# 财务 · 结算利润 PR-2（发货单 / 发货单明细 / 销售出库单同步）数据源决策

- 调查日期：2026-11-16（发货单、明细探测）、2026-10-26（销售出库单拉取）、2026-11-26（本决策）
- 调查人：Rocky 侧代码 AI（财务板块）
- 目标接口（领星 OpenAPI，均 POST、只读、query sign 鉴权）：
  - `/basicOpen/multiplatform/query/shippingList`（查询平台仓发货单列表 v2，LX-9D5A176AC470）：`platformCodes=["10008"]`（只查 Walmart）、`storeIds=[store_id]` 一次一店、`timeField=2`（发货时间）+ `startTime/endTime`、`offset/length`；响应 `data.list[]` + `data.total`（字符串）
  - `/basicOpen/multiplatform/query/shippingDetail`（查询平台仓发货单详情，LX-418571887440）：`shippingListCode` 一次一张；响应 `data.firstLetListResponseList[]`（发货单 × MSKU 的货本：采购价、出库头程、头程费用、税、单位成本）
  - `/erp/sc/routing/wms/order/wmsOrderList`（查询销售出库单列表，LX-FD9302CF208A）：`sid_arr=[store_id]` 一次一店、`time_type=update_at` + `start_date/end_date`、`page/page_size`（上限 200）；响应 `data[]` + 顶层 `total`
- 业务用途：订单审核的货本与头程（PRP §8.3）、结算利润里非 WFS 自发货订单的尾程物流费用（§8.5）。三份数据落 #365 建好的 `ods_lingxing_fin_shipping_lists` / `ods_lingxing_fin_shipping_detail_items` / `ods_lingxing_fin_wms_outbound_orders`，原始响应进 `ods_api_raw_blobs` + `ods_api_raw_request_refs`。
- 接口总体状态：**READY_FOR_PRP**（PRP `finance-settlement-profit-v3.md` §10 PR-2；本 PR 实现）
- 是否包含 NEED_OWNER_DECISION：否（Rocky 2026-11-26 已定「开始做」；打开、回填、定时各要单独授权）

## 口径

1. 发货单按**发货时间**取窗：没发货的单子没有实际成本，等发货后进入滚动窗再拉。表里是当前状态（按发货单号 upsert），内容没变不动 `updated_at`。
2. 明细只拉**已发货**（`shippingListStatus=2`）、发货时间在窗内、且「明细没拉过（发货单 `detail_synced_at` 为空）」或「发货单在明细之后变过（`detail_synced_at` < `updated_at`）」的单子（迁移 0099 加这一列）；拉完在同一事务里 upsert 新明细、删掉这张单不在新集合里的 MSKU 行、记 `detail_synced_at`——明细为空也记，不反复重拉。同一 MSKU 在一张单里出现多次把发货量加总、单价取第一条（`raw_row.merged_rows` / `merged_delivery_num` 记合并结果，行指纹按合并后算）。
3. 销售出库单按**变更时间**取窗（出库后运费会被补分摊，`update_at` 会往后挪），按出库单号 upsert；`platform_order_no` 取接口数组第一个；`items` 只留 MSKU、数量、分摊运费、库存成本等计算要用的键。
   - `sid_arr` 传的是多平台店铺 ID（`dim_lingxing_stores.store_id`）：2026-10-26 的拉取脚本就是这样传的（9 家店 ID 直接作 `sid_arr`），返回行的 `sid` 与传入值一致，拉到的单数与本地归档一致（数字不入库）；本账号的 Walmart 店铺 ERP `sid` 与多平台 `store_id` 是同一个值。代码再加一道保险：返回行 `sid` 与请求的店不一致就整页判脏（`SYNC_FIN_WMS_INVALID_ROW`），不会悄悄写 0 条当成功（#370 复审 P1）。
4. 收件人、电话、地址、邮编、买家留言、客服备注、税号、备注附件、面单文件（`surface_file`，链接指向带收件人姓名地址的面单）、拣货人 / 发货人（员工姓名）、商品备注（`customization`，可能带买家文字）在落原始层**之前**就删掉（`scrub_pii`），RAW 和 ODS 都没有。
5. 一个店失败不影响其他店；有店失败整次记失败（`SYNC_FIN_STORE_PARTIAL` / `SYNC_FIN_ALL_STORES_FAILED`），下次重跑补齐。
6. 默认关闭（接口 outbound、配置 is_enabled、定时都关）。打开顺序：登记 → 只开手动（首次手动同步当受控探测）→ 开每周定时 → 回填 2026-05-01 起（代码下限 `FIN_SHIPPING_EARLIEST_DATE`）。定时三个接口**错开**：发货单周三上海 04:00、出库单 04:30、明细 05:00（三个接口各自一把执行锁，同一时刻排会并行，所以靠错开时间保证明细在发货单之后；沃尔玛账单同步在 03:00）。
7. 滚动窗 90 天；翻页上限按配置 `max_pages`（发货单 200 页、明细一次最多 2000 张、出库单 200 页），超过报 `*_TOO_MANY_PAGES`；领星没理会翻页参数、连续两页单号完全相同时立刻报 `*_PAGE_REPEATED`；都记该店失败。
8. 执行层租约丢失（`SYNC_LOCK_LEASE_LOST`）整次运行立即停，不继续下一家店。通用抓取入口 `fetch_pages` 拒绝这三个路径，只能走受控的 `fetch_fin_*` 方法。

## 已知限制

- 三张 ODS 都是「当前状态」表，只 upsert 不删：领星里被删掉（接口不再返回）的发货单 / 出库单会留着上次的状态；作废的发货单接口仍返回（`shippingListStatus=3`），会照常更新状态。要清理已删单据另开票据。
- `*_INCOMPLETE` 只能发现「拉到的比领星报的 total 少」；total 本身不准发现不了，首次探测仍要按 runbook 核对条数。

## 不做

- 不接评价加速器快照同步（V4 通用通道的业务层权限 / 只读限制另定后再做）。
- 不补 SB / SV 广告（另一 PR）。
- 不读 PMC #282 的 `ods_lingxing_wfs_shipping_lists` 作初始化来源（两表各自同步）。

实现：`backend/app/modules/integration_sync/fin_shipping_catalog.py`、`handlers/lingxing_fin_sync_base.py`、`handlers/lingxing_fin_shipping_sync.py`、`handlers/lingxing_fin_wms_outbound_sync.py`；迁移 `20261126_0099_fin_shipping_list_detail_synced_at`（发货单表加 `detail_synced_at`，回滚在有值时拒绝）；上线步骤见 `docs/runbooks/finance-settlement-profit-sync.md`。
