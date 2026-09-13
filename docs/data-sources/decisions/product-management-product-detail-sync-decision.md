# 产品管理产品详情同步与计算字段数据源决策

## 1. 决策状态

```text
调查日期：2026-09-13
调查人：架构师 Codex（仅复核仓库静态证据）
决策文件：docs/data-sources/decisions/product-management-product-detail-sync-decision.md
后续 PRP：PRPs/product-detail-sync-product-management-api-v1.md
接口总体状态：READY_FOR_PRP
是否包含 NEED_OWNER_DECISION：否（批准范围内）
负责人批准状态：已批准（2026-09-13）
进入 PRP：已批准
实现授权：由本决策引用的 Approved PRP 和后续独立实现 Prompt 共同授予
真实外部 API 调用：本次未执行；生产真实调用仍未授权
数据库或服务器访问：未执行
```

`READY_FOR_PRP` 仅适用于本文定义的产品详情同步代码路径、产品管理 BFF、版本化规则和计算投影。负责人已允许对应 PRP 进入批准状态；本决策本身不授权执行真实 Lingxing 请求、请求真实 Token、连接生产数据库/服务器、运行生产 migration、真实同步或部署。生产真实 `batchGetProductInfo` 必须在代码合并 `main` 后再次单独授权。

## 2. 目标接口

```text
GET  /api/product-management/skus
GET  /api/product-management/skus/{sku_id}
GET  /api/product-management/options
POST /api/product-management/skus/export
GET  /api/user-table-views/product-management
PUT  /api/user-table-views/product-management
GET  /api/product-management/pricing-rules
PUT  /api/product-management/pricing-rules
POST /api/product-management/skus/recalculate-pricing
GET  /api/product-management/skus/{sku_id}/pricing-breakdown
```

业务用途：以公司内部 SKU 为页面粒度，组合已确认的 Product Core、已同步的 Lingxing 产品详情、内部运营标签、版本化费用/售价规则和可重建计算结果。API route 只读新系统 PostgreSQL 中已发布的数据，不在请求期间调用 Lingxing、Walmart 或其他外部平台。

## 3. 关联证据

- `docs/decisions/2026-09-12-integration-sync-governance-backend-v1-source-decision.md`
- `PRPs/integration-sync-governance-backend-v1.md`
- `docs/api/integration-sync-governance-sku-detail-v1.md`
- `docs/data-sources/decisions/products-basic-information-query-decision.md`
- `PRPs/product-management-backend-mvp.md`
- `backend/app/modules/integration_sync/handlers/lingxing_batch_product_info.py`
- `backend/app/modules/integration_sync/parsers/lingxing_product_info.py`
- `backend/app/modules/sku_detail/models.py`
- `backend/app/modules/sku_detail/publisher.py`
- `backend/app/modules/sku_detail/router.py`
- `backend/app/modules/products/models.py`
- `frontend/src/pages/products/ProductManagementPage.tsx`
- `frontend/src/pages/products/productManagementTypes.ts`
- `docs/integrations/lingxing-walmart-openapi/normalized/interfaces.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/request_params.csv`
- `docs/integrations/lingxing-walmart-openapi/normalized/response_fields.csv`
- `docs/integrations/lingxing-walmart-openapi/api-verification-status.csv`

静态证据能证明现有表、parser、publisher、route 及候选字段的位置，但不能证明生产数据、新鲜度、外部接口限流或真实返回稳定性。负责人另于 2026-09-13 确认 Walmart WFS Pricing 页面为第一版费率人工取证来源；本次未调用或抓取该页面，实际配置值仍必须经受控录入和版本发布。

## 4. 旧系统与来源调查

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 本次未读取 `old-system/**`。现有新前端页面证据为 `ProductManagementPage.tsx`，当前使用静态页面数据，不是来源证据。 |
| 旧 API | 本次不采用旧系统 API。既有新后端 SKU 详情 API 只读持久化投影，见 `docs/api/integration-sync-governance-sku-detail-v1.md`。 |
| 旧接口文件位置 | 不适用；本决策禁止引入旧系统运行时依赖。 |
| 读取表 | 已实现候选包括 `products`、`product_platform_listings`、`dwd_lingxing_sku_identity_index`、`dwd_lingxing_sku_product_info_current`、`dwd_lingxing_sku_product_images`、`dwd_lingxing_sku_global_tags`、`dws_sku_base_profile_current`。规则、内部标签、用户表格视图和价格投影对象由 Approved PRP 限定后新增。 |
| 表写入方 | Product Core 由 Product Management service 写；Lingxing DWD/DWS 由已治理 importer/parser/publisher 写。Approved PRP 可实现规则、内部标签、用户视图及重算 writer，但不得运行生产写入。 |
| cron / 脚本 / 外部 API | ProductList 正式手工同步有独立边界；`batchGetProductInfo` 允许实现默认关闭的 outbound 代码、run/work-item、解析和入库路径。本 PR 不执行真实调用，不启用 schedule。 |
| 人工写库入口 | 禁止直接 SQL。现有 Product Core 只允许经 API service 写；未来内部标签、规则和视图也必须经受保护 API、审计和事务边界写入。 |
| 外部平台重新获取可能性 | Lingxing 详情可按 `REBUILD_SYNC` 建设；官方参数仍缺时只实现 fail-closed/default-off 路径，不得猜测或真实执行。WFS 费率由负责人确认的官方页面人工取证后发布为版本化配置，不调用 Walmart API。 |
| 少量配置数据可行性 | 头程、毛利率、WFS 费率、佣金、`usd_cny_rate` 和等级阈值均由版本化价格规则配置维护；默认值和缺失行为已由负责人确认。 |
| 短期策略 | 在 MockTransport/synthetic 测试下实现详情同步、规则、投影和 API；所有真实 Lingxing/Token/生产连接开关保持关闭。 |
| 长期策略 | 外部数据 RAW-first 同步至 DWD；内部规则写入版本化配置；计算结果进入可重建投影；BFF 只组合已确认身份映射和获批字段。 |

## 5. 数据集分类

`数据角色` 用来区分规则配置与派生投影，不是第二种数据源分类。每行仍只使用门禁允许的一种分类。以下分类已由负责人批准进入 PRP；真实外部执行仍受独立门禁约束。

| ID | 数据集或字段组 | 业务用途 | 当前/目标权威来源 | 分类 | 数据角色 | 短期策略 | 长期策略与切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|---|
| A | Lingxing SKU identity | 为详情同步提供稳定输入 | 已同步 `dwd_lingxing_sku_identity_index.lingxing_sku_id` | `REBUILD_SYNC` | L6 identity | 只使用 ProductList 发布的 identity 行 | 详情同步以 external ID 工作项运行；禁止用 SKU 字符串猜测 `product_id` | 否 |
| B | Lingxing 产品详情 | 名称、SKU code、开发人、采购、报关、材质、用途、尺寸、重量、箱规 | Lingxing `batchGetProductInfo`，经 RAW/标准化/DWD 发布 | `REBUILD_SYNC` | 外部同步数据 | 实现 default-off outbound；不执行真实请求 | 官方证据不足处 fail closed；API route 永不实时拉取 | 否：真实执行另行批准 |
| C | Lingxing 图片 | 产品图片展示 | `batchGetProductInfo` 图片字段，经 `dwd_lingxing_sku_product_images` | `REBUILD_SYNC` | DWD child | 只读已发布行 | 随详情 snapshot 重建，保留 RAW lineage | 否 |
| D | Lingxing 标签 | 展示来源标签 | `batchGetProductInfo` 标签字段，经 `dwd_lingxing_sku_global_tags` | `REBUILD_SYNC` | DWD child | 与内部运营标签严格分开 | 随详情 snapshot 重建，不接受人工覆盖 | 否 |
| E1 | 内部运营标签 | 测品、清货、停售等内部运营标记 | 新系统受保护人工维护入口 | `NEW_SYSTEM_OWNED` | L10 manual | 由 Approved PRP 建设最小表/API | 单独存储、审计、保留历史；不得写回 Lingxing 标签 | 否 |
| E2 | 产品等级规则/人工结果 | A/B/C/异常等内部判断 | 新系统版本化规则和受审计人工覆盖 | `NEW_SYSTEM_OWNED` | G5 + L10 | 按已批准阈值计算，人工 override 优先 | 计算值与人工值分离，形成 effective value | 否 |
| F | WFS fulfillment fee 规则 | 计算每件 WFS 配送费 | Walmart WFS Pricing 页面（负责人确认 2026-09-13）+ 新系统配置 | `NEW_SYSTEM_OWNED` | calculated rule config | 不调用 Walmart API；无配置时返回安全状态 | 保存 `source_url/confirmed_at/version/is_active` 及完整费率条件 | 否 |
| G | WFS 每日仓储费规则 | 按包装体积计算每日单位及估算仓储费 | 同一 Walmart WFS Pricing 来源 + 新系统配置 | `NEW_SYSTEM_OWNED` | calculated rule config | 月基准和估算天数默认均为 30 | 版本化保存费率、体积/时间单位、条件和有效期 | 否 |
| H | 头程费用规则 | 以单品毛重计算单位头程费用 | 负责人批准默认 `12.00 CNY/kg` | `NEW_SYSTEM_OWNED` | calculated rule config | 缺毛重时 `missing_weight` | 前端配置新版本；两位小数；箱规/体积重另发新版本 | 否 |
| I | 售价目标规则 | 建议/最低/清仓售价 | 批准毛利率 `0.20`、`0.10`、`0.00` | `NEW_SYSTEM_OWNED` | calculated rule config | 后端 Decimal 计算，rounding 默认 `none` | 前端配置新版本；预留 `nearest_0_99/nearest_0_95` | 否 |
| J1 | ROI 与等级阈值规则 | 按建议售价对应的毛利率和 ROI 计算产品等级 | 负责人批准的 purchase-cost ROI 和 A/B/C 阈值 | `NEW_SYSTEM_OWNED` | calculated rule config | ROI 分母默认采购成本；阈值按批准值 | `roi_base` 可在新规则版本改为 `total_cost` | 否 |
| J2 | 对外展示的 ROI/产品等级结果 | 产品管理展示与筛选 | 获批输入和规则生成的后端结果 | `NEW_SYSTEM_OWNED` | calculated projection | 缺必要输入时为“异常”并给出 reason | 由版本化输入重建，人工 override 优先 | 否 |
| K | 产品管理计算投影 | 组合 DWD、Product Core 和规则版本后的费用/售价/breakdown | 获批输入与 calculation service | `NEW_SYSTEM_OWNED` | calculated projection / L9 | 只更新 current/profile，不改历史 snapshot | 可由来源和规则版本重建，不是独立权威 | 否 |
| L | 用户表格视图 | 保存用户列配置 | 新系统受保护用户偏好入口 | `NEW_SYSTEM_OWNED` | application state | 不由前端 storage 冒充服务端状态 | 按 principal + page key 隔离，版本化 schema 并可重置 | 否 |

## 6. 数据血缘

| 接口字段/字段组 | 源系统、表或接口 | 原始字段/输入 | 标准字段或目标 | 转换/公式 | 时区 | 币种/单位 | 更新与新鲜度 | 写入方 | 风险与证据 |
|---|---|---|---|---|---|---|---|---|---|
| `sku_id`（BFF resource ID） | L6 identity | `dwd_lingxing_sku_identity_index.id` | `identity_id`（API alias 为 `sku_id`） | 直接使用新系统内部 identity UUID；绝不暴露 Lingxing ID 为主路径 | N/A | N/A | 取 identity persisted freshness | identity publisher | Product Core 字段仅通过 confirmed `product_id` mapping 组合；不得用 SKU 猜测 |
| Lingxing sync input | `dwd_lingxing_sku_identity_index` | `lingxing_sku_id` | batch work-item ID list | 只取 account-scoped active identity；不以 SKU code 反推 | UTC | N/A | 取已发布 identity 的 persisted freshness | ProductList publisher / sync dispatcher | `product_id` 可空；未映射仍可同步详情但不能自动并入 Product Core |
| 产品详情 | `batchGetProductInfo` -> ODS RAW refs -> DWD snapshot/current | `data[]` 候选字段 | parser 中定义的产品、报关、材质、尺寸、重量字段 | 可逆类型/单位标准化并记录 parser version、raw ref、run ID | 来源时间待证；系统时间 UTC | 金额用 Decimal/Numeric 并带 `currency_code`；尺寸/重量保留单位 | 由 sync run 决定，不能声称实时 | integration handler/parser/publisher | 离线字段表存在，但验证状态为“未验证” |
| 图片 | `data[].pic_url` / `picture_list[]` | URL、primary 标记 | `dwd_lingxing_sku_product_images` | 受控 URL 校验、ordinal、snapshot lineage | UTC metadata | N/A | 随详情 snapshot | SKU detail publisher | 不返回 RAW 图片对象或非必要源字段 |
| Lingxing 标签 | `data[].global_tags[]` | tag ID/name/color | `dwd_lingxing_sku_global_tags` | 保留来源语义与 snapshot lineage | UTC metadata | N/A | 随详情 snapshot | SKU detail publisher | 不等于内部运营标签 |
| 内部标签 | 受保护标签 API | 受控 label + assignment | L10 internal tags/assignments | 新版本/assignment event；保留 actor、reason、request ID | UTC | N/A | 人工变更 | Product Management service | 停用不删除历史；与 Lingxing global tags 分开 |
| 采购成本输入 | DWD detail / Product Core | `purchase_cost_cny`、`products.purchase_price` | `effective_purchase_cost` | Product Core 人工 override 优先；否则按配置/内部资料、Lingxing 来源的批准顺序解析 | UTC | amount + `currency_code`; FX 记录 `fx_rate/fx_date/fx_source` | 记录输入 snapshot 与规则版本 | calculation service | 不允许同步覆盖 Product Core 人工值 |
| WFS fulfillment fee | Walmart WFS Pricing 页面 + 版本化配置 + 获批产品属性 | 费率区间、重量/尺寸/类别 | `wfs_fulfillment_fee` | 后端按 active rule version 计算；缺尺寸/重量/费率返回安全状态 | effective date | Decimal，明确 currency、重量/尺寸单位和 rounding | 规则版本生效时间 | pricing calculation service | 来源 URL 由负责人确认；具体费率值须受控录入，现有 listing 人工值优先 |
| WFS 每日仓储费 | 同一官方来源 + 配置 + 包装尺寸 | length/width/height in、monthly rate、basis/storage days | daily/estimated storage outputs | `volume_cuft=L*W*H/1728`；daily=`volume*monthly_rate/30`；estimated=`daily*30`，天数均为可配置默认值 | rule effective date | USD 与经配置 FX 转换的 CNY；cuft/day | 规则版本生效时间 | pricing calculation service | 缺尺寸/费率返回 `storage_calc_status`，不抛 500 |
| 头程费用 | 版本化配置 + 单品毛重 | `12.00 CNY/kg`、gross weight kg | `first_leg_fee_cny` | 单品毛重 kg × rate；保留两位小数 | effective date | CNY/kg，Decimal | 规则版本生效时间 | pricing calculation service | 缺毛重返回 `missing_weight`；箱规/体积重需新版本 |
| 售价/毛利率/ROI/等级 | 成本输入 + WFS/头程/佣金/FX + 版本化规则 | target margins、commission、purchase-cost ROI、thresholds | price/breakdown/grade projection | 后端统一计算；rounding 默认 `none`；ROI=`gross_profit/purchase_cost_cny`；缺输入返回状态 | rule effective date | Decimal + currency；FX 来自 `usd_cny_rate` 配置 | 记录 input snapshot、rule IDs、calc version、calculated_at | pricing calculation service | commission 缺失按 0 并标记来源；除零和缺 FX 必须 fail safely |
| 产品管理 BFF | Product Core + confirmed identity + DWD/DWS + calculated projection | 受控字段 | API response | 后端 join/投影；不读 RAW、不实时调外部 API | 返回 UTC timestamp，前端按规则展示 | 金额用 decimal string + currency/breakdown | 返回 persisted freshness/stale flags | Product Management query service | 数据 scope、字段 permission、分页和映射粒度必须 fail closed |

## 7. 写入、优先级与发布边界

1. `products` 与 `product_platform_listings` 仍遵守现有 `NEW_SYSTEM_OWNED` 决策；外部同步不得静默覆盖其人工字段。
2. `dwd_lingxing_sku_*` 只保存可追溯的 Lingxing 来源值；内部运营标签不得写入 `dwd_lingxing_sku_global_tags`。
3. 已批准优先级为：人工 override > 新系统配置/内部产品资料 > Lingxing 同步来源事实 > 计算字段。各层分开保存，breakdown 标明实际来源。
4. 费用、售价、ROI 和等级输出必须记录输入 snapshot、规则 ID/version、公式 version、有效期、币种、舍入规则和计算时间。
5. L9/DWS/BFF 是可重建投影，不得接收外部或人工原始写入，也不得成为唯一权威来源。
6. 前端只展示后端结果与 breakdown，不计算 WFS 配送费、每日仓储费、建议售价、最低售价、清仓售价、ROI 或产品等级。

## 8. 风险检查清单

- [x] 所有字段组已拆分，未使用 `MIXED`。
- [x] 批准范围内不存在未解决的 `NEED_OWNER_DECISION`；负责人已给出 OD-01 至 OD-14 结论。
- [x] `batchGetProductInfo` 证据缺口已转化为实现停止条件：只允许默认关闭、保守配置和 mock 测试；真实执行另行批准。
- [x] 外部同步采用 RAW-first -> parser -> DWD/DWS；API route 不实时拉取外部平台。
- [x] SKU、MSKU、Lingxing ID、identity UUID 和 `product_id` 不互相猜测。
- [x] BFF `{sku_id}` 已批准为新系统内部 identity UUID；Product Core 只经 confirmed mapping 组合。
- [x] Lingxing 标签与内部运营标签分开。
- [x] manual/config/sync/calculated precedence 已批准，manual override 优先。
- [x] WFS 来源 URL、确认日期、storage 公式和版本化要求已批准；具体 fulfillment/storage rate 值只通过配置发布。
- [x] 头程计费重、佣金缺省行为、FX 配置来源、毛利率、ROI、等级阈值、舍入和历史重算策略已批准。
- [x] 金额禁止 float，必须配 `currency_code`；换汇必须记录 `fx_rate`、`fx_date`、`fx_source`。
- [x] RAW、payload、认证材料和第三方原始响应不得由产品管理 API 返回。
- [x] 日志不得记录真实 SKU、商品原始字段值、费用值、RAW payload 或认证材料。
- [x] 内部标签、配置、重算、导出和用户视图已获准进入 PRP，并受权限、审计、范围上限和安全返回约束。
- [x] 本次调查未连接数据库/服务器、未调用外部 API、未读取 `.env`、未修改业务代码。

## 9. 负责人决定结果

| ID | 已批准结论 | 实现/执行边界 |
|---|---|---|
| OD-01 | 允许实现 `batchGetProductInfo` outbound 代码、构造、响应、run/work-item、解析、入库、错误和测试 | default off、fail closed；本 PR 不真实执行 |
| OD-02 | 本实现 PR 禁止真实 `batchGetProductInfo` 与真实 Token | 合并 `main` 后由负责人另行授权生产同步 |
| OD-03 | 必须引用仓库可定位的官方证据；normalized/未验证索引只能标成未验证 | 不得猜测缺失参数；缺口触发停止条件 |
| OD-04 | 未确认的批量/限流/重试采用保守可配置上限 | 默认关闭；未经后续证据/授权不得放宽或执行 |
| OD-05 | WFS 来源为 `https://marketplace.walmart.com/walmart-fulfillment-services-pricing/`，负责人确认日期 2026-09-13 | 配置保存 `source_url/confirmed_at/version/is_active`；不调用 Walmart API |
| OD-06 | FX 使用价格规则配置 `usd_cny_rate`，不接实时 FX API | 不写固定值；缺失时 `pricing_calc_status=missing_fx_rate`；记录 actor/time 和 canonical FX metadata |
| OD-07 | `platform_commission_rate` 可配置；缺失按 0 | breakdown 必须标记 `commission_source=default_zero/configured` |
| OD-08 | ROI 默认分母为采购成本，`ROI=gross_profit/purchase_cost_cny` | `roi_base` 可按新规则版本切换 `purchase_cost/total_cost`；零/缺失分母安全失败 |
| OD-09 | 异常及 A/B/C 阈值按负责人给定规则 | 阈值前端可配置、版本化；返回 `productGrade/gradeReason` |
| OD-10 | 规则变化不自动全量重算历史 | 仅后续主动重算/同步更新 current；snapshot 不改；保留 rule version |
| OD-11 | BFF `{sku_id}` 是新系统内部 `identity_id` | 不用真实 SKU 字符串或 Lingxing SKU ID 作主路径；不猜 `product_id` |
| OD-12 | 优先级为 manual override > new-system config/internal > Lingxing sync > calculated | 各层分开保存；外部同步不得覆盖 Product Core 人工值 |
| OD-13 | 头程默认 `12.00 CNY/kg`，使用单品毛重 kg，两位小数 | 缺重量为 `missing_weight`；箱规/体积重另建规则版本 |
| OD-14 | export 第一版允许安全占位或异步设计，上限 5000 行 | 遵守 permission/scope/脱敏；完整文件生成可标记 Phase 2 |

## 10. 官方证据缺口与停止边界

仓库当前只提供 `batchGetProductInfo` 的 normalized 派生索引：

- `normalized/interfaces.csv` 引用了官方文档路径 `/docs/Product/batchGetProductInfo.md`；该原始页面文件未在当前仓库中定位到。
- `normalized/request_params.csv` 记录 `productIds`、`sku_identifiers`、`skus` 三选一且候选上限 100。
- `normalized/response_fields.csv` 记录候选 `code=0`、`data[]` 及详情字段。
- `api-verification-status.csv` 明确标记为“未验证”，账号权限、分页/批量、频控、字段范围和错误码仍未确认。

仍缺：可复核官方原始页面或批准的官方取证文档、认证/query-sign 适用规则、Content-Type、三选一组合的精确定义、请求/响应样例的脱敏契约、成功/错误码全集、批量/频控/重试规则。

这些缺口不再阻塞 default-off/mock-only 后端实现，但形成强制停止条件：实现只能引用现有证据、采用保守配置并保持专用 outbound 开关默认关闭；任何无法由证据确定的参数不得猜测。真实 Token、真实 provider transport、生产 run 或放宽批量/重试设置均须在合并后另获负责人授权。

WFS fulfillment 与每日仓储费的来源 URL 和人工确认日期已由负责人确定，但仓库尚未记录具体费率表、市场区间、旺季条件和 fulfillment 分段算法。实现可建设版本化配置、公式框架和缺失状态，不得从页面标题猜费率或自动抓取；只有受控录入并激活的规则版本可产生金额。

## 11. 最终建议

- 接口总体状态：`READY_FOR_PRP`。
- 当前是否 `READY_FOR_PRP`：是，仅限本文件和 Approved PRP 的实现范围。
- 推荐短期策略：实现 default-off/mock-only 详情同步路径、版本化规则、计算投影和受保护 API；不执行真实外部或生产操作。
- 推荐长期策略：ProductList identity -> governed `batchGetProductInfo` RAW/DWD sync -> confirmed identity mapping -> versioned configuration/calculation -> rebuildable projection -> Product Management BFF。
- 旧库退出条件：不适用；本方案不读取旧系统运行库。
- 迁移或同步边界：不迁移、不实时 route 拉取、不默认双写；真实同步必须单独授权。
- 主要风险：Lingxing 官方 contract 和 WFS 具体费率仍不完整；通过默认关闭、保守配置、缺失状态及生产执行二次授权控制。
- PRP 必须引用的结论：前端仅展示；外部数据 RAW-first；内部规则版本化；投影可重建；认证材料和 RAW 永不出现在业务 API/日志。

## 12. 负责人批准记录

```text
决定：批准进入 PRP
接口总体状态：READY_FOR_PRP
批准的数据集分类：第 5 节 A-L
批准的短期策略：default-off/mock-only 实现，不执行真实外部或生产操作
批准的长期策略：RAW-first 同步、版本化配置、可重建投影、受保护 BFF
OD-01 至 OD-14：已按第 9 节解决
batchGetProductInfo 官方证据：继续补充；缺失部分不得猜测并阻断真实执行
WFS 证据来源：https://marketplace.walmart.com/walmart-fulfillment-services-pricing/
WFS 人工确认日期：2026-09-13
身份 grain：新系统内部 identity_id；API alias 为 sku_id
字段优先级：manual override > new-system config/internal > Lingxing sync > calculated
生产真实同步：未授权；代码合并 main 后须单独批准
批准人：Project Owner
批准日期：2026-09-13
批准类型：Source Decision 与 PRP-entry approval
```

本决策允许 `PRPs/product-detail-sync-product-management-api-v1.md` 进入批准状态。工程师仍须等待负责人单独下发 implementation Prompt；该 Prompt 不得授权真实 Token、真实 Lingxing 调用、生产数据库/服务器访问、生产 migration、真实同步或部署。
