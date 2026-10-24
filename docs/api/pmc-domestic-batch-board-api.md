# PMC 国内仓批次看板 API

## 1. 状态与边界

国内仓批次看板只读查询及筛选选项。读取当前收货批次、产品负责人 DWD 和店铺 DIM，不请求领星，不读 ODS / RAW，不写库，不触发同步。

页面 `/pmc/domestic-warehouse-board` 已有前端接入，本地状态 testing，部署与真实数据待联合验收。出库分配表尚未发布，追溯接口把出库标成未知，不现场调领星。

路径前缀 `/api/pmc/domestic`（仓库惯例，无 `v1`）。

统一返回：

```json
{ "success": true, "data": {}, "error": null, "meta": {}, "request_id": "..." }
```

`meta` = `{ source: "new_system_postgresql", source_objects, freshness_at, page, page_size, total }`。
`freshness_at` 是当前筛选结果里 `dwd_domestic_receipt_batch.updated_at` 的最大值。
`source_objects` 基础为 `dwd_domestic_receipt_batch`、`dwd_domestic_receipt_batch_link`；选择负责人时额外列明 `dwd_lingxing_sku_identity_index`、`dwd_lingxing_sku_product_info_current`。选项接口再包含 `dim_lingxing_stores`，其 `freshness_at=null`，不冒充统一快照时间。

到仓日是收货单 `receive_time` 转成的台北日历日 `received_business_date`。在仓天数 = 请求时台北日历日 − 该日期。收货日为空时 `days_in_warehouse` 为空，`arrival_date_status=unknown`。

一行 = 一张收货单的一行。统计按收货行，不按采购单去重。链接只要有一条 `matched`，该行 `mapping_status=matched`；没有链接也算 `unresolved`。不按 SKU 和数量猜测对应关系。

## 2. 认证、权限、数据范围

路由声明权限 `pmc:domestic-batch:read`，请求策略映射为页面权限 `page:pmc:domestic-warehouse-board:view`。另需可信 `source_account_ref` 范围（`require_source_account_scope`，缺范围失败）。预览主体可访问 `/api/pmc/` 下这些 GET。

本切片无写接口，无高危动作，不写审计。

## 3. 接口

### `GET /api/pmc/domestic/filter-options` — 店铺与当前负责人

无请求体及筛选参数。统一 envelope 的 data 为 `{ stores: [{value,label}], owners: [{value,label}] }`，空结果返回两个空数组。
store value 为可见收货批次关联的真实店铺ID；label从同账号店铺DIM取名称，无名称或跨平台/账号名称歧义显示ID。不局限沃尔玛店铺。
owner value 为当前产品负责人UID，label为名称（缺失/歧义显示UID）；同名不同UID不合并。只包含可见批次能通过同账号+SKU匹配到唯一active产品身份的当前负责人；多身份不猜归属，历史归属不在此契约内。
选项复用国内仓现有权限与账号范围，不要求额外Listing页面权限；不返回跨模块数量，不调用外部服务。
数据源决策：`docs/data-sources/decisions/pmc-domestic-filter-options-decision.md`；PRP：`PRPs/pmc-domestic-filter-options.md`。

### `GET /api/pmc/domestic/batches` — 列表

Query：`page`（≥1）、`page_size`（1–200）、`sort`（`received_date_desc` 默认 | `received_date_asc` | `qty_desc`）、`warehouse_id[]`、`store_id[]`（经链接）、`sku[]`、`purchase_order_sn[]`、`receipt_order_sn[]`、`mapping_status`（`unresolved` | `matched`）、`received_from` / `received_to`、`search`（SKU / 收货单号 / 采购单号 / 库存批次号 / 批次单据号的模糊匹配，可与精确筛选叠加）。未知参数或日期反序为 `422 VALIDATION_ERROR`。

行字段：`id, source_account_ref, receipt_order_sn, line_ordinal, purchase_order_sn, source_warehouse_id, sku, received_qty, receive_time, received_business_date, days_in_warehouse, arrival_date_status, mapping_status, links[]`。

新增重复参数 `owner_uid`，例如 `?owner_uid=001&owner_uid=002&store_id=S1`。最多50项，每项1–255字符，空白UID拒绝。当前负责人UID内OR，与店铺、日期、SKU等其他条件AND；列表与统计共用同一实现。无归属或SKU身份歧义在未筛选列表中保留，选择负责人时不匹配，不重复计数。现有精确多值筛选最多50项。到仓日期口径不变。

`links[]`：`id, batch_order_sn, batch_no, store_id, mapped_qty, mapping_status, mapping_method`。

### `GET /api/pmc/domestic/batches/summary` — 统计

筛选与列表相同，不含分页和 `sort`。

| 字段 | 含义 |
|---|---|
| `receipt_batch_count` | 当前筛选下的收货行数 |
| `received_qty` | 实收数量合计，空数量不计入 |
| `warehouse_count` | 有仓库 ID 的收货行，按仓库去重 |
| `matched_batch_count` | 至少有一条已对应库存批次的收货行 |
| `unresolved_batch_count` | 还没有已对应库存批次的收货行 |
| `missing_arrival_date_count` | 收货日为空 |
| `as_of` | 请求时的台北日历日 |

### `GET /api/pmc/domestic/batches/{batch_id}` — 详情

账号范围外或无此行返回 `404 NOT_FOUND`。返回与列表相同的一行。

### `GET /api/pmc/domestic/batches/{batch_id}/trace` — 追溯

返回 `{ batch, outbound }`。`outbound.status` 固定 `unknown`，`reason` 固定 `source_not_published`，`events` 为空数组。等出库来源表发布后再补真实事件。

## 4. 错误码

`401 UNAUTHORIZED`、`403 FORBIDDEN`、`403 DATA_SCOPE_DENIED`、`404 NOT_FOUND`、`422 VALIDATION_ERROR`，服务端异常使用统一500错误envelope（不回显数据库细节）。

## 5. 数据来源

| 项 | 值 |
|---|---|
| 是否只读 | 是 |
| 是否审计 | 否 |
| 是否高危 | 否 |
| sourceTables | `dwd_domestic_receipt_batch`, `dwd_domestic_receipt_batch_link` |
| 同步 / 发布 | 本切片不包含。表为空时列表为空。 |

选项/负责人筛选另依赖既有 `dim_lingxing_stores`、`dwd_lingxing_sku_identity_index`、`dwd_lingxing_sku_product_info_current`；无新表、迁移或来源写入。接口可在数据中心API文档的PMC/国内仓看板下查看，OpenAPI包含response_model与owner_uid参数。
