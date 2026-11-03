# PRP：PMC 采购组 —— 采购看板补差 + 自动补货（采购计划草稿）

状态：`Draft`（待项目负责人 mz-liuyunlong 确认；PRP 不等于批准开发）

- 起草：PMC A 采购组代码 AI · 2026-11-02 · 需求方 Rocky
- 流程：本地 DEMO 工作区 `AGENTS.md` §1.1（8088 业务逻辑为准 → PRP 经刘云龙确认 → 5173 开发 → PR + CI → 审核 AI → Rocky 5173 验收合并 → 刘云龙发布 8443）；本仓库 §11 / §11.1
- 数据源决策：`docs/data-sources/decisions/pmc-purchase-group-decision.md`（A 采购看板 `READY_FOR_PRP`；B 自动补货 `BLOCKED_BY_OWNER_DECISION`）
- 业务来源（需求以此为准，不入仓库代码）：Rocky Mac `features/pmc-purchase/drafts/`（8088 采购看板）、`features/pmc-replenishment/`（8088 自动补货：`drafts/build_from_daily.py`、`drafts/src/app.jsx`、`review_server/server.py`、`context/decisions.md` 第 1–88 条、`context/solution-v1-for-yunlong.md`）；PMC 决策 R-4 ~ R-10
- 关联：`PRPs/pmc-purchase-board.md`（PMC-PURCHASE-1，已 Approved）、#288（ItemID 规则 v2，`origin/pmc/purchase-itemid-rule` ba15384）、#296（待采购超时主表内联）、#282（WFS 货件 ODS）
- 分期：**一期只读**（本 PRP 申请批准的范围）；二期 2a 本系统两层审批、2b 写入领星 `createPurchasePlan`（**只标出，不纳入一期**，各自另出 PRP / 票据）

---

## 0. 需要负责人决定的事

| # | 事项 | 选项 | 建议 |
|---|---|---|---|
| D1 | 补货表归属与命名（原 Y1） | 新模块 `pmc_replenishment`，表见 §6.3 | 同意新模块；表名按 §6.3 |
| D2 | 补货依赖数据接入顺序（原 Y3）：Walmart 期初可售 / 入库中、WFS 货件与 SP 发货单（#282）、众壹轨迹 | a 等各板块先接、补货只复用；b 补货自己接 | a。一期先做引擎和页面，缺的数据集页面标「未接入」 |
| D3 | 日销用的每日库存 / 销量来源 | a 复用 `fact_walmart_listing_inventory_daily` + `fact_walmart_sales_item_daily`；b 另接 inventory-log | a，实现前只读核实 8 店 × 90 天覆盖 |
| D4 | 补货采购交期口径 | a 按 8088（首次收货日 − 下单日）；b 读 `dws_purchase_sku_cycle`（累计 ≥50% 收货日，含人工基准） | 一期 a（与 8088 对数 0 差），详情并列显示 b；统一口径另议 |
| D5 | 补货供应归属顺序（**风险：两套 ItemID 归属规则并存**，见 §6.1.6） | a 补货按 8088（人工对照表 → 备注 ItemID → 店铺内唯一 → SKU 全店唯一），采购看板仍按 #288 v2；b 补货也统一到 #288 v2（`purchase.remark.store.v2`）；c 统一到 8088，采购看板也一起改回 8088 顺序 | 待刘云龙选定。任一方案下页面都标注本页用的是哪套规则 |
| D6 | 人工对照表 `manual_item_map.csv` | a 一次性迁入 `manual_pmc_item_map`；b 不迁（R-10：新草稿自带 ItemID） | a，否则 8088 靠对照表归上的供应（09-29 时约 3,700 件：采购计划 2,070、采购单 1,178、待下单 454、惠州 60）在正式系统变「待归属」 |
| D7 | 8088 草稿号 / 台账 / 审批 / 写入回执迁移与切换 | a 切换日一次性迁入，之后正式系统唯一发号；b 正式系统从新号段起 | a。切换前正式系统只影子计算、不发号，防同号双发 |
| D8 | 归档判断旧系统兜底 | a 取消（本期命中 0）；b 保留（变成读旧库） | a |
| D9 | 一期范围 | a 只读（不含审批）；b 一期就含本系统两层审批 | a（按本次要求「第一期只读」） |

---

## 1. Goal

- **A 采购看板**：按 8088 补两处差异——采购单行带出「采购计划草稿号」（来源改为采购计划备注优先）、搜索类型加「草稿号 / 计划号」；其余维持现状（含 #288 ItemID 规则 v2、R-9 / R-9a、#296）。
- **B 自动补货 · 采购计划草稿（新页面）**：每期（一次拉数 = 一个数据日）按 ItemID 计算补货量，在 Rocky 批准该期后按规则发草稿号（`CG` + 数据日 6 位 + `-` + 3 位序号），冻结快照，展示草稿列表、详情（计算过程 / 供应明细 / 交期样本 / 利润退货 / 补货历史 / 写入预览）、规则参数与写入核对。一期只读，不审批、不写领星。

## 2. Why

- R-10（Rocky 2026-11-02）：以后不在领星直接建采购计划，全部从系统「采购计划草稿」创建再写入领星，规则一律按 8088 DEMO。草稿自带店铺与 ItemID，采购看板「未归属 / 待打包单」不再新增。
- 8088 已跑 5 期（260929、261010、261017、261025、261102；261102 期发出 87 张），流程验证过，需要搬到正式系统。

## 3. Scope

### In scope（一期，只读）

- [ ] A1 采购看板 DWS / API 增加计划备注草稿号来源（计划优先，采购单行备注兜底），待采购计划下钻带草稿号
- [ ] A2 采购看板搜索类型增加「草稿号 / 计划号」（单个 + 批量）
- [ ] A4 采购看板隐藏「小罗」（负责人 / 采购员 / 供应商，名单可配置）
- [ ] B1 补货计算引擎（纯函数，无框架依赖，规则见 §6.1），与 8088 `calc()` / `calc_default()` 同一口径
- [ ] B2 每期计算任务（手动触发的命令 / Celery 任务，默认 disabled，不改调度）：读已同步数据 → 写 DWS / AI 层；期次已批准才发号、冻结快照
- [ ] B3 只读 API ×8（§7）
- [ ] B4 前端 `/pmc/replenishment`：草稿列表 + 统计卡 + 筛选 + 详情抽屉 + 规则设置（只读）+ 写入核对面板 + 下载草稿表
- [ ] B5 写入核对（草稿号 ↔ 领星计划号双向核对，§6.1.10），只读领星已同步的计划
- [ ] B6 本地对数：同一数据日（建议 20261102）5173 与 8088 逐项对比，附差异表
- [ ] 文档：`docs/api/pmc-replenishment-api.md`、`docs/sop/pmc/replenishment.md`、帮助页

### Out of scope（一期不做）

- [ ] **二期 2a**：本系统两层审批（产品负责人 → 运营负责人林翔）、批注规则、改量 / 改写入店铺、管理员改量 / 退回重审、回传表导入
- [ ] **二期 2b**：写领星 `createPurchasePlan`（只传 sku / quantity_plan / sid 字符串 / 产品备注 `ITEMID:<11位> | 草稿:<草稿号>`）、`planCancel`、失败不自动重试先查重；需写接口登记 + 契约 + Rocky 逐单书面批准
- [ ] 飞书通知（8088 `notify_feishu.py` 默认 dry-run）
- [ ] A5 领星负责人清理（写领星，R7a / R7b 单独票据；定时任务 8443 上线后另批）
- [ ] 新增任何外部数据同步（D2 = a 时）；Walmart / 领星真实调用；开启定时
- [ ] 海外仓扣减出差额草稿（decisions 第 69 条在 8088 页面未实现，8088 只提示「海外仓 N（未计入）」，一期照 8088）
- [ ] PMC 总看板、库存过剩、生命周期、Amazon、紧急补货
- [ ] 导航 / 路由 / 权限目录 / main.py 注册（共享文件，交 PMC 总负责 AI 排队）

## 4. Navigation / Page

```text
一级：PMC
二级：采购看板        /pmc/purchase-board      pmc_purchase_board        testing（已有）
二级：自动补货        /pmc/replenishment       pmc_replenishment         planned → building
```

菜单名照 8088（`pmc-v2-app/src/config/navigation.ts`：「自动补货」）。导航项由总负责 AI 加。

## 5. Permissions

```text
采购看板：沿用 pmc:purchase:read
自动补货 page：page:pmc:replenishment:view
自动补货 read：pmc:replenishment:read（全员可看，同 8088）
二期预留（一期不建）：action:pmc:replenishment:review-po、action:pmc:replenishment:review-op（只林翔）、action:pmc:replenishment:write-lingxing（high，二次确认 + 审计）、action:pmc:replenishment:round-approve（只 Rocky）
data scope：无行级限制
```

5173 写入按钮一律置灰（R-6）；一期本来就没有写按钮。

## 6. Data Source

引用决策文件结论：A1 计划备注优先；A3 维持 #288；B 一期只读、不写领星、不另建外部同步。

### 6.1 自动补货业务规则（以 8088 代码为准）

#### 6.1.1 范围与粒度
- 在售 = 领星 Walmart 在线商品 `status_name` ∈ {PUBLISHED, SYSTEM PROBLEM} 且 `fulfillment_type_name` ∈ {WFS Eligible, Walmart Fulfilled} 且有本地 SKU（无本地 SKU 时用人工对照表 SKU，D6）。SYSTEM PROBLEM / 非 PUBLISHED 照常归属库存在途，但不出草稿。
- 排除店铺「晶彩绝伦」`110652398125259264`。
- **ItemID 是草稿唯一值**：同一 ItemID 多店铺在售时销量、可售、全部供应合并（第 52 条）。店铺 ID 全程字符串（18 位）。

#### 6.1.2 日销与有货日（第 71、75 条）
- 回看 90 天（不含数据日当天）。有货日 = 当天期初 WFS 可售 ≥ `instockMin`（5），期初 = 前一天日终，多店铺合并判断。
- 日销 = 最近 30 个有货日的销量 ÷ 有货日数；不足 30 天有几天算几天（标「有库存天数 N 天」）。
- 90 天无一天有货 → 「近 90 天无库存」，不出草稿；90 天最高只有 1–4 件 → 「尾货 <5 件」。
- WFS 可售 1–4 件标「库存 N 件（<5 视同断货）」；断货天数 = 距最后一个有货日。

#### 6.1.3 采购交期（D4）
- 每 SKU：采购单（非作废、明细 sid 非 0、未删除）的下单日（order_time，否则 create_time）→ 该单该 SKU 首次收货日；整数天；<2 天剔除；按下单日倒序取近 5 个有效样本，≥2 个才用平均（保留 1 位小数）。
- 否则领星产品采购交期 `cg_delivery`>0；否则兜底 15 天。

#### 6.1.4 公式与参数
```text
提前期 L = 审批到下单 approve 5 + 采购交期 + 打包发货 pack 7 + 运输 transport 30 + 上架缓冲 shelf 10
补货周期 R = 特殊 ItemID 覆盖 ?? cycle 14
目标量 = 日销 × (L + R + safety 0)
建议量 = ceil(目标量 − 有效供应)，≤0 记 0
单次封顶：有货日 < capDays 30 且建议量 > capQty 300 → 建议量 = 300（标「单次封顶 300」）
箱规取整：不足半箱舍、≥半箱进、至少 1 箱；封顶时取整不得超过封顶量（向下取整箱，一箱都超则不取整）
```
参数全部可配、带版本与生效日；每期计算记录所用版本（第 13 条）。另有 `lowMargin` 5（只提示）。

#### 6.1.5 有效供应（互斥，按 ItemID 归属）
| 状态 | 数量 | 预计可售日（时间线用） |
|---|---|---|
| WFS 可售 | Walmart availableUnits | 今天 |
| 收货中余量 | 货件已有上架时：发货 − 已上架 | 今天 |
| ①b 入库中差额 | 同店 × ItemID：min(Walmart inboundUnits − 系统在途 − 未发货货件件数, 窗口内非取消货件未过账件数 − 系统在途)，>0 才计；超出部分记「疑似陈旧」只提示 | 今天 |
| 已发货未上架 | 货件（非 CLOSED / CANCELLED、已发货）× 商品行 发货数 | 到仓日（实际优先，否则 SP 预计，`arrival_rules.cargo_arrival`）+ shelf；已过可售日标红 |
| 国内仓 | 惠州 wid 16168 可用 + 锁定 | 今天 + pack + transport + shelf |
| 采购单待到货 | status 2 的 `quantity_receive` | max(下单 + 交期, 今天) + pack + transport + shelf |
| 采购单待下单 | status 1 的 `quantity_real` 或 `quantity_plan` | 今天 + 交期 + 尾段 |
| 采购计划待采购 | **只 status 2**（121 待审批不计，Rocky 2026-10-13） | max(创建 + approve, 今天) + 交期 + 尾段 |

不计：海外仓（只按 SKU 提示）、作废 / 关闭、CLOSED / CANCELLED 货件、Walmart Received 不另算。

#### 6.1.6 供应归属（D5，按 8088）
> **风险：两套 ItemID 归属规则并存。** 采购看板已按 #288 v2（`item_id_resolution`，`purchase.remark.store.v2` + R-9 / R-9a）归属；本节补货按 8088 顺序归属。两者对同一采购单 / 计划可能归到不同 ItemID，采购看板与补货的供应数会对不上。可选：a 补货按 8088（采购看板不动）；b 补货也统一到 #288 v2；c 统一到 8088，采购看板也一起改。等刘云龙选定（D5）。不论选哪个，采购看板和补货页面都要在表头 / 说明里标注本页用的归属规则（如「ItemID 归属：#288 v2」或「ItemID 归属：8088」）。依据原文与快照 sha256 见决策文档附录。

人工对照表（SKU + 单号）→ 人工对照表（SKU，只填了一个 ItemID 时）→ 备注 11 位 ItemID（须为该店在售）→ 店铺内唯一在售 ItemID → SKU 在全部店铺只有 1 个在售 ItemID。批次所在店铺没上架但别店在售 → 照样计入该 ItemID。都不中 → 列「待归属」，不计入。
- 货件 / 发货单（已发货未上架、收货中）：数量取领星 WFS 货件商品行的发货数（`shipments_num`）；ItemID = 该货件店铺（`store_id`）下 MSKU 对应的 Listing，MSKU 对不上再用 GTIN；对不上的进「待归属」。SP 发货单不单独计数量，只用来定到仓日（实际到仓 / 预计到仓）、查验与轨迹；一个货件挂多个 SP 时取已发货 SP 的最早实际到仓，没有实际再取预计最晚（`arrival_rules.cargo_arrival`）。未发货的货件不计（货还在国内仓，按国内仓算，避免重复）。
- 国内仓出库：惠州「可用 + 锁定」按 `seller_id` + SKU 走上面的归属顺序；已出库发走的货进入货件那一段，不在国内仓重复计。

#### 6.1.7 出草稿条件
日销 > 0 且 建议量 ≥ minQty 50 且 Listing = PUBLISHED 且 产品标签不含「历史产品 / 其他用途」 且 未归档（`listing_archive_states`，D8） 且 **近 R 天内领星没有该 ItemID 的采购计划**（读领星实际计划：create_time 距数据日 ≤ R，状态不含已作废 124 / -3、已驳回 122；按备注 ItemID → 店铺 + SKU 归属）。

#### 6.1.8 期次与草稿号（第 76、78 条，2026-10-13 / 10-14）
- 期次 = 数据日 6 位（如 261102）。**每期须 Rocky 单独批准**才发号；未批准的期不发号、不写台账，页面「本期」退回最近一个已批准的期（冻结模式只显示已发号草稿）。
- 草稿号 `CG<期>-<3 位序号>`：同期同 ItemID 只发一次、发过不变、只追加不重排；发号只用默认参数。
- 发号时冻结快照（日销、有货日、断货天数、交期及来源、L、供应分项与单据号、目标量、公式建议、封顶、建议量、箱规、拦截计划、参数、当时利润广告），之后只补审批 / 计划号 / 核对字段；重算只记 `recalc_suggest`。
- 写入店铺默认：在途最多 → 近 30 天销量 → WFS 可售 → 店名；候选只能是该 ItemID 在售的店铺。

#### 6.1.9 提醒标签（只提示，不改量）
低利润 · 建议不补（近 30 天且近 7 天利润率 <5%，置顶标红）、已归档、已过可售日未上架、被查验、超期无物流轨迹、R 天内已有采购计划、标签剔除、Listing 异常、单次封顶、尾货、近 90 天无库存、库存 <5 视同断货、有库存天数 N、已断货 N 天、采购交期无样本、多个负责人、缺默认箱规（已发过货仍无）、海外仓 N（未计入）、退货率 >5%（销量 <20 件另提示比例受单笔影响）。
利润 / ROI / 广告占比 / 退货率口径：第 81、84、85 条及 10-10 22:28 修正（窗口截止数据日 − 2 天；近 30 / 15 / 7 天；ROI 三档 <0.5 / 0.5–1 / ≥1；利润率四档 >22 / 15–22 / 10–15 / <10；档位名称不自拟）。

#### 6.1.10 写入核对（第 79 条，一期只读）
- 正向：台账里有 plan_sn 的草稿，按 plan_sn 找领星计划：找不到 → 「写入未确认」（拉数当天写入的记「待拉数核对」；有写入读回记录则记一致）；备注草稿号不同 → 「计划号对不上」；数量 / 店铺与审批不同 → 「领星已改量」；记作废的 → 领星仍有效则「作废未落实」；已完成且有采购单 → 「已转采购单」。
- 反向：领星备注带 `草稿:` 的计划，草稿号必须在台账且计划号一致（已作废的重复计划不算）。
- 近 7 天无草稿号的人工计划单独列出。

#### 6.1.11 断货时间线（第 26 条）
现有可售（今天可售的各项）按日销往后推，未来批次按预计可售日加入，得到「能卖到哪天 / 下一批可售日 / 断几天」（≤400 天）。补货周期内断货只标红，不破例出草稿（第 41 条）。

### 6.2 采购看板补差规则

- A1 草稿号：采购单行 → 关联计划（`relation_purchase_plan` / `plan_sn` 中的 PP 号）→ 计划 `remark` / `plan_remark` 中 `草稿:CG\d{6}-\d{3}`，多计划去重排序以「/」连接；取不到再用现有采购单行备注解析。待采购计划下钻同样带草稿号。
- A2 搜索：类型「草稿号 / 计划号」匹配草稿号或计划号（包含匹配，同其他类型；批量最多 200 个）。
- A3 不改：ItemID 按 #288 `item_id_resolution`（`purchase.remark.store.v2`）+ R-9 / R-9a；S2 / S3 阈值、到仓 50%、审批周期、交期不稳定等口径与 8088 一致，已在 PMC-PURCHASE-1 实现。
- A4 隐藏「小罗」（Rocky 2026-11-02 定：照搬 8088）：负责人、采购员、供应商三个字段里名字为「小罗」的不显示、不进负责人筛选项；同一行有多个负责人时去掉小罗后取第一个。名单做成配置（`pmc_purchase_hidden_names`，默认 [小罗]），不写死在前端。
- A5 领星产品负责人去掉名单人员（Rocky 2026-11-02 选 b，**不在一期代码范围**）：名单可配置，现为 11507967 郑跃鹏、10885607 小罗（API 操作人账号；`product/set` 不带 `product_duty_uids` 时会被领星自动追加）。属领星写入，做法同 R3~R6：R7a 只读全库出清单 → Rocky 按数量书面批准 → R7b 受控写（只传 sku + 保留负责人 + `is_append_product_duty=0`，先改 1 个逐字段比对，非负责人字段有变化即恢复并停；只剩名单人员的产品不改只报）。8443 上线前每周拉数后人工跑一次 R7a→R7b；改成定时任务等 8443 上线后另出票、Rocky 书面批准。**这是领星写操作**：须先登记写接口（`/erp/sc/routing/storage/product/set`）、签写入合同，每次操作都要 Rocky 书面批准；不在第一阶段范围内，一期代码不调用任何领星写接口。

### 6.3 表（D1，命名按现有 ODS / DWD / DWS / manual_ 习惯）

| 层 | 表 | 内容 | 写入方 |
|---|---|---|---|
| 规则 | `pmc_replenishment_rule_versions` | 12 个参数 + 版本 + 生效日 | 迁移种子（默认值同 8088） |
| manual | `manual_replenishment_item_params` | 特殊 ItemID 补货周期 | 二期页面；一期迁移种子 / 运维命令 |
| manual | `manual_replenishment_round_approvals` | 期次批准（期、批准人、时间、依据原话） | 一期运维命令按票据；永不被计算覆盖 |
| manual | `manual_pmc_item_map`（D6） | SKU / 单号 → ItemID / 店铺 | 一次性迁移 |
| DWS | `dws_replenishment_item_daily` | 期 × ItemID × 日：期初可售、销量、是否有货 | 计算任务 |
| DWS | `dws_replenishment_supply` | 期 × 供应行：状态、数量、店铺、单据号、归属 ItemID、归属方式、预计可售日 | 计算任务 |
| AI / 计算 | `ai_replenishment_runs` | 每期每次计算：数据日、规则版本、开始结束、状态、各项计数（只追加） | 计算任务 |
| AI / 计算 | `ai_replenishment_suggestions` | 期 × ItemID：全部计算结果、提醒、时间线、默认店铺、各店铺在途 / 销量 / 可售 | 计算任务（同期重算覆盖本期本行，不动已冻结快照） |
| gov | `gov_replenishment_drafts` | 草稿号（主键）、期、ItemID、SKU、店铺、发号时间、冻结快照 JSON、规则版本、plan_sn、核对结果 | 计算任务发号（只追加；快照不改） |
| mart | `mart_replenishment_draft_board` | 前端读模型 | 计算任务 |
| 二期 | `manual_replenishment_reviews`、`evt_replenishment_plan_writes` | 审批事件（只追加）、写领星请求摘要 / 结果 / plan_sn / request_id | 二期 |

计算只写计算层（DWS / AI / gov / mart），不改 RAW / ODS，不覆盖人工记录，不删历史。

## 7. API Contract（一期，全部 GET，前缀 `/api/pmc/replenishment`，权限 `pmc:replenishment:read`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/rounds` | 已批准期次列表、当前有效期、数据日、是否冻结（数据日那期未批准） |
| GET | `/drafts` | 列表：`round`、`store_id`、`owner`、`status`、`keyword`（草稿号 / ItemID / SKU / MSKU / 品名）、`risk`（断货风险 / 退货率 >5%）、`show_all`（含不需补货）、分页排序 |
| GET | `/drafts/summary` | 统计卡：在售 WFS ItemID、本轮草稿（张 / 件）、待产品负责人审批、已通过（待写入）、已写入领星、不通过、有断货风险、退货率高于 5% |
| GET | `/drafts/{draft_id}` | 草稿详情（冻结快照 + 当前重算 + 写入预览文本 `ITEMID:<id> \| 草稿:<号>` + 核对） |
| GET | `/items/{item_id}` | 无草稿 ItemID 的计算详情（显示「不需补货 / 拦截原因」）+ 补货历史（历期草稿） |
| GET | `/check` | 写入核对：异常（4 类 + 反向）、待拉数核对、近 7 天人工计划、计数 |
| GET | `/rules` | 当前参数版本、特殊 ItemID 周期 |
| GET | `/drafts/export` | 下载本期草稿表 xlsx（三页：草稿 34 列 / 填写说明 / 参数快照；一期不含回传导入） |

采购看板（已有接口，改返回）：`GET /api/pmc/purchase/board` 增加 `search_type=draft`；`draft_no` 来源调整；`GET /api/pmc/purchase/plans/pending` 增加 `draft_no`。

错误码沿用仓库统一格式；不在 route 里调外部接口。

## 8. UI Requirements（照 8088 `app.jsx`，外框同 5173）

- 统计卡（可点筛选）：§7 summary 八项。
- 筛选：店铺、负责人、草稿状态、期次（本期 = 最近已批准期；往期 = 台账冻结快照表）、关键词、只看断货风险、显示不需补货的。
- 列：草稿号、ItemID（`WalmartItemLink`）/ SKU、店铺（跨店显示 +N 店；默认写入店铺）、负责人、日销、有货日、提前期、补货周期、有效供应、目标量、建议量、草稿量（箱规取整）、现有可售能卖到、下一批预计可售、断几天、利润率 / ROI / 广告占比、退货率（近 30 天）、提醒、状态、领星计划号、采购单。
- 详情抽屉：计算过程、补货计算器（只在页面算，不保存）、有效供应明细、采购交期样本（近 5 单）、近 90 天销量柱、每日数据 60 天、销量 / 退货 30 / 60 / 90 天、利润 / ROI / 广告 30 / 15 / 7 天、退货率与原因前三、提醒、补货历史时间线、写入领星预览（一期只显示文本）、操作记录（一期空 / 只读历史）。
- 审批区一期显示「二期开放」，不放可点按钮。
- 规则设置：参数表与特殊 ItemID 周期只读展示（版本、生效日）。
- 写入核对面板：只在有异常 / 待核对时显示三类计数。
- 数据新鲜度：显示数据日与计算时间；未接入的数据集明确标「未接入」，不做 mock（R-6）。

## 9. SOP / API Docs

- 新增 `docs/api/pmc-replenishment-api.md`、`docs/sop/pmc/replenishment.md`（每期流程：拉数 → Rocky 批准期次 → 计算发号 → 审批（二期）→ 写入（二期）→ 核对）、`frontend/public/help/pmc-replenishment.html`
- 更新 `docs/api/pmc-purchase-api.md`（draft 搜索、草稿号来源）、`docs/sop/pmc/purchase-board.md`
- 数据中心接口文档由总负责 AI 统一加

## 10. Implementation Plan（分 PR，每个 PR 独立可回滚）

1. **PR-A 采购看板补差**（READY）：dwd / refresh 加计划备注草稿号；API search_type=draft；待采购下钻带草稿号；前端搜索选项；测试。
2. **PR-B 补货引擎**：`pmc_replenishment/calculations.py` 等纯函数 + 单测；用 8088 `demo-data.json`（20261102）做金样对照（只用已拉下文件，不调接口）。
3. **PR-C 表与计算任务**：迁移（§6.3 一期表）+ 计算任务（手动触发、默认 disabled）+ 发号 / 冻结 / 核对；数据缺项按 D2 / D3 结果处理。
4. **PR-D 只读 API + 文档**。
5. **PR-E 前端页面**（导航 / 路由 / 权限键由总负责 AI 同步加）。
6. **PR-F（D6 / D7 批准后）**：8088 迁移脚本（对照表、登记表、台账、回执、审批历史），只追加，带数量核对；生产执行另出票。

每步：从最新 main 建 `ai/YYYYMMDD-task`；跑 lint / test / build / `scripts/check-rule-pack.sh` / `git diff --check`；合进 `pmc/local-preview` 给 Rocky 5173 改动清单（R-8）。

## 11. Validation Gates

```bash
# backend
cd backend && uv run ruff check . && uv run pytest tests/modules/pmc_purchase tests/modules/pmc_replenishment
# frontend
cd frontend && npm run lint && npx vitest run src/pages/pmc/purchase-board src/pages/pmc/replenishment && npm run build   # build 含 tsc -b
# repo
scripts/check-rule-pack.sh && git diff --check
```

对数（5173 vs 8088，同一数据日，数据只用已拉下 daily 或 RAW 回放灌本地库）：
- 在售 ItemID 数、本期草稿数与草稿号集合、建议合计件数、被 14 天计划拦下数（261102 期 8088：87 张 / 38 个拦下）——差 0
- 每个 ItemID 的日销、有货日、交期及来源、L、各分项供应、目标量、建议量、草稿量——差 0
- 写入核对各类计数一致
- 有差异逐条列差异表并说明原因（多半是数据集未接入）

## 12. Forbidden Actions

- 不调领星 / Walmart / 众壹真实接口；不读凭证；不碰服务器；不改定时任务
- 一期不写领星（`createPurchasePlan` / `planModifyRemark` / `planCancel` 全部二期，逐单书面批准）
- 计算不写 RAW / ODS，不覆盖 manual 表，不删历史；草稿快照发号后不改
- 未批准期次不发号；切换日前正式系统不发号（防同号双发）
- 不改共享文件；不改 #288 共享 ItemID 规则文件（属国内仓 / 采购共用，改动先报总负责 AI）
- 不推 main、不自行合并

## 13. Rollback Plan

- PR-A：回退提交即可（只加列与筛选，DWS 重刷）。
- 补货：新模块新表，回退 = 关闭导航项 + downgrade 迁移（一期表无外部依赖、无人工数据；迁入的 8088 数据在 8088 原文件仍在）。
- 计算任务默认 disabled，不改调度。

## 14. Acceptance Checklist

- [ ] D1 ~ D9 有负责人结论，决策文件「负责人决定」已填
- [ ] 采购看板：草稿号来源与搜索按 §6.2，ItemID 规则未变
- [ ] 补货：§11 对数差 0（或差异有解释并经 Rocky 认可）
- [ ] 未批准期次不发号；同期重算草稿号不变；快照不变
- [ ] 页面无写按钮、无 mock；未接入数据集有标注
- [ ] lint / test / build / rule-pack / diff-check 全绿，CI 全绿
- [ ] Rocky 5173 验收；发布单交刘云龙

---

## 附：二期（只标出，不纳入一期）

- **2a 两层审批**（第 55、59、63、87、88 条）：状态 待产品负责人审批 → 待运营审批（林翔）→ 已通过（待写入领星）/ 不通过；只有通过 / 不通过；产品负责人批注 >15 字（通过 / 不通过都要），可改量、改写入店铺，超封顶要在批注写原因；运营不通过必须批注，改量 / 改店必须批注；产品负责人一步不限本人、运营只限林翔；状态不可倒退；管理员改量（stage=admin，原记录保留）、退回重审；通过的 ItemID 补货周期内不再出草稿（实际由领星计划拦截实现）；回传表导入。
- **2b 写入领星**：`POST /erp/sc/routing/data/local_inventory/createPurchasePlan`（令牌桶 1）；只传 `sku`、`quantity_plan`（运营最终量，否则产品负责人量）、`sid`（Walmart store_id 字符串）、产品备注 `ITEMID:<11位> | 草稿:<草稿号>`；不写批次备注、不传仓库 / 供应商 / 采购方 / 期望到货 / 采购员；建出即「待采购」不进领星审批（本系统审批是唯一关口）；无幂等 → 失败不自动重试，先按 当天创建 + 备注草稿号 查重；写前校验 ItemID 仍 PUBLISHED、近 R 天无新计划；逐条读回；错单 `planCancel`。需：写接口登记、契约、受控写票据、Rocky 逐单书面批准。
