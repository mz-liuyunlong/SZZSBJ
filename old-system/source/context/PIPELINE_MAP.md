# PIPELINE_MAP

最后核对：2026-07-31  
核对来源：生产 `crontab -l` 全量只读采集（2026-07-31，见文末 Active cron snapshot 节）、`/opt/lingxing-auto` 源码、systemd 服务清单。  
范围：只记录数据管道、通知任务、日志和断点确认；不记录任何密钥值。

## 总览

当前生产 crontab 共 49 条 active 任务（2026-07-31 快照；另有 daily-operation-log-base、sync:feishu-item-owner 停用注释保留；gptKwOwnerSummary 为 7-28 一次性任务已过期未清）。按时间链分为：
- 主数据链：成员(02:30)/应用账号开户(02:35 sync-app-users,2026-08-04挂)/店铺(03:00)/领星日数据链(16:45 backfillDailyChain deadline=19:10)/广告词(18:10)/产品成本(19:00)/利润ETL(19:30)/挂链渠道订单(07:35)/采购单(07:40)/本地库存(07:45)/WFS发货(08:20)/Listing价格(05:20)。
- DIM/FACT 构建链（晚间）：derive-launch-date(20:15)→product-business-state(20:30)→arrival-events(20:40)→operation-log-base(20:50)→product-rule-signals(20:55)；order-drop 检测 16:25/20:00。
- 通知报表链：不出单(09:00)/清负责人(09:00)/缺负责人(09:10 周1,4)/月度规划催办(09:20)/月度规划未填扣分(09:25·8号起)/运营不动作(09:30)/清货审批(09:33)/清货无目标特批(09:35·8号起)/归档到货卡(09:40)/低毛利(09:45 周1,4)/数据哨兵主检(20:15)+整点提醒(9-23点)+周报(周一9点)/清货复活卡(08:50)/归档卡(10:05)/清尾卡(10:16 周5)/绩效日报(10:00)/周报(周一17:00)/月报(3日16:00)/到货通报(14:00)/订单下滑(16:50)/自动广告导入检查(17:25)/CS测品(17:16 检测·18:03 通报 工作日)。
- 周报确认链：周四16:00确认卡→周四/周五19:30排队检查→每30分钟提醒(周4,5)；月报生成链：4日06:00生成→09:00推送（2026-08 M8：原03:00改06:00）。
- 考勤链（2026-07-30/31 上线）：00:45 sync:attendance --daily；09:50 缺卡通报 --push --send；21:50 缺卡重发 --remind --send。
- AI 周评：周四 23:00 aiOpsLogReview --confirm-write（LLM 出口=.env AI_*，2026-07-31 起 openlux）。
- 月度结算：25日 04:40 WFS配送费结算回填、05:10 月利润刷新。
- 按需手动任务：`syncProductNameFromLingxing.ts` 用于从领星本地产品详情回填 `dim_product.product_name`，当前无 cron。

主链依赖图：

`02:30 refreshFeishuMembers -> 03:00 syncWalmartStores -> 09:00 clearDepartedOwners -> 09:10 unmatchedOwnerNotify -> 16:45 backfillDailyChain(方案B：FACT/每日销售明细RAW/订单利润RAW三层T-6~T-2回溯) -> 18:10 手动广告词 -> 19:00 产品成本 -> 19:30 利润ETL -> 20:15 launch_date推导 -> 20:30 状态表计算 -> 20:50 operation-log-base(MySQL) -> 20:55 product-rule-signals`

风险红线：任何新任务插入时间链时，必须先核对上游数据就绪时间、数据日期口径、写入表粒度和是否会覆盖人工维护字段。

按需任务补充（2026-07-08）：`npm run sync:product-name -- --confirm-write` 已执行一次 Task D 回填。该任务必须按“领星 API -> raw_lingxing_api -> dim_product”顺序执行；写库前生成 rollback CSV；只写 `dim_product.product_name`，本轮不写 `sku`。baseSku 模式抽验 `605/919=65.83%`，低于 95% 阈值，baseSku 只允许用于 product_name 查询命中，不允许补 `sku`。该任务不在当前 crontab 中。

按需任务补充（2026-07-08 Task H-1E）：`npm run build:product-rule-signals -- --dry-run|--confirm-write` 已上线。2026-07-09 复核生产 crontab 后确认该任务已接入 `20:55`：`55 20 * * * cd /opt/lingxing-auto && npm run build:product-rule-signals -- --confirm-write >> /opt/lingxing-auto/logs/product-rule-signals.log 2>&1 # db-only-product-rule-signals`。默认 `signal_date=dim_product_business_state.MAX(stat_date)`，依赖最新状态表与广告 FACT，不得插到 20:30 前；当前顺序固定在 `20:50 build:operation-log-base` 之后。

## 当前 crontab 全量任务

| 时间 | 任务名 | 脚本路径 | 输入 | 输出 | 上游依赖 | 数据日期口径 | 日志路径 |
|---|---|---|---|---|---|---|---|
| 02:30 | refreshFeishuMembers | `/opt/lingxing-auto/src/refreshFeishuMembers.ts --write` | 飞书通讯录 API | `dim_feishu_member`，并支撑负责人花名册与 `update-owner` 资格校验 | 无硬依赖，建议早于通知类任务 | 当前成员快照 | `/opt/lingxing-auto/logs/refresh-feishu-members.log` |
| 03:00 | syncWalmartStores | `/opt/lingxing-auto/src/syncWalmartStores.ts` | 领星店铺/授权店铺接口 | `dim_store` / 店铺相关配置 | 无硬依赖，需早于后续按店铺同步任务 | 当前店铺快照 | `/opt/lingxing-auto/logs/sync-walmart-stores.log` |
| 08:00 周一/周四 | lowProfitNotify | `/opt/lingxing-auto/src/lowProfitNotify.ts --send` | `raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')` | 飞书低毛利通报 | 依赖前一轮订单利润快照 | 近 7 天聚合，受订单利润 T-2 影响 | `/opt/lingxing-auto/logs/low-profit-notify.log` |
| 09:00 | noOrderNotify | `/opt/lingxing-auto/src/noOrderNotify.ts --send` | 领星商品/销量 API、`dim_product.owner` | 飞书不出单产品通报、操作日志 | 建议在 02:30 成员刷新后 | 当前/近段商品销量，具体由脚本实时拉取 | `/opt/lingxing-auto/logs/no-order-notify.log` |
| 09:30 | sync:feishu-item-owner | `/opt/lingxing-auto/src/syncFeishuItemOwnerToMysql.ts --confirm-write` | 飞书 `<REDACTED_FEISHU_SHEET_ID>` ItemID负责人表 | `raw_feishu_table`；RAW-only，不写结构化表 | 已停用（2026-07-07）；不再作为有效上游依赖 | 已废弃 | `/opt/lingxing-auto/logs/sync-item-owner-mysql.log` |
| 09:00 | clearDepartedOwners | `/opt/lingxing-auto/src/clearDepartedOwners.ts --execute` | `dim_feishu_member`、`dim_product`、`dim_product_owner` | 清空满 7 天离职负责人商品；写入 `event_product_owner_clear` 审计表 | 必须在 02:30 花名册同步之后；人工已改派商品应在事务内跳过 | 当前成员/商品快照 | `/opt/lingxing-auto/logs/clear-departed-owners.log` |
| 09:10 | unmatchedOwnerNotify | `/opt/lingxing-auto/src/unmatchedOwnerNotify.ts --send` | `dim_product.owner`、产品管理状态、`dim_feishu_member`、`dim_product_owner` | 飞书三段通报（缺负责人 / 离职待移交 / 负责人冲突） | 依赖 02:30 花名册同步与 09:00 清空任务；不依赖 09:30 RAW-only 写入 | 当前 MySQL 主数据快照 | `/opt/lingxing-auto/logs/unmatched-owner-notify.log` |
| 10:00 | report:performance daily | `/opt/lingxing-auto/src/performanceSummaryReport.ts --mode=daily` | `raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')` | 飞书经营日报、操作日志 | 依赖前一晚 18:30 订单利润快照 | 日报取已落库订单利润日期，受 T-2 影响 | `/opt/lingxing-auto/logs/performance-daily.log` |
| 16:00 每月3日 | report:performance monthly | `/opt/lingxing-auto/src/performanceSummaryReport.ts --mode=monthly` | `raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')` | 飞书经营月报、操作日志 | 依赖订单利润历史覆盖完整 | 上月/月度聚合，受订单利润 T-2 影响 | `/opt/lingxing-auto/logs/performance-monthly.log` |
| 16:10 | checkAutoAdSearchTermImport | `/opt/lingxing-auto/src/checkAutoAdSearchTermImport.ts --send` | 自动广告搜索词导入状态/相关广告表 | 飞书导入检查通知 | 应在当天导入窗口后执行 | 当天导入状态 | `/opt/lingxing-auto/logs/check-auto-ad-import.log` |
| 16:45 | backfillDailyChain（方案B） | `/opt/lingxing-auto/src/backfillDailyChain.ts --execute --deadline=19:10` | 领星商品/销售/库存/广告 API、店铺配置、已入库 FACT | `fact_sales_daily`、`fact_inventory_daily`、`fact_ads_product_daily`、`raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')`、`raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')` | 依赖 03:00 店铺发现/配置；三阶段串行，单实例锁保护 | 每日自动回溯 `T-6 ~ T-2` 五天；FACT -> 每日销售明细 RAW -> 订单利润 RAW | `/opt/lingxing-auto/logs/backfill-daily-chain.log`，每次输出 `SUMMARY_JSON` |
| 17:00 周一 | report:performance weekly | `/opt/lingxing-auto/src/performanceSummaryReport.ts --mode=weekly` | `raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')` | 飞书经营周报、操作日志 | 依赖订单利润历史覆盖完整 | 上周/近周聚合，受订单利润 T-2 影响 | `/opt/lingxing-auto/logs/performance-weekly.log` |
| 18:10 | syncManualAdKeywordDaily | `/opt/lingxing-auto/src/syncManualAdKeywordDaily.ts` | 领星/手动广告关键词链路 | `fact_ads_keyword_daily(source_type='manual_kw')` | 依赖 16:45 日数据完成更稳 | 通常同步目标日广告词，需以脚本实参/默认口径为准 | `/opt/lingxing-auto/logs/manual-ad-keyword-daily.log` |
| 18:30 | sync:order-profit-daily（已并入16:45） | 原 `/opt/lingxing-auto/src/syncOrderProfitDaily.ts --date T-2` cron 已于 2026-07-12 停用 | 已并入 16:45 `backfillDailyChain` 订单利润 RAW 阶段 | `raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')` | 2026-07-12 起并入 16:45 单链；不得再单独恢复旧 18:30 cron，除非重新评估 | 历史 T-2 单日，现为 16:45 `T-6~T-2` | 历史日志 `/opt/lingxing-auto/logs/order-profit-daily.log`，现看 `/opt/lingxing-auto/logs/backfill-daily-chain.log` |
| 19:00 | sync:product-cost | `/opt/lingxing-auto/src/syncLingxingProductCost.ts --confirm-write --date=T-2` | 领星产品成本接口 | `dim_product_cost_config` | 建议在 16:45 后；当前晚于 18:30 订单利润，可能影响次日订单利润使用最新成本 | `DATA_DATE = today - 2 days`，T-2 | `/opt/lingxing-auto/logs/product-cost-mysql.log` |
| 19:30 | profit ETL | `/opt/ads-ai-api/scripts/build_fact_profit_daily_from_raw_feishu.py --execute` | `raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')` | `fact_profit_daily` | 必须在 18:30 订单利润后 | `start=today-4 days` 到 `end=yesterday`，实际受 RAW T-2 就绪影响 | `/opt/ads-ai-api/scripts/profit_etl.log` |
| 20:15 | derive:launch-date | `/opt/lingxing-auto/src/deriveLaunchDate.ts --confirm-write` | `dim_product`、`fact_ads_product_daily`、`fact_inventory_daily` | `dim_product.launch_date` 补空值、`reports/derive_launch_date_YYYYMMDD*.csv` 审计白名单 | 依赖 16:45 库存事实、18:10/广告事实已就绪；必须早于 20:30 状态表 | 当前全量空值扫描，只写 NULL 补值 | `/opt/lingxing-auto/logs/derive-launch-date.log` |
| 20:30 | build:product-business-state | `/opt/lingxing-auto/src/buildProductBusinessState.ts --confirm-write` | `dim_product`,`fact_profit_daily`,`fact_sales_daily`,`fact_inventory_daily`,`fact_ads_product_daily` | `dim_product_business_state` | 必须在 19:30 利润 ETL 后；14 天窗口与 15% 广告占比线已于 2026-07-09 合并部署 | 默认取最新可用业务日 `stat_date=2026-07-06` | `/opt/lingxing-auto/logs/product-business-state.log` |
| 20:50 | build:operation-log-base | `/opt/lingxing-auto/src/buildOperationDailyLogBase.ts --confirm-write` | `dim_product`、`fact_inventory_daily`、`dim_store`、`dim_product_business_state`、`biz_product_operation_log` | `biz_product_operation_log` 当日基础行，仅刷新 `source='system_base' AND is_locked=0` | 必须在 20:30 状态表后；依赖最新状态快照不超过 3 天 | 默认取 `dim_product_business_state.MAX(stat_date)`，显式 `--date` 不得晚于最新状态快照 | `/opt/lingxing-auto/logs/operation-log-base.log` |
| 20:55 | build:product-rule-signals | `/opt/lingxing-auto/src/buildProductRuleSignalsDaily.ts --confirm-write` | `dim_product_business_state`、`fact_ads_product_daily`、`fact_sales_daily` | `biz_product_rule_signal_daily` 当日系统规则信号 | 必须在 20:30 状态表后；当前排在 20:50 运营日志基础行之后 | 默认取 `dim_product_business_state.MAX(stat_date)`；广告窗口固定近 3 天，常规经营指标窗口固定近 14 天 | `/opt/lingxing-auto/logs/product-rule-signals.log` |
| 23:00 周四 | ai:ops-log-review | `/opt/lingxing-auto/src/aiOpsLogReview.ts --confirm-write` | `biz_product_operation_log`（实质日志）、`biz_product_rule_signal_daily`、`dim_feishu_member` | AI 运营日志周评 → `ai_ops_log_review_item`/`ai_ops_log_review_summary`（仅页面展示，V1 不扣分） | 依赖 20:50 运营日志基础行 / 20:55 规则信号当日已构建 | 周期=上周五~本周四（window_end=最近周四，week_start=终点−6）；确定性抽样20个ItemID | `/opt/lingxing-auto/logs/ai_ops_log_review.log` |

## 主链任务说明

### 02:30 refreshFeishuMembers

目的：同步公司通讯录花名册到 `dim_feishu_member`。  
关键护栏：公司通讯录是唯一来源；在册=`active`，不在册=`left`；无姓名硬安全阀必须通过才允许写入；旧固定群只允许做诊断，不得做在职判断。

### 09:00 clearDepartedOwners

目的：对“已离职且无同名 active，且 `left_detected_at` 满 7 天”的负责人执行第 8 天自动清空。  
输入：`dim_feishu_member`、`dim_product`、`dim_product_owner`。  
输出：清空 `dim_product.owner`、停用对应 `dim_product_owner active` 行，并写 `event_product_owner_clear` 审计表。  
关键护栏：事务内 `SELECT ... FOR UPDATE`；`locked.length` / `affectedRows=1` 严格检查；审计后置；人工已改派商品必须跳过；跨表姓名比较必须显式 `COLLATE utf8mb4_unicode_ci`。

### 09:10 unmatchedOwnerNotify

目的：生成产品管理三段通报：缺负责人、离职负责人待移交、负责人冲突。  
关键口径：离职待移交段与 `clearDepartedOwners` 共用“无同名 active + MAX(left_detected_at)”判定，只是时间窗为 1~7 天；跨表姓名 JOIN 必须显式 `COLLATE utf8mb4_unicode_ci`，否则会触发排序规则冲突。

目的：刷新飞书人员 open_id/成员信息，支撑负责人通知和 @ 人链路。  
风险：通知类任务如果早于成员刷新，可能使用旧成员映射。

### 03:00 syncWalmartStores

目的：同步店铺维度/授权店铺信息。  
风险：后续领星日数据、广告数据、商品主数据均依赖店铺配置准确性。

### 09:30 负责人同步 RAW-only（已停用）

目的（停用前）：把飞书 `<REDACTED_FEISHU_SHEET_ID>` 作为历史镜像写入 `raw_feishu_table`。  
当前状态：已停用（2026-07-07）；V1.2 起脚本本身已硬锁 RAW-only，不写 `dim_product`、`dim_product_owner`、`dim_product_cost_config`、`dim_product_identity`、`dim_owner`。  
原因：产品管理 Tab 已成为负责人、WFS 配送费、产品状态的主维护入口，旧飞书结构化同步会覆盖运营在页面维护的数据。  
停用原因补充：最新批次 `raw_feishu_table.sheet_id='<REDACTED_FEISHU_SHEET_ID>'` 已出现表头退化（`col_N`），继续运行只会持续写入废弃且不可用的垃圾 RAW 数据；该退役链路不再修复。  
变更时间线：2026-07-06 09:30 旧 cron 执行时报 `Unknown column 'source_raw_id' in 'field list'`；2026-07-07 02:01 左右生产文件改为 RAW-only；2026-07-07 晚间曾短暂恢复 09:30 cron；同日按飞书链路退役口径再次停用并保留注释。

### 16:45 领星日数据

目的：拉取 T-2 的销售、库存、商品、广告商品事实，并生成 RAW viewer 快照。  
输出是 18:30 订单利润、状态表、报表的关键上游。
2026-07-08 补充：`syncLingxingToRawFeishu.ts` 生成每日销售明细 `<REDACTED_FEISHU_SHEET_ID>` 时，MSKU fallback 已使用 `NULLIF(...,'')` 跳过空字符串，避免 `fact_ads_product_daily.msku` 空值截断 `fact_inventory_daily/dim_product` 的 MSKU。当天已幂等重跑 `2026-06-29` 至 `2026-07-05` 的 `<REDACTED_FEISHU_SHEET_ID>` 明细 RAW：各日写入 784/793/809/808/811/805/807 行；重跑后 7 日共 5617 行，MSKU 空 308 行、owner 空 1225 行，剩余为空的多为上游/维表无法解析，接口展示层继续按唯一命中规则补齐。

### 18:10 手动广告词

目的：同步手动广告关键词事实到 `fact_ads_keyword_daily`。  
注意：自动广告 CSV 另有导入检查任务，关键词 FACT 中 `source_type` 用于区分来源。

### 18:30 订单利润

目的：从 DIM/FACT 聚合订单利润 Beta RAW 快照。  
关键口径：毛利润 = 销售额 - 广告费 - WFS 配送费*销量 - 平台佣金 - (采购成本+头程成本)*销量/汇率。  
Task H-1D 起，订单利润 Beta 默认排除 `dim_product.product_management_status='archived'`，`product_management_status=all` 放开 archived 作为内部排查视图；无法匹配产品状态的聚合行默认保留。
风险：它当前早于 19:00 产品成本同步，若当天成本变化必须确认是否会影响当日订单利润口径。

### 19:00 产品成本

目的：同步采购成本、头程成本等成本配置到 `dim_product_cost_config`。  
风险：成本写入晚于订单利润，插入新任务或调整时间时必须核对订单利润是否需要最新成本。

### 19:30 利润 ETL

目的：把 `raw_feishu_table(order_profit_daily)` 回填到 `fact_profit_daily`。  
关键口径：运营端毛利；`net_profit` 默认 0，非财务净利。

### 20:15 launch_date 推导（已上线）

生产任务：`cd /opt/lingxing-auto && npm run derive:launch-date -- --confirm-write >> /opt/lingxing-auto/logs/derive-launch-date.log 2>&1`  
输入：`dim_product`、`fact_ads_product_daily`、`fact_inventory_daily`。  
输出：仅补空 `dim_product.launch_date`，并导出 `reports/derive_launch_date_YYYYMMDD*.csv` 审计白名单。  
口径：只处理 `platform='walmart' AND launch_date IS NULL`；CS 测品取广告商品事实中 `ad_spend > 0` 的最早 `stat_date`，按 `platform + store_id + item_id` 关联，不带 `msku`；非 CS 常规产品取库存事实中同商品 `wfs_available_stock > 0` 的最早 `snapshot_date`，按 `platform + store_id + item_id + msku` 关联。推导不出的继续保持 NULL，不做兜底。  
依赖：16:45 领星库存事实和广告事实已落库，18:10 广告链路已完成；必须早于 20:30 状态表，使当天新增 `launch_date` 当天参与生命周期判定。  
上线状态：2026-07-07 已加入生产 crontab；首次手动 `--confirm-write` 候选 0、实际写入 0，生成空白名单 CSV，当前 39 个 NULL 产品均无首广花费或 WFS 正库存来源。

### 20:30 状态表计算（已上线）

生产任务：`cd /opt/lingxing-auto && npm run build:product-business-state -- --confirm-write >> /opt/lingxing-auto/logs/product-business-state.log 2>&1`  
输入：`dim_product`、`fact_profit_daily`、`fact_sales_daily`、`fact_inventory_daily`、`fact_ads_product_daily`。  
输出：`dim_product_business_state`。  
依赖：必须在 19:30 利润 ETL 后。  
生命周期口径：系统推导值写入 `system_lifecycle_stage`；最终 `lifecycle_stage` 读取 `dim_product.manual_lifecycle_stage`，trim 后非空时人工值优先，否则使用系统建议。该任务只读人工生命周期字段，不写回 `dim_product.manual_lifecycle_*`；人工确认只影响重算后的状态快照，不回改历史快照。
archived 口径：Task H-1D 起源查询排除 `product_management_status='archived'`，后续不再生成 archived 快照；已清理最新 `stat_date=2026-07-06` 的 archived 快照，历史快照保留。
2026-07-09 合并部署补充：常规产品统计窗口已统一为近 14 天（字段名 `*_30d` 保留历史命名），`ad_status='广告占比偏高'` 阈值从 18% 调整为 15%。本次手动重跑后，`MAX(stat_date)=2026-07-06`，最新快照仍 1127 行，利润等级分布变为 `空=853/A=69/B=38/C=49/D=118`。
上线状态：2026-07-07 已加入生产 crontab；Task H-1D 后 `MAX(stat_date)=2026-07-06`，最新快照 1127 行，archived=0。

### 20:50 operation-log-base（MySQL 链路）

生产任务：`cd /opt/lingxing-auto && npm run build:operation-log-base -- --confirm-write >> /opt/lingxing-auto/logs/operation-log-base.log 2>&1`  
输入：`dim_product`、`fact_inventory_daily`、`dim_store`、`dim_product_business_state`、`biz_product_operation_log`。  
输出：`biz_product_operation_log` 每日基础行。  
保护：默认 log_date 取 `dim_product_business_state.MAX(stat_date)`；显式 `--date` 晚于最新状态快照直接失败；最新状态快照早于中国今天-3天时 confirm-write 默认熔断，dry-run 仅告警，`--allow-stale` 可显式绕过。写入只新增或刷新 `source='system_base' AND is_locked=0` 的基础字段，不更新 `data_issue/solution/log_content/ai_diagnosis`，不覆盖 `source='feishu_migration'` 或锁定行。  
上线状态：2026-07-08 Task H-1C 已切到 MySQL 链路；旧 `sync:daily-operation-log-base` 飞书链路 crontab 已注释保留，`runDailyAutomation.ts` 也不再触发该旧步骤。

### 20:55 product-rule-signals（已上线）

生产任务：`cd /opt/lingxing-auto && npm run build:product-rule-signals -- --confirm-write >> /opt/lingxing-auto/logs/product-rule-signals.log 2>&1`  
输入：`dim_product_business_state`、`fact_ads_product_daily`、`fact_sales_daily`。  
输出：`biz_product_rule_signal_daily`。  
依赖：必须在 20:30 状态表后；当前 crontab 排在 `20:50 build:operation-log-base` 之后。  
口径补充：广告窗口仍为近 3 天（如 `2026-07-04~2026-07-06`），但常规产品经营指标窗口已于 2026-07-09 合并部署统一为近 14 天；常规产品 `trigger_reason` 统一带 `【近14天】` 前缀，B级广告占比信号阈值为 15%。  
上线状态：2026-07-09 复核生产 crontab 确认 20:55 正式行存在；本次手动重跑后 `signal_date=2026-07-06` 总信号数 395，`REGULAR_B_AD_RATIO_HIGH=10`。  

## 通知类任务

| 任务 | 时间 | 读取 | 发送/输出 | 风险 |
|---|---|---|---|---|
| noOrderNotify | 09:00 每天 | 领星商品/销量 API、`dim_product.owner` | 飞书不出单产品通报 | 负责人来自 `dim_product.owner`，不再依赖飞书 `<REDACTED_FEISHU_SHEET_ID>` |
| clearDepartedOwners | 09:00 每天 | `dim_feishu_member`、`dim_product`、`dim_product_owner` | 离职满 7 天负责人自动清空 + 审计 | 只处理无同名 active 且满 7 天离职者；人工改派后跳过 |
| unmatchedOwnerNotify | 09:10 每天 | `dim_product.owner`、`product_management_status`、`dim_feishu_member`、`dim_product_owner` | 飞书三段通报 | 缺负责人只检查 active 产品；离职待移交按产品记录生成；归档不参与 |
| lowProfitNotify | 08:00 周一/周四 | `raw_feishu_table(order_profit_daily)` | 飞书低毛利通报 | 受订单利润 T-2 和 RAW 快照完整性影响 |
| performance daily | 10:00 每天 | `raw_feishu_table(order_profit_daily)` | 飞书经营日报 | 已从飞书活表迁移到 MySQL，口径与旧飞书活表可能有小差异 |
| performance weekly | 17:00 周一 | `raw_feishu_table(order_profit_daily)` | 飞书经营周报 | 依赖订单利润历史覆盖 |
| performance monthly | 16:00 每月 3 日 | `raw_feishu_table(order_profit_daily)` | 飞书经营月报 | 依赖上月订单利润覆盖 |
| checkAutoAdSearchTermImport | 16:10 每天 | 自动广告导入状态/广告关键词相关数据 | 飞书导入检查通知 | 应在自动广告导入窗口后运行 |

## 一次性任务

2026-07-08 21:30 cron validation 行已于 Task H-1C 删除；历史前后快照见生产 `reports/crontab_before_taskH1C_20260708_190709.txt` 与 `reports/crontab_after_taskH1C_20260708_190709.txt`。

用途（删除前）：一次性 cron 和数据最大日期巡检。  
状态：已删除，避免后续误读为常规调度任务。

## 断点修复确认

### 1. syncFeishuItemOwnerToMysql.ts 为什么降级为 RAW-only

证据：
- `src/syncFeishuItemOwnerToMysql.ts` 顶部注释写明“V1.2 硬锁定：本脚本已降级为 RAW-only 历史镜像脚本”。
- `docs/feishu_item_owner_sync.md` 写明 V1.2 起飞书 `<REDACTED_FEISHU_SHEET_ID>` 不再是日常维护入口，脚本只写 `raw_feishu_table`。
- `reports/product_management_v1_2_acceptance_report.md` 显示生产验收通过，执行 `--confirm-write` 后结构化表计数不变，只有 `raw_feishu_table/<REDACTED_FEISHU_SHEET_ID>` 增加。

原因：
- 产品管理 Tab 已替代飞书 `<REDACTED_FEISHU_SHEET_ID>` 成为负责人、WFS 配送费、产品状态的维护入口。
- 旧脚本继续写结构化表会用飞书旧快照覆盖产品管理页面维护的数据。
- 2026-07-06 09:30 旧日志出现 `Unknown column 'source_raw_id' in 'field list'`，说明旧结构化写入路径与真实表结构不一致，进一步证明不能直接恢复旧写法。

时间：
- 生产 `src/syncFeishuItemOwnerToMysql.ts` 修改时间：2026-07-07 02:01:11 +0800。
- `docs/feishu_item_owner_sync.md` 修改时间：2026-07-07 02:01:12 +0800。
- `reports/product_management_v1_2_acceptance_report.md` 修改时间：2026-07-07 02:17:58 +0800。
- 生产目录不是 git worktree，`git log` 不可用；以上时间来自文件 mtime 和验收报告。

### 2. 产品管理页面是什么

前端入口：
- URL：`/admin/#/feishu-raw-sales-data`
- Tab：`产品管理`
- 前端文件：`admin-frontend/src/FeishuRawSalesData.tsx`

接口：
- `GET /api/feishu-raw-sales/product-management`
- `POST /api/feishu-raw-sales/product-management/update-owner`
- `POST /api/feishu-raw-sales/product-management/update-wfs-fee`
- `POST /api/feishu-raw-sales/product-management/update-status`
- `GET /api/feishu-raw-sales/product-management/owner-options`

维护字段：
- 可维护：负责人 `dim_product.owner` + `dim_product_owner` 历史记录。
- 可维护：WFS 配送费 `dim_product_cost_config.delivery_fee`。
- 可维护：产品管理状态 `dim_product.product_management_status*`。
- 展示但当前无页面写入口：`dim_product.launch_date`、生命周期/状态表字段。

### 3. launch_date 当前是否有路径落到 dim_product

当前数据：
- `dim_product` 总行数：1541。
- `launch_date` 非空：1502。
- 范围：2025-03-25 ~ 2026-07-04。

当前写入路径结论：
- 2026-07-07 起已上线 `src/deriveLaunchDate.ts` 每日 20:15 增量推导任务，是 `launch_date` 唯一增量来源。它只补 `launch_date IS NULL`，不覆盖任何非空值；CS 测品与 CS测品分析 Beta 使用同一 `ad_spend > 0` 首广口径，非 CS 常规产品使用首次 WFS 正库存日。
- 当前 `syncFeishuItemOwnerToMysql.ts` 不再写 `dim_product.launch_date`，只在未调用的 `writeStructuredLayersDEPRECATED()` 中保留历史 SQL。
- 产品管理页面显示 `上架时间`，但当前未发现 `update-launch-date` 之类写入口；`update-owner`、`update-wfs-fee`、`update-status` 均不写 `launch_date`。
- `syncLingxingDailyToDb.ts` 当前 upsert `dim_product` 只写 `platform/store_id/item_id/msku/sku/item_name`，不写 `launch_date`。
- `scripts/updateProductManagementStatus.ts` 只读 `dim_product.launch_date` 做停用判断，不写该字段。
- 领星同步草稿将来部署时必须移除其写 `launch_date` 的逻辑，`launch_date` 增量唯一来源为本推导任务。
- 2026-07-07 起已上线每日状态表 cron：`30 20 * * * cd /opt/lingxing-auto && npm run build:product-business-state -- --confirm-write >> /opt/lingxing-auto/logs/product-business-state.log 2>&1 # db-only-product-business-state`。
- 当前生产口径：16:45 领星日数据、18:10 广告链路、18:30 订单利润快照、19:30 利润 ETL 完成后，20:15 先补 `launch_date` 空值，20:30 统一构建 `dim_product_business_state`，作为订单利润 Beta、产品管理状态视图和 `/api/ops/analyze` 的最新状态快照来源。

### 4. dim_product_business_state 每日任务（已上线）

- 上线时间：2026-07-07
- 生产 cron：
  - `30 20 * * * cd /opt/lingxing-auto && npm run build:product-business-state -- --confirm-write >> /opt/lingxing-auto/logs/product-business-state.log 2>&1 # db-only-product-business-state`
- 目的：
  - 将当日可用的利润/销售/库存/广告/产品维度统一聚合为 `dim_product_business_state`
  - 保证订单利润 Beta、产品经营状态分析、`/api/ops/analyze` 共用同一套状态快照
  - CS 测品仅输出两态系统生命周期且不允许 NULL：按每个商品自己的 `fact_inventory_daily.MAX(snapshot_date)` 读取 `available_stock`，`>0` 为 `测品期`，`=0/NULL` 为 `测品结束`；最终 `lifecycle_stage` 仍由 trim 后非空人工值优先覆盖
- 上游依赖：
  1. `16:45` `sync:lingxing-daily`
  2. `18:30` `sync:order-profit-daily`
  3. `19:00` `sync:product-cost`
  4. `19:30` `profit ETL`
- 日志：
  - `/opt/lingxing-auto/logs/product-business-state.log`
- 技术债：
  - CS 测品分析 Beta 的 `test_end_date` 当前仍有硬编码 `2026-06-27`，且 CS Beta `non_wfs_available_stock` 是测品过程分析口径；产品管理生命周期改用 `available_stock` 管理视角有货/没货口径，两者并存不混用。
  - 状态表常规库存状态、库存周转、problem_tags 当前仍使用全局最新库存快照日；2026-07-08 核查发现 14 个 CS 商品与产品管理页逐商品最新库存快照不一致。本任务只为 CS 生命周期补充逐商品库存口径，常规产品库存口径不动，后续 B 线再议。

## 变更规则

新增或调整任何 cron 前必须回答：
1. 上游数据是否已经就绪。
2. 目标数据日期是今天、昨天、T-2，还是一段回填窗口。
3. 是否写 RAW、DIM、FACT、EVENT、AI 哪一层。
4. 是否覆盖人工维护字段。
5. 是否需要 dry-run、备份、验收 SQL、回滚方案。

## 2026-07-11 / 批A + 批B 通报链路修复

### deriveLaunchDate（20:15）

- 脚本：`src/deriveLaunchDate.ts`
- cron：`15 20 * * * cd /opt/lingxing-auto && npm run derive:launch-date -- --confirm-write >> /opt/lingxing-auto/logs/derive-launch-date.log 2>&1 # db-only-derive-launch-date`
- 当前口径：
  - 连接层启用 `dateStrings:true`
  - `--execute` 与 `--confirm-write` 等价
  - 候选日期先归一到 `YYYY-MM-DD`
  - 非法日期只计数告警，不写库
  - 只补 `launch_date IS NULL`
- 2026-07-11 人工补算结果：4 条 CS 商品补齐，重跑 dry-run 候选归零，无 `Wed Jul 08` / `ER_TRUNCATED_WRONG_VALUE`

### 飞书通报统一发送模块

- 公共模块：`src/feishuNotify.ts`
- 接入任务：
  - `src/noOrderNotify.ts`
  - `src/lowProfitNotify.ts`
  - `src/performanceSummaryReport.ts`
  - `src/checkAutoAdSearchTermImport.ts`
- 未接入且本轮零修改：
  - `src/unmatchedOwnerNotify.ts`

### 任务级新约束

- `noOrderNotify` / `lowProfitNotify`
  - 原负责人个人发送改为统一花名册解析 + `feishuNotify`
  - 支持额外接收端环境变量
  - dry-run 零发送；`noOrderNotify` dry-run 还要求零表格日志写入
- `performanceSummaryReport`
  - 群 webhook 改读 `.env -> FEISHU_PERF_WEBHOOK_URL`
  - `FEISHU_PERF_RETRY_ENABLED=1` 时启用 19006/11232/429 分类重试与纯文本降级
  - 支持显式 `--dry-run`，零飞书调用、零表格日志写入
- `checkAutoAdSearchTermImport`
  - 日期列支持 `header` / `positional` 双模式
  - 当前生产 `1HeaCn` 实测使用 `positional`，列索引 `2`
  - webhook / 个人 / 群 三通道结果分离汇总
  - webhook 成功而花名册或 token 失败时，整体状态允许 `partial_success`
  - dry-run 禁止真实 ID 解析、禁止 token 获取、禁止真实接收端构造

### 2026-07-11 / 批B测试模式第3版正式验收闭环

- 新增测试旁路命令：
  - `notify:test:no-order`
  - `notify:test:low-profit`
  - `notify:test:performance`
  - `notify:test:auto-ad`
  - `notify:test:all`
- 四个业务脚本均新增 `--test-send`，只允许把消息旁路到测试群；禁止借测试旁路触达原负责人、原生产群或 webhook。
- `runNotifyTests.ts` 严格串行：无订单 -> 低利润 -> 业绩日报 -> 自动广告，每项间隔 `60s`，单项失败不阻断后续，整体通过条件为 `exitCode=0 && NOTIFY_TEST_SENT=1`。
- 2026-07-11 已完成双门验收：runner 自动验收通过 `4/4`，且四项均满足 `exit 0 + NOTIFY_TEST_SENT=1`；需求方同日确认四类测试消息全部实收、标题均带 `【测试】`、只进入测试群、自动广告消息中的 `@江梓博` 为纯文本、且无重复消息。
- 正式验收归档日志固定为：`/opt/lingxing-auto/logs/notify_test_all_20260711_221950.log`，长期证据统一引用该永久路径。
- 当前测试通道仍复用公共飞书应用：`getNotifyTenantToken()` 在 `FEISHU_NOTIFY_APP_ID/SECRET` 均为空时回退现有公共应用；这次测试闭环即走该回退路径完成，不代表独立通报应用已启用。
- 生产自然任务仍沿用现有 cron 与接收端；本轮未修改生产 cron、未改变生产接收端、未修改数据库、未重启服务、未部署批C。

### 业绩日报发送链路（截至 2026-07-11）

- 当前生产路径：
  - `performanceSummaryReport`
  - `-> FEISHU_PERF_PROVIDER` 为空或 `webhook`
  - `-> FEISHU_PERF_WEBHOOK_URL`
  - `-> 生产群`
- 当前状态：
  - webhook 生产路径保持不变
  - 现有 cron 保持不变
  - 现有生产接收群保持不变
- 已就绪但未启用的 App 路径：
  - `performanceSummaryReport`
  - `-> FEISHU_PERF_PROVIDER=app`
  - `-> sendCardWithFallbackToChat`
  - `-> getNotifyTenantToken()`
  - `-> FEISHU_PERF_CHAT_ID`
- App 路径代码已就绪，但当前未转正：
  - `FEISHU_PERF_PROVIDER` 仍为空
  - `FEISHU_PERF_CHAT_ID` 仍为空
  - 不得表述为“业绩日报已迁移 App 机器人”


## 2026-07-14 / WFS到货提醒链路（阶段1已部署，cron待授权）

阶段1已完成：
- `npm run sync:wfs-shipments -- --confirm-write --days=90`：拉取 WFS 货件并写入 `fact_wfs_shipment` / `fact_wfs_shipment_item`，同时生成 R1 货件状态事件。
- `npm run build:arrival-events -- --confirm-write`：基于库存 0->非0、可售后无广告、升级规则生成到货提醒事件。
- `npm run notify:test:arrival`：测试群验收通道，标题带 `【测试】`，不回写事件状态。

拟转正 cron（尚未新增，需需求方确认测试群消息后单独授权）：
- `08:20`：`npm run sync:wfs-shipments -- --confirm-write`，日志 `logs/wfs-shipments.log`。
- `20:40`：`npm run build:arrival-events -- --confirm-write`，位于 20:30 状态表与 20:50 运营日志之间，日志 `logs/arrival-events.log`。
- `08:40`：`npm run notify:arrival:send`，日志 `logs/arrival-notify.log`。

边界：阶段1未修改 crontab；生产发送 `notify:arrival:send` 只能在阶段2 cron 转正后由自然任务触发，禁止手工执行生产发送。
### WFS到货提醒阶段2（2026-07-15 上线）

- 08:20 `sync:wfs-shipments -- --confirm-write`
  - 作用：同步 Walmart WFS 货件与商品明细到 shipment 事实层。
- 14:00 `notify:arrival:send`
  - 作用：读取 `event_arrival_notify` pending 事件，按群 + 负责人私信发送到货提醒。
  - 通道：当前生产确认为 `FEISHU_ARRIVAL_CHAT_ID` 应用机器人群通道；若后续切换外部群 webhook，代码已支持 `FEISHU_ARRIVAL_WEBHOOK_URL` 回退。
- 20:40 `build:arrival-events -- --confirm-write`
  - 作用：基于 shipment / inventory / ads 生成到货、上架、无广告升级等 arrival 事件。

时序关系：`08:20 货件同步 -> 20:40 事件构建 -> 次日/当日 14:00 通知发送`。

### R5/R6 广告组静默监控（2026-07-15 上线）
- `20:40` `build:arrival-events`
- `20:45` `build:ad-silence-events -- --confirm-write`
- `20:50` `build:operation-log-base -- --confirm-write`
- 顺序敏感：`20:45` 位于到货事件构建与运营日志基表之间，仅写 `event_arrival_notify`，由次日 `14:00 notify:arrival:send` 统一发送。

### 清货链路 cron（2026-07-20 批①）
- `09:33 notify:clearance-approval -- --send` 清货审批汇总卡（待审批为空静默退出）
- 已定稿待上线（批③）：周五 10:16 清尾卡（≤60天线，继续清货14天不重发）；每日清零+7天归档卡；新货件/新采购单复活卡。补货目标70天与清尾线60天为两个独立参数。
### 通知调整汇总（2026-07-20）
- 已取消：09:05 低利润卡、16:10 广告导入检查、周五17:30周报补推、断货提醒发送（检测保留）、R5/R6发送（cron已删）
- 改频/改时：待认领 周一四09:10；低毛利 周一四09:45；订单下滑私信统一发林翔（FEISHU_ORDER_DROP_RECEIVER）
- 无动作监控：每日09:30 正式发负责人个人卡片（⚠️橙头卡），总览进测试群留档
- 周报手动生成接口：一律 --test-send 只进测试群；全员推送仅周四确认卡链路

## 2026-07-23 / 飞书写入链路退役核查（只读）

部署AI只读实扫生产 crontab 结论：active cron 无任何任务写“真飞书在线表格”。仍相关的 active 线：16:45 `backfillDailyChain` 刷新 `raw_feishu_table` 系统快照(`<REDACTED_FEISHU_SHEET_ID>`，及仍被刷新的 `<REDACTED_FEISHU_SHEET_ID>/<REDACTED_FEISHU_SHEET_ID>`)；19:30 利润ETL 读 `order_profit_daily` 写 `fact_profit_daily`；20:50 `build:operation-log-base` 写 `biz_product_operation_log`(不碰飞书)。
已停用保留注释：`#09:30 sync:feishu-item-owner`(原写 `<REDACTED_FEISHU_SHEET_ID>`)、`#20:50 sync:daily-operation-log-base`(旧飞书在线表链路,关联 `<REDACTED_FEISHU_SHEET_ID>`)。
僵尸脚本(crontab 命中=0)：`syncNoMovingProducts / syncYuesiTestProductAnalysis / syncRecentProfitAndAds / syncFeishuItemOwnerToMysql / aiDailyDiagnosis / syncDailyOperationLogBase`。
待拍板(未执行)：`<REDACTED_FEISHU_SHEET_ID>/<REDACTED_FEISHU_SHEET_ID>` 是否随下批停止 `syncLingxingToRawFeishu` 刷新。详见 TASK_CHANGE_LOG 2026-07-23 节。

## 2026-07-24 / CS测品异常预警 cron（新增，不动既有）｜【2026-08-17 起已暂停：两条cron注释保留，CS产品已全量归档，恢复=取消注释，见 TASK_CHANGE_LOG 2026-08-17】
- 16 17 * * 1-5  csTestAlertNotify.ts --detect --execute  → logs/cs_alert_detect.log （工作日17:16 检测 upsert biz_cs_test_alert）
- 3  18 * * 1-5  csTestAlertNotify.ts --notify --send     → logs/cs_alert_notify.log （工作日18:03 发负责人卡/汇总卡/扣分明细黄少如）
- 首次正式发送=2026-07-27(周一)18:03（周末 1-5 不跑）。第一次 send_count 0→1 不扣分。

## Active cron snapshot as of 2026-07-31

以下为生产 `crontab -l` 原样快照（49 条 active）。**本节为判定本文档是否过期的基准**：与最新 `crontab -l` 不一致即需重新校准。

```
# noOrderNotify
0 9 * * * cd /opt/lingxing-auto && npx ts-node src/noOrderNotify.ts --send >> /opt/lingxing-auto/logs/no-order-notify.log 2>&1

# unmatchedOwnerNotify
10 9 * * 1,4 cd /opt/lingxing-auto && npx ts-node src/unmatchedOwnerNotify.ts --send >> /opt/lingxing-auto/logs/unmatched-owner-notify.log 2>&1
# checkAutoAdSearchTermImport
# report:performance daily
0 10 * * * cd /opt/lingxing-auto && npm run report:performance -- --mode=daily >> /opt/lingxing-auto/logs/performance-daily.log 2>&1
# report:performance weekly
0 17 * * 1 cd /opt/lingxing-auto && npm run report:performance -- --mode=weekly >> /opt/lingxing-auto/logs/performance-weekly.log 2>&1
# report:performance monthly
0 16 3 * * cd /opt/lingxing-auto && npm run report:performance -- --mode=monthly >> /opt/lingxing-auto/logs/performance-monthly.log 2>&1
# lowProfitNotify
45 9 * * 1,4 cd /opt/lingxing-auto && npx ts-node src/lowProfitNotify.ts --send >> /opt/lingxing-auto/logs/low-profit-notify.log 2>&1
# 50 20 * * * cd /opt/lingxing-auto && npm run sync:daily-operation-log-base -- --confirm-write >> /opt/lingxing-auto/logs/daily-operation-log-base.log 2>&1 # disabled 2026-07-08 taskH-1C operation-log moved to MySQL; see TASK_CHANGE_LOG
# syncWalmartStores
0 3 * * * cd /opt/lingxing-auto && npx ts-node src/syncWalmartStores.ts >> /opt/lingxing-auto/logs/sync-walmart-stores.log 2>&1
# sync:lingxing-daily
45 16 * * * cd /opt/lingxing-auto && exec /usr/bin/node /opt/lingxing-auto/node_modules/ts-node/dist/bin.js src/backfillDailyChain.ts --execute --deadline=19:10 >> /opt/lingxing-auto/logs/backfill-daily-chain.log 2>&1
# syncManualAdKeywordDaily
10 18 * * * cd /opt/lingxing-auto && npx ts-node src/syncManualAdKeywordDaily.ts >> /opt/lingxing-auto/logs/manual-ad-keyword-daily.log 2>&1
# sync:order-profit-daily
# sync:product-cost
0 19 * * * cd /opt/lingxing-auto && bash -lc 'DATA_DATE=$(date -d "2 days ago" +\%F); npm run sync:product-cost -- --confirm-write --date="$DATA_DATE"' >> /opt/lingxing-auto/logs/product-cost-mysql.log 2>&1
# profit ETL
30 19 * * * cd /opt/ads-ai-api/scripts && python3 build_fact_profit_daily_from_raw_feishu.py --execute --start-date $(date -d "4 days ago" +\%F) --end-date $(date -d "yesterday" +\%F) >> /opt/ads-ai-api/scripts/profit_etl.log 2>&1
# refreshFeishuMembers
30 2 * * * cd /opt/lingxing-auto && npx ts-node src/refreshFeishuMembers.ts --write >> /opt/lingxing-auto/logs/refresh-feishu-members.log 2>&1
# sync:feishu-item-owner
#30 9 * * * cd /opt/lingxing-auto && npm run sync:feishu-item-owner -- --confirm-write >> /opt/lingxing-auto/logs/sync-item-owner-mysql.log 2>&1 # db-only-sync-feishu-item-owner # disabled 2026-07-07 飞书链路退役，见TASK_CHANGE_LOG
30 20 * * * cd /opt/lingxing-auto && npm run build:product-business-state -- --confirm-write >> /opt/lingxing-auto/logs/product-business-state.log 2>&1 # db-only-product-business-state
15 20 * * * cd /opt/lingxing-auto && npm run derive:launch-date -- --confirm-write >> /opt/lingxing-auto/logs/derive-launch-date.log 2>&1 # db-only-derive-launch-date
50 20 * * * cd /opt/lingxing-auto && npm run build:operation-log-base -- --confirm-write >> /opt/lingxing-auto/logs/operation-log-base.log 2>&1 # db-only-operation-log-base
55 20 * * * cd /opt/lingxing-auto && npm run build:product-rule-signals -- --confirm-write >> /opt/lingxing-auto/logs/product-rule-signals.log 2>&1 # db-only-product-rule-signals
0 9 * * * cd /opt/lingxing-auto && npx ts-node src/clearDepartedOwners.ts --execute >> /opt/lingxing-auto/logs/clear-departed-owners.log 2>&1
0 16 * * 4 cd /opt/lingxing-auto && npx ts-node src/sendWeeklyReportConfirmCard.ts --send >> /opt/lingxing-auto/logs/weekly_confirm_card.log 2>&1
0 3 4 * * cd /opt/lingxing-auto && python3 scripts/generate_monthly_report.py --trigger cron >> /opt/lingxing-auto/logs/monthly_report_cron.log 2>&1
0 9 4 * * cd /opt/lingxing-auto && npx ts-node src/sendBusinessReportNotify.ts --latest --kind monthly --send >> /opt/lingxing-auto/logs/monthly_report_notify_cron.log 2>&1
20 9 * * * cd /opt/lingxing-auto && npx ts-node src/checkMonthlyPlanReminder.ts --send >> /opt/lingxing-auto/logs/monthly_plan_reminder.log 2>&1
20 8 * * * cd /opt/lingxing-auto && npm run sync:wfs-shipments -- --confirm-write --days=90 >> /opt/lingxing-auto/logs/wfs-shipments.log 2>&1 # db-only-wfs-shipments
40 20 * * * cd /opt/lingxing-auto && npm run build:arrival-events -- --confirm-write >> /opt/lingxing-auto/logs/arrival-events.log 2>&1 # db-only-arrival-events
0 14 * * * cd /opt/lingxing-auto && npm run notify:arrival:send >> /opt/lingxing-auto/logs/arrival-notify.log 2>&1
30 4 * * 0 cd /opt/lingxing-auto && bash -lc 'S=$(date -d "14 days ago" +\%F); E=$(date -d "3 days ago" +\%F); npx ts-node src/syncManualAdKeywordDaily.ts --startDate="$S" --endDate="$E"' >> /opt/lingxing-auto/logs/manual-ad-keyword-backfill.log 2>&1
30 9 * * * cd /opt/lingxing-auto && npx ts-node src/checkOpsInactionAlert.ts --send >> logs/ops_inaction.log 2>&1
20 5 * * * cd /opt/lingxing-auto && npx ts-node src/syncWalmartListingPrice.ts --confirm-write >> logs/walmart_listing_price.log 2>&1
25 16 * * * cd /opt/lingxing-auto && npm run check:order-drop -- --confirm-write >> logs/order-drop-check.log 2>&1 # db-only-order-drop
50 16 * * * cd /opt/lingxing-auto && npm run notify:order-drop -- --send >> logs/order-drop-notify.log 2>&1
0 20 * * * cd /opt/lingxing-auto && npm run check:order-drop -- --confirm-write --slot=2000 >> logs/order-drop-control.log 2>&1 # db-only观察期对照
40 4 25 * * cd /opt/lingxing-auto && npx ts-node src/syncWfsFeeFromSettlement.ts --confirm-write >> logs/wfs_fee_auto.log 2>&1
10 5 25 * * /opt/lingxing-auto/scripts/refresh_month_profit.sh >> /opt/lingxing-auto/logs/month_profit_refresh.log 2>&1
33 9 * * * cd /opt/lingxing-auto && npm run notify:clearance-approval -- --send >> logs/clearance-approval.log 2>&1
16 10 * * 5 cd /opt/lingxing-auto && npm run notify:clearance-cards -- --type=tail --send >> logs/clearance-tail.log 2>&1
5 10 * * * cd /opt/lingxing-auto && npm run notify:clearance-cards -- --type=archive --send >> logs/clearance-archive.log 2>&1
50 8 * * * cd /opt/lingxing-auto && npm run notify:clearance-cards -- --type=revive --send >> logs/clearance-revive.log 2>&1
40 7 * * * cd /opt/lingxing-auto && npm run sync:purchase-orders -- --confirm-write >> logs/purchase-orders.log 2>&1
45 7 * * * cd /opt/lingxing-auto && npm run sync:local-inventory -- --confirm-write >> logs/local-inventory.log 2>&1
25 17 * * * cd /opt/lingxing-auto && npx ts-node src/checkAutoAdSearchTermImport.ts --send >> /opt/lingxing-auto/logs/check-auto-ad-import.log 2>&1
0 23 * * 4 cd /opt/lingxing-auto && npx ts-node src/aiOpsLogReview.ts --confirm-write >> /opt/lingxing-auto/logs/ai_ops_log_review.log 2>&1
30 19 * * 4,5 cd /opt/lingxing-auto && npx ts-node src/checkWeeklyReportPending.ts >> /opt/lingxing-auto/logs/weekly_report_pending.log 2>&1 # weekly-report-pending-1930
*/30 * * * 4,5 cd /opt/lingxing-auto && npx ts-node src/sendWeeklyReportConfirmCard.ts --send --remind >> /opt/lingxing-auto/logs/weekly_confirm_card.log 2>&1 # weekly-confirm-remind
35 7 * * * cd /opt/lingxing-auto && npx ts-node src/syncMpOrdersChannelDaily.ts --execute >> /opt/lingxing-auto/logs/mp_orders_channel.log 2>&1
# [PAUSED 20260817 CS暂停] 16 17 * * 1-5 cd /opt/lingxing-auto && npx ts-node src/csTestAlertNotify.ts --detect --execute >> /opt/lingxing-auto/logs/cs_alert_detect.log 2>&1
# [PAUSED 20260817 CS暂停] 3 18 * * 1-5 cd /opt/lingxing-auto && npx ts-node src/csTestAlertNotify.ts --notify --send >> /opt/lingxing-auto/logs/cs_alert_notify.log 2>&1
10 9 28 7 * cd /opt/lingxing-auto && /usr/bin/npx ts-node src/gptKwOwnerSummary.ts --send >> /opt/lingxing-auto/logs/gptKwSummary_20260728.log 2>&1
45 0 * * * cd /opt/lingxing-auto && npm run sync:attendance -- --daily --write >> /opt/lingxing-auto/logs/attendance-sync.log 2>&1
50 9 * * * cd /opt/lingxing-auto && npx ts-node src/attendanceLackAlert.ts --push   --send >> logs/att_lack_push.log   2>&1
50 21 * * * cd /opt/lingxing-auto && npx ts-node src/attendanceLackAlert.ts --remind --send >> logs/att_lack_remind.log 2>&1
```


## 2026-08 目标管理新规 新增/变更定时（M3 / M5c / M8）
- **checkMonthlyPlanDeduction.ts**（每日 **09:25** `--confirm-write`，8号起；M3 月度规划未填扣分）：扫描当月 在营·非CS·非新品·v5非豁免 且未完成(无 biz_monthly_plan 行 或 target_sales_amount 空)，按负责人 GROUP BY → 每负责人每天 event_monthly_plan_unfilled + biz_perf_deduction(biz_type=monthly_plan_unfilled, 5分)。**每人每天固定5分**、不封顶。首扣 8/8。日志 `logs/*monthly-plan-deduction*`。
- **checkClearanceNoTargetAlert.ts**（每日 **09:35** `--send`，8号起；M5c 清货无目标特批）：当月清货品(生命周期=清货期)无清货目标→发林翔待特批清单+清货中心链接。8号闸门(ALERT_START_DAY=8，--test-send 不限)。
- **checkMonthlyPlanReminder.ts**（09:20，M3.5 已对齐 v5+todo口径+7号截止/8号）：档期 5/7/8；催办口径 ⊇ 扣分口径（同 v5 豁免、完成=有行且填销售额目标）。
- **generate_monthly_report.py**（月报生成链：4日 **06:00** 生成→09:00 推送；M8 由 03:00 改 06:00）：豁免判定同步 v5（报告月整月 WFS 库存 MAX=0 且 WFS 销量=0 且 WFS 在途=0）。写 ai_business_report(period_key=报告月) + ai_monthly_issue_item(plan_month=报告月+1)，纯 INSERT 到 AI 层。
- 口径：以上四处「豁免/完成/新品」口径与 aiBusinessRoutes /monthly-plan/todo 完全一致（2026-08 定稿）。
- **checkDataSentinel.ts**（P7数据完整性哨兵,2026-08-10上线）：`15 20 * * *` 主检(--check --send:5项零容差——saleStat族三表T-2~T-4恒等/<REDACTED_FEISHU_SHEET_ID>行数≥600/当日库存快照/msku空串增量/渠道表有无)+`0 9-23 * * *` 整点提醒(先复查,通过自动闭环)+`0 9 * * 1` 周报。异常发交互卡仅陈佳聪;确认→sentinelCore白名单系统代码执行(重跑对应同步/ETL/库存sentinel_backfill补录)→立即复查→闭环/满2次转人工。事件表 event_sentinel_alert(SQL040)。日志 logs/sentinel.log。
- **checkArchivedRestockAlert.ts**（每日 **09:40** `--send`，2026-08-05 上线）：归档且最新快照 WFS>5 → 每产品一张飞书卡(按钮:恢复在售/继续归档)发负责人DM、无负责人→经营周报群；keep=暂停提醒、库存超基线自动复提；事件表 event_archived_restock_alert(SQL039)；回调 feishuCardCallbackRoutes(biz=archived_restock)。日志 logs/archived-restock-alert.log。

### 快照后增量（2026-08-04）

- `35 2 * * * npx ts-node src/syncAppUsersFromMembers.ts --confirm-write >> logs/sync-app-users.log`（新员工自动开户：花名册02:30同步后，为缺户 active 成员建 dim_app_user，幂等，绝不动现有/超管账号。起因：新员工李遇青在花名册但无账号，首登发卡报「请联系人事」）。
- 另有并行批次同日新增 09:25 月度规划扣分(checkMonthlyPlanDeduction)、09:35 清货待特批通报(checkClearanceNoTargetAlert)，详见 TASK_CHANGE_LOG M3/M5c 条目。下次全量校准时并入主快照。

## 2026-08-17 / 订单利润V2 批1 · 退货数据链（代码就绪，待部署）

- 脚本：`src/syncWalmartReturnOrders.ts`（md5 3ac85753）。拉领星售后接口 `/basicOpen/openapi/multiplatform/walmart/returnOrder/list`（dateType=1 售后时间），默认近7天窗（覆盖退款状态滞后更新），`--start/--end` 历史回补，`--confirm-write` 才写库（默认 dry-run 零写入），限速 1500ms/页、pageSize=100。
- 链路：售后接口 → `raw_walmart_return_order`（幂等 upsert，状态/金额可更新）→ 窗口聚合重算 → `fact_refund_daily`（仅 REFUND 入FACT；item_id 经 dim_product 映射，active 优先）。
- cron：**本批不挂**。批4 统一挂 `50 7 * * *`（每日 07:50 拉近7天窗）。
- 建表：`sql/047_walmart_refund_tables.sql`（md5 e57c28d8，幂等 IF NOT EXISTS）。

## 2026-08-18 / 订单利润V2 批2 · 折扣链+仓储日摊（代码就绪，待部署）

- `src/syncMpOrderDiscount.ts`（2e248627）：订单列表接口→raw_mp_order_discount→fact_promo_discount_daily。日拉模式=update_time近2天窗；回补模式=--start/--end订购时间窗(≤31天硬校验)。折扣=item_info[].discount_amount商品行级；FACT排除取消单(status=7)。cron批4挂（每日 08:05 拟）。
- `src/expandStorageFeeDaily.ts`（39564580→2026-08-19分段升级 220e81d9(首版d53f6c1d因mysql2 JSON列自动parse致提取归零被dry-run闸门拦截,CAST取原文热修)）：fact_wfs_storage_fee→fact_storage_fee_daily全量重展开，幂等；逐期+总额守恒断言。触发=仓储CSV导入后手动/批4挂钩，非每日cron。2026-08-19 起两步：步骤0 statement RAW→fact_storage_weekly_charge（结算周实扣提取，store_id取请求侧sids防double丢精度）；步骤1 分段日摊——账期周数据齐且Σ周与账期额差≤$0.05时按周实扣分段均摊（结算周窗口可与店铺后台对账单对平），否则回退整期均摊（SUMMARY计数 segmented_rows/fallback_uniform_rows）。⚠️statement RAW 拉取截至 posted 07-24（2026-08-19探针），此后新账期在补拉前走回退均摊；账单同步调度现状待部署单核实。
- 建表：`sql/048_promo_discount_storage_daily.sql`（cc5b92fe）。

## 2026-08-18 / 订单利润V2 批3a · 一次查询路由+新Tab（代码就绪，待部署）

- `src/orderProfitV2Routes.ts`（b63e11db）：GET /api/profit-v2/order-profit，只读JOIN四张FACT（profit/refund/promo_discount/storage_daily）+权威广告表全类型；无cron、无写入。
- 前端 `OrderProfitV2.tsx`（ca91df16）hash=#/profit/order-v2；三壳文件纯新增行(基线32af6832/bfbee18d/d1229bfb)。
- 旧「订单利润 Beta」零改动，对账期并行。

## 2026-08-19 / 账单statement每日同步cron挂载 + 3月历史回补（已上线✅ 2026-08-20 验收）

- crontab 新增一条：`35 8 * * * cd /opt/lingxing-auto && npx ts-node src/syncWalmartBillDaily.ts >> logs/walmart_bill_daily.log 2>&1`（默认20天滚动窗按交易入账日拉全店铺，入账滞后行posted日为新、滚动窗天然不漏；时点错峰07:35~08:20既有链之后）。
- 背景：此前该链无任何调度、statement RAW停在posted 07-24（2026-08-19探针实证，全局统一非个别店铺）；下游=fact_reconciliation_*、fact_storage_weekly_charge（经expandStorageFeeDaily提取）、返还明细/佣金等账单消费方。
- 上线状态：cron 已挂，2026-08-20 08:35 首跑成功（08:39完成，聚合账期4/明细939/守恒0/错误0）；回补后周费表 69 行覆盖 03-21~07-24，日摊分段 1793 行/回退 401 行，69周全量对照 60周 diff=0.00。
- 同批手工回补：--startDate/--endDate 分三段（04-16~05-08、03-22~04-15、03-01~03-21）先近后远串行；领星接口回看≈150天（边界≈03-22），最早一段尝试性拉取、拉不到如实记录不算失败；回补后重跑 expandStorageFeeDaily --confirm-write 扩大分段覆盖。

## 2026-08-18 / 订单利润V2 批4a · cron挂载 + 仓储导入触发钩子

- crontab 新增两条（部署单执行）：
  - `50 7 * * * cd /opt/lingxing-auto && npx ts-node src/syncWalmartReturnOrders.ts --confirm-write >> logs/refund_sync.log 2>&1`（退货日拉，默认近7天窗覆盖状态滞后）
  - `5 8 * * * cd /opt/lingxing-auto && npx ts-node src/syncMpOrderDiscount.ts --confirm-write >> logs/promo_discount_sync.log 2>&1`（折扣日拉，update_time近2天窗，美西日归因）
- 仓储日摊触发＝账单驱动：`aiFinanceRoutes.ts` 仓储CSV导入接口落FACT成功后 fire-and-forget spawn `expandStorageFeeDaily.ts --confirm-write`（失败只记日志不影响导入；脚本自带守恒断言+幂等），无独立cron。
- 待办（批4c/4d）：P7哨兵V2守恒检查⑦、账单接口周对账、新旧Tab对账报告。
