# WFS 费用异常自动检测 API

状态：`approved_for_implementation`；PR #257 implementation ready for review，未合并、未部署、未执行生产迁移或真实采集。

## 数据链路

```text
Lingxing WFS settlement（受控、默认关闭）
→ Integration Sync RAW blob / request ref
→ gov_wfs_settlement_collections（店铺/窗口完整性证明）
→ fact_walmart_wfs_fee_actual（绑定 collection）
→ 订单级费用与订单次数众数
→ Product Management 标准费 + Daily Sales 累计销量
→ 异常候选
→ ops_wfs_fee_detection_evidence（append-only 系统证据）
→ ops_wfs_fee_anomaly_cases（独立开关、insert-only）
```

认证参数、Token、签名与 Authorization 只用于出站请求，不进入 RAW、数据库、响应、日志或异常。

## 检测预览

### `POST /api/warehouse/wfs-fee-alerts/detection-preview`

- 用途：对已经完整采集并持久化的 WFS 证据执行只读 dry-run。
- 权限：可信会话、真实超级管理员、获授权 `source_account_ref` 范围。
- 外部调用：无。
- 数据库写入：无；不创建或更新案件。
- Content-Type：`application/json`。

请求：

```json
{
  "start_date": "2026-08-19",
  "end_date": "2026-10-17",
  "store_id": null
}
```

约束：

- `start_date <= end_date`，窗口最多 366 天。
- 只扫描调用者获授权账号与动态发现的 Walmart 店铺。
- 相同账号、店铺和窗口必须存在状态为 `verified` 的 collection；账号级 run 状态不能代替店铺级完成证明。
- Collection 仅在分页总数稳定、全部返回行分类守恒、无 invalid/duplicate/missing identity/missing store 且持久化事实数一致时成为 `verified`。
- Preview 不请求 provider、不写案件、也不写 detection evidence。Backtest 同样禁止业务写入。

响应 `data`：

| 字段 | 含义 |
|---|---|
| `scanned_accounts` | 扫描的授权账号数 |
| `scanned_stores` | 扫描或失败的店铺数 |
| `scanned_skus` | 从结算证据解析的 MSKU 数 |
| `valid_samples` | 达到有效费用条件的 MSKU 数 |
| `overcharge_candidates` | 检测到的异常候选数 |
| `would_create` | 正式执行时可能新增的案件数；不是已新增 |
| `already_exists` | 已存在案件、将保持不变的数量 |
| `review_required` | 因规则/时效/证据边界需人工复核的数量 |
| `skipped` | 身份、标准费、销量等证据不足而跳过的数量 |
| `failed` | 采集完成证明或店铺检测失败数 |
| `stores` | 每店铺的同类聚合结果 |

错误：

- `401 UNAUTHORIZED`：无可信认证。
- `403 FORBIDDEN` / `DATA_SCOPE_DENIED`：权限或账号范围不足。
- `422 INVALID_REQUEST`：日期、窗口或请求格式不合法。

## 既有案件接口

`GET /api/warehouse/wfs-fee-alerts` 与 `/api/warehouse/wfs-fee-cases/**` 保持兼容。新增证据字段仅为可空字段，包括有效费用订单数、有效销售件数、众数订单数、逐单理论超额、全样本净差额、最新结算日、标准费来源、质量状态、销量覆盖证明、WFS 范围证据、自动立案资格和检测时间。

这些字段是候选证据，不代表已确认索赔或已追回金额。

## 正式采集与调度边界

- 复用 Integration Sync 已有 trigger、run/work item、lease 和 Celery task，不新增第二套任务系统。
- 接口 key：`wfsProfitOrder`；handler：`lingxing.wfs.profit_order.v1`。
- 默认 `outbound_enabled=false`、`is_enabled=false`、`schedule_enabled=false`。
- 应用设置默认 `WFS_AUTO_DETECT_ENABLED=false`、`WFS_AUTO_CASE_CREATE_ENABLED=false`。
- 每日窗口按 `America/Los_Angeles` 的 T-2 结束日与 60 天回看计算。
- 正式时效按真实检测日期减最新结算日期；历史窗口重跑不能刷新证据年龄。
- 超过单窗口分页上限时按不重叠日期范围递归拆分；单日仍超限时 collection 进入 partial，不得静默截断。
- `CS*` 行作为 business exclusion 参与总数守恒；无效币种、非批准平台/交易类型、重复、缺身份或未知店铺会阻断该 collection。
- 当前仓库证据不足以确认所有 profit-order 物流费均为 WFS，`WFS_SETTLEMENT_SCOPE_VERIFIED` 默认 `false`；未确认范围只能人工复核。
- 销量覆盖必须由 Listing 生命周期起点和连续成功同步窗口证明；存在 MART 行本身不等于 `complete`。
- 正式 Provider 请求、案件写入、定时启用、迁移和部署分别需要 Owner 授权。

## 数据来源

- RAW：`ods_api_raw_blobs`, `ods_api_raw_request_refs`。
- 实际费用：`fact_walmart_wfs_fee_actual`。
- Listing 身份：`dim_walmart_listings`。
- 销量：`mart_daily_sales_item_day`。
- 标准费：Product Management 当前身份、规则和定价计算。
- 案件：`ops_wfs_fee_anomaly_cases`。
- 检测证据：`ops_wfs_fee_detection_evidence`，append-only，不拥有人工案件状态。

## 安全错误边界

- `WFS_COLLECTION_NOT_VERIFIED` / `WFS_COLLECTION_INCOMPLETE`：店铺窗口证据未完成。
- `WFS_SETTLEMENT_SOURCE_IDENTITY_CONFLICT`：来源行身份与已有 Item/MSKU/store 冲突。
- `SYNC_WFS_DAY_PAGE_LIMIT`：单日仍超过批准分页上限，显式失败而非截断。
- `WFS_SALES_IDENTITY_UNRESOLVED` / coverage `unknown|partial|missing`：销量或覆盖不能安全证明。
- `product_management_default_unconfirmed` / `fee_scope_status=unverified`：仅人工复核，禁止自动立案。

错误响应与日志只使用安全错误码，不包含 RAW payload、认证参数或商品字段值。
