# Product Detail Sync + Product Management API V1 PRP

```text
Status: Approved for implementation — Ready for implementation
Owner Approval Required: Completed (2026-09-13)
Implementation Allowed: Yes, within this Approved PRP after this docs-only gate update
Implementation Resume Authorized: Yes (2026-09-13)
Main Execution Role: Backend Engineer
Assigned Agent Skill: engineering-backend-architect
Source Decision: docs/data-sources/decisions/product-management-product-detail-sync-decision.md
Source Decision State: READY_FOR_PRP
Real Lingxing Call Allowed: No
Real Token Request Allowed: No
Production Sync Execution Allowed: No
```

## 1. 任务背景

现有 Integration Sync Governance + Lingxing SKU Detail Foundation 已建立 ProductList identity、`batchGetProductInfo` 禁用 handler/parser skeleton、DWD detail/images/tags、DWS base profile 和受保护 SKU 详情读取。现有 Product Management Backend MVP 另行维护 `products` 与 `product_platform_listings`，前端产品管理页面仍使用静态数据。

本 PRP 已由负责人批准，用于把详情同步、内部标签、版本化费用/售价规则、可重建计算结果和产品管理 BFF 组合为一个受治理后端能力。负责人已补齐售价公式并解除 Recovery Stop，允许在当前分支恢复实现。批准仅覆盖代码、migration、文档和 mock/synthetic 测试，不得执行真实外部或生产操作；本次门禁更新本身仍为 docs-only。

## 2. 前置门禁

当前已满足：

1. Source Decision 已为 `READY_FOR_PRP`，批准范围内无未解决的 `NEED_OWNER_DECISION`。
2. 负责人已于 2026-09-13 批准 OD-01 至 OD-27。
3. WFS 来源、FX、佣金、included costs、不含税收入、售价反推、价格下限、毛利率、ROI、等级、头程、历史重算、BFF identity、WFS override 与字段 precedence 已有明确决定。
4. 本 PRP 已为 `Approved for implementation — Ready for implementation`。
5. 负责人已明确允许 `engineering-backend-architect` 在当前分支恢复实现。

`batchGetProductInfo` 官方 contract 仍不完整，因此只允许实现默认关闭、保守配置、fail-closed 的 outbound 路径和 mock/synthetic 测试；任何真实 Token、真实 provider transport、生产数据库/服务器、生产 migration、真实同步或部署仍须代码合并 `main` 后另行批准。

## 3. 已批准的上游边界

以下是既有合并能力及本 PRP 必须保持的边界：

- Product Core `products` / `product_platform_listings` 是新系统人工维护权威，外部同步不得静默覆盖。
- ProductList 发布的 `dwd_lingxing_sku_identity_index.lingxing_sku_id` 是详情同步候选输入。
- `product_id` 只能来自有证据的 confirmed mapping，不得用 SKU/MSKU/名称猜测。唯一例外是 `OD-ProductInfo-Bootstrap-01`：官方 ProductInfo `data[].sku` 可用于一次性受控的 exact SKU bootstrap；这不是模糊推断，且必须写可追溯 evidence ref。
- 外部数据遵循 Source Registry/RAW -> parser -> DWD -> 可选 DWS/read projection；业务 API 不读 RAW。
- 现有 `batchGetProductInfo` handler 默认拒绝 outbound；实现可补齐受专用安全开关保护的代码路径，但默认仍拒绝真实 transport。
- 现有 SKU detail route 只读持久化投影，不在 request path 调用外部平台。

## 4. 明确不允许事项

- 在本次 docs-only 门禁更新中编写或修改业务代码、migration、model、service、router 或测试；后续恢复实现须严格遵守本 PRP allowlist。
- 超出 Source Decision、本 PRP 或后续实现 Prompt 的 allowlist。
- 修改 `frontend/**`、`admin-frontend/**` 或 `old-system/**`。
- 读取 `.env`、请求 Token、调用 Lingxing/Walmart 或运行真实同步。
- API route 实时调用或批量拉取 `batchGetProductInfo`。
- 用 SKU、MSKU、名称、图片或顺序推断内部 `product_id`；`OD-ProductInfo-Bootstrap-01` 明确批准的 ProductInfo exact SKU bootstrap 除外。
- 写 DIM/FACT/Core 而没有批准的 writer/precedence；同步覆盖 Product Core 人工值。
- 把 Lingxing 标签与内部运营标签合并为同一权威数据集。
- 前端计算 WFS 配送费、每日仓储费、售价、ROI 或产品等级。
- 使用 float 处理金额/比率，假定币种、汇率、时区、费率、佣金或舍入。
- API/日志/错误返回 RAW、`payload_json`、第三方响应原文、认证材料、真实 SKU 或商品原始字段值。
- 自动历史重算、定时任务、全量同步、生产执行或部署。
- 默认双写、直接 SQL、未审计人工覆盖或未授权导出。

## 5. 后端实现范围

负责人已授权恢复实现，可包含且仅包含：

1. 为 `batchGetProductInfo` 补齐 default-off endpoint contract、请求构造、响应处理、work-item handler、RAW request/blob 引用、parser、DWD publisher、错误处理和测试；实现 PR 不执行真实请求。
2. 复用既有 DWD detail/images/Lingxing tags 和 DWS base profile；只在确有字段/约束缺口且 Source Decision 已批准时创建 migration。
3. 建立内部运营标签、规则版本、计算投影和用户表格视图的最小持久化模型。
4. 建立费用/售价 calculation service，输出版本化 breakdown；不在 router/frontend 重复公式。
5. 建立产品管理 BFF、配置、重算、视图与受限导出 API。
6. 建立 `OD-ProductInfo-Bootstrap-01` 约束的一次性 Product Core bootstrap：仅从已持久化 ProductInfo current 读取官方 `data[].sku/product_name` 投影，最小创建 Product 或 exact-link active Product；不覆盖 Product、不创建 listing，默认 dry-run，execute 必须显式授权。
6. 新增 `docs/api/product-management-api.md` 与 `docs/runbooks/production-lingxing-product-info-sync.md`，并同步字段字典、Data Interface Registry、Backend Module Catalog 和 Task Registry；runbook 只描述后续受控执行，不授权本 PR 生产操作。

不得为了“将来可能需要”创建通用规则引擎、第二套任务框架、通用报表平台、缓存、搜索索引或 speculative mart。

## 6. 数据库模型与 migration 计划

### 6.1 复用对象

- `products`、`product_platform_listings`：Product Core 人工权威。
- `dwd_lingxing_sku_identity_index`：外部 identity 与 confirmed Product mapping。
- `dwd_lingxing_sku_product_info_snapshots/current`：Lingxing detail 来源值。
- `dwd_lingxing_sku_product_images`：Lingxing 图片。
- `dwd_lingxing_sku_global_tags`：Lingxing 来源标签。
- `dws_sku_base_profile_current`：可重建基础尺寸/重量/成本投影。
- governance/ODS/lineage tables：同步 run、work item、RAW refs、parse/lineage evidence。

### 6.2 批准规划对象

以下对象获准进入实现设计，但仍须优先复用现有对象并保持最小集合；不得为未来需求新增字段、索引或通用框架：

| 规划对象 | Layer / grain | 用途 | 必要约束 |
|---|---|---|---|
| `manual_product_tags` | L10；一条内部运营标签定义 | 测品/清货/停售等受控词表 | stable key、状态、颜色、创建/停用 actor/time；禁止硬删除历史 |
| `manual_product_tag_assignments` | L10；product + tag + effective period | 内部标签分配 | Product FK、有效期、不重复生效、actor/reason/request ID |
| `ref_product_pricing_rule_versions` | L5/G5；一个 rule version | WFS、头程、毛利率、佣金、FX/引用和等级阈值 | immutable published version、effective_from/to、approval、currency/unit/rounding、无重叠生效区间 |
| `dws_product_management_pricing_current` | L9；一个内部 product + rule/input version | 当前费用、售价、ROI、grade、breakdown | 可由输入重建；唯一 input/rule hash；不接收人工或外部原始写入 |
| `user_table_views` | application state；principal + page key + view key | 产品管理列配置 | JSON 仅存 UI 配置；schema_version；owner-only scope；不存业务数据 |

`products.grade`、`products.purchase_price` 和 `product_platform_listings.wfs_fee` 已存在。任何新同步/计算字段不得复用这些列造成无声权威切换；已批准 precedence 为人工 override > 新系统配置/内部资料 > Lingxing 同步 > 计算字段，各层必须分开保存并在 breakdown 标明来源。

### 6.3 migration 规则

- migration 只覆盖本节获准且经代码现状确认确有必要的最小对象；本次 docs-only 更新不创建 migration。
- 使用 PostgreSQL、SQLAlchemy 2 和 Alembic；不得手写生产 SQL。
- 金额使用 `Numeric(18,4)` 或经批准的更高精度，API 使用 decimal string；比率使用明确 precision/scale。
- 配置版本不得就地覆盖；生效区间不得重叠；历史记录不得删除。
- 外键、唯一约束、check constraint 和索引只服务已批准的写入/查询。
- DWS/current 可重建，权威输入和规则必须留 lineage；不把 breakdown 只藏在不可审计 JSON 中。
- migration 只能在测试数据库验证；生产执行不属于默认实现范围。

## 7. `batchGetProductInfo` 同步设计

### 7.1 输入与分批

- 只从 account-scoped、active 的 `dwd_lingxing_sku_identity_index.lingxing_sku_id` 生成工作项。
- 不以 `lingxing_sku_code`、内部 SKU、MSKU 或名称反推 ID。
- 仓库 normalized 索引只提供 `productIds` / `sku_identifiers` / `skus` 三选一及候选上限 100，且 verification 状态为未验证；实现不得把它表述为已验证官方 contract。
- outbound endpoint 仅限 `/erp/sc/routing/data/local_inventory/batchGetProductInfo`，使用专用安全开关且默认关闭；未知 endpoint、字段或认证策略在 transport 前拒绝。
- 未取得官方原始证据前，mock-only 构造采用最小单 ID 工作项、单并发、无推测性 provider retry；batch size、频控、重试、并发、超时和 provider error 分类集中配置，不得以候选上限作为真实执行授权。
- 如果无法从仓库证据确定真实字段名、Content-Type、认证/query-sign 或响应契约，停止对应 outbound 构造，不得猜测。

### 7.2 执行与发布

```text
identity index
  -> governed id_batch_page work items
  -> approved readonly client
  -> credential-redacted ODS RAW blob/request ref
  -> versioned parser
  -> DWD snapshot/current + images + Lingxing tags
  -> lineage/DQ
  -> optional DWS recalculation
```

- API 失败仍记录受控 failure metadata；不得记录认证材料或未经脱敏 payload。
- 幂等基于 interface/account/work-item/request hash/run 边界；repository 不 commit，service/task 管理事务。
- 同步失败不得清空 current 或覆盖最后成功投影。
- API route 不触发实时详情补拉；stale/missing 以状态返回。
- 实现 PR 全部使用 MockTransport/synthetic fixtures。生产真实同步必须在代码合并后另获执行授权。

## 8. 产品详情入库设计

- parser 只映射官方证据和 Approved 字段字典中的字段；未知字段保留在 RAW，不自动进入 DWD/API。
- 原始值、canonical 值、source JSON path、parser version、source raw request ref、run ID 和 observed time 可追溯。
- 图片按 snapshot + ordinal 发布，主图唯一性延续现有约束。
- Lingxing global tags 按 snapshot 发布，绝不充当内部运营标签 writer。
- 成本、人员、商品文本和图片 URL 为敏感字段，必须有 field permission；默认列表不得返回开发人/负责人或成本。
- 空值、单位、currency、组合商品和 provider enum 不得猜测；DQ failure 不静默丢弃。

## 9. WFS 配送费计算设计

- 第一版费率证据来源为 `https://marketplace.walmart.com/walmart-fulfillment-services-pricing/`，由负责人于 2026-09-13 人工确认；该页面不是 runtime API，本实现不得自动抓取。
- 配置必须保存 market、fee type、尺寸/重量/类别区间、amount/rate、`currency_code`、unit、effective period、`source_url`、`confirmed_at`、`version`、`is_active`、confirmed actor 和 rounding rule。
- Product Management grain 是 SKU identity，不按 Product 聚合后随意选择 listing。WFS fee 依次选择：active identity-level override、primary Walmart listing active override、唯一 active listing override、多个 active listing 的一致 override、系统规则计算值。
- 多个 active Walmart listings 的 override 值不一致时，返回 `wfs_calc_status=needs_confirm` 与 `wfs_calc_reason=multiple_listing_wfs_overrides`，不得静默选择第一条。
- breakdown 返回 `wfsFeeSource`：`manual_sku_override`、`manual_primary_listing_override`、`manual_single_listing_override`、`manual_consistent_listing_override`、`calculated_rule` 或 `needs_confirm`。
- 计算输入只用有单位的获批尺寸/重量；无人工 override 且尺寸、重量或激活费率缺失时返回对应安全状态。无 active rate config 时 `wfs_calc_status=missing_rate`，聚合 pricing 状态为 `missing_wfs_rate`。
- `product_platform_listings.wfs_fee` 的人工值与 calculated fulfillment fee 分开；同步或计算值不得覆盖人工 override。
- 不调用 Walmart API，不把 WFS fulfillment fee 与 storage fee 合并。

## 10. WFS 每日仓储费计算设计

- 输入为包装长宽高（inch）、适用月费率和规则版本；体积来源、单位换算和规则版本必须可追溯。
- 公式固定为：

```text
package_volume_cuft = package_length_in * package_width_in * package_height_in / 1728
daily_storage_fee_per_unit_usd = package_volume_cuft * monthly_storage_rate_usd_per_cuft / storage_month_basis_days
estimated_storage_fee_usd = daily_storage_fee_per_unit_usd * pricing_storage_days
```

- `storage_month_basis_days` 默认 30，`pricing_storage_days` 默认 30，定价包含开关统一为 `include_storage_fee=true`；三者进入版本化规则配置。
- API 返回 `dailyStorageFeePerUnitUsd`、`dailyStorageFeePerUnitCny`、`estimatedStorageFeeUsd`、`estimatedStorageFeeCny` 和 breakdown。
- 输出是每件每日费用与按配置天数估算的每件费用；本 PRP 不引入库存数量或账单事实。
- 缺尺寸或激活费率时返回 `storage_calc_status`，不抛 500、不使用零值或最新规则回算历史。

## 11. 头程费用计算设计

- `first_leg_cost_per_kg_cny` 默认 `12.00`，由版本化配置发布，不散落硬编码。
- 第一版计费重量固定使用单品毛重 kg；缺失时 `pricing_calc_status=missing_weight`，不得改用净重、箱规或体积重猜测。
- 结果使用 Decimal 并保留两位小数；箱规摊分或体积重必须另建规则版本。
- 规则通过受保护配置 API 发布新版本；保存 effective period、change reason、approver 和 audit reference。
- 来源成本与人工规则值分开；输出 breakdown 引用重量输入 snapshot 和 rule version。

## 12. 建议/最低/清仓售价设计

第一版 `suggested_gross_margin_rate=0.20`、`minimum_gross_margin_rate=0.10`、`clearance_gross_margin_rate=0.00`，由前端通过受保护 API 配置并形成不可变规则版本。

- `price_usd` 表示 Walmart 前台不含销售税、VAT、GST 或其他税费的商品售价。第一版税费、平台代收税和单独运费收入均不进入收入、成本、毛利或 ROI；未来纳税口径需新 Source Decision/PRP。
- `usd_cny_rate` 只来自 pricing rule config，不写固定值；缺失时 `pricing_calc_status=missing_fx_rate`。配置记录 `updated_at`、`actor_ref` 及 canonical FX metadata。
- `revenue_cny = price_usd * usd_cny_rate`。平台佣金基数固定为收入：`commission_cny = revenue_cny * platform_commission_rate`。
- `platform_commission_rate` 允许全局默认；缺失按 0 计算，breakdown 返回 `commission_source=default_zero`，配置存在时为 `configured`。
- 第一版固定成本不含平台佣金：

```text
included_costs_cny =
    purchase_cost_cny
    + included_first_leg_cost_cny
    + included_wfs_fulfillment_fee_cny
    + included_estimated_storage_fee_cny
    + other_fixed_cost_cny
```

- `include_first_leg_fee`、`include_wfs_fulfillment_fee`、`include_storage_fee` 默认 `true`，`other_fixed_cost_cny` 默认 `0`。每项在 breakdown 返回 source 和 `included=true/false`。
- 缺采购价，或相应 include 开关为 true 时缺重量、WFS 费率、仓储费率，分别返回 `missing_purchase_cost`、`missing_weight`、`missing_wfs_rate`、`missing_storage_rate`，不抛 500。
- 毛利口径固定为：`gross_profit_cny = revenue_cny - commission_cny - included_costs_cny`；`gross_margin_rate = gross_profit_cny / revenue_cny`。`revenue_cny <= 0` 时返回 `invalid_revenue`。
- 三种售价按目标毛利率反推：

```text
price_usd = included_costs_cny
    / (usd_cny_rate * (1 - platform_commission_rate - target_margin_rate))
```

- 清仓售价同样包含平台佣金。`1 - platform_commission_rate - target_margin_rate <= 0` 时返回 `invalid_pricing_denominator` 和安全 reason，不返回猜测价格、不抛 500。
- 规则必须满足 suggested target margin >= minimum target margin >= clearance target margin，否则返回 `invalid_pricing_rule_config`。结果必须满足 `suggested_price_usd >= minimum_price_usd >= clearance_price_usd`，其中 clearance 是第一版系统价格下限。
- `manual_min_price_usd` 可预留但不强制实现完整维护入口；已有 active override 时，最终价格不得低于 `max(clearance_price_usd, manual_min_price_usd)`，breakdown 标记 `source=manual_override`。
- `raw_price_usd` 使用 Decimal 高精度。`rounding_mode=none` 时先按 `ROUND_HALF_UP` 保留两位；若结果低于 raw price 并破坏目标毛利率，则提升到下一美分。预留 `nearest_0_99` / `nearest_0_95`，后续启用时同样必须向上取整。
- breakdown 至少返回 `target_margin_rate`、`denominator`、`raw_price_usd`、`final_price_usd`、`rounding_mode`、各成本项和来源。
- 三种售价分别保存 target、result、`currency_code`、rule IDs、input snapshot refs、calc version 和 breakdown。前端只展示，不补算。

## 13. 毛利率、ROI 与产品等级设计

- ROI 默认 `roi_base=purchase_cost`，公式为 `roi=gross_profit_cny/purchase_cost_cny`；`roi_base=total_cost` 时分母为 `included_costs_cny`，breakdown 返回 `roiBase`。
- ROI 分母缺失或非正时返回 `missing_purchase_cost` 或 `invalid_roi_base`，不抛 500。
- 产品等级只按建议售价下的 `gross_margin_rate` 和 ROI 计算：毛利率 >= `0.20` 且 ROI >= `1.00` 为 A；毛利率 >= `0.10` 且 ROI >= `0.50` 为 B；其他可计算商品为 C。
- 缺采购价、重量、WFS 费率、仓储费率、汇率、非法定价分母或无法计算价格时为异常；API 返回 `productGrade` 与 `gradeReason`。
- `grade_a_min_margin_rate`、`grade_a_min_roi`、`grade_b_min_margin_rate`、`grade_b_min_roi` 由前端通过受保护 API 配置并形成版本。
- calculated grade 与 manual grade/source status 分开；不得把 Lingxing `status` 或 `products.grade` 静默替换为计算结果。
- AI 不参与权威等级计算。
- 每次发布记录 rule version、calc version、input snapshot、effective/business date 和 audit lineage。

## 14. Product Management BFF API

所有响应使用现有 `{ success, data, error, meta, request_id }` envelope。`{sku_id}` 第一版固定表示 `dwd_lingxing_sku_identity_index.id` 对应的新系统内部 `identity_id`，不是 SKU 字符串、Lingxing external ID 或未经确认的 Product Core ID；仅通过 confirmed `product_id` mapping 组合 Product Core。

| Method | Route | 目的 | Required permission | 核心边界 |
|---|---|---|---|---|
| GET | `/api/product-management/skus` | 服务端分页/筛选产品管理行 | `products:read` | bounded page，稳定排序；不返回人员/RAW；不实时计算/拉外部 API |
| GET | `/api/product-management/skus/{sku_id}` | 产品管理详情与当前 breakdown 摘要 | `products:read`；成本另需 `products:cost:read` | confirmed mapping；field permission；不存在/越 scope 均安全 404/403 |
| GET | `/api/product-management/options` | 返回已批准筛选/标签/等级选项 | `products:read` | 只读 reference/manual config；禁止 unscoped distinct scan |
| POST | `/api/product-management/skus/export` | 受限导出当前查询 | `products:export`（新增前须登记） | 执行同等 row/field scope；默认最多 5000 行；首版可返回 `queued` / `not_implemented_safe` |

列表首屏只返回核心字段；详情、图片和 breakdown 按需读取。筛选、排序、批量 SKU 搜索和分页在后端完成；禁止前端加载全量数据。响应 `meta` 标记 persisted freshness、stale/partial/input-missing 状态，不把系统 `updated_at` 冒充来源新鲜度。

列表 contract 的最小字段映射如下：

| 响应字段 | 来源/含义 | 边界 |
|---|---|---|
| `sku_id` | 新系统内部 `identity_id` | 不使用 SKU 字符串、Lingxing ID 或猜测的 `product_id` 代替 |
| `sku`、`product_name` | Product Core effective identity/name | 不以 Lingxing code/name 静默覆盖 |
| `primary_image` | confirmed mapping 对应的 DWD primary image | 可空；不返回原始图片对象 |
| `internal_tags` | 新系统内部运营标签 | 与 `lingxing_tags` 分开；列表默认不返回来源标签 |
| `product_grade` | 获批 precedence 后的 effective grade | manual/calculated/source 状态分开，缺规则时不猜测 |
| `wfs_fulfillment_fee` | 版本化规则的每件履约费投影 | 不复用含义不明的裸 `wfs_fee` |
| `wfs_daily_storage_fee` | 版本化规则的每日单位仓储费投影 | 不乘库存数量，不表示累计账单费用 |
| `suggested_price_usd`、`minimum_price_usd`、`clearance_price_usd` | 获批成本与目标 margin 的不含税计算结果 | decimal string + `currency_code=USD`；缺输入时为空并返回状态 |
| `calculation_status`、`calculated_at`、`rule_version` | 投影状态与版本 | `calculated_at` 不是来源新鲜度 |

详情 contract 在列表字段之外按需返回已批准的基础资料、报关/清关、规格、图片和 pricing breakdown。开发人、负责人、成本及来源标签只在字段权限明确时返回；列表不得为详情 convenience 预加载全部图片或 history。

## 15. 价格规则配置 API

| Method | Route | 目的 | Required permission |
|---|---|---|---|
| GET | `/api/product-management/pricing-rules` | 查询规则版本与当前生效版本 | `products:pricing_rules:read` |
| PUT | `/api/product-management/pricing-rules` | 发布新规则版本 | `products:pricing_rules:update` |

- PUT 不是原地覆盖：创建新版本并保留旧版本。
- 请求必须包含 change reason、effective period 和完整的 approved rule set；敏感改动需确认/审批/审计。
- 第一版配置至少覆盖 WFS fulfillment/storage 规则引用、`storage_month_basis_days=30`、`pricing_storage_days=30`、`include_first_leg_fee=true`、`include_wfs_fulfillment_fee=true`、`include_storage_fee=true`、`other_fixed_cost_cny=0`、`usd_cny_rate`、`platform_commission_rate`、`first_leg_cost_per_kg_cny=12.00`、三档毛利率、`roi_base`、四个等级阈值和 `rounding_mode=none`。
- `usd_cny_rate` 不设文档默认数值；更新时记录 `updated_at` 与 `actor_ref`。前端可维护获准配置，但所有权威计算只在后端执行。
- 后端检查目标 margin 顺序、非法定价分母、区间冲突、单位、`currency_code`、precision、scale 和 rounding；不接受 unknown fields。配置可保存但计算非法的分母必须在重算时产生明确状态。
- 响应不回传 secret、来源原文或不必要业务样本。
- WFS 官方费率证据、FX reference 和审批引用只保存安全 reference，不在配置中存网页凭据或 token。

## 16. 重新计算与 breakdown API

| Method | Route | 目的 | Required permission |
|---|---|---|---|
| POST | `/api/product-management/skus/recalculate-pricing` | 创建受控重算任务或小范围同步计算 | `products:pricing:recalculate` |
| GET | `/api/product-management/skus/{sku_id}/pricing-breakdown` | 查看已持久化计算组成 | `products:read`；敏感成本另需 `products:cost:read` |

- 重算必须有显式 product scope、rule version/effective date、reason、idempotency key、影响预览和最大数量。
- `scope` 只允许 `all`、`selected`、`missing_price`、`pricing_failed`；`selected` 必须提供 bounded internal identity IDs，其他 scope 也必须执行 permission/data-scope 和数量保护。
- 重算必须创建安全 task/run 记录；不得在 HTTP 请求中无界循环。
- PUT pricing rules 只发布当前/未来规则版本，不同步阻塞式全量重算。新规则仅影响后续主动重算和后续同步计算。
- 不修改历史 snapshot，只更新 current/pricing profile 当前结果，并保留 `pricing_rule_version`。
- breakdown 只返回批准后的 components、decimal amount/currency、rule/version、input status 和 calculated_at；不返回 RAW、第三方 payload 或 source field values。

## 17. 用户表格视图 API

| Method | Route | 目的 | Required permission |
|---|---|---|---|
| GET | `/api/user-table-views/product-management` | 读取当前 principal 的产品管理视图 | `products:read` |
| PUT | `/api/user-table-views/product-management` | 保存当前 principal 的列配置 | `products:table_views:update` |

- 服务端从可信 principal 取得 owner，不接受 body 中任意 user ID。
- schema 只允许列 key、顺序、宽度、visible/fixed 等 UI metadata；不得保存过滤出的真实 SKU、业务数据、权限或 secret。
- 校验 page key、schema version、允许列清单和 payload 大小；unknown/retired columns 有确定迁移或重置策略。
- 不使用 localStorage/sessionStorage 作为权威保存；不复制 navigation metadata。

## 18. 权限与数据范围

- 所有端点 protected by default，不硬编码角色名。
- 复用 `products:read` 与 `products:cost:read`；export/rules/recalculate/view-write 使用独立 permission key，并须在实现 PR 同步登记。
- BFF 必须同时执行 Product Core scope 与 Lingxing `source_account_ref` scope；缺失 provider、未知 scope、`none` 或 mapping 不确认时 fail closed。
- 无获准 `source_account_ref` 不返回数据，且禁止跨账号读取。成本、售价、ROI、毛利率均按敏感经营字段处理；现有权限能力不足时在 API 层保留并强制 cost permission gate seam，而不是默认放行。
- 列表不默认返回采购成本、开发人、负责人等敏感字段。
- 写规则、标签、重算、导出均记录 actor、action、internal target IDs、request ID、状态和时间；日志不记录真实值。
- Repository 只做 scoped query，不做权限判断、不 commit、不调用外部 API、不读 legacy MySQL。

## 19. 安全与脱敏

- API 不返回 ODS/RAW、`payload_json`、request body、第三方响应原文、认证材料、签名或 secret reference value。
- 日志、异常、审计 message 不打印真实 SKU、MSKU、商品名称、成本、商品原始字段、图片 URL、完整 external ID list 或计算输入值。
- 安全上下文仅保留内部 UUID、safe count、rule/calc version、request/run/work-item ID 和稳定 error code。
- 外部 client 在序列化/持久化前脱敏；产品管理 BFF 永不绕过 DWD/DWS 去读取 RAW。
- 导出应用同等 page/action/data/field/export permission、脱敏、行数上限和审计。

## 20. 错误码

以下稳定错误码必须与现有 Backend API Foundation 对齐：

| HTTP | Error code | 含义 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 缺少可信 principal |
| 403 | `FORBIDDEN` | 缺少 permission |
| 403 | `DATA_SCOPE_DENIED` | 数据范围缺失或拒绝 |
| 404 | `NOT_FOUND` | 资源不存在或不可见 |
| 409 | `IDENTITY_MAPPING_REQUIRED` | 没有 confirmed Product/Lingxing mapping |
| 409 | `RULE_VERSION_CONFLICT` | 规则版本或生效区间冲突 |
| 409 | `RECALCULATION_NOT_AUTHORIZED` | 历史/大范围重算未批准 |
| 422 | `VALIDATION_ERROR` | 输入、单位、币种、分页或配置验证失败 |
| 422 | `CALCULATION_INPUT_INCOMPLETE` | 缺少计算所需输入 |
| 424 | `RULE_NOT_AVAILABLE` | 对应日期无获批规则 |
| 503 | `SOURCE_DATA_STALE` | 持久化来源过期且 policy 禁止继续发布 |
| 500 | `INTERNAL_ERROR` | 安全通用错误 |

外部 provider 原始错误、SQL、stack trace、配置值和输入值不得透传。

`pricing_calc_status`、`storage_calc_status`、`commission_source`、`productGrade` 和 `gradeReason` 是数据状态/breakdown 字段，不应把缺尺寸、重量、费率或 FX 转换为 500。

第一版至少支持以下安全状态：`missing_fx_rate`、`missing_purchase_cost`、`missing_weight`、`missing_wfs_rate`、`missing_storage_rate`、`invalid_revenue`、`invalid_pricing_denominator`、`invalid_pricing_rule_config`、`invalid_roi_base`。WFS 组件另返回 `wfs_calc_status=missing_rate/needs_confirm`；listing override 冲突 reason 为 `multiple_listing_wfs_overrides`。

## 21. 测试计划

### 21.1 同步与 parser

- synthetic fixtures 覆盖 batch contract、分批、幂等、失败 metadata、空/未知字段、单位/currency 和 lineage。
- MockTransport 覆盖 approved endpoint、认证参数脱敏、限流/重试上限和 outbound disabled。
- 覆盖专用 outbound 开关默认关闭、真实调用 fail closed、官方 contract 缺口不被猜测，以及未授权 transport/token 调用次数为 0。
- 验证 route/request path 不调用外部 client；同步失败不清空 last-good current。
- 真实 API、Token、数据库/服务器连接和生产 migration 不在测试中执行。

### 21.2 计算

- 对每个 approved rule version 使用确定性 Decimal 测试向量，覆盖边界区间、缺失输入、currency/FX、单位换算、舍入和 effective date。
- 验证 suggested/minimum/clearance、margin、ROI、grade 与 breakdown 同源；前端无计算依赖。
- 覆盖不含税收入、commission revenue base、included-cost 开关、反推售价、毛利/毛利率、非法 revenue/price denominator、目标 margin 顺序与价格下限。
- 覆盖 WFS/storage 缺尺寸/重量/费率、`missing_fx_rate`、`missing_purchase_cost`、`missing_weight`、commission default-zero、storage 两个 30 天默认值、purchase/total-cost ROI 分母、A/B/C/异常阈值和 `ROUND_HALF_UP` 两位。
- 覆盖 identity/primary/single/consistent listing WFS override、冲突 `needs_confirm`、无 override 后 calculated rule，以及不得静默选第一条。
- 覆盖 `manual_min_price_usd` 存在时的 floor；若测试预留 `nearest_0_99/nearest_0_95`，结果必须向上且不破坏目标毛利率。
- 验证 manual/source/calculated precedence、rule change、current rebuild 和历史不自动重算。
- 性质测试或参数化测试可覆盖区间边界；不引入额外依赖除非必要且获批。

### 21.3 API、权限与安全

- 产品列表/详情/options 的分页、筛选、稳定排序、scope 和字段权限。
- 导出与当前 query/scope/field permission 一致，默认上限 5000；若首版仅安全占位，覆盖 `queued` / `not_implemented_safe` 且不得假装生成文件。
- pricing rules 版本新增、不重叠、审批/audit；recalculate 的 idempotency 和上限。
- user table views owner isolation、allowlist、schema version、payload size 和无业务数据。
- 每个端点覆盖 401/403/404/409/422/5xx safe envelope 与 `request_id`。
- 响应、repr、exception、日志和 audit 不包含 RAW、认证材料、真实 SKU/商品值或第三方原文。

### 21.4 验证命令

实现 Prompt 必须基于实际 `pyproject.toml`/README 确认命令，至少真实运行并报告：

```bash
cd backend
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy app tests
uv run pytest -q -rs
uv run alembic -c alembic.ini heads
cd ..
git diff --check
git status --short --untracked-files=all
```

数据库集成测试或 migration upgrade 只能使用明确授权的 disposable test PostgreSQL；未运行必须写 `Not run` 和原因，不得声称通过。

## 22. 验收标准

- [x] Source Decision 为 `READY_FOR_PRP`，OD-01 至 OD-27 全部解决。
- [x] PRP 已由负责人批准为 Ready for implementation。
- [x] 负责人已解除售价公式 Recovery Stop，并授权在当前分支恢复 Approved PRP 实现。
- [ ] 实现 diff 仅在批准 allowlist，未触及 frontend/old-system/secrets。
- [ ] 所有目标 API 有 schema、response model、permission、data scope、安全 envelope 和测试。
- [ ] `batchGetProductInfo` 只通过治理同步写 RAW/DWD，不在业务 route 实时调用。
- [ ] Product/Lingxing identity 只通过 confirmed mapping 组合；除 `OD-ProductInfo-Bootstrap-01` 的 exact SKU bootstrap 外，未使用 SKU 字符串推断。
- [ ] Lingxing 标签与内部运营标签、source/manual/calculated grade 分离。
- [ ] 费用、售价、ROI、grade 只由后端版本化规则计算；breakdown 可追溯，前端不计算。
- [ ] 金额/比率/单位/时区/舍入符合项目 canonical contract。
- [ ] API、日志、错误、导出不泄露 RAW、第三方原文、认证材料或未授权业务值。
- [ ] 规则更新与重算可审计、幂等、有范围上限，不静默重写历史。
- [ ] Registry、Catalog、API docs、Task Registry 与实现事实同步，不提前标记 implemented。
- [ ] Ruff、mypy、pytest、Alembic heads、diff/scope/secret scans 按实际结果报告。

## 23. 实现停止条件

遇到任一情况立即停止并交回负责人/架构师：

- 实际 worktree、branch、allowlist 或任务范围与本 PRP 不一致。
- 需要真实 Lingxing/Walmart 调用、真实 Token、生产 sync/migration/database/server/deployment。
- `batchGetProductInfo` 需要使用仓库未证实的请求字段、Content-Type、认证/query-sign、成功/错误码、批量上限、频控或 retry 语义；不得猜测或据此放行真实 transport。
- WFS 具体 fulfillment/storage 费率、市场/旺季区间或 fulfillment 分段算法尚未被受控录入并激活：允许实现配置、calculator、状态、API 字段和 synthetic 测试，但真实费用金额计算必须停止并返回缺失状态，不得抓取网页或猜测金额。
- 需要引入未获准的实时 FX 来源、类目佣金、箱规/体积重头程、价格取整策略或历史规则回算。
- 需要使用 SKU/MSKU/名称猜测 identity，或存在未处理的一对多/多对多 mapping；`OD-ProductInfo-Bootstrap-01` 仅豁免受控 exact SKU create/link，重复或不确定映射仍必须跳过并 fail closed。
- 需要让外部/计算值覆盖 Product Core 人工字段而 precedence/override 未批准。
- 需要新增未批准表、API、permission、依赖、worker、schedule、mart、cache 或第二套框架。
- 需要在 API route 调外部平台、读 RAW、返回第三方原文或记录敏感值。
- 查询/导出/重算无法限制数据 scope、字段、数量、时间或性能。
- migration 与现有 metadata/head 冲突，或测试需要未授权真实数据库。
- 工作区、分支或 allowlist 与 Prompt 不一致。

## 24. 负责人批准记录

```text
Status: Approved for implementation — Ready for implementation
Source Decision approved and READY_FOR_PRP: Yes
Approved implementation scope: Sections 5-21 only
Approved database objects/migrations: Minimal objects required by Section 6; test validation only
Approved APIs and permissions: Sections 14-18; protected and fail closed
Approved batchGetProductInfo evidence/outbound boundary: Default-off code path and mock/synthetic tests only; no real request
Approved WFS/first-leg/pricing/margin/ROI/grade rules: Owner decisions recorded in Sections 9-13 and Source Decision OD-05 to OD-27
Approved pricing formula: Tax-exclusive price; revenue, commission, included costs, gross profit/margin and reverse-price equations in Section 12
Approved WFS override rule: identity > primary listing > single listing > consistent listing > calculated; conflicts fail safe
Approved identity and field precedence: internal identity_id; manual override > new-system config/internal > Lingxing sync > calculated
Approved ProductInfo bootstrap exception: OD-ProductInfo-Bootstrap-01; minimal Product sku/product_name create or exact active-SKU link only; no overwrite/listing
Approved export/recalculation boundary: export <= 5000 or safe placeholder; bounded run-based recalc; no automatic historical full recalculation
Approved docs: docs/api/product-management-api.md and docs/runbooks/production-lingxing-product-info-sync.md
Approved Agent Skill: engineering-backend-architect
Approved by: Project Owner
Approved date: 2026-09-13
Implementation Recovery Stop resolved: Yes
Implementation resume on current branch authorized: Yes
```

当前结论：本 PRP 已 Ready for implementation，售价公式阻塞已解决。主执行角色 Backend Engineer 可使用 `engineering-backend-architect` Agent Skill 在当前分支继续 Approved PRP 实现；本次门禁更新仍只修改文档。该批准不包含任何真实 Token、真实 Lingxing/Walmart 调用、生产数据库/服务器、生产 migration、真实同步、生产配置修改或部署。
