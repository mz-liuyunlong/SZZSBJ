# PMC 采购组（采购看板补差 + 自动补货采购计划草稿）数据源决策

- 调查日期：2026-11-02
- 调查人：PMC A 采购组代码 AI（只读：仓库代码 / 文档 / Mac 本地 8088 Demo 源码与已拉下的 daily 文件；未连数据库、未调外部接口）
- 目标 method/path：
  - A 采购看板（已上线接口改字段来源 / 增加筛选）：`GET /api/pmc/purchase/board`、`GET /api/pmc/purchase/plans/pending`
  - B 自动补货（新接口，一期只读）：`GET /api/pmc/replenishment/rounds`、`/drafts`、`/drafts/summary`、`/drafts/{draft_id}`、`/items/{item_id}`、`/check`、`/rules`、`/drafts/export`
- 业务用途：采购看板带出「采购计划草稿号」并可按草稿号 / 计划号搜；自动补货每期按 ItemID 计算补货量、发草稿号、出草稿列表与详情、写入核对（一期不写领星）
- 接口总体状态：A = `READY_FOR_PRP`；B = `BLOCKED_BY_OWNER_DECISION`
- 是否包含 NEED_OWNER_DECISION：是（只在 B）
- 负责人批准状态：待确认（mz-liuyunlong）
- 关联证据：`PRPs/pmc-purchase-board.md`、`docs/data-sources/decisions/pmc-purchase-board-decision.md`、#288（`origin/pmc/purchase-itemid-rule` 6fdba9b）、Mac `features/pmc-replenishment/`（8088 Demo：`drafts/build_from_daily.py`、`drafts/src/app.jsx`、`review_server/server.py`、`context/decisions.md`、`context/solution-v1-for-yunlong.md`）、Mac `features/pmc-purchase/drafts/`（8088 采购看板）
- 决策文件路径：`docs/data-sources/decisions/pmc-purchase-group-decision.md`
- 后续接口 PRP：`PRPs/pmc-purchase-group.md`

## 3.1 旧系统与来源调查

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 8088 Demo：`/purchase/`（采购看板）、`/replenishment/`（自动补货 · 采购计划草稿）。旧 MySQL 系统无对应页面。 |
| 旧 API | 8088 `review_server/server.py`：`GET /pmc-api/reviews?round=`、`POST /pmc-api/review`（审批事件只追加写 `data/events_<期>.jsonl`）。只服务 8088，不是正式数据源。 |
| 旧接口文件位置 | Mac `features/pmc-replenishment/review_server/server.py`；构建脚本 `drafts/build_from_daily.py`（离线计算，产物 `demo-data.json`）。 |
| 读取表 | 8088 不读数据库，读每周拉数文件 `features/pmc-wfs-shipment/data/daily/<日>/`（purchase/、domestic/、lingxing/、walmart/<store>/、zhongyi/、facts/）+ 新系统只读导出 `features/new-system-db/data/export_*`（`mart_daily_sales_item_day`、退款明细、`listing_archive_states`）+ 旧系统归档探测文件。 |
| 表写入方 | 每周拉数由部署 AI 按票据执行（领星 / Walmart 一店一服务器 / 众壹，只读）；`draft_registry.csv` / `draft_ledger.json` / `rounds_approved.json` 由构建脚本与 Rocky 批准写入；审批事件由 server.py 追加。 |
| cron / 脚本 / 外部 API | 无定时（Rocky 手动拉数，decisions 第 64、86 条）；脚本 `refresh_demo.py`、`build_from_daily.py`、`import_review.py`、`notify_feishu.py`（默认 dry-run）。外部写只发生在部署 AI 执行的写入票据（W1b ~ W5，`createPurchasePlan`）。 |
| 人工写库入口 | 人工对照表 `data/manual_item_map/manual_item_map.csv`（Rocky 2026-09-29 填，124 个 ItemID）；期次批准 `rounds_approved.json`；server.py `--amend` / `--reopen`（管理员改量 / 退回重审）。 |
| 外部平台重新获取可能性 | 领星、Walmart 数据都可重新拉取；草稿号、审批记录、写入回执只存在于 8088 文件，无法从外部重新获取（领星计划备注里只有 `ITEMID | 草稿号` 两段）。 |
| 少量配置数据可行性 | 规则参数 12 个、特殊 ItemID 补货周期覆盖、期次批准名单，都可作为新系统配置 / manual 表维护。 |
| 短期策略 | 8088 继续跑（Rocky：DEMO 至少再维护 2 周）；正式系统一期只读计算与展示，同一数据日与 8088 对数。 |
| 长期策略 | 正式系统接管计算、发号、审批（二期 2a）、写领星（二期 2b）；8088 补货页退役。 |

## 7. 数据集分类表

### A 采购看板补差

| 数据集或字段组 | 业务用途 | 当前权威来源 | 分类 | 短期策略 | 长期策略 | 退出条件或切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|
| A1 草稿号 `draft_no`（新增来源：采购计划备注） | 采购单行带出系统草稿号 | 领星采购计划 `remark` / `plan_remark` 中 `草稿:CGyymmdd-nnn`（经 `relation_purchase_plan` / `plan_sn` 关联到采购单行） | `REBUILD_SYNC`（复用已同步 `ods_lingxing_purchase_plan`，不新增同步） | 计划备注优先，采购单行备注（现有 `parse_draft_remark`）兜底 | 同短期 | — | 否（8088 已定，PRP 写明顺序） |
| A2 搜索类型「草稿号 / 计划号」 | 按 CG… / PP… 查采购单 | 同 A1 + `plan_sn` | `REBUILD_SYNC`（同上） | DWS 增加可检索列 | 同短期 | — | 否 |
| A3 ItemID 归属 | 采购行 ItemID / 店铺 | #288 共享规则 `item_id_resolution.py`（`purchase.remark.store.v2`）+ R-9 / R-9a（`store_from_remark` / `remark_store_conflict`） | `REBUILD_SYNC`（不变） | 维持 #288，不回退到 8088 写法 | 同短期 | — | 否（Rocky R-4 / R-9 / R-10 已定） |
| A4 隐藏姓名名单（默认「小罗」） | 负责人 / 采购员 / 供应商不显示该名字 | Rocky 2026-11-02 决定（照 8088） | `NEW_SYSTEM_OWNED` | 配置 `pmc_purchase_hidden_names`，展示层过滤，不改 ODS | 同短期 | — | 否 |

### B 自动补货（采购计划草稿）

| 数据集或字段组 | 业务用途 | 当前权威来源 | 分类 | 短期策略 | 长期策略 | 退出条件或切换点 | 需负责人确认 |
|---|---|---|---|---|---|---|---|
| B1 在售 WFS ItemID / 店铺 / SKU / GTIN / MSKU | 计算范围、写入店铺候选 | 领星 Walmart 在线商品 → `dim_walmart_listings`（含 `fulfillment_type`，PMC-PURCHASE-1 已加） | `REBUILD_SYNC`（已在库） | 复用 | 同 | — | 否 |
| B2 WFS 可售 / 每日期初可售 / 每日销量（90 天） | 日销、有货日、断货线 | Walmart `/v3/wfs/inventory` + `/v3/fulfillment/inventory-log`；新系统已有 `fact_walmart_listing_inventory_daily`、`fact_walmart_sales_item_daily`（data_pages） | `NEED_OWNER_DECISION` | 8088 两种来源都支持（facts 优先，否则 inventory-log 倒推）；正式系统建议读两张 fact | 读 fact；覆盖与新鲜度不足时补 Walmart 只读同步 | fact 覆盖 8 店 × 90 天且与 8088 同日对数一致 | 是（两张 fact 是否覆盖 90 天 / 8 店、是否按「期初 ≥ 5」可用，需只读核实） |
| B3 Walmart「入库中」inboundUnits 与货件明细（items / receipt 过账件数） | 入库中差额（①b） | Walmart `/v3/wfs/inventory`、inbound-shipments items、inventory-log Receipt | `NEED_OWNER_DECISION` | 正式库目前无表（采集器只落文件）；一期可暂缺并在页面标「未接入」，但会与 8088 不一致 | 随 Walmart 只读同步 / WFS 板块接入 | 表上线 | 是 |
| B4 WFS 货件 / SP 发货单（已发货未上架、收货中、默认箱规 spec_pack_list） | 有效供应、到仓日、箱规 | 领星 WFS 货件、平台仓发货单 → `ods_lingxing_wfs_cargos` / `_cargo_goods` / `_shipping_lists`（**#282 分支，未合 main**） | `NEED_OWNER_DECISION` | 等 #282 合并后复用，不在补货模块另建同步 | 同 | #282 合入 main | 是（接入顺序 Y3） |
| B5 众壹轨迹（实际签收、查验、轨迹） | 到仓日、被查验 / 无轨迹提醒 | 众壹物流外部接口 | `NEED_OWNER_DECISION` | 正式库无；属物流板块（PMC-02）。一期缺失时到仓日按 SP 预计 / Walmart 签收，提醒项标「未接入」 | 物流板块接入后复用 | 物流 PRP | 是 |
| B6 国内仓库存（惠州 wid 16168 可用 + 锁定；海外仓只提示） | 有效供应「国内仓」 | 领星库存明细 → `ods_lingxing_domestic_inventory`（main） | `REBUILD_SYNC`（已在库） | 复用 | 同 | — | 否 |
| B7 采购单 / 明细 / 收货单 / 采购计划 | 采购单待到货 / 待下单、计划待采购、14 天拦截、采购交期样本、写入核对 | 领星三单 → `ods_lingxing_purchase_*`（PMC-PURCHASE-1 Gate 2） | `REBUILD_SYNC`（已在库） | 复用；注意 getPurchasePlans 按 update_time 拉、当天改动的计划要次日才进（8088 2026-10-14 教训） | 同 | — | 否 |
| B8 采购交期（每 SKU 近 5 单有效样本） | 提前期 | 8088：首次收货日 − 下单日；`dws_purchase_sku_cycle`：累计 ≥ 50% 收货日 − 下单日 + 人工基准 | `NEED_OWNER_DECISION` | 推荐一期按 8088 口径在补货模块内算（保证对数 0 差），同时并列展示 `dws_purchase_sku_cycle` 值 | 统一到一个口径 | 负责人选定口径 | 是 |
| B9 产品资料（负责人、采购交期 cg_delivery、默认箱规、产品标签 global_tags、采购员） | 负责人筛选、兜底交期、箱规取整、标签剔除 | 领星 batchGetProductInfo → `ods_lingxing_product_info_batch_items`（main） | `REBUILD_SYNC`（已在库） | 复用；四个字段是否已标准化抽列需实现前核实，不足则在 ODS→DWD 增列（不改 RAW） | 同 | — | 否（字段核实属实现前置检查） |
| B10 订单利润 / ROI / 广告占比 / 退货率 / 每日数据 60 天 | 只提示不改量 | 新系统 `mart_daily_sales_item_day`（+ 退款明细） | `NEW_SYSTEM_OWNED` | 直接读本库（8088 是导出文件再读） | 同 | — | 否（口径已由 Rocky 定：第 81、84、85 条及 10-10 22:28 修正） |
| B11 归档状态 | 归档不出草稿 | 新系统 `listing_archive_states`；8088 另有旧系统 `dim_product.archived` 兜底（本期命中 0） | `NEW_SYSTEM_OWNED` | 只读新系统；推荐取消旧系统兜底 | 同 | — | 是（取消旧系统兜底需确认，否则变成 `READ_LEGACY_TEMPORARILY`） |
| B12 人工对照表（SKU / 单号 → ItemID / 店铺） | 供应归属第一优先 | Mac `manual_item_map.csv`（Rocky 填） | `NEED_OWNER_DECISION` | 方案 a：`MIGRATE_ONCE` 到 `manual_pmc_item_map`；方案 b：不迁，按 R-10 让新草稿自带 ItemID，旧件不归属 | — | — | 是 |
| B13 规则参数（12 项）+ 特殊 ItemID 补货周期 | 计算 | 8088 `PARAMS_INIT` / `P_DEF`（页面内可临时改，不持久） | `NEW_SYSTEM_OWNED` | `pmc_replenishment_rule_versions`（版本 + 生效日）+ `manual_replenishment_item_params` | 同 | — | 否 |
| B14 期次批准（每期须 Rocky 单独批准才发号） | 发号闸门 | 8088 `rounds_approved.json` | `NEW_SYSTEM_OWNED` | `manual_replenishment_round_approvals`（一期由运维命令按票据写，不做页面按钮） | 二期加页面操作 + 权限 | — | 否 |
| B15 草稿号登记 + 台账快照 | 发号、冻结快照、补货历史 | 8088 `draft_registry.csv`、`draft_ledger.json`（CG260929 ~ CG261102-087） | `NEED_OWNER_DECISION` | 推荐 `MIGRATE_ONCE`（切换日一次性导入，按草稿号数量核对），切换前正式系统只「影子计算」不发号 | 正式系统为唯一发号方 | 切换日由 Rocky / 刘云龙定 | 是 |
| B16 审批事件（产品负责人 / 运营 / admin 改量 / 退回重审） | 草稿状态 | 8088 `events_<期>.jsonl` | `NEED_OWNER_DECISION` | 一期只读：不迁、不展示审批（或随 B15 一起 `MIGRATE_ONCE` 只读展示历史） | 二期 2a 由 `manual_replenishment_reviews` 接管 | 二期上线 | 是 |
| B17 写入回执（草稿号 → plan_sn、读回、作废） | 双向核对 | 8088 `written_*.json`（W2 ~ W5） | `NEED_OWNER_DECISION` | 随 B15 `MIGRATE_ONCE`；一期核对只读领星计划 + 迁入回执 | 二期 2b `evt_replenishment_plan_writes` | 二期上线 | 是 |

## 8. 数据血缘表（核心字段）

| 接口字段 | 数据集 | 源系统/表/接口 | 原始字段 | 标准字段 | 转换或公式 | 时区 | 币种 | 更新频率/新鲜度 | 写入方 | 风险与证据 |
|---|---|---|---|---|---|---|---|---|---|---|
| `draft_no`（采购看板） | A1 | ods_lingxing_purchase_plan | remark / plan_remark | draft_no | 正则 `草稿[:：]\s*(CG\d{6}-\d{3})`；计划优先，采购单行备注兜底 | — | — | 随采购同步 | 同步任务 | 8088 `pmc-purchase/drafts/build_from_daily.py` plan_draft |
| `daily_sales` | B2 | fact_walmart_sales_item_daily / inventory-log Ship | sales_qty | daily_sales | 最近 30 个有货日销量 ÷ 有货日数，回看 90 天（不含数据日当天）；有货日 = 当天期初 WFS 可售 ≥ instockMin(5)，期初 = 前一天日终；多店铺同 ItemID 合并 | 店铺日（Walmart 北美日） | — | 每期 | 计算任务 | app.jsx calc()、decisions 71、75 |
| `lead_days` | B8 | ods 采购单 / 收货单；ods 产品 | order_time、receive_time、cg_delivery | lead_days | 近 5 单有效样本（≥2 天）平均且样本 ≥2；否则领星 cg_delivery>0；否则 15 | 北京日 | — | 每期 | 计算任务 | build_from_daily.py「采购交期」段 |
| `L`（提前期） | B13 | 规则 | — | lead_total | approve 5 + lead_days + pack 7 + transport 30 + shelf 10 | — | — | — | — | decisions 21、29、33；transport 38→30（第 78 条） |
| `supply` | B4/B6/B7/B3 | 见各数据集 | — | supply_by_kind | WFS 可售 + 收货中余量 + 已发货未上架 + 国内仓(可用+锁定) + 采购单待到货 + 采购单待下单 + 计划待采购(status 2)；每件只属一个状态，按 ItemID 合并 | — | — | 每期 | 计算任务 | build ①~⑤、①b |
| `suggest` | — | 计算 | — | suggest_qty | ceil(daily × (L + R + safety) − supply)，≤0 记 0；有货日 < capDays(30) 时封顶 capQty(300) | — | — | 每期 | 计算任务 | app.jsx |
| `boxed` | B9/B4 | 箱规 | box_default_pcs / spec_pack_list / cg_box_pcs | box_qty | 不足半箱舍、≥半箱进、至少 1 箱；封顶时不超过封顶量 | — | — | — | — | app.jsx |
| `pm_margin / roi / ad_ratio / return_rate` | B10 | mart_daily_sales_item_day | 订单利润、销售额、广告 + SEM、采购 + 头程成本、退款数量 | — | 30 / 15 / 7 天窗口截止数据日 − 2 天；利润率 = 利润合计 ÷ 销售额合计；ROI = 利润 ÷ (采购成本 + 头程)；退货率 = 退款数量合计 ÷ 销量合计 | 北美业务日 | USD | 每期 | 计算任务 | decisions 81、84、85、10-10 22:28 |

## 9. 风险检查清单

- [x] 每个数据集或字段组已有且仅有一种分类。
- [ ] 不存在未解决的 `NEED_OWNER_DECISION`。（B2 / B3 / B4 / B5 / B8 / B11 / B12 / B15 / B16 / B17 待定）
- [x] 权威来源、写入方、字段定义、公式、时区、币种和新鲜度均有证据（以 8088 代码为证；B2、B9 字段覆盖待实现前只读核实）。
- [x] 不使用 `READ_LEGACY_TEMPORARILY`（推荐取消 B11 旧系统兜底）。
- [x] `REBUILD_SYNC` 全部复用已有同步，不在 API route 实时拉外部平台。
- [ ] `MIGRATE_ONCE`（B12 / B15 / B16 / B17）的数量核对、映射、切换点、回滚待负责人定方案后补。
- [x] 不读取 `ARCHIVE_ONLY` 数据。
- [x] 不双写：切换前正式系统只影子计算、不发号；切换后 8088 停止发号。
- [x] 敏感字段：负责人姓名、审批人姓名；无客户个人信息（退货原因不带买家备注）。
- [x] 调查未连接真实数据库、未调用真实外部 API、未修改任何数据。

## 最终建议

- 接口总体状态：A `READY_FOR_PRP`；B `BLOCKED_BY_OWNER_DECISION`
- 推荐短期策略：A 直接做；B 先做「计算引擎 + 只读页」并用已拉下的 daily 文件灌本地库对数，缺的数据集在页面标「未接入」，不在补货模块里另建同步
- 推荐长期策略：B 的供应数据随 WFS（#282）、物流、Walmart 只读同步接入后复用；正式系统成为唯一发号与审批方
- 旧库退出条件：不适用（不读旧库）
- 迁移或同步边界：只迁 8088 的发号 / 台账 / 审批 / 回执（一次性、只追加）；不迁每周拉数原始文件
- 主要风险：同号双发；供应口径缺项导致建议量偏大；交期口径不一致
- 待负责人决定：见 PRP §0（D1 ~ D9）
- PRP 必须引用的结论：A1 计划备注优先；A3 维持 #288；B 一期只读、不写领星

## 负责人决定

- 决定：
- 批准的数据集分类：
- 批准的短期策略：
- 批准的长期策略：
- 约束与退出条件：
- 批准人：
- 批准日期：
- 备注：
