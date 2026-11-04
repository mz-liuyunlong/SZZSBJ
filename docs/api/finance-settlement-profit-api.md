# 财务 · 结算利润 V2 接口（PR-4）

依据：`PRPs/finance-settlement-profit-v2.md` Rev 4.6 §5、§7、§8.9。代码：`backend/app/modules/finance/settlement_profit/`（`access.py` 权限与数据范围，`queries.py` 读，`commands.py` 写，`router.py` 路由，`schemas.py` 请求 / 响应模型）。迁移 `backend/alembic/versions/20261104_0075_fin_settle_write_log.py`。

前缀 `/api/finance/settlement-profit`。OpenAPI tag `Finance Settlement Profit`，每个接口有 `operation_id`，写接口都有 `response_model`。

## 通用约定

- **Envelope**：沿用 `app/core/api.py`。成功 `{success, data, error: null, meta, request_id}`；错误 `{success: false, data: null, error: {code, message, details}, meta: null, request_id}`。
- **读接口 meta**：`source = finance_settlement_profit_v2`、`source_tables`、`calc_version`、`data_as_of`、`total`。
- **写接口 meta**：`source`、`idempotent_replay`（true 表示这是 24 小时内同一请求的重放）、`write_id`（写入日志行 id）。
- **金额**：一律成对 `{"amount": "12.3400", "currency_code": "USD"}`，amount 为 4 位小数字符串；外部 ID 一律字符串。
- **分页**：`page` 从 1 开始，`page_size` 1–200，默认 50。超出范围返回 422。
- **排序**：`sort_by` 只接受白名单字段，`sort_order` 为 asc / desc。白名单外返回 422。
- **月份**：`months` 为 `YYYY-MM`，可重复传（`?months=2030-01&months=2030-02`）。格式不对返回 422。
- **店铺筛选**：`store_ids` 可重复传。

## 权限与数据范围

| 角色 | 权限 key | 数据范围 |
|---|---|---|
| 财务专员 | `page:finance:settlement-profit:view`、`action:finance:settlement-profit:adjust`、`action:finance:settlement-profit:review-first` | 全部店铺 |
| 财务主管 | 以上 + `action:finance:settlement-profit:review-final`、`close-month`、`config` | 全部店铺 |
| 管理层 | `page:finance:settlement-profit:view` | 全部店铺，只读 |
| 运营负责人 | `page:finance:settlement-profit:view`，data scope = owner | 只看自己负责的商品 |

- 字段权限：`field:finance:settlement-profit:cost`（货本列、库存货值）、`net-profit`（纯利列）、`company-cost`（公司级费用，PR-4 接口不返回公司级费用总额）。没有字段权限时，响应里不出现对应字段（不是返回 null）。
- 店铺范围来自 RBAC `store` 授权，`*` 为全部店铺。没有任何店铺授权返回 403 `DATA_SCOPE_DENIED`。请求了范围外的店铺返回 403 `DATA_SCOPE_DENIED`；按 id 访问范围外的行返回 404 `NOT_FOUND`。
- 负责人范围只对「没有任何财务动作权限、且有 owner 授权」的用户生效；财务角色和管理层不受 owner 限制。
- 预览账号、非数字用户 id 一律 403。
- 权限 key 由 0075 写入 `app_permissions`（`page_key = finance_settlement_profit`），与 `permission_catalog_v2` 的 finance 模块「结算利润」页一致。

### 未对上店铺（`store_id = __unmapped__`）

库存流水店铺代码对不上任何店铺时，待指定行的 store_id 为占位值 `__unmapped__`（PRP §8.4）。它不是店铺：

- 不出现在 `GET /stores`（店铺筛选项）、汇总、商品瀑布、库存异动、对平里。
- `store_ids=__unmapped__` 作为筛选条件一律返回 422 `VALIDATION_ERROR`。带了店铺筛选时，也不会顺带返回未对上店铺的行。
- 只在订单审核清单和调整台账里出现，并且只给「数据范围为全部店铺的财务用户」看，`store_label` 显示「未对上店铺」。管理层（全部店铺、但没有财务动作权限）、只有部分店铺的财务、运营负责人都看不到，也不能对它写调整（404）。
- 测试：`tests/modules/finance/test_settlement_profit_access.py`（不连库）、`tests/modules/finance/test_settlement_profit_api.py`（PostgreSQL）。

## 写操作的公共规则

- **Idempotency-Key**（请求头，必填，1–128 字符）：同一人、同一接口、同一 key 在 24 小时内重复请求，返回第一次的结果，`meta.idempotent_replay = true`。同一 key 换了请求内容返回 409 `IDEMPOTENCY_CONFLICT`；超过 24 小时返回 409 `IDEMPOTENCY_KEY_EXPIRED`。出错的请求不记录，改正后可用同一个 key 重试。
- **审计**：每次成功的写请求在 `manual_settlement_write_log` 留一行（actor_id、actor_role、acted_at、request_id、reason、before、after、response）；调整、审核、结账表本身也带同样的审计列。
- **乐观锁**：调整、撤销、审核、纯利设置都要带 `expected_version`。与当前版本不一致返回 409 `STALE_VERSION`，`details.current_version` 给出当前版本。目标行在事务里加行锁。
- **确认口令 confirm_token**（高风险操作，放在请求体里，按原样输入）：

| 操作 | 口令 |
|---|---|
| 结账 | `CLOSE 2030-01`（`CLOSE` + 空格 + 账单月） |
| 反结账 | `REOPEN 2030-01` |
| 修改纯利设置 | `CONFIG 2030-01`（生效月） |
| 一次审核 20 行或以上 | `REVIEW 20`（`REVIEW` + 空格 + 行数） |

  口令不对返回 422 `CONFIRM_TOKEN_MISMATCH`，`details.expected_format` 给出应输入的口令。
- **已结账**：店铺该月已结账时，调整、撤销、审核返回 `MONTH_CLOSED`。
- **重算**：调整、撤销、反结账、纯利设置写完后调用重算钩子，响应里 `recalc = {status, month, store_ids}`。生产用的数据库读取实现还没上 main（PRP §10 PR-3 的遗留项），这之前 `status = deferred`：写入和行版本已生效，金额等下一次整月重算更新。读取实现合并后，钩子改为同步重算，`status = done`，返回的 `line.version` 已是重算后的版本。

## 读接口

全部只读、不审计、不高危。权限 `page:finance:settlement-profit:view` + 店铺数据范围。

| 接口 | Method / URL | 参数 | 返回 data | sourceTables | 错误码 |
|---|---|---|---|---|---|
| 店铺筛选项 | GET `/stores` | months | rows[]：store_id、label（不含未对上店铺） | `mart_settlement_reconcile_store_month` | 403 |
| 汇总 | GET `/summary` | months、store_ids、owner_ids、view = item / store / owner、currency = USD / CNY、page、page_size、sort_by（sales / gross_profit / margin / ad_cost / revenue）、sort_order | rows[]：key、sales、revenue、order_fees、item_fees、ad_cost、disposal_loss、gross_profit、goods_cost（需货本字段权限）、net_profit（CNY，需纯利字段权限，可空）、margin；totals | `mart_settlement_profit_item_month` | 403、422 |
| 商品瀑布 | GET `/items/{store_id}/{item_id}` | months | months[]：费用组 → 列、gross_profit（USD / CNY）、fx_status、ad_scope_note、net_profit | `mart_settlement_profit_item_month` | 404 |
| 订单审核 | GET `/orders` | months、store_ids、owner_ids、status、reason（missing_purchase / missing_head / unassigned / unmapped_store / reconcile_diff）、keyword（订单号 / item_id / line_key）、page、page_size、sort_by（bill_month / store_id / platform_order_no / status / amount / profit） | rows[]：line_id、line_key、row_kind、month、store_id、store_label、platform_order_no、order_item_no、item_id、owner_ref、sku、gtin、serial_number、ordered_at、shipped_at、settled_at、quantity、amounts、costs（需货本权限）、profit、status、reasons[]、version、初审 / 终审人 | `mart_settlement_order_review`、`fact_settlement_order_lines` | 403、422 |
| 库存异动 | GET `/inventory` | months、store_ids、category | summary[]、details[]（货值需货本权限） | `mart_inventory_movement_month`、`fact_inventory_movement_lines` | 403、422 |
| 调整台账 | GET `/adjustments` | months、status = active / revoked、page、page_size | rows[]：id、line_key、store_id、month、kind、payload、reason、status、version、actor_id、actor_role、acted_at、撤销信息 | `manual_settlement_order_adjustments` | 403 |
| 对平 | GET `/reconcile` | months、store_ids | rows[]：结算单总额、订单级合计、待指定、差额、广告 / 入库运费差异、跨月弃置操作费、status、fx_status、frozen | `mart_settlement_reconcile_store_month` | 403（运营负责人不可看） |
| 纯利设置 | GET `/config/net-profit` | month（必填） | effective_month、fixed_cny、excluded_owner_ids[]、version（无设置时为 0）、is_default | `cfg_net_profit_allocation` | 403（只给财务角色） |

## 写接口

全部需要 `Idempotency-Key`，全部审计。

### POST `/orders/{line_id}/adjustments` 调整一行

- 权限 `action:finance:settlement-profit:adjust`；`kind = cost` 另需 `field:finance:settlement-profit:cost`。高危：否。
- line_id 为订单审核清单的 `line_id`。
- 请求：`kind`、`payload`、`reason`（必填）、`expected_version`。

| kind | 适用行 | payload |
|---|---|---|
| `cost` | 订单行 | `purchase_cny`、`head_cny`（至少一个，≥ 0，最多 4 位小数） |
| `amount` | 订单行 | `column`（订单级列：sales_amount_usd、platform_subsidy_usd、refund_amount_usd、commission_usd、wfs_fulfillment_fee_usd、return_fee_usd、tax_withheld_usd）、`delta`（非 0）、`currency`（只能 USD）。存为 `{column, delta_usd}` |
| `assign_item` | 店铺的待指定行 | `item_id` |
| `assign_store` | 未对上店铺的待指定行 | `store_id`（已存在的店铺，不能是 `__unmapped__`；目标店铺该月已结账返回 `MONTH_CLOSED`） |
| `note` | 任何行 | `text`（可选） |

- 效果：写 `manual_settlement_order_adjustments`；该行状态变为 `adjusted`，初审 / 终审清空，version + 1。
- 返回：`adjustment`（台账行）、`line`（line_id、status、version）、`recalc`。
- 错误码：404 `NOT_FOUND`、409 `MONTH_CLOSED` / `STALE_VERSION` / `IDEMPOTENCY_CONFLICT` / `IDEMPOTENCY_KEY_EXPIRED`、422 `VALIDATION_ERROR`。

示例（合成数据）：

```http
POST /api/finance/settlement-profit/orders/00000000-0000-0000-0000-000000000001/adjustments
Idempotency-Key: 6f1c0d4e-0000-4000-8000-000000000001

{"kind": "amount", "payload": {"column": "sales_amount_usd", "delta": "1.5", "currency": "USD"},
 "reason": "合成调整", "expected_version": 1}
```

### POST `/orders/review` 批量初审 / 终审 / 退回

- 权限：stage = first 需 `review-first`，stage = final 需 `review-final`。高危：20 行或以上需 `confirm_token = REVIEW <行数>`。
- 请求：`line_ids[]`（1–500）、`stage`、`decision = pass / reject`、`comment`（退回必填）、`expected_versions{line_id: version}`（每行必填）、`confirm_token`。
- 逐行处理，逐行返回 `{line_id, ok, code, status, version}`，一行失败不影响其他行。逐行错误码：`NOT_FOUND`、`NOT_REVIEWABLE`（只有订单行能审核）、`MONTH_CLOSED`、`STALE_VERSION`、`STAGE_ORDER`（终审前须初审；已初审 / 终审的行不能再初审）、`SAME_REVIEWER`（同一人不能对同一行既初审又终审）。
- 退回：状态变为 `rejected`，回到初审。每次成功审核写一行 `manual_settlement_review_actions`。
- 整体错误码：403、409 `IDEMPOTENCY_*`、422 `VALIDATION_ERROR` / `CONFIRM_TOKEN_MISMATCH`。

### POST `/adjustments/{adjustment_id}/revoke` 撤销调整

- 权限 `adjust`。请求：`reason`（必填）、`expected_version`（调整记录的 version）。
- 效果：调整记录变为 `revoked`（写 revoked_by、revoked_at、revoke_reason），version + 1；所属行回到待初审（`pending`），重算时也不会恢复撤销前的审核结果。
- 错误码：404、409 `ALREADY_REVOKED` / `MONTH_CLOSED` / `STALE_VERSION`。

### POST `/months/{month}/close` 结账

- 权限 `close-month`。高危：`confirm_token = CLOSE YYYY-MM`。
- 请求：`store_ids[]` 或 `"ALL"`（需要全部店铺数据范围；ALL 指该月有对平结果的全部店铺，不含未对上店铺）。
- 先检查，全部通过才写，任何一店有拦截就整体不写。拦截码：`NOT_CALCULATED`（该店该月没有计算结果）、`ALREADY_CLOSED`、`FX_MISSING`、`RECONCILE_FAILED`、`UNASSIGNED_PENDING`（本店有未指定的待指定，或当月有未对上店铺的待指定，后者拦所有店铺）、`OWNER_MISSING`、`OWNER_SALES_ZERO`（纯利跨店计算，拦所有店铺）。返回 409，`error.code` 为排在最前的拦截码，`details.blockers` 列出每店的全部拦截码。
- 效果：每店写或更新一行 `manual_settlement_month_close`（status = closed、frozen_calc_version、snapshot_totals），冻结该店该月当前版本的订单行、商品月、对平行（写 frozen_at / frozen_by）。之后源数据变化只写结算后差异（PR-3 已实现）。

### POST `/months/{month}/reopen` 反结账

- 权限 `close-month`。高危：`confirm_token = REOPEN YYYY-MM`，`reason` 必填。
- 请求：`store_ids[]` 或 `"ALL"`（该月所有已结账店铺）。
- 任何一店不是已结账状态，整体返回 409 `NOT_CLOSED`。
- 效果：结账行变为 `reopened`（写 reopen_reason），解除冻结，未处理的结算后差异标为 `resolved_by_reopen`，然后调用重算钩子。写入日志里记录每店反结账前的合计（before）。

### PUT `/config/net-profit` 修改纯利设置

- 权限 `config`。高危：`confirm_token = CONFIG YYYY-MM`（生效月）。
- 请求：`effective_month`、`fixed_cny`（≥ 0，最多 4 位小数）、`excluded_owner_ids[]`（不重复）、`expected_version`（该生效月还没有设置时传 0）、`reason`。
- 生效月已有店铺结账返回 409 `MONTH_CLOSED`。
- 效果：新建或更新该生效月的设置，version + 1，调用重算钩子。

## 错误码一览

| code | HTTP | 含义 |
|---|---|---|
| `FORBIDDEN` | 403 | 缺少页面 / 动作 / 字段权限 |
| `DATA_SCOPE_DENIED` | 403 | 没有店铺数据范围，或请求了范围外的店铺 |
| `NOT_FOUND` | 404 | 行不存在或不在数据范围内 |
| `VALIDATION_ERROR` | 422 | 参数不合法（含把 `__unmapped__` 当店铺筛选） |
| `CONFIRM_TOKEN_MISMATCH` | 422 | 确认口令不对 |
| `STALE_VERSION` | 409 | 数据已被他人修改，请刷新 |
| `MONTH_CLOSED` | 409 | 该月已结账 |
| `ALREADY_REVOKED` | 409 | 调整已撤销 |
| `NOT_CLOSED` | 409 | 反结账的店铺该月未结账 |
| `NOT_CALCULATED` / `ALREADY_CLOSED` / `FX_MISSING` / `RECONCILE_FAILED` / `UNASSIGNED_PENDING` / `OWNER_MISSING` / `OWNER_SALES_ZERO` | 409 | 结账拦截 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 key 用于不同请求，或另一人已用过这个 key |
| `IDEMPOTENCY_KEY_EXPIRED` | 409 | key 超过 24 小时 |
| `STAGE_ORDER` / `SAME_REVIEWER` / `NOT_REVIEWABLE` | 逐行 | 审核逐行结果 |

## 与 PRP 的差异和本 PR 的边界

- 重算：PRP §8.9 要求写后同步重算。数据库读取实现要等结算单行表和领星流水表上 main 才能写，本 PR 先接一个可替换的重算钩子，默认 `deferred`（见上文「重算」）。测试里用合成数据的读取实现验证了同步重算这条路径。
- 读取实现的约定（给后续 PR）：调整只传有效状态的；`StoreMonthInput.adjustment_changed_at` 传每行所有调整（含已撤销）最晚的 acted_at / revoked_at；审核动作全部传，引擎会丢掉早于最后一次调整变化的审核。
- PRP §5「批量调整 ≥ 20 行要 confirm_token」：调整接口一次只调一行，本 PR 把这条规则用在批量审核上（20 行或以上）。
- 本 PR 不调用任何外部接口，不新增同步，不改 RAW / ODS / FACT 的数据，只写 manual_、订单审核状态、冻结标记和 cfg_。
