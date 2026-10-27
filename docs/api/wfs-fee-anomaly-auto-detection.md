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
- `product_management_default_unconfirmed` / `historical_applicability=current_only` / `fee_scope_status=unverified`：仅保留理论估算并进入人工复核，禁止自动立案。

错误响应与日志只使用安全错误码，不包含 RAW payload、认证参数或商品字段值。

## Provider 合同与上线前状态（2026-10-27）

- 官方离线契约：`LX-DB6D62E9EE37`，`POST /basicOpen/multiplatform/profit/report/order`，请求体为 JSON。
- `sids` 是“查询多平台店铺信息”的领星 `store_id` 字符串（多值时逗号分隔），不是 Walmart 外部店铺号或店名。运行时必须从已授权账号下的 Walmart 店铺维度精确取得并核对。
- 当前 client 固定 `platformCodeS=["10008"]`、`transactionTypeS=[0]`、`currencyCode="USD"`、`searchDateType="2"`，`offset/length` 由受控分页器生成，`length <= 20`。
- 官方摘要把 `platformLogisticsAmount` 定义为通用“平台物流费”，并单列 `wfsShipmentFee` 等 WFS 字段。尚无证据证明两者在 Walmart 销售行上恒等，也未完成 Seller Fulfilled/调整/退款排除验证。
- 因此 `API_CONTRACT_VALIDATED=PARTIAL`、`PAGINATION_VERIFIED=MOCK_ONLY`、`REAL_API_TEST_EXECUTED=NO`、`WFS_SCOPE_STATUS=UNVERIFIED`。不得开启 `WFS_SETTLEMENT_SCOPE_VERIFIED`。

后续最小真实验证必须另获授权，并硬限制为一个账号、一个经核对的领星多平台店铺 `store_id`、MSKU `YC00115-1A`、2026-09-01 至 2026-09-30、每页 20、最多 3 页。验证期间不得写数据库、RAW 或案件；只允许输出脱敏字段/类型/计数。`total > 60`、店铺或 MSKU 不一致、分页变化、字段语义不明、出现非销售交易时立即停止。

已提供默认拒绝的只读工具 `backend/scripts/wfs_settlement_probe.py`。只有 Owner 对真实 Provider read 单独授权、且受控环境注入 secret refs 后，才能执行：

```bash
WFS_PROBE_ALLOW_READ=YES \
WFS_PROBE_SOURCE_ACCOUNT_REF=primary \
WFS_PROBE_STORE_ID=110704872940532224 \
WFS_PROBE_MSKU=YC00115-1A \
WFS_PROBE_START_DATE=2026-09-01 \
WFS_PROBE_END_DATE=2026-09-30 \
WFS_PROBE_PAGE_SIZE=20 \
WFS_PROBE_MAX_PAGES=3 \
LINGXING_ENABLE_REAL_CALLS=true \
LINGXING_ENABLE_TOKEN_REQUESTS=true \
uv run python scripts/wfs_settlement_probe.py
```

该命令在本次验收中未执行，不能据此把 Provider contract 或 WFS scope 标记为已验证。

## 标准费边界

- 已知 $6.55 是当前 Product Management 公式结果：当前 SKU product-info 中 1000g、36.5×20.5×17cm → 6lb 计费重 → `$4.15 + $0.40 × 6`。
- `ACTIVE_RULE_COUNT=0` 时来源为 `product_management_default_unconfirmed`，只作人工比较，不具备自动立案资格。
- 当前规则按来源账号及有效期生效，没有 SKU/Item/store 级 WFS override；产品重量和尺寸也是当前值，不是订单历史快照。Owner 未确认目标窗口的历史适用策略前，不能把 $6.55 当作历史权威标准。
- 检测器现在要求 `historical_applicability=historical_confirmed` 才具备建案资格；`current_only` 的理论金额仍可展示，但状态固定为 `REVIEW_REQUIRED`。
- 规则变化不会覆盖 append-only detection evidence；每条证据保存当次 `standard_fee_source`、`rule_version`、业务日期和检测时间。

## 最终本地验收记录（2026-10-27）

- 远端 PR HEAD `6695114a8594ad585e0556e6491a3b0f7e1f430e` 的 12 个 GitHub checks 全部成功；尚无正式 Reviewer approval。
- 本地补修提交 `064bad82d356077c9c9f43a6645040d489b6cbf4` 尚未推送，因此远端 CI 不覆盖该提交。
- 本地：Ruff format/check PASS；WFS `157 passed, 9 skipped`；全后端 `1783 passed, 127 skipped`；应用导入与 Alembic 0061 单一 head PASS。
- Frontend 未改动；Node 24 单 worker Vitest `60 files / 281 tests`、lint、build PASS。
- 未调用真实 Provider/Token，未连接数据库，未执行 migration，未创建案件或启用调度。

生产 0061 只读预检工具为 `backend/scripts/preflight_wfs_0061.py`。Owner/DBA 批准目标数据库只读访问后，可由受控环境执行：

```bash
WFS_0061_PREFLIGHT_ALLOW_DB_READ=YES uv run python scripts/preflight_wfs_0061.py
```

这不等于迁移授权；备份恢复证明、磁盘容量、锁窗口及实际 `alembic upgrade` 仍是独立生产门禁。
