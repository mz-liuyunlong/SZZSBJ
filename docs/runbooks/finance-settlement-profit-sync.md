# 结算利润 V3 · 同步 runbook（PR-2：发货单 / 发货单明细 / 销售出库单）

对应 PRP `PRPs/finance-settlement-profit-v3.md` §10 PR-2；决策 `docs/data-sources/decisions/finance-settlement-profit-pr2-sync-decision.md`；表结构 `docs/api/finance-settlement-profit-tables.md`。

## 1. 三个接口（任务中心登记名）

| interface_key | 领星接口 | 目标表 | 分页 | 默认 page_size / max_pages |
|---|---|---|---|---|
| `finShippingList` | `/basicOpen/multiplatform/query/shippingList`（v2，只查 Walmart，按发货时间） | `ods_lingxing_fin_shipping_lists` | offset/length | 100 / 200 页 |
| `finShippingDetail` | `/basicOpen/multiplatform/query/shippingDetail` | `ods_lingxing_fin_shipping_detail_items` | 一张发货单一次请求 | 1 / 一次运行最多 2000 张 |
| `finWmsOutboundOrders` | `/erp/sc/routing/wms/order/wmsOrderList`（按变更时间） | `ods_lingxing_fin_wms_outbound_orders` | page/page_size | 200 / 200 页 |

- 三个都是只读，一个店一次请求，每页先落 `ods_api_raw_blobs` + `ods_api_raw_request_refs` 再写 ODS，每页提交一次；全部 upsert，重跑安全。
- 店铺来自 `dim_lingxing_stores`（Walmart 平台），和沃尔玛账单同步同一份。
- 时间窗：手动 / 定时 = 最近 90 天（上海日期）；回填 = 任务中心给的窗，下限 2026-05-01。
- 任务中心「手动同步」对这三个接口放行（#369 定时 PR 一并修：此前手动同步只放行商品 / 数据页 / 财务审批 / 汇率 / 沃尔玛账单，这三个会被拒 `SYNC_PRODUCTLIST_ONLY`）。
- 明细只拉已发货、发货时间在窗内、且发货单 `detail_synced_at` 为空或早于 `updated_at` 的单子；拉完同一事务里删掉不在新明细里的 MSKU 行并记 `detail_synced_at`（明细为空也记）。发货单列表要先跑过明细才有东西拉：手动触发按 发货单 → 出库单 → 明细 的顺序，等前一个跑完再点下一个。
- 定时三个接口错开（UTC cron）：发货单 `0 20 * * 2`（周三上海 04:00）、出库单 `30 20 * * 2`（04:30）、明细 `0 21 * * 2`（05:00）。三个接口各自一把执行锁，排同一时刻会并行，所以靠错开时间保证顺序。
- 个人信息（收件人、电话、地址、邮编、买家留言、客服备注、税号、备注附件、面单文件、拣货人 / 发货人、商品备注）在落原始层之前删掉。
- 迁移 `20261126_0099_fin_shipping_list_detail_synced_at`：发货单表加 `detail_synced_at` 一列；有值时拒绝回滚。

## 2. 上线步骤（负责人授权后由部署 AI 按票据执行）

0. 迁移：`uv run alembic upgrade head`（到 `20261126_0099_fin_shipping_list_detail_synced_at`），再做后面的步骤。
1. 登记（全部关闭）：`FIN_SHIPPING_GOVERNANCE_BOOTSTRAP_AUTHORIZED=true FIN_SHIPPING_SOURCE_ACCOUNT_REF=<账号引用> uv run python scripts/bootstrap_fin_shipping_governance.py`。
2. 只开手动：`FIN_SHIPPING_SYNC_ENABLE_AUTHORIZED=true FIN_SHIPPING_SOURCE_ACCOUNT_REF=<账号引用> uv run python scripts/enable_fin_shipping_sync.py`。
3. 首次手动同步当作受控探测：任务中心依次触发 `finShippingList` → `finWmsOutboundOrders` → `finShippingDetail`（等前一个跑完再点下一个），核对条数与本地归档（2026-11-16 发货单探测、2026-10-26 出库单拉取）一致（只回报是否一致，不回报金额）。
4. 开定时：探测通过后，同上命令再加 `FIN_SHIPPING_SYNC_SCHEDULE_AUTHORIZED=true` 重跑一次（三个接口各自的 cron 见 §1）。
5. 回填：任务中心对三个接口分别发起回填，2026-05-01 至今，按月分批（先发货单，再明细，再出库单）。

回滚：任务中心关掉 `is_enabled` 立即停；迁移 0099 的 downgrade 在 `detail_synced_at` 有值时拒绝（不删数据）。

## 3. 错误码（任务中心可见）

`SYNC_FIN_RUNTIME_NOT_AUTHORIZED`（测试环境 / 未开真实调用）、`SYNC_FIN_EXECUTION_NOT_AUTHORIZED`、`SYNC_FIN_GOVERNANCE_DISABLED`、`SYNC_FIN_NO_STORES`、`SYNC_FIN_PAGINATION_INVALID`、`SYNC_FIN_WINDOW_INVALID`、`SYNC_FIN_REQUEST_FAILED`、`SYNC_FIN_RESPONSE_FAILED`（领星 code ≠ 0）、`SYNC_FIN_SHIPPING_RESPONSE_SHAPE` / `SYNC_FIN_WMS_RESPONSE_SHAPE`（响应不是预期结构）、`SYNC_FIN_SHIPPING_INVALID_ROW` / `SYNC_FIN_WMS_INVALID_ROW`（缺单号；出库单还包括返回行 `sid` 不是请求的店）、`SYNC_FIN_SHIPPING_TOO_MANY_PAGES` / `SYNC_FIN_WMS_TOO_MANY_PAGES`、`SYNC_FIN_SHIPPING_PAGE_REPEATED` / `SYNC_FIN_WMS_PAGE_REPEATED`（连续两页单号完全相同）、`SYNC_FIN_SHIPPING_INCOMPLETE` / `SYNC_FIN_WMS_INCOMPLETE`（领星报的 total 还没拉够就给了空页；只能发现「少于 total」，total 本身不准要靠 §2 第 3 步核对条数）、`SYNC_FIN_STORE_FAILED`（店失败但不是上面任何一种，如数据库出错）、`SYNC_FIN_STORE_PARTIAL` / `SYNC_FIN_ALL_STORES_FAILED`（运行级汇总；`error_message` 里按店列出各自的错误码）。
