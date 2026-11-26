# 查询WFS成本计价明细 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-8437AD0BCB9E`（手工键：仓库规则为 SHA1("POST\|api_path\|document_path") 前 12 位；本接口不在 normalized 索引内、缺官方 document_path，改取 SHA1(api_path) 前 12 位） |
| Contract status | `READY_FOR_PRP` |
| Source document | 领星 API 文档「多平台 → 查询WFS成本计价明细」（2026-09-10 新增接口，对应【多平台管理】>【WFS成本计价】），rocky 2026-09-23 提供的官方页面摘录；仓库外原件：`features/pmc-wfs-shipment/context/lingxing-wfs-cost-valuation-api.md` |
| Normalized interface source | 无（手工登记，不在 `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv`） |
| Path | `/basicOpen/multiplatform/wfs/cost/valuation/detail` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Side effect | 无（只读查询） |
| Pagination | `offset/length`（默认 20，最大 200） |
| Page / batch limit | `200` |
| Rate limit evidence | 令牌桶容量 `1` |
| Authentication | 文档写明与其他 basicOpen 接口相同的 URL 参数鉴权（access_token / timestamp / sign / app_key）；客户端按 query-sign 实现，适用性待首次授权探测确认。本文件不记录任何凭证或签名值。 |
| Can enter PRP planning | `yes`（`PRPs/wfs-inventory-claim.md`） |
| Owner | 库存索赔 PRP PR 1（全仓库唯一的契约登记与 ODS） |
| Consumer | `ods_lingxing_wfs_cost_valuation_flow`（同步 `wfsCostValuationFlow`）；结算利润 V2 只读 `is_current = true` |

## Request parameters

| Path | Name | Type | Required | Note | 本系统同步取值 |
|---|---|---|---|---|---|
| `startDate` | `startDate` | `string` | `是` | yyyy-MM-dd | 窗口起；是否含端点待探测 |
| `endDate` | `endDate` | `string` | `是` | yyyy-MM-dd | 窗口止；是否含当天待探测 |
| `dateType` | `dateType` | `int` | `否` | 0 出入库日期（默认）/ 1 结算日期 | `0` |
| `sidList` | `sidList` | `array` | `否` | 店铺 ID 列表；不传查全部 | 不传 |
| `businessType` | `businessType` | `array` | `否` | 出入库类型编码（多选） | **不传（全量）** |
| `costSource` | `costSource` | `array` | `否` | 成本来源编码 | 不传 |
| `costZeroType` | `costZeroType` | `int` | `否` | 0 不筛选 / 1 仅成本缺失项 | 不传 |
| `searchField` | `searchField` | `string` | `否` | gtin / msku / title / localName / localSku | 不传 |
| `searchValue` | `searchValue` | `string` | `否` | | 不传 |
| `searchValueList` | `searchValueList` | `array` | `否` | | 不传 |
| `businessNumber` | `businessNumber` | `string` | `否` | 货件号 | 不传 |
| `businessNumberList` | `businessNumberList` | `array` | `否` | | 不传 |
| `orderNumber` | `orderNumber` | `string` | `否` | 订单号 | 不传 |
| `orderNumberList` | `orderNumberList` | `array` | `否` | | 不传 |
| `length` | `length` | `int` | `否` | 默认 20，最大 200 | `200` |
| `offset` | `offset` | `int` | `否` | | 按页递增 |
| `sortField` | `sortField` | `string` | `否` | dateLocal / quantity / purchaseTotalAmount / logisticsTotalAmount / otherTotalAmount / date1 | `dateLocal` |
| `sortType` | `sortType` | `string` | `否` | asc / desc | `asc` |

客户端白名单（`app/integrations/lingxing/wfs_cost_valuation_contracts.py`）只允许 `startDate`、`endDate`、`dateType`、`sortField`、`sortType`、`offset`、`length`。

## Response fields

源文档未逐字段标注类型与必填；实现以合成 fixture 为准，金额按字符串转 Decimal（numeric(18,4)）。

| Path | Name | Meaning | ODS 列 |
|---|---|---|---|
| `data.page.records[].dateLocal` | `dateLocal` | 出入库日期（时区待探测） | `date_local`、`business_date` |
| `data.page.records[].imageUrl` | `imageUrl` | 图片 | 仅 payload_json |
| `data.page.records[].gtin` | `gtin` | GTIN | `gtin` |
| `data.page.records[].msku` | `msku` | MSKU | `msku` |
| `data.page.records[].title` | `title` | 标题 | 仅 payload_json |
| `data.page.records[].localName` | `localName` | 品名 | 仅 payload_json |
| `data.page.records[].localSku` | `localSku` | SKU | `local_sku` |
| `data.page.records[].sellerName` | `sellerName` | 店铺名（含员工姓名，敏感） | `store_code`（前 6 位）；原值仅 payload_json |
| `data.page.records[].businessType` | `businessType` | 出入库类型（字符串枚举） | `business_type` |
| `data.page.records[].businessName` | `businessName` | 出入库名称 | `business_name` |
| `data.page.records[].businessDesc` | `businessDesc` | 出入库描述 | `business_desc` |
| `data.page.records[].quantity` | `quantity` | 数量（带符号） | `quantity` |
| `data.page.records[].businessNumber` | `businessNumber` | 货件号 | `business_number` |
| `data.page.records[].costSource` | `costSource` | 成本来源 | `cost_source` |
| `data.page.records[].orderBasePurchaseAmount` | `orderBasePurchaseAmount` | 单位采购成本 | `order_base_purchase_amount` |
| `data.page.records[].purchaseTotalAmount` | `purchaseTotalAmount` | 采购成本合计 | `purchase_total_amount` |
| `data.page.records[].orderBaseLogisticsAmount` | `orderBaseLogisticsAmount` | 单位头程成本 | `order_base_logistics_amount` |
| `data.page.records[].logisticsTotalAmount` | `logisticsTotalAmount` | 头程成本合计 | `logistics_total_amount` |
| `data.page.records[].orderBaseOtherAmount` | `orderBaseOtherAmount` | 单位其他成本 | `order_base_other_amount` |
| `data.page.records[].otherTotalAmount` | `otherTotalAmount` | 其他成本合计 | `other_total_amount` |
| `data.page.records[].orderNumber` | `orderNumber` | 订单号 | `order_number` |
| `data.page.records[].date1` | `date1` | 结算日期 | `settlement_date` |
| `data.page.records[].serialNumber` | `serialNumber` | 库存流水编号（不唯一，跨批次会变） | `serial_number` |
| `data.page.records[].sid` | `sid` | 文档未列；PMC 实测多数为空 | 店铺对照第一优先 |
| `data.detail.calculationStartTime` / `calculationEndTime` | — | 重算时间 | 仅 RAW |
| `data.page.total` / `size` / `current` / `pages` | — | 分页 | `total` 用于行数校验 |
| — | — | 金额币种：文档未写，待探测 | `currency_code`（确认前为 NULL） |

## Boundary

- 不含任何示例值、店铺、订单号、金额或凭证。
- 真实请求只走 Integration Sync（`wfsCostValuationFlow`，`is_enabled=false`、`schedule_enabled=false` 默认关闭），首次开启与补历史数据须 rocky 书面同意。
- 待探测：endDate 是否含当天；dateLocal / date1 时区；金额币种；不传 businessType 时的类型全集；`sid` 何时有值；鉴权方式适用性。
