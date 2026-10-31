# Listing 生命周期与评级证据清单（PR #277）

状态：**DRAFT / READ_ONLY_EVIDENCE_AUDIT**。2026-10-31 核对当前分支的源码、模型及现有数据源决策，并对生产数据库执行了限时、只读、只返回聚合的复核；未调用旧系统或外部 API。生产业务日期、数量和金额不写入公开仓库，现场聚合结果另行向负责人报告。表存在、字段存在、代码能够查询，均不等于历史数据覆盖完整或业务权威已批准。本清单不批准正式评级、生命周期写回、任务启用或迁移。

## 1. 核对范围与共同口径

- Listing 当前身份：`source_account_ref + store_id + item_id`，来源 `mart_listing_management_current`；日销售 MART 与库存 FACT 还使用可空 `msku` 做精确匹配。不能以 SKU、MSKU 或 Item ID 单独推断归属。
- 时间：评级代码按 LA 业务日的执行日减两天确定截止日；需要逐业务日证明覆盖，不用最新一条快照代替历史。
- `null`、缺行、同步失败、已确认的零，是四种不同状态。没有独立完整性证明时，一律不把缺行补为零。
- 状态列：`源码可读`只说明字段/查询已存在；`证明缺失`说明尚不能正式发布；`待负责人决定`说明权威来源或业务含义未批准。此处没有一项标为“生产数据已认证”。

## 2. 逐项证据

| ID / 关联 LM | 要证明什么、最小粒度 | 当前源码与字段 | 当前证据状态 | 缺证据时安全结果 |
|---|---|---|---|---|
| E01 / 001,003,010,023 | Listing 身份、账号范围、当前阶段及等级；账号＋店铺＋Item ID | `data_pages/models.py::ListingManagementCurrentMart` 的 `source_account_ref/store_id/item_id/lifecycle_status/product_grade`；`listing_rule_config/preview.py` 按授权账号读取 | 源码可读；当前字段不是首次阶段的来源证明 | 阶段待确认；不因空阶段推断正式等级 |
| E02 / 004,005,009,010,018 | 首次上架、测品、经营、清货及人工审批顺序；Listing＋事件时间 | 当前 MART 只保留 `lifecycle_status`；`evaluation.py::lifecycle_listing` 对流程阶段优先，但无完整事件流 | 历史事件来源待负责人决定 | 仅输出诊断候选及缺失原因；不写正式阶段 |
| E03 / 013,014,020,025 | 每个 LA 业务日的销售量与金额，以及该日是否已完成采集；账号＋店铺＋Item ID＋可空 MSKU＋日期 | `DailySalesItemDayMart.business_date_la/sales_qty/sales_amount/sales_currency_code`；`preview.py::basic_financial_candidate` | 已有日 MART；逐日采集完成证明未核实 | 缺行与真实零销量分开；该日不计为有效财务日 |
| E04 / 006,020,021,025 | 广告费用覆盖、归因、币种和明确无广告的证明；同一身份＋日期 | `WalmartAdItemSpDailyFact`、`DailySalesItemDayMart.ad_spend_amount/sem_ad_spend_amount/ad_spend_currency_code/source_lineage_json` | 字段存在；独立发布或对账证明缺失 | `ADS_COST_PUBLICATION_PROOF_MISSING`；不发布正式 A/B/C/D |
| E05 / 006,020,025 | 采购、头程、仓储、佣金、WFS 费、汇率在业务日完整且口径一致 | Daily MART 的各费用金额、`cost_status/missing_cost_codes_json/calculation_warnings_json/fx_date/fx_source` | 计算字段存在；`cost_status=complete` 不能单独证明全部上游费用最终收齐 | 标记费用证据不足；不将 `null` 当零费用 |
| E06 / 006,020,025 | 退款及退货影响已覆盖到正确购买日，金额和币种可信 | `fact_walmart_refund_items`、`after_sales_refund_items`，Daily MART 的 `refund_amount/refund_currency_code` | 来源与计算路径存在；逐日完整性与结算水位未核实 | 退款证据不足，不发布正式利润评级 |
| E07 / 011,015,016 | WFS 每日零库存、有库存及缺快照可区分；账号＋店铺＋Item ID＋日期 | `WalmartListingInventoryDailyFact.snapshot_date_la/wfs_available_quantity/captured_at`；`preview.py::stockout_candidate` 要求连续观察到零 | 结构与诊断规则存在；历史覆盖率和采集成功水位未核实 | 缺快照不判为零库存，也不判连续断货 |
| E08 / 005,009,011,012 | FBM 等非 WFS 的可售量及断货依据 | 库存 FACT 有 `available_quantity`，`evaluation.py` 可处理 FBM 候选 | `available_quantity` 的 FBM 权威来源与历史覆盖待负责人决定 | 不用 WFS 零库存判 FBM 断货；阶段待确认 |
| E09 / 015,016,017,018 | 断货前阶段、恢复过程、清货和归档在指定截止日的历史状态 | `ListingArchiveState` 只有当前归档状态及最近归档／恢复时间；`preview.py::archive_has_post_cutoff_event` 只做保守阻断 | 不可变事件序列未找到，历史 as-of 无法完整回放 | 后续事件发生过的历史日不反推当前状态；保留 `ARCHIVE_STATE_AS_OF_CUTOFF_UNVERIFIED` |
| E10 / 014,080 | 划线价和购物车异常的具体成功观察及采集时间 | `StandardizedWalmartMonitorListingObservation` 的成功结果和 `captured_at`；`preview.py` 按 LA 日期读取 | 已批准作诊断观察；生产 RAW 投递覆盖和字段质量未核实 | 没观察就未知；不推断连续异常或正式阶段 |
| E11 / 007,020,024 | 每次计算使用的规则版本、截止日与结果快照 | `ListingGradeRuleVersion`、`ListingEvaluationRun/Snapshot`、诊断输出中的 `rule_version/cutoff_la/published` | 诊断快照存在；正式发布及回滚链路未获批准 | `published=false`；保留候选，不覆盖 MART 正式字段 |
| E12 / 059,060,065,067,068 | 批次逐 Listing 错误、正式发布后跟进和提醒的权限与运行证据 | `listing_rule_config/batch.py/tasks.py`、`ListingEvaluationRun/Snapshot` | 诊断任务部分存在；正式发布与运营动作依赖 E01–E11 | 只显示诊断状态和可见错误；不启用正式调度或自动 C/D 跟进 |

## 3. 需要用真实数据补的核验（只读，需单独授权）

| 核验 | 只输出的安全聚合 | 合格条件 / 失败处理 |
|---|---|---|
| Listing 身份与账号隔离 | 当前行数、稳定键重复数、空键数、可见账号数量 | 重复或空键先修身份；不输出账号或商品明细 |
| 销售日覆盖与零销量 | 截止日前 14/30 日按日期的预期对象数、已收到数、明确零数、缺失数、失败数 | 缺失与明确零必须分开；未有采集完成水位则不得认证零日 |
| 广告及费用 | 按 LA 日的来源批次数、成功/失败、金额非空、币种缺失、未归因、对账差异数 | 证明所有相关来源已经完成且币种/归因一致；单纯 `cost_status=complete` 不够 |
| 退款 | 按 LA 日的同步完成、未匹配、缺币种与迟到变更数 | 证明购买日归属及结算水位；迟到数据需使旧认证失效 |
| WFS/FBM 库存 | 每日应有快照数、实际成功数、真零数、缺快照数、FBM 来源覆盖数 | FBM 来源未获证实前单独保持未知；缺快照不补零 |
| 历史流程 | 有时间戳的初始化、审批、断货、恢复、归档／恢复事件覆盖数及冲突数 | 不可从当前状态合成历史事件；无法回放则历史结果保持诊断 |
| 版本与权限 | 生效规则版本数、无版本计算数、未发布快照数、跨账号拒绝测试结果 | 未发布快照不得被前端解释为正式评级；权限从后端校验 |

以上是验收**方法**。本轮已按只读事务、查询时长限制和聚合输出约束执行其中一部分；它们不是已经通过的完整性认证。后续复核仍需按账号权限执行，只返回聚合；不输出账号标识、商品标识、标题、URL、payload 或密钥。

### 本轮现场证据结论（公开版）

- 当前 Listing 稳定业务键无重复或空值；正式生命周期和等级字段仍未填充。身份质量通过不代表阶段、等级来源已获批准。
- 最近业务日的销售、广告和库存数据存在，但库存日覆盖有缺口；销售日出现不完整信号，缺少足以认证真实零销量的采集水位。
- 广告事实存在未归属店铺的记录；相关同步任务有失败记录。费用字段或计算状态不能代替完整性和归因证明。
- 退款数据分布在不同来源表；退款同步的近期成功水位不足，不能据单个来源表判断退款已经完整结算。
- 归档表主要反映当前状态，缺少可完整回放的历史事件；规则版本虽存在，正式计算运行和结果快照仍为空，不能证明发布链路已经闭环。
- 因此 E02–E09、E11–E12 仍未达到正式评级、历史生命周期写回或生产调度启用门槛；继续保持诊断和未发布状态。具体聚合数字仅在本次私有会话中提供，不进入 Git 文档或 PR 正文。

## 4. 待负责人一次确认的决定

1. **财务完整性**：哪个上游运行／对账记录证明广告、费用及退款在某 LA 业务日最终完整？迟到数据怎样撤销既有证明？建议没有独立证明时仅显示“待评级”。
2. **库存与零销售**：FBM 的权威可售库存来源是什么？哪个采集水位证明某日确实零销售？建议缺来源或缺水位时显示“待确认”，不把缺失当零。
3. **历史阶段**：首次上架、测品、清货、断货恢复、归档／恢复的权威事件在哪里？人工审批与自动规则谁优先？建议无历史事件时不正式回填历史阶段。
4. **发布边界**：在 E01–E11 全部达到可复核状态后，另行批准正式发布的权限、审计、冻结规则版本和回滚 PRP；生产调度仍需单独授权。

依据：`docs/data-sources/decisions/listing-evaluation-preview-decision.md` 当前是 `BLOCKED_BY_OWNER_DECISION`；项目数据分层及字段标准化规则要求源头、粒度、时间、币种和血缘可追溯。本清单不更改该决定状态。

## 5. 同批问题的其他证据边界

| 关联 LM | 已核对的结构或现状 | 仍缺的决定／证明 | 当前安全做法 |
|---|---|---|---|
| 048 | 标签关联当前以账号和 Item ID 为粒度；同账号跨店铺同 Item ID 可共享标签 | 标签到底属于商品还是单店铺 Listing，以及旧关联如何无损拆分 | 保持现有粒度，不自动迁移或改写旧标签 |
| 058 | 当前 GPT 入口保存关键词／广告分析链接 | 链接管理是否继续作为产品功能，或另行接入 AI 中心结果 | 页面只称链接，不称已完成 AI 分析 |
| 076–079 | `dim_walmart_listings.listing_start_source_raw` 保存原始文本；Listing MART 的 `listing_start_at_utc` 对新记录可为空；另有首次 WFS 有货相关字段 | 平台上架日、首次可售日和首次 WFS 有货日的权威含义与证据；标准时间是否存在明确时区来源 | 继续原样展示来源日期；不猜时区、不解析 raw 伪造 UTC、不回填标准字段 |
| 080 | 监控标准化观察有采集时间，独立 RAW 键清单见 `docs/data-sources/listing-monitor-raw-key-inventory.md` | 生产接收覆盖、历史投递对账、字段质量和受限审计引用 | 页面只展示已经审核的摘要；原始 payload 不进入普通业务 API |
