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
- 明细只拉已发货、发货时间在窗内、且没有明细或发货单比明细新的单子；发货单列表要先跑过明细才有东西拉，三个按登记顺序依次手动触发即可。
- 个人信息（收件人、电话、地址、邮编、买家留言等）在落原始层之前删掉。

## 2. 上线步骤（负责人授权后由部署 AI 按票据执行）

1. 登记（全部关闭）：`FIN_SHIPPING_GOVERNANCE_BOOTSTRAP_AUTHORIZED=true FIN_SHIPPING_SOURCE_ACCOUNT_REF=<账号引用> uv run python scripts/bootstrap_fin_shipping_governance.py`。
2. 只开手动：`FIN_SHIPPING_SYNC_ENABLE_AUTHORIZED=true FIN_SHIPPING_SOURCE_ACCOUNT_REF=<账号引用> uv run python scripts/enable_fin_shipping_sync.py`。
3. 首次手动同步当作受控探测：任务中心依次触发 `finShippingList` → `finShippingDetail` → `finWmsOutboundOrders`，核对条数与本地归档（2026-11-16 发货单探测、2026-10-26 出库单拉取）一致（只回报是否一致，不回报金额）。
4. 开定时：探测通过后，同上命令再加 `FIN_SHIPPING_SYNC_SCHEDULE_AUTHORIZED=true` 重跑一次（每周三上海 04:00，cron `0 20 * * 2` UTC）。
5. 回填：任务中心对三个接口分别发起回填，2026-05-01 至今，按月分批（先发货单，再明细，再出库单）。

回滚：任务中心关掉 `is_enabled` 立即停；本 PR 没有迁移（表由 #365 建）。

## 3. 错误码（任务中心可见）

`SYNC_FIN_RUNTIME_NOT_AUTHORIZED`（测试环境 / 未开真实调用）、`SYNC_FIN_EXECUTION_NOT_AUTHORIZED`、`SYNC_FIN_GOVERNANCE_DISABLED`、`SYNC_FIN_NO_STORES`、`SYNC_FIN_PAGINATION_INVALID`、`SYNC_FIN_WINDOW_INVALID`、`SYNC_FIN_REQUEST_FAILED`、`SYNC_FIN_RESPONSE_FAILED`（领星 code ≠ 0）、`SYNC_FIN_SHIPPING_RESPONSE_SHAPE` / `SYNC_FIN_WMS_RESPONSE_SHAPE`（响应不是预期结构）、`SYNC_FIN_SHIPPING_INVALID_ROW` / `SYNC_FIN_WMS_INVALID_ROW`（缺单号）、`SYNC_FIN_SHIPPING_TOO_MANY_PAGES` / `SYNC_FIN_WMS_TOO_MANY_PAGES`、`SYNC_FIN_STORE_FAILED`（店失败但不是上面任何一种，如数据库出错）、`SYNC_FIN_STORE_PARTIAL` / `SYNC_FIN_ALL_STORES_FAILED`（运行级汇总；`error_message` 里按店列出各自的错误码）。
