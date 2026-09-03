# API_MAP.md — 全渠道对外接口能力台账

> **建档**：2026-08-21。起因：广告出价/预算/竞价策略探测过程中发现，接口能力的探测结论散落在四处
> （`docs/lingxing/` 21 份文档、`reports/*_probe.md`、`TASK_CHANGE_LOG` 若干条、代码里在跑的路径），
> 每次要回答"这个字段拿不拿得到"都得重新翻一遍，且已因此**重复踩过坑**（详见 §6 教训）。
>
> **本文件的定位**：**接口能力的唯一台账**。回答三类问题——
>   ① 某个字段/能力，哪个渠道哪个接口给？ ② 这个接口我们接没接、落到哪张表？ ③ 探过没有、结论是什么？
>
> **维护规矩（写死）**：
> 0. **做任何接口探测之前，必须先通读本文件**。目的：不重复探已探过的、不重复踩已记过的坑、
>    不把"本文件已判定为不可用"的接口再试一遍。**探测前未读本文件＝流程违规**（2026-08-21 需求方定）。
> 1. **任何新接口探测完成，必须回写本文件**（新增一行 + 探测日期 + 结论），漏记＝交付未完成。
> 2. 结论一律写**实测事实**，不写文档承诺。文档写了但实测无值的，写"文档有/实测空"并注明样本。
> 3. **"查不到"必须区分三种**：接口不提供 / 提供但本账号无数据 / 查询本身报错。三者处置完全不同，
>    混为一谈已造成过误判（§6-1）。
> 4. 本文件只记**对外接口**（我们调别人）。系统自身对外提供的只读 API 见 `docs/internal_api_readonly.md`。

---

## 1. 渠道总览

| 渠道 | 用途 | 鉴权 | 写能力 | 台账小节 |
|---|---|---|---|---|
| 领星 ERP OpenAPI | 广告/商品/结算/利润/退货 主数据源 | app_key + sign + access_token | **沃尔玛侧全部只读**（见 §2.0） | §2 |
| 飞书 开放平台 | 通报推送、通讯录、考勤、表格镜像 | tenant_access_token | ✅ 有写（发消息/写表格） | §3 |
| Walmart 报表（CSV 人工导出） | 领星 API 不覆盖的口径 | 无（人工下载后上传） | 只读 | §4 |
| 系统内部只读 API | 供 GPT/外部只读消费 | 内部 token | 只读 | §5 |

---

## 2. 领星 ERP OpenAPI

**基址** `https://openapi.lingxing.com` ｜ **令牌** `/api/auth-server/oauth/access-token`
**客户端** `src/lingxingClient.ts`（签名、令牌缓存、超时统一在此）
**铁律** 外部数据一律先入 `raw_lingxing_api` 再进结构层。

### 2.0 写能力结论（2026-08-07 探测，已复核）

> **沃尔玛广告 16 个接口全部为查询类。写接口（修改SP广告活动和广告位 / 修改广告商品状态 / 添加SP关键词 / 否定词）
> 仅存在于亚马逊体系，沃尔玛不支持。** 出处：`TASK_CHANGE_LOG.md:3011`（2026-08-07 条目，逐字核对 4 份 apidoc 存档）。
>
> **推论（important）**：一切"由系统自动改出价/改预算/开关广告"的方案在领星通道上**不可行**。
> 我们能做的是**读快照 + 差分**，即"看见人工改了什么"，而不是"替人工去改"。

### 2.1 广告 — 已接入

| 路径（`/basicOpen/multiplatform/ads/…` 除注明外） | 粒度 | 关键字段 | 落表 | 调用方 | 探测/实测结论 |
|---|---|---|---|---|---|
| `reportAdItemSpList` | 日 × campaign × item | 花费/曝光/点击/销售 | `fact_ads_product_daily` | `syncLingxingDailyToDb.ts` | ✅ 主力。2026-08-03 发票级审计通过，**一切"按ItemID算广告费"以本表为准** |
| `reportKeywordSpList` | 日 × 关键词 | + `keywordBid` | `fact_ads_keyword_daily` | `syncManualAdKeywordDaily.ts`、`replayManualAdKeywordFromRaw.ts` | ✅ 已接。`keyword_bid` 非空率 **52.39%**（129,813 行中 68,013）。⚠️ 见 §2.5-a |
| `/basicOpen/adReport/advertiser/list` | 店铺 → 广告主 | advertiserId | `dim_store*` | `syncWalmartStores.ts` | ✅ 已接 |

**⏱ 广告数据的到位时点（2026-08-22 实测，六天规律一致）**
业务日 D 的广告数据在 **D+2 的 16:40~16:55 首次落库**，到 **17:30 前后**还有一波补写（新增的活动/关键词组合）。
实测样本（`fact_ads_product_daily` 的 `MIN(created_at)`）：
`08-19 → 08-21 16:40:04`｜`08-18 → 08-20 16:40:04`｜`08-17 → 08-19 14:09:11`｜`08-16 → 08-18 16:53:58`｜`08-15 → 08-17 16:53:54`｜`08-14 → 08-16 16:52:39`
⇒ **广告费做不到 T-1，建表也解决不了**——这是接口侧的归因延迟（`adSpend` 有 `day=14` 归因），不是我们没建表。
⇒ 运营**早上 9 点看到的最新广告/利润日是 T-3；下午 5 点之后变成 T-2**。
对应 cron `40 16 * * * syncSbSvAdsDaily`。⚠️ **17:30 那波补写的写入方尚未确认**——`sbsv_ads_daily.log` 16:40:52 即结束，时间对不上（见 §7 待办）。

### 2.2 广告 — 2026-08-21 探测，**可用但尚未接入**

| 路径 | 粒度 | 实测结论（样本见备注） | 关键字段 |
|---|---|---|---|
| `queryCampaignSpList` | 活动级 | ✅ **可用，且同一接口能返回 SP 与 SV**。CN2502 SP=1145活动；CN2601 SP=918、**video=13** | `dailyBudget` ✅全有值 · `budgetType` ✅(全 daily) · `rollover` ✅ · `biddingStrategy{strategy,troas,biddingStrategyStatus}` ✅ · `campaignStatus` ✅ · `targetingType` ✅ · `entityCreateAt` ✅ · `startDate` ✅ |
| `reportKeywordSvList` | SV 关键词 | ✅ **可用**。CN2601 返回 119 行 | `keywordBid` ✅119/119 · **`keywordState`=enabled** · **`keywordStatus`=approved** · `keywordId` ✅ · `matchType`(exact60/broad32/phrase27) · `adGroupStatus` |
| `reportKeywordSpList`（已接入，但字段没取全） | SP 关键词 | ✅ 66 字段，`data.total=8613`。**`keywordId`/`keywordState`/`keywordBid` 每天都返回却未入库** | `keywordBid` ✅200/200 · **`keywordState`(enabled193/paused7)** · `keywordStatus`(approved 全同值) · `keywordId` ✅ · `matchType`(broad76/exact73/phrase51) · `adGroupStatus` · `campaignStatus`(live184/paused15/completed1) |
| `reportKeywordSbList` | SB 关键词 | ⚠️ **0 行 ≠ 接口不可用**。CN2502/CN2601 均 0，且 `fact_ads_product_daily` 里 `campaign_type` 只有 `video` 无 `sba` → 判定为**公司未投放 SB 广告** | — |
| `queryGroupSpList` | 广告组级 | ✅ **可用**。2026-08-21 实测：CN2601(571910) 返回 **1071 组**、CN2501(497124) 返回 **392 组** → **「广告组增减」可判定** | `adGroupId` ✅ · `adGroupName` ✅ · `campaignId` ✅ · `adGroupStatus` ✅ · ⚠️ `entityCreateAt` **仅 20~39/200 有值** → **新增广告组不得靠创建时间判定，必须用 `adGroupId` 首次出现日** |
| `reportPlatformSpList` / `reportPlatformSvList` | 日 × 平台位 | ⚠️ **可用，但不给竞价倍数**。字段表里有 `bid`，**两家店实测全空**，详见 §2.6 | — |
| `queryPageTypeSPList` | 页面类型 | ⚠️ **2026-07-02 的「服务端异常」结论已作废**（见 §2.3）：2026-08-21 实测 `code=0`，CN2601 返回 80 行、CN2501 返回 93 行。**但返回行内没有任何广告位维度字段**，行无法归属到 Buy-Box / Search Ingrid → **拿不到位置维度** | — |

**实测要点（都是文档里没有、只能靠跑出来的）**
- `campaignStatus` 实测枚举含 **`proposal`**（SV 13 行中 7 个），文档未列。**做状态差分必须按实测枚举，不能照文档。**
- `biddingStrategy.strategy` 实测分布 **FIXED 191 / DYNAMIC 9**（CN2502）、**FIXED 194 / DYNAMIC 6**（CN2601）→ 有区分度。
  对比：自动广告 CSV 的 `Current Bidding Strategy` 实测 **292 行全是 Fixed、`Current Target ROAS` 全空** → **CSV 那列当前信息量为零，该走 API**。
- `totalBudget` / `endDate` 全空——与 `budgetType` 全为 `daily` 一致，属**合理为空**，不是缺陷。
- `appliedTemplate` / `benchmarkVal` 全空且 `isApplyTime` 全 false → **本账号未使用分时策略**，不是接口不给。
- **限流**：`queryCampaignSpList` 文档标注**令牌桶容量 = 1**，探针内置 2500ms 间隔。
- **⏰ 限流的时段规律（2026-08-22 实测，同代码同账号两次跑出相反结果）**：
  · **北京 00:16~00:38 跑**：campaign sp/sba/video 三类 9 店**全部成功**，`combo_failed=9`（只有已知的 group/video 参数错）。
  · **北京 17:40~17:59 跑**：campaign 三类 **9 店 27 个组合全部 `new requests too frequently`**，`campaign upsert=0`，
    `combo_failed=36`（27 限流 + 9 已知参数错），该日 campaign 维度快照为空。
  · 成因：`queryCampaignSpList` 令牌桶容量 = 1，而 campaign 是脚本里**第一个跑的实体**；白天同账号还有
    `25 17 checkAutoAdSearchTermImport`、`40 16 syncSbSvAdsDaily`、`45 16 backfillDailyChain` 等任务在打领星接口，
    一启动就撞上被占的桶，campaign 全灭；等轮到 group/keyword 时其他任务已跑完，于是全部成功。
    ⚠️ 勘误（2026-08-24 源码核实）：旧文曾把 `*/30 9-20 checkSemImport` 也列为占桶任务——**错**。该脚本只读 MySQL + 发飞书卡片，
    无 LingxingClient、不调领星接口（唯一 http 命中是卡片里的页面链接字符串 `PAGE_URL`）。
  · **API 忙闲实测（2026-08-24，近7天 raw_lingxing_api 按小时/10分钟桶直方图，回执 20260824_定时任务与API空档）**：
    北京 **14:30~16:20 七天零调用**（干净空档）；**16:21 起进入高峰**（reportAdItemSpList/list/pageList 为主，hour=16 共 5892 次）。
  > **⇒ 快照 cron 的安全依据从「凭密集时段推断」改为「按实测忙闲直方图选空档」（2026-08-24 起）。**
  > **⇒ 2026-08-24 起快照挪至 `10 15 * * *`（北京15:10=美西00:10，实测空档内，事件窗对齐完整美西自然日），另挂 `30 20` 条件补拍（`--if-incomplete`，当日快照完整则直接退出）。原 `30 6` 下线。哨兵判据=fact_ads_snapshot_status 的 is_complete，⚠️ 不得用 sync_task_log 的 status——SV group「参数有误」使该任务天天记 failed，无区分度。**
  > **⇒ 限流是「可重试」的临时失败，与 group/video 的「参数有误」性质完全不同，两者不可混为一谈。**
- **参数硬约束**：`startDate`/`endDate` 间隔 ≤ 31 天；`paging` 必填 true；`pageSize` < 2000；`operationSourceType` 必传 `gateway`；`day` 归因天数枚举 3/14/30。
- **SB 三个路径实测存在**：`reportAdGroupSbList` / `reportPageTypeSbList` / `reportPlatformSbList` 均 `code=0, total=0`
  → **路径正确、公司无 SB 投放**（非接口不可用）。需求方 2026-08-21 明确「SB 以后可能开」，**设计时 SB 必须一并做进去，不得因当前 0 行省略**。
- **两个 SV 路径是猜错的**：`queryAdGroupSvList` 返回「参数有误」、`reportPageTypeSvList` 直接 404。
  这两个路径**是照 `docs/lingxing/_sidebar.md` 的文件名拼出来的，未经 apidoc 正文确认** → 只能记「路径未证实」，不得记「接口不可用」。见 §6-5。

### 2.3 广告 — 探测失败 / 未接入

| 路径 | 结论 |
|---|---|
| `queryPageTypeSPList` | ⚠️ **本结论已于 2026-08-21 作废 —— 接口现在能返回数据了，见 §2.2**。原结论存档：❌ 2026-07-02 探测：HTTP 200 但业务 code≠0、`message="程序内部错误"`，**8 种参数组合全败**；同鉴权下 `reportPlatformSpList` 正常 → 判定为**领星服务端对本账号异常，非参数问题**。出处 `reports/lingxing_page_type_api_probe.md` |
| `reportPlatformSpList` | 探测可用（`probeAdsNewDimensions.ts`），**未接入**。注：`sql/009` 定义的 `fact_ads_platform_daily` 表**在生产从未创建**（`ERROR 1146`），是空壳 |
| `reportAdItemSbList` / `reportAdItemSvList` / `reportCampaignSbList` / `reportCampaignSvList` | 仅在探针 `probeSbSvAdData.ts` / `probeSbSvParamIsolate.ts` 出现，未接入生产同步 |
| `reportProductSpList` | 仅 `testReadAdKeywordFields.ts`，未接入 |

### 2.4 非广告接口

| 路径 | 用途 | 落表 | 调用方 |
|---|---|---|---|
| `/basicOpen/multiplatform/walmart/list` | 在线商品列表（**含 `price` 挂牌价**） | `raw_lingxing_walmart_listing` → `dim_product.buy_box_price` | `syncWalmartListingPrice.ts`、`adminDataFetcher.ts`、`noOrderNotify.ts` |
| `/basicOpen/multiplatformFinance/walmart/bill/statement/list` | 结算对账单 | 结算相关 FACT | `syncWalmartBillDaily.ts` 族 |
| `/basicOpen/multiplatformFinance/walmart/bill/payout/list` | 打款 | 同上 | `syncWalmartBillDaily.ts` |
| `/basicOpen/openapi/multiplatform/walmart/returnOrder/list` | 退货售后 | 退货 FACT | `syncWalmartReturnOrders.ts`（限速 1500ms/页，`--confirm-write` 才写） |
| `/basicOpen/multiplatform/profit/report/msku` `/order` `/sku` | 结算利润报表 | — | 多个探针 |
| `/basicOpen/platformStatisticsV2/saleStat/pageList` | 销量统计 | — | `noOrderNotify.ts`、`checkRecentProfitItem.ts` |
| `/basicOpen/multiplatform/temu/list` | TEMU 在线商品 | 清货台账 | `syncTemuClearanceListing.ts` |

**⚠️ 已知禁用口径**：`profit/report/msku` 的 `platformAdvertisingFee` / `semMarketingFee` / `advertisementAmount`
**不可用作广告费口径**（实测仅真实发票的 0~1.4%）。按品广告费一律读 `fact_ads_product_daily.ad_spend`。出处 `DATABASE_MAP.md:97`。

### 2.5 已知缺口与坑

- **a. `keyword_bid` 覆盖率 52.39% 的成因未定**：假设是"自动搜索词本无出价"，**尚未验证**（分组查询未跑）。
  另注 `syncManualAdKeywordDaily.ts` v2 有「五项指标全为 0 的行不写 FACT」规则 → **有出价但当天无曝光的关键词进不了 FACT**，
  RAW 里是全的。做出价盘点须从 RAW 回放，不能直接用 FACT。
- **b. `fact_ads_keyword_daily.keyword_bid` 这一列在 `sql/` 目录里没有任何建表或 ALTER 语句** —— 绕过编号 SQL 直接在生产加的，属流程外裸改，已在案。
- **c. SP 关键词状态字段 —— ✅ 2026-08-21 已验，可用**。`reportKeywordSpList` 返回 **66 个字段**（与 SV 同构），
  `keywordId` / `keywordState` / `keywordStatus` / `keywordBid` / `adGroupStatus` / `campaignStatus` 全部 200/200 有值。
  ⚠️ **两个 status 字段语义完全不同，别用错**：
    · **`keywordState`＝开关状态**，实测 `enabled=193 / paused=7` → **「关闭关键词」判定用它**
    · `keywordStatus`＝**审核状态**，实测 `approved=200` 全同值、无区分度 → 不可用于开关判定
  另注：该接口 `data.total=8613`（全量关键词，含无曝光的），而 `fact_ads_keyword_daily` 因「五项指标全为0不写FACT」只存有数据的行
  —— 这是 §2.5-a 覆盖率缺口的另一面。**这些状态字段每天都随接口返回，但 FACT 表无对应列，等于每天丢弃。**
  ⚠️ 该接口返回中**没有 `item_id` / `msku`**（66字段核对确认），广告变更若要落到商品维度，需经 `fact_ads_product_daily` 的 campaign→item 映射。
- **d. 划线价 / 促销价 / 促销类型：API 完全不下发。** 双重实证——
  官方文档响应字段表 43 条无此三项；生产 `raw_lingxing_walmart_listing` **54,151 行 `JSON_KEYS` 键数完全一致 = 35**，
  且 35 个键中无任何价格类补充字段。领星**前端页面有**这三列，属未开放到 openapi。
  （搜 `promo|msrp|clearance` 命中的 16 行经溯源为**同一商品标题**含 "Low Ground Clearance"，纯误伤。）
- **e. `dim_product.buy_box_price` 语义混淆**：同步取 `buy_box_price ?? price`，
  而 RAW 里 `buy_box_price="0.00"` 每天约 330~416 行（约 22%）。实测 DIM 内 `is_zero=0`、`min=4.99`，
  **0 未被写入**（代码侧此前推断"会写 0"，实测证否）；但该列值时而是 BuyBox 价、时而是挂牌价，**列名与语义不符**。
  **运营调价一律以 `price` 为准。**

### 2.6 竞价倍数（bid multiplier）—— ❌ API 不下发（2026-08-21 定论）

**背景**：领星**前端**有「竞价倍数」弹窗（Buy-Box / Search Ingrid / PC端 / App端 / 移动端，0~900%），
需求方截图确认 **CN2501-掌上便捷** 已配置 Buy-Box 10% / Search Ingrid 10%。

**实测**：

| 店铺 | advertiserId | 接口 | 行数 | `bid` 字段 |
|---|---|---|---|---|
| CN2601-瑞盈龙盛 | 571910 | `reportPlatformSpList` | 200 | ❌ 全空 0/200 |
| CN2501-掌上便捷（**前端已配置倍数**） | 497124 | `reportPlatformSpList` | 200 | ❌ 全空 0/200 |

**判定依据**：特意取了一家**前端可见、确已配置倍数**的店铺，`bid` 仍然全空
→ 已排除「本账号无数据」（§6-2 那个坑），坐实**接口不下发**。
这是第三例「前端有、openapi 不给」，前两例是划线价、促销价（§2.5-d）。

**业务推论（需求方 2026-08-21 口径）**：竞价倍数在**沃尔玛后台**改，领星连操作记录都不会有；在**领星**改，领星操作日志会有。
但操作日志这条路当天即被否决（§2.8）⇒ **竞价倍数变更目前无任何可用数据源，一期不做，转二期**。

### 2.7 否定关键词 —— ❌ 沃尔玛侧无接口（2026-08-21）

- `docs/lingxing/_sidebar.md` 中**所有**否定词接口都在 `docs/newAd/` 章节下（亚马逊体系，与沃尔玛根本没有的 SD 广告同章）→ 沃尔玛无对应接口。
- 自动广告 CSV `ItemKeywordPerformance_*.csv` 的 38 列中**无任何否定词列**（§4）。
- 领星**前端**有「否定关键词」页签（需求方截图确认）→ 又一例前端有、openapi 不给。
- ⇒ **「新增 / 移除否定关键词」这类人工动作既无法靠快照差分，操作日志接口也已否决（§2.8）⇒ 一期不做，转二期。**

### 2.8 操作日志类接口 —— ❌ 已否决，不再探测（2026-08-21 需求方判定）

`docs/lingxing/_sidebar.md` 中有 5 个操作日志接口。**需求方 2026-08-21 明确：这 5 个全部不是沃尔玛的，亚马逊广告日志完全没用，一律不查。**

| 文档路径 | 名称 | 判定 |
|---|---|---|
| `docs/Statistics/operateLogV2List` | 查询运营日志(新) | ❌ 非沃尔玛，不探 |
| `docs/Statistics/operateLogList` | 查询运营日志(旧) | ❌ 非沃尔玛，不探 |
| `docs/Sale/listingOperateLogPageList` | Listing 操作日志 | ❌ 非沃尔玛，不探 |
| `docs/Product/GetPagingLogLists` | 产品操作日志 | ❌ 非沃尔玛，不探 |
| `docs/newAd/apiLogStandard` | 亚马逊广告操作日志 | ❌ 亚马逊体系，完全无用 |

> **由此产生的最终定论（重要，一期方案的地基）**：
> **沃尔玛侧拿不到任何「谁改的」。** 领星 openapi 对沃尔玛只给**状态快照**，不给操作流水。
> ⇒ 系统运营日志**只能靠快照差分**产生，`operator` 一律为空/记为 `system_detected`，
> **人工是谁做的只能由运营在人工运营日志里自己写**（`biz_product_operation_log` 已有该能力）。
> ⇒ 早先设想的 `detect_source` 双源合并（`lingxing_log` / `snapshot_diff`）**作废，一期只有 `snapshot_diff` 一种来源**。
> ⇒ 快照差分**不是备选方案，是唯一方案**。因此快照的完整性与频率直接决定日志质量，不能省。

### 2.9 `price` 字段语义 —— 实测定性（2026-08-21 两轮只读探针）

样本：窗口 30 天 · 对照集 44906 行（快照日×店×item×msku）· 覆盖 1758 个 店×item×msku。
探针：`src/probePriceVsOrderAvg.ts`、`src/probePriceOscillationAndRepricing.ts`（均只读）。

| 实测项 | 数值 |
|---|---|
| 窗口内 price 从未变过的 item | 1296 / 1758 = **73.72%** |
| 变过价的 item | 462 = 26.28%，其中方向翻转≥3 次的「对倒型」**82 个（占变价 item 17.75%）** |
| 有订单可核的快照日 | **10.62%**（其余 89.38% 当天无单） |
| 有订单时 price 与成交均价吻合（偏离≤1%） | **87.42%** |
| **变价日前后都有订单的 440 条事件** | 成交均价**纹丝不动 85.68%** · 同向 8.41% · 反向 5.91% |
| 变价 item 的成交中位价位置 | **≈最低挂牌价 54.30%** · ≈最高挂牌价 21.77% · 落在两者之间 23.92% |
| 最高价/最低价 ≥3 倍的 item | 22 个（4.76%） |

**定性结论（三条，都是实测支撑，不是推断）**：
1. **`price` ≠ 实际成交价。** 变价日里 85.68% 的成交均价根本不动，且 54.30% 的变价 item 成交价长期锁死在窗口最低挂牌价
   ⇒ 实际售价由**促销价**决定，而促销价 openapi 不下发（§2.5-d）。**任何按售价计算的口径仍须用订单侧 `sales_amount / sales_qty`。**
2. **`price` 可以当「调价动作发生了」的信号用**，但必须配成交价交叉验证，否则会把大量「price 动而实际没动」记成调价。
3. **警惕「抬价代替下架」**：实测存在 13.99→53.99、18.99→65.99、29.99→80.99 而成交价不变的行。
   这类不是调价，是把价格抬到离谱值代替下架。**不得按调价处理。**

**需求方判据的落地量测**（判据：price 变更 且 当日成交价与新价一致 ⇒ 判定为调价；不一致 ⇒ 提醒人工写运营日志）：

| 分类 | 条数 | 占比 | 日均 |
|---|---|---|---|
| 判定为调价 | 428 | 37.38% | **14.3** |
| 异常·需提醒人工 | 124 | 10.83% | **4.1** |
| 无订单可核 | 593 | 51.79% | 19.8 |

放宽到「当日或次日一致」后判定为调价升至 502（日均 16.7）—— 差额 74 条即**美西日界 vs 北京快照日**错位的代价。

> ⚠️ **已知副作用（阈值副产品，实测样例）**：一致性阈值 1% 会把**变价幅度本身小于 1%** 的记成「调价一致」。
> 实测 JJ2032-1A 出现 `9.99 → 10.00`、`10.00 → 9.99` 的一分钱来回，成交价始终 9.99，却被判为调价。
> ⇒ 若不加「最小变价幅度」门槛，日志会被一分钱波动刷屏。

>
> **需求方 2026-08-21 决定：不加最小变价幅度门槛，全部照记。**
> 理由是宁可多记也不漏记；判定不对由运营在人工日志里修正，**系统不追加、不回改**。
> **此条已定，勿再提议加门槛。**

### 2.10 系统运营日志的覆盖边界（2026-08-22 一期定稿）

系统运营日志靠**快照差分**产生（§2.8 定论：沃尔玛侧拿不到操作人，快照差分是唯一方案）。
能不能记下某个运营动作，**完全取决于领星 openapi 给不给该对象的状态快照**。边界如下，**这是一期的能力上限，不是待办**。

**✅ 系统能自动记的**

| 动作 | 数据来源 |
|---|---|
| 售价调价 | `raw_lingxing_walmart_listing.price` 每日快照 + 订单级成交价核对（§2.9） |
| 关键词出价（BID） | `fact_ads_keyword_snapshot_daily.keyword_bid` |
| 活动预算 / 竞价策略 | `fact_ads_campaign_snapshot_daily`（`dailyBudget` / `biddingStrategy`） |
| 活动 · 广告组 · 关键词的增减与开关 | 三张快照表的实体存在性 + `keywordState` / `campaignStatus` |

**❌ 系统记不了、只能由运营在人工日志里写的**

| 动作 | 为什么记不了 |
|---|---|
| **SEM 的一切调整**（出价、预算、策略） | **领星对 SEM 根本没开放 API**。领星广告接口属 Walmart Connect 体系，不覆盖 SEM；两份 SEM CSV 无出价、无预算、无策略（§4）。**需求方 2026-08-22 明确：系统运营日志不需要管 SEM 的调整。** |
| 否定关键词的增删 | 沃尔玛侧无接口、CSV 无该列（§2.7） |
| 竞价倍数变更 | API 不下发，前端有、openapi 不给（§2.6） |
| 在**沃尔玛后台**直接做的任何改动 | 领星连操作记录都没有（§2.6 业务推论） |

> **这条边界正是「人工日志 > 系统日志」权重的真正理由**——不只是"人工可以纠错"，而是**有整整几类动作系统根本看不见，只有人工日志里才有**。
> 后来者勿把「SEM 没记录」「否定词没记录」当缺陷重查。

---

## 3. 飞书开放平台

**基址** `https://open.feishu.cn` ｜ **令牌** `/open-apis/auth/v3/tenant_access_token/internal`

| 路径 | 能力 | 用途 | 调用方 |
|---|---|---|---|
| `/open-apis/auth/v3/tenant_access_token/internal` | 读 | 换取租户令牌 | 全部飞书脚本 |
| `/open-apis/im/v1/messages` | **写** | 发群消息 / 私信 / 卡片 | `feishuNotify.ts` |
| `/open-apis/im/v1/images` | **写** | 上传卡片图片 | `feishuNotify.ts` |
| `/open-apis/im/v1/chats/` | 读 | 群信息 | `feishuNotify.ts` |
| `/open-apis/contact/v3/users/` `find_by_department` | 读 | 通讯录 → `dim_feishu_member` | `refreshFeishuMembers.ts` |
| `/open-apis/contact/v3/departments/` | 读 | 部门树 | `refreshFeishuMembers.ts` |
| `/open-apis/bot/v2/hook/…` | **写** | 机器人 webhook | `feishuNotify.ts` |

**其它飞书相关**：`syncFeishuAttendance.ts`（考勤）、`feishuSheetWriter.ts`（表格写入）、
`feishuMeetingReader.ts`（会议）、`feishuCardCallbackRoutes.ts`（卡片回调入站）、
`syncLingxingToRawFeishu.ts`（领星→RAW 虚拟 sheet 镜像）。

> **⚠️ 上线纪律（`CODE_DEPLOY_SOP` 已固化）**：一切新增或改动的飞书通报，
> 上线前必须先 `--test-send` 发测试群、由需求方确认后才允许真实发送。
> **本渠道是唯一有写能力的对外通道，改动一律按高风险处理。**

---

## 4. Walmart 报表（CSV 人工导出通道）

领星 API 不覆盖的口径靠运营从沃尔玛后台导出 CSV，再由系统解析入库。

| 报表 | 关键列 | 入库模块 | 结论 |
|---|---|---|---|
| `ItemKeywordPerformance_*.csv`（自动广告） | 38 列。含 `Current Bidding Strategy` / `Current Target ROAS` / `Bidded Keyword` / `Searched Keyword` / `Match Type` | `walmart_ads` | ⚠️ **策略三列每天进来但被整列丢弃**（代码库内这三个字符串一次未出现，`fact_ads_keyword_daily` 也无对应列）。实测样本 292 行：策略全 `Fixed`、Target ROAS 全空 → **当前信息量为零**，优先级低于 §2.2 的 API。**无任何 budget 列** |
| SEM 日绩效 `CAMPAIGN_LEVEL_DAILY_REPORT` | `Date/Campaign Name/Campaign ID/Impressions/Clicks/Spend/Sales` | `walmart_sem` | 必需列不含出价/预算/策略 |
| SEM 账单历史 `BILLING_HISTORY_DETAILED_REPORT` | `Invoice ID/Invoice Date/Billing From/Billing To/Charge Type/…` | `walmart_sem` | 同上 |
| Walmart Connect 发票 PDF | 发票级扣款方式/Credit 抵扣 | `walmart_connect_invoice` | ✅ 已接入 |

> **SEM 结论（2026-08-21 定稿）**：领星广告接口属 Walmart Connect 体系，**不覆盖 SEM**；
> SEM 两份 CSV 无出价、无预算、无竞价策略。**SEM 侧目前没有更多数据可取**，不再追。

---

## 5. 系统内部只读 API

系统自身对外提供的只读接口（供 GPT / 外部只读消费），文档见 `docs/internal_api_readonly.md`
与 `交付件/internal_readonly_api_接口文档_20260727.md`，实现于 `src/internalReadonlyApi.ts`。
本台账只记"我们调别人"，故此处仅留指针。

---

## 6. 本台账建立前踩过的坑（写在这里，防止重犯）

1. **把"查询报错"当成"接口不提供"**：2026-08-20 用 `page_key LIKE 'ads-%'` 找帮助文，
   该语句被终端吃掉百分号报 **1064 语法错**，却被当作"查无此项"，导致给同一入口造出两篇重复文章。
   → **任何返回错误码的查询一律不得用于支撑结论。**
2. **把"本账号无数据"当成"接口不可用"**：2026-08-21 首轮探 SB/SV 用了没有 SB/SV 活动的店铺（CN2502），
   四次调用 `code=0` 但 `total=0`，差点判成"接口不覆盖"。换 CN2601 后 SV 立刻返回 13 行 + 119 关键词。
   → **`total=0` 必须先排除样本问题再下结论。**
3. **把"文档有"当成"实测有值"**：`appliedTemplate`/`benchmarkVal`/`totalBudget` 文档都在，实测全空。
   → 探针一律带"定向判定：文档有 ≠ 实测有值"。
4. **接口结论散落导致重复劳动**：本文件即为此而建。
5. **把「从文件名推断的路径」当成「文档确认的路径」**：2026-08-21 探广告组 / 竞价倍数时，9 个探测目标里有 7 个路径
   是照 `docs/lingxing/_sidebar.md` 的**文件名拼**出来的。结果 `queryAdGroupSvList` 报「参数有误」、`reportPageTypeSvList` 直接 404。
   → **路径未经 apidoc 正文确认的，结论只能写「路径未证实」，不得写「接口不可用」。**

6. **把「日志文件 0 字节」当成「任务从没跑过」**：2026-08-22 见 `logs/ads_config_snapshot.log` 为 0 字节，
   据此断言「广告配置快照一次都没跑」。实测快照表里有 campaign 3205 / group 4007 / keyword 33553 行完整数据
   —— 是手动执行时输出未进该日志文件。**日志为空只说明「这个文件没被写过」，不能推出「任务没执行过」，
   判断任务是否跑过一律查目标表的行数与 `created_at`。**
7. **从脚本文件名推断数据源**：由 `/opt/ads-ai-api/scripts/build_fact_profit_daily_from_raw_feishu.py` 的文件名
   推断出「飞书源数据滞后」，而本系统早已与飞书**无任何数据对接**，该名称属历史遗留。
   → **文件名、表名、变量名都不是证据，结论只能来自代码正文或实测数据。**

---

## 7. 待办

- [x] §2.5-c SP 关键词接口的 `keywordState`/`keywordStatus` 验证 —— **2026-08-21 已完成，可用**
- [x] §2.2 `queryGroupSpList` 广告组接口 —— **2026-08-21 已验，可用**（1071 / 392 组）
- [x] §2.6 竞价倍数能否取到 —— **2026-08-21 已定论：不可取**
- [x] §2.7 否定关键词能否取到 —— **2026-08-21 已定论：沃尔玛侧无接口**
- [x] §2.8 五个操作日志接口 —— **2026-08-21 需求方否决：全部非沃尔玛，不探测**
- [ ] `queryPageTypeSPList` 换参数能否拿到广告位维度（当前返回无维度字段）
- [ ] SV 广告组 / 页面类型的**正确路径**（现推断路径均报错，需 apidoc）
- [x] 售价与订单均价一致性（conflict 率）—— **2026-08-21 已完成两轮**，结论见 §2.9
      （探针 `probePriceVsOrderAvg.ts` / `probePriceOscillationAndRepricing.ts`，均已在生产执行）
- [ ] **saleStat 与折扣RAW 的日级归因错配**（2026-08-21 新立，需求方定「另开一轮」）：
      实测 saleStat 会漏收部分送样单（差额永远是整数件整价 ⇒ 整单没被统计）。
      危险的是**反方向看不见**：若送样被 saleStat 算在 D 日、折扣RAW 归在 D±1 日，
      则 D 日有送样未被剔除 → 销售额虚高 + 成本多扣 + 利润低估，**页面零痕迹**。
      下一轮三步：① dump `raw_mp_order_discount.row_json` 看有无 `global_purchase_time` 之外的时间字段
      ② 无则拿 2026-08-17 那 6 个订单号调订单接口取全字段 ③ 同轮量化反方向规模
      （逐日偏差绝对值之和 vs 整窗口偏差）。**未量化出规模前不动 saleStat**（P7 三表恒等基准）。

### 7.1 二期范围（2026-08-21 需求方划定，一期不做、也暂不探测）

| 事项 | 归口 | 备注 |
|---|---|---|
| 否定关键词动作 | 广告 | §2.7：无接口、CSV 无列，一期无解 |
| 竞价倍数变更 | 广告 | §2.6：API 不下发，一期无解 |
| **断货**（库存卖到 0 即断货） | 库存 | 判定口径待定 |
| **采购单** | 供应链 | — |
| **本地仓（惠州仓）到货** | 供应链 | — |
| **创建货件 / 发货** | 供应链 | — |
| **沃尔玛接收货件 / 货件接收结束** | 供应链 | — |

> **需求方 2026-08-21 原话**：「其余的先不要探测」。上表各项在二期启动前**不得发起接口探测**。
- [ ] §2.5-a `keyword_bid` 52.39% 缺口的成因分组验证
- [ ] §2.2 三个可用接口的接入方案（快照表 + 差分 → 运营日志）
- [ ] 划线价/促销价：**已搁置**（需求方 2026-08-21 决定）。若日后重启，路径为 领星前端导出 CSV 或 提工单请领星开放
- [ ] `docs/lingxing-api.json` 是坏文件（非合法 JSON，字节数与 `docs_sidebar.md` 完全相同，疑为误存重复），待清理
- [ ] `sql/009` 定义的 `fact_ads_platform_daily` 在生产从未建表，需求方决定是建还是废
- [ ] **`fact_ads_product_daily` 每日 17:30 前后那波补写的写入方未确认**（2026-08-22 新立）：
      `syncSbSvAdsDaily` 16:40:52 即结束，时间对不上；需定位是哪个任务在 17:30 继续插入新行。
- [ ] **`YC00012-1A`（CN2601 / item 19992364838）归档状态存疑**（2026-08-22 新立）：
      `dim_product.product_management_status = archived`，但库存 4 件、2026-08-21 当天售出 6 件、运营仍在调价。
      疑为主数据状态标错，需核实后决定是改状态还是改判定口径。

## 2026-08-25 / reportAdItemSvList 的两行结构定案（探测回写，长期有效）

- **定案**：SV 商品级报表对每个实际投放中的 video campaign 固定回传两类行：商品行（itemId/adItemId/itemPageUrl/adName 齐全，出订单）+ **素材行**（itemId='1001' 占位、adItemId 等全 null、adName/adStatus='--'，有曝光/点击/花费）。两行同 adGroupId，自 campaign 首个实际投放日同日出现（probe6 实证投放前全零）。依需求方业务事实：开视频广告=加商品+加素材，素材侧数据无 itemId 可挂。非故障，勿当异常重查。
- 判读纪律：①短数字 itemId 勿关联 dim_product，素材行花费按 adGroupName 前缀归属该组商品；②min/max 日期区间会把「并存」伪装成「切换」，判切换必须日级检查（探测1误读实证）；③RAW 证据只覆盖领星响应边界，'1001' 由哪侧生成未定亦无需定（口径细节），要官方语义走领星口径咨询（非归责）。
- 结构备忘（probe3~6 趟平，复用勿重探）：reportAdItemSvList 信封 $.list[*]、键驼峰、RAW 自 2026-05-01 留存；walmart/list 信封 $.data[*]、键蛇形（item_id/status_name）、RAW 自 2026-04-01 每日一帧；JSON_TABLE 对 CTE 派生列须 CAST(... AS JSON)；raw_lingxing_api 无 store 列，walmart/list 行内带 store_id/store_name（CN2601=110687423514268160）；同一 walmart item_id 可跨店挂多 msku。
- raw_lingxing_walmart_listing 仅 2026-07-16 起有快照；更早 listing 状态历史用 raw_lingxing_api 的 walmart/list 路径（04-01 起）。
