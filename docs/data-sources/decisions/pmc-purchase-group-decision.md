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
- 关联证据：`PRPs/pmc-purchase-board.md`、`docs/data-sources/decisions/pmc-purchase-board-decision.md`、#288（`origin/pmc/purchase-itemid-rule` ba15384）、Mac `features/pmc-replenishment/`（8088 Demo：`drafts/build_from_daily.py`、`drafts/src/app.jsx`、`review_server/server.py`、`context/decisions.md`、`context/solution-v1-for-yunlong.md`）、Mac `features/pmc-purchase/drafts/`（8088 采购看板）
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
| A4 隐藏姓名名单（默认「小罗」） | 负责人 / 采购员 / 供应商不显示该名字 | Rocky 2026-11-02 决定（照 8088） | `NEW_SYSTEM_OWNED` | 环境变量 `PMC_PURCHASE_HIDDEN_OWNER_NAMES`（默认「小罗」），接口 `meta.hidden_owner_names` 下发，展示层过滤，不改 ODS | 同短期 | — | 否 |

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
- 主要风险：两套 ItemID 归属规则并存（采购看板 #288 v2，补货 8088；方案 a / b / c 见 PRP §0 D5，待刘云龙选定，页面须标注各自规则）；同号双发；供应口径缺项导致建议量偏大；交期口径不一致
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

## 附录 A：所依据的 8088 规则与公式

8088 Demo 源码不在本仓库（在 Rocky Mac 本地 DEMO 工作区的 `features/` 目录）。下表记录 2026-11-02 取摘录时的文件快照 sha256，可按 `shasum -a 256 <路径>` 对照；路径相对本地 DEMO 工作区 `features/`。摘录与快照不符时以快照为准重新核对。

| 文件 | sha256 | 用途 |
|---|---|---|
| `pmc-replenishment/drafts/build_from_daily.py` | `e9906a75ba8414e98419a6163f4f3f232679763f64aad7484486a195392c628b` | 交期、日销、供应、出草稿条件 |
| `pmc-replenishment/drafts/src/app.jsx` | `cd448ed3f6e02960ca65637ace3ef44a13171c57e12b4ac531ee5b94547f6d15` | 页面 calc() 建议量公式 |
| `pmc-replenishment/context/decisions.md` | `eb42ab2f38ad2ebfe1b3ae09a5e5dbe63cc1ef359d981ca51efef691c6db53b4` | 补货业务决策 |
| `pmc-replenishment/review_server/server.py` | `df25d244efa57f2775d2eb1238637acaf013532c7e69661e43f4a63dbd5535d3` | 审批 / 发号接口 |
| `pmc-replenishment/data/rounds_approved.json` | `b3954eeb1148f65371a4e4f4dab636a9dcbcaad69798072dc8e402c6696ff601` | 期次批准 |
| `pmc-purchase/drafts/build_from_daily.py` | `0d50ec39323d044c58dcadf05b8ac1bd8aec4819c8f9020f6f0a75c51fe259af` | 8088 采购看板数据 |
| `pmc-purchase/drafts/demo-v2.html` | `0057dfcc2e87f7130b7c16aa852550acfde261d3ebf70b26115ff1ee39a15316` | 8088 采购看板页面 |
| `tools/ops_report/arrival_rules.py` | `b076eda9969aa8aa89da824d5980c6131913ffa967ba33874828fd705893bc55` | 到仓 / 可售日口径 |
| `pmc-overview/context/decisions.md` | `57dcb15101c93d2d345e4f0793a0f52a8308eab493cbc3e88b3b06dfddc6211b` | R-4 ~ R-10（#288 规则 v2） |

### 附录 A-1 `pmc-replenishment/drafts/build_from_daily.py` 第 219–246 行（采购交期）

```python
# ---------- 采购交期（采购看板规则：到仓日期 − 下单日期；<2 天剔除；近 5 单有效样本平均，≥2 样本才用）----------
orders = {r['order_sn']: r for r in load('purchase/purchase_orders.csv')}
recv_orders = {r['order_sn']: r for r in load('purchase/receipt_orders.csv')}
first_recv = {}
for it in load('purchase/receipt_order_items.csv'):
    ro = recv_orders.get(it['receipt_order_sn'])
    if not ro:
        continue
    po, t = ro['business_order_sn'], dd(it['receive_time'] or ro['receive_time'])
    if po and t:
        k = (po, it['sku'])
        if k not in first_recv or t < first_recv[k]:
            first_recv[k] = t
po_items = load('purchase/purchase_order_items.csv')
lead_samples = collections.defaultdict(dict)
for it in po_items:
    o = orders.get(it['order_sn'])
    if not o or o['status'] == '-1' or it['sid'] in ('0', '') or it['is_delete'] not in ('0', ''):
        continue
    od, rv = dd(o['order_time']) or dd(o['create_time']), first_recv.get((it['order_sn'], it['sku']))
    if od and rv:
        lead_samples[it['sku']][it['order_sn']] = {'po': it['order_sn'], 'order': iso(od), 'recv': iso(rv), 'days': (rv - od).days}
lead = {}
for sku, m in lead_samples.items():
    lst = sorted(m.values(), key=lambda x: x['order'], reverse=True)
    valid = [x for x in lst if x['days'] >= 2][:5]
    lead[sku] = {'avg': round(sum(x['days'] for x in valid) / len(valid), 1) if len(valid) >= 2 else None, 'n': len(valid),
                 'samples': [dict(x, excluded=x['days'] < 2) for x in lst[:5]]}
```

### 附录 A-2 `pmc-replenishment/drafts/src/app.jsx` 第 125–188 行（`calc()`）

```javascript
function calc(it,P,ov){
  // 日销 = 最近 30 个有货日的销量 ÷ 有货日天数，最长回看 90 天（Rocky 2026-09-27，取代 20 / 10 / 5 天窗口）
  const s=it.sales, LB=s.daily.length; let inN=0,salesN=0,lastIn=-1,firstIdx=LB;
  // 有货日 = 当天期初 WFS 可售 ≥ instockMin（默认 5；Rocky 2026-09-30：库存 1–4 件的日子销量被库存卡住，不算有货日）；没有 start 字段的旧数据退回原口径
  const instock=s.start?s.start.map(v=>v>=P.instockMin?1:0):s.instock;
  for(let i=LB-1;i>=0&&inN<30;i--){ if(instock[i]){ if(lastIn<0) lastIn=i; inN++; salesN+=s.daily[i]; firstIdx=i; } }
  const maxStart=s.start?Math.max(0,...s.start):0;
  const tailStock=lastIn<0&&maxStart>0&&maxStart<P.instockMin;        // 尾货：90 天里最多只有 1–4 件，从没到过阈值
  const n30=inN, N=lastIn>=0?LB-firstIdx:0;            // n30 = 用到的有货日数；N = 回看跨度（天）
  const daily=inN>0?salesN/inN:0;
  const oosDays=lastIn>=0?LB-1-lastIn:null;             // 距最后一个有货日的天数（null = 近 90 天无库存）
  const noStock90=lastIn<0;
  const leadP=it.lead.avg!=null?it.lead.avg:(it.cg_delivery>0?it.cg_delivery:P.leadFallback);
  const L=P.approve+leadP+P.pack+P.transport+P.shelf;
  const R=ov[it.key]??P.cycle;
  const tail=P.pack+P.transport+P.shelf;
  const r0stores=it.stores.length;
  const bs=[{kind:"wfs",qty:it.wm.available,date:TODAY,src:`Walmart wfs/inventory availableUnits${r0stores>1?"（"+it.stores.map(x=>x.name.split("-")[0]+" "+x.available).join(" + ")+"）":""}`}];
  it.batches.forEach(b=>{ let date="",note="",overdue=false;
    if(b.kind==="receiving"){ date=TODAY; note=b.cargo_status==="INBOUND_GAP"?`Walmart 入库中差额（已收货待上架 / 货件已关闭库存未转可售）：${b.how}`:`货件 ${b.cargo} 发货 ${b.shipped} / 已上架 ${b.putaway}，首批上架 ${b.first}`; }
    else if(b.kind==="shipped"){ const sell=b.arrival?addDays(b.arrival,P.shelf):""; overdue=!!sell&&sell<TODAY; date=sell?maxD(sell,TODAY):""; note=`货件 ${b.cargo} · ${b.sp||"无 SP"} · 到仓 ${b.arrival||"—"}（${b.arrival_src}）${overdue?` · 已过可售日 ${sell}`:""}`; }
    else if(b.kind==="domestic"){ date=addDays(TODAY,tail); note=`惠州 可用 ${b.valid} + 锁定 ${b.lock} · ${b.how}`; }
    else if(b.kind==="po"){ date=addDays(maxD(addDays(b.order,leadP),TODAY),tail); note=`${b.po} 下单 ${b.order} · ${b.how}`; }
    else if(b.kind==="po_pending"){ date=addDays(TODAY,leadP+tail); note=`${b.po} 待下单 · ${b.how}`; }
    else if(b.kind==="plan"){ date=addDays(maxD(addDays(b.created,P.approve),TODAY),leadP+tail); note=`${b.plan} ${b.status} · 创建 ${b.created} · ${b.how}`; }
    bs.push({...b,date,note:(b.store&&r0stores>1?`【${b.store}】`:"")+note,overdue}); });
  const supply=sum(bs,b=>b.qty);
  const target=daily*(L+R+P.safety);
  const gap=target-supply; const suggestRaw=gap>0?Math.ceil(gap):0;
  // 单次封顶（Rocky 2026-09-28）：有货日不足 capDays 天的，建议量最多 capQty 件，不允许单次超出
  const capOn=inN<P.capDays, capped=capOn&&suggestRaw>P.capQty; const suggest=capped?P.capQty:suggestRaw;
  let boxed=null; if(it.box>0&&suggest>0){ const n=Math.floor(suggest/it.box), rem=suggest-n*it.box; boxed=Math.max(1,(rem>=it.box/2?n+1:n))*it.box; if(capOn&&boxed>P.capQty) boxed=n>0?n*it.box:null; }   // 封顶时取整不得超过封顶量（向下取整箱；一箱都超则不取整）   // 不足半箱向下、满半箱向上；向下到 0 箱则至少 1 箱（向下会断货则向上）
  // 断货时间线：现有可售（WFS 可售 + 收货中余量）按日销往后推，各批次按预计可售日加入
  let sellout=null,gapDays=0,resume=null;
  const future=bs.filter(b=>b.date&&b.date>TODAY&&b.qty>0).sort((a,b)=>a.date<b.date?-1:1);
  const next=future[0]?.date||"";
  if(daily>0){ let stock=sum(bs.filter(b=>b.date===TODAY),b=>b.qty); const arr={}; future.forEach(b=>{ const t=daysBetween(TODAY,b.date); arr[t]=(arr[t]||0)+b.qty; });
    for(let t=0;t<=400;t++){ if(t>0) stock+=arr[t]||0; stock-=daily; if(stock<0){ sellout=addDays(TODAY,t); const t2=Object.keys(arr).map(Number).filter(x=>x>t).sort((a,b)=>a-b)[0]; resume=t2!=null?addDays(TODAY,t2):null; gapDays=t2!=null?t2-t:null; break; } } }
  const flags=[];
  if(it.archived) flags.push(["已归档 · 不出草稿",'default',`${it.archived.src}${it.archived.at?" "+it.archived.at:""}`]);   // 决策 #82
  if(bs.some(b=>b.overdue)) flags.push(["已过可售日未上架",'red',sum(bs.filter(b=>b.overdue),b=>b.qty)+" 件"]);
  if(bs.some(b=>b.inspected)) flags.push(["被查验",'volcano',"物流轨迹出现查验，周期无法评估"]);
  if(bs.some(b=>b.overdue&&b.no_track)) flags.push(["超期无物流轨迹",'red',""]);
  const tagBad=(it.tags||[]).filter(t=>EXCLUDE_TAGS.includes(t));
  // 第 78 条：领星里补货周期 R 天内已有采购计划（待审批 / 待采购 / 已完成，不含作废 / 驳回）→ 不出草稿；读的是领星实际存在的计划，写入失败下一轮自动再出
  const blockPlans=(it.plans_recent||[]).filter(pl=>daysBetween(pl.created,TODAY)<=R);
  if(blockPlans.length) flags.push([`${R} 天内已有采购计划`,'blue',blockPlans.map(pl=>`${pl.plan} ${pl.status} · ${pl.created} 建 · ${fmt(pl.qty)} 件（${pl.how}）`).join('；')]);
  if(tagBad.length) flags.push([`标签 ${tagBad.join(" / ")}`,'default',"领星产品标签为历史产品 / 其他用途，不出采购计划草稿（Rocky 2026-09-28）；库存 / 在途照常计入"]);
  if(it.listing&&it.listing!=="PUBLISHED") flags.push([`Listing ${it.listing}`,'magenta',"Walmart 在线商品状态异常（领星 Walmart 在线商品 status），不出草稿；库存 / 在途照常计入"]);
  if(capped) flags.push([`单次封顶 ${P.capQty}`,'orange',`有货日只有 ${inN} 天（< ${P.capDays}），按公式建议 ${suggestRaw} 件，单次最多补 ${P.capQty} 件`]);
  // 利润下限（Rocky 2026-10-10 23:12 定 5%）：近 30 天利润率 < 5% 且近 7 天利润率 < 5%（或近 7 天无销售）→ 标红"低利润 · 建议不补"；草稿照出，只提示不改量，跑几周再定要不要不出草稿
  const PMF=P.lowMargin??5; const lowM=it.pm&&it.pm.margin!=null&&it.pm.margin<PMF&&(!it.pm.p7||it.pm.p7.margin==null||it.pm.p7.margin<PMF);
  if(lowM) flags.unshift([`低利润 · 建议不补`,'red',`近 30 天利润率 ${pct(it.pm.margin)}、近 7 天 ${it.pm.p7&&it.pm.p7.margin!=null?pct(it.pm.p7.margin):"无销售"}，都低于 ${PMF}%（第 261010 期复盘：低于 5% 的 18 张否了 17 张）；只提示，不改建议量`]);
  if(tailStock) flags.push([`尾货 <${P.instockMin} 件`,'default',`近 90 天库存最多 ${maxStart} 件，从没到过 ${P.instockMin} 件，算不出日销；卖完即止`]);
  else if(noStock90) flags.push(["近 90 天无库存",'default',`90 天里没有一天期初库存 ≥ ${P.instockMin} 件，算不出日销，人工处理`]);
  if(it.wm.available>0&&it.wm.available<P.instockMin) flags.push([`库存 ${it.wm.available} 件（<${P.instockMin} 视同断货）`,'red',"WFS 可售低于有货日阈值，按断货处理"]);
  else if(n30<30) flags.push([`有库存天数 ${n30} 天`,'gold',`近 90 天只有 ${n30} 个有货日，用这 ${n30} 天算日销`]);
  if(oosDays>0&&daily>0) flags.push([`已断货 ${oosDays} 天`,'red',`最后一个有货日 ${addDays(TODAY,-oosDays-1)}`]);
  if(it.lead.avg==null) flags.push(["采购交期无样本",'default',`有效样本 ${it.lead.n}，${it.cg_delivery>0?`用领星产品采购交期 ${it.cg_delivery} 天`:`领星也没填，用兜底 ${P.leadFallback} 天`}`]);
  if(it.owner_count>1) flags.push(["多个负责人",'orange',`${it.owner}（Rocky：一个产品只有一个负责人）`]);
  if(it.box_missing_after_ship) flags.push(["缺默认箱规",'orange',"已发过货仍无默认箱规 → 提醒中台和采购"]);
  if(it.overseas_sku) flags.push([`海外仓 ${fmt(it.overseas_sku)}（未计入）`,'default',"海外仓库存未分店铺，无法归属 ItemID"]);
  return {...it,n30,N,salesN,inN,daily,oosDays,noStock90,tail:tailStock,maxStart,instock,leadP,leadSrc:it.lead.avg!=null?"real":(it.cg_delivery>0?"lx":"fallback"),L,R,bs,supply,target,gap,suggest,suggestRaw,capOn,capped,boxed,sellout,gapDays,resume,next,newArrive:addDays(TODAY,L),flags,blockPlans,isDraft:FROZEN?!!DRAFT_IDS[it.item_id]:(daily>0&&suggest>=P.minQty&&(!it.listing||it.listing==="PUBLISHED")&&!tagBad.length&&!blockPlans.length&&!it.archived),tagBad,belowMin:daily>0&&suggest>0&&suggest<P.minQty,draftId:draftIdOf(it.item_id)};
}
```

### 附录 A-3 `pmc-replenishment/context/decisions.md` 第 64 / 69 / 71 / 75 / 79 / 86 条（原文）

| # | 项 | 结论 |
|---|---|---|
| 86 | 拉数与审批节奏（Rocky 2026-10-10 14:16） | 拉数时间由 Rocky 定（一般周六或周日），拉完即生成草稿；审批截止 = 数据日之后的第一个周一（本期数据日 10-10 周六 → 周一 10-12 审完）。页面不再写"每周五凌晨拉数 / 周五 08:00 前生成"。 |
| 64 | 拉数方式（过渡期） | 先**人工跑**：Rocky 周四晚在终端手动跑 run_scheduled.sh + 采购计划草稿刷新 + 箱规核对；系统每周四 19:46（北京时间）推送提醒（Cowork 定时任务「周四晚 · 手动跑每周拉数提醒」）。票据 v10e 未执行、**暂缓**；Mac 上 launchd 任务仍是周三 / 周六且无权限，是否停用由 Rocky 决定 |
| 69 | 海外仓与草稿（修订第 68 条） | 海外仓仍不计入有效供应，但出草稿时先扣：分给该 ItemID 的海外仓件数 = 同 SKU 海外仓可用按「断货最早先用」分配；**采购量 = 建议量 − 海外仓分配**，≥50 件（箱规取整）出草稿、并提示海外仓先补入，<50 件不出草稿只提示。都需要时人工分摊。海外仓发 WFS 识别 = 发货单物流商 WFS（6899）；这类货件不套众壹轨迹规则（pmc-overview 第 17–22 条） |
| 71 | 日销口径修订（取代第 3、23、30 条的窗口写法，Rocky 2026-09-27） | **日销 = 最近 30 个有货日的销量 ÷ 有货日天数，最长回看 90 天**（每周拉数的 Walmart inventory-log 就是 90 天）。有货日不足 30 天有几天算几天，标「有库存天数 X 天」（不再叫「销售数据不足」）；90 天里没有一天有货 → 标「近 90 天无库存」，算不出日销、不出草稿、人工处理。断货天数 = 距最后一个有货日。取消 20 / 10 / 5 天备用窗口（按日历取窗口会把断货期算进去：YC00347 断货 13 天被判日销 0 / 滞销，同类 55 个）。20260925：有日销 483、近 90 天无库存 486、有货不足 30 天 282；本轮草稿 78 → 159、建议合计 17,017 → 32,342 件（断货中的 ItemID 有了日销，多出的草稿要人工过：季节品 / 停售品可能不该补） |
| 75 | 有货日最低库存 5 件（Rocky 2026-09-30，修订第 71 条的有货日定义） | **有货日 = 当天期初 WFS 可售 ≥ instockMin（默认 5，规则设置可改）**，期初 = 前一天日终（inventory-log 倒推），多店铺同 ItemID 按合并库存判。库存 1–4 件的日子销量被库存卡住，不算有货日、销量也不进分子。同口径：**WFS 可售 < 5 视同断货**（总看板「已断货」= 日销 > 0 且可售 < 5，草稿页标「库存 N 件（<5 视同断货）」）；90 天最多只有 1–4 件、从没到过阈值的标「尾货 <5 件」（不是真断货，卖完即止，不出草稿）。模拟依据：09-29 数据 90 天里 1–4 件的低库存日占全部有货日 22.6%（439 个 ItemID）；改后 84 个 ItemID 日销上升 >20%、5 个下降；极端例 20090553004 日销 5.3 → 35.7。结果：草稿 95 → 112、总看板 93 → 108，已断货 184，近 90 天无库存 506（含尾货）。备选（先不做）：阈值改 max(5, 1 天日销)。 |
| 79 | 首批写入后的三条口径（Rocky 2026-09-30 讨论定，同日实现进 Demo） | ① **领星备注只写两段钥匙**：产品备注 = `ITEMID:<11位> | 草稿:<草稿号>`（如 `ITEMID:20299665653 | 草稿:CG260929-030`），不写表头备注（批次备注），不写建议量 / 审批量 / 理由 / 参数 / 超封顶提示——采购员不需要知道运营批准超封顶；一次创建写完，不再调 planModifyRemark。已建的 PP260930007 / 008 备注不改。审批理由、计算快照、参数、广告利润等全部存本系统台账（正式系统 draft 表）。② **草稿号 ↔ 领星计划号双向核对**（每周拉数后构建时自动跑）：正向——每张「已写入」草稿按 plan_sn 在 purchase_plans.csv 里找，找不到 → 「写入未确认」；找到但备注草稿号不是它 → 「计划号对不上」；数量 / 店铺与审批不一致 → 「领星已改量」记新值；状态变化回填。反向——领星里所有备注带 `草稿:` 的计划，草稿号必须在登记表且状态「已写入」，对不上的列出人工处理（防复制计划）。没带 `草稿:` 的新计划 = 人工计划，单独列，第 78 条照样拦草稿。页面「写入核对」只在有异常时显示三类数。前提：v10h（拉到当天计划）。③ **历史草稿看法**：不加 Tab、不加筛选，列表永远只显示最新一轮；某个 ItemID 的历史在它的抽屉里看「补货历史」时间线，一条 = `轮次 · 草稿号 · 建议 N → 审批 M（产品负责人 / 运营负责人）· 计划号 · 状态`，点开看当时快照和批注；**只追到「已转采购单（已采购）」为止**，不追到货 / 上架。**冻结时点 = 发号那一刻**：发草稿号时把计算快照（日销 / 供应 / 参数 / 建议量）写进台账，此后同轮重算不改快照（页面标「按当前参数重算为 N」），审批 / 计划号是往这一行补字段；不通过的下一轮新号新行；重算冒出的新草稿正常发号标「补发」。09-25 / 09-28 两轮不倒补，历史从 260929 轮起。 |
