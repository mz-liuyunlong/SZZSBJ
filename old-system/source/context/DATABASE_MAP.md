# DATABASE_MAP

最后核对：2026-07-31  
数据库：`walmart_ai_data`  
核对方式：生产 MySQL `information_schema` + 只读聚合查询 + 代码扫描（07-31 为代码扫描口径的增量校准，未做全库 information_schema 重扫）。

## 数据库概况

用途：跨境电商运营数据中台，承接领星 API、飞书表格、Walmart 广告 CSV、Admin 后台、Custom GPT 经营分析。

分层：RAW / DIM / FACT / EVENT / AI。前端和 GPT 不应新增直查 RAW 的业务能力；RAW 仅用于留痕、审计、回放、历史镜像。

截至本次核对的主要覆盖：
- `fact_sales_daily`：2026-04-01 ~ 2026-07-05，11867 行。
- `fact_ads_product_daily`：2026-04-01 ~ 2026-07-05，277187 行。
- `fact_ads_keyword_daily`：2026-05-01 ~ 2026-07-05，1012592 行。
- `fact_inventory_daily`：2026-04-01 ~ 2026-07-05，104477 行。
- `fact_profit_daily`：2026-05-01 ~ 2026-07-05，62641 行。
- `raw_feishu_table(order_profit_daily)`：2026-04-01 ~ 2026-07-05，89036 行。
- `dim_product_business_state`：最大 `stat_date=2026-07-06`（2026-07-09 合并部署后最新快照 1127 行，archived 已清理为 0，`extra_json.metrics_window_days=14`）。

## RAW层

| 表名 | 用途 | 数据来源 | 更新方式 | 最后核对 |
|---|---|---|---|---|
| `raw_lingxing_api` | 领星 API 原始响应留存 | 领星 API | `syncLingxingDailyToDb.ts`、`syncProductNameFromLingxing.ts` 等同步链路 | 2026-07-08 |
| `raw_feishu_table` | 飞书/虚拟 sheet RAW 镜像；含 `order_profit_daily` 订单利润快照 | 飞书表格、同步脚本生成的虚拟 sheet | `syncLingxingToRawFeishu.ts`、`syncOrderProfitDaily.ts`、历史飞书同步 | 2026-07-07 |
| `raw_walmart_ads_csv` | Walmart 自动广告 CSV 原始行 | Walmart CSV / 自动广告导入 | 自动广告导入链路 | 2026-07-07 |
| `raw_frontend_upload` | 前端上传文件记录 | Admin 前端上传 | 当前 0 行 | 2026-07-07 |
| `raw_sync_tasks` | 同步任务记录 | 同步脚本 | 同步任务 Tab 读取 | 2026-07-07 |
| `raw_walmart_return_order` | Walmart 售后退货单原始留存（单头+明细存 `row_json`，含换货/预购全类型） | 领星售后接口 `/walmart/returnOrder/list`（dateType=1 售后时间） | `syncWalmartReturnOrders.ts`（V2批1·已上线2026-08-18,60天回补1889单$36945守恒验证；cron 批4 挂 07:50） | 2026-08-17 |
| `raw_mp_order_discount` | 促销折扣订单商品行（仅折扣≠0行；取消单留RAW带status） | 领星订单列表 `/pb/mp/order/v2/list`（platform_code=10008） | `syncMpOrderDiscount.ts`（V2批2·待部署） | 2026-08-18 |

注意：`raw_feishu_table.sheet_id='<REDACTED_FEISHU_SHEET_ID>'` 是系统生成快照，不是飞书真实 sheet。新前端功能不得直接依赖 RAW，除非是 RAW 查看器/审计场景。
补充：`sheet_id='<REDACTED_FEISHU_SHEET_ID>'`（ItemID负责人）已废弃，2026-07-07 起停止写入；最新批次存在表头退化（`col_N`），历史批次（2026-07-06 前）表头正常，可仅作存档查询，不再作为修复链路。

## DIM层

| 表名 | 用途 | 核心字段 | 唯一键/关键索引 | 关联关系 | 最后核对 |
|---|---|---|---|---|---|
| `dim_store` | 店铺维度 | `platform`,`store_id`,`store_name`,`advertiser_id`,`owner` | `uq_dim_store(platform,store_id)` | FACT 表按 `store_id` 关联 | 2026-07-07 |
| `dim_store_config` | 店铺配置/动态店铺来源 | 店铺/平台配置字段 | 生产 10 行，详见表结构 | `storeRegistry.ts` 读取 | 2026-07-07 |
| `dim_product` | 商品主维表 | `platform`,`store_id`,`item_id`,`msku`,`sku`,`product_name`,`item_name`,`owner`,`launch_date`,`product_management_status`,`manual_lifecycle_stage`,`manual_lifecycle_by`,`manual_lifecycle_at`,`walmart_publish_status` | `uq_dim_product(platform,store_id,item_id,msku(64))` | FACT、状态表、产品管理页核心维度 | 2026-07-08 |
| `dim_owner` | 负责人/人员维度 | `owner_name`,`feishu_user_id`,`status` | `uq_dim_owner(owner_name,department(64))` | 负责人筛选、通知 @ 人映射 | 2026-07-07 |
| `dim_feishu_member` | 飞书花名册/成员状态映射 | `open_id`,`name`,`employment_status`,`last_seen_at`,`left_detected_at` | 生产 31 行 | `update-owner` 资格校验、离职清空、三段通报 | 2026-07-11 |
| `dim_product_owner` | 负责人历史/来源追溯 | `platform`,`store_name`,`item_id`,`msku`,`owner_name`,`effective_date`,`status` | `uq_dim_product_owner(platform,store_name(64),item_id,msku(64),owner_name(64))` | 历史追溯；主口径逐步转向 `dim_product.owner` | 2026-07-07 |
| `dim_product_cost_config` | 成本配置 | `delivery_fee`,`purchase_cost`,`first_mile_shipping_cost`,`effective_date`,`source_system` | `uq_dim_product_cost(platform,store_name(64),item_id,msku(64),effective_date)` | 订单利润、产品管理 WFS 配送费 | 2026-07-07 |
| `dim_product_identity` | 商品身份追溯 | 商品多身份字段 | 生产 634 行 | 产品管理历史追溯 | 2026-07-07 |
| `dim_product_business_state` | B 线规则统一输出/每日快照 | `stat_date`,`platform`,`store_id`,`item_id`,`msku`,`profit_level`,`lifecycle_stage`,`inventory_status`,`ad_status`,`problem_tags` | `uk_pbs(stat_date,platform,store_id,item_id,msku)` | `buildProductBusinessState.ts` 写；订单利润接口和 `/api/ops/analyze` 读；2026-07-08 Task H-1D 起不再生成 archived 快照；2026-07-09 起常规产品统计窗口固定 14 天，`ad_status` 异常线 15% | 2026-07-09 |
| `biz_product_rule_signal_daily` | 分析层只读系统规则信号日快照 | `signal_date`,`platform`,`store_id`,`store_key`,`item_id`,`msku`,`rule_code`,`rule_level`,`should_notify`,`ad_window_start`,`ad_window_end` | `uk_rule_signal_day(signal_date,platform,store_key,item_id,msku,rule_code)` | `buildProductRuleSignalsDaily.ts` / `build:product-rule-signals` 生成；Admin/GPT/第5期只读消费；2026-07-09 起常规产品提醒带 `【近14天】` 与 trigger_reason 口径，B级广告规则阈值统一 15% | 2026-07-09 |
| `dim_keyword` | 关键词维度 | `keyword_text`,`normalized_keyword`,`keyword_type` | `uq_dim_keyword(platform,normalized_keyword(200),keyword_type)` | 当前 0 行 | 2026-07-07 |

`dim_product` 特别说明（2026-07-07 复核）：
- `launch_date` 语义当前应视为“商品上架时间/上线时间候选值”，不是 `created_at`，也不是首次销量日期反推值。
- 定稿口径 v2：存量以 2026-07-06 飞书 G 列人工一次性回填为主；增量由每日 `deriveLaunchDate.ts` 双轨推导补空值。CS 测品（`msku` 以 `CS` 开头）取 `fact_ads_product_daily` 中 `ad_spend > 0` 的最早 `stat_date`，与 CS测品分析 Beta“首次广告日期”同源，广告表只按 `platform + store_id + item_id` 关联，不带 `msku`；非 CS 常规产品取 `fact_inventory_daily` 中同商品 `wfs_available_stock > 0` 的最早 `snapshot_date`，库存表按 `platform + store_id + item_id + msku` 关联。推导不出的纯非 WFS 品、历史窗口外老品、未开售 listing 或死品继续保持 NULL，由生命周期人工处理。
- 每日推导任务只允许执行 `UPDATE dim_product SET launch_date = ... WHERE launch_date IS NULL`；任何已有值（含 2026-07-06 人工回填的 1502 条）永不修改。`--confirm-write` 前会导出候选白名单 CSV 到 `reports/derive_launch_date_YYYYMMDD*.csv`，作为审计记录和极端误写回滚白名单。
- 现网 `syncLingxingDailyToDb.ts` 生产版当前 **不** 持续写 `launch_date`；其 `dim_product` upsert 只写 `platform/store_id/item_id/msku/sku/item_name`。仓库本地存在未跟踪草稿版已加上 `product_name/launch_date` 与 `listing_start_time` 解析，但本次核查确认该版本未部署到 `company-ai`。
- 护栏：领星同步草稿将来部署时必须移除其写 `launch_date` 的逻辑，`launch_date` 唯一增量来源为 `deriveLaunchDate.ts` 推导任务；严禁把 `launch_date` 放进任何 UPSERT 全量覆盖列清单。
- `product_name` 权威来源：2026-07-08 起以领星本地产品详情 `batchGetProductInfo.data.product_name` 为准，由 `syncProductNameFromLingxing.ts` 执行“领星 API -> raw_lingxing_api -> dim_product”链路。confirm-write 前必须重新调用 API，并先将每批响应写入 `raw_lingxing_api`；RAW 写入/查询失败的批次不得更新 DIM。`product_name` 只允许使用非空、非纯空格的领星返回值覆盖；本次上线写入 1354 条，Walmart `dim_product.product_name` 非空数为 1354。
- `sku` 写入护栏：`sku` 只允许补空，且只能写领星接口返回的 `data.sku`，不得写入剥离 MSKU 后的 `baseSku`。2026-07-08 baseSku 模式抽验为 `605/919=65.83%`，低于 95% 阈值，本次 `sku` 写入 0 条，Walmart `sku` 空值仍为 622。
- `manual_lifecycle_stage/manual_lifecycle_by/manual_lifecycle_at/manual_lifecycle_system_snapshot`：生命周期人工确认字段，持久放在 `dim_product`，不放状态快照表。NULL、空字符串、纯空格均视为未人工确认；`buildProductBusinessState.ts` 只读取 `TRIM(manual_lifecycle_stage)` 后的非空值，并按 `lifecycle_stage = COALESCE(trimmed_manual_lifecycle_stage, system_lifecycle_stage)` 写入当日状态快照，`system_lifecycle_stage` 保留系统建议。`manual_lifecycle_system_snapshot` 记录人工确认发生时的系统生命周期快照，仅用于产品管理页蓝/红高亮基线，不是最终生命周期。人工确认只影响之后重算/生成的状态快照，不回改历史快照行。2026-07-08 hotfix 起，CS 测品只允许人工设置 `测品期/测品结束/空值`，常规产品只允许人工设置 `新品期/上升期/稳定期/清货期/空值`，跨类型值必须 400 且不写库。
- 写保护：`manual_lifecycle_*` 与 `manual_lifecycle_system_snapshot` 唯一写入口是 `POST /api/feishu-raw-sales/product-management/update-lifecycle`，按 `platform + store_id + item_id + msku` 全键命中单行后写入或清空；snapshot 不允许前端传入，必须由后端读取最新状态表 `system_lifecycle_stage` 后写入。同步脚本、领星/飞书同步、利润 ETL、`deriveLaunchDate.ts`、状态表计算任务不得写入或覆盖这些字段。2026-07-08 已按精确全键清理任务 C 验收遗留的 CS 非法人工值 `20117751052/CS008-1B=清货期`。
- `syncFeishuItemOwnerToMysql.ts` 在 V1.2 之前曾通过飞书 `<REDACTED_FEISHU_SHEET_ID>` 结构化写入 `dim_product.launch_date`；表头别名识别 `上架时间/上架日期/launch_date/Launch Date/上线时间`，但源码里没有独立日期解析函数、时区转换或非法值兜底逻辑，属于“读到什么就原样透传到 SQL，依赖 MySQL 自身日期接受能力”的旧实现。V1.2 起该脚本降级为 RAW-only，`launch_date` 结构化写入只保留在未调用的 `writeStructuredLayersDEPRECATED()` 中。
- 当前 1502 条历史非空 `launch_date` 的直接证据来自 2026-07-06 生产回填产物：`reports/dim_product_launch_date_update_result.csv` 与 `reports/sync_launch_date_item_owner_g_result_20260706T135752.csv`。其中前者显示按 `item_id + msku (+ sku)` 命中 `dim_product` 后写入 `launch_date`，后者显示数据源为飞书 ItemID负责人表 G 列（`sheet_launch_raw/sheet_launch_parsed`），并将该列回写到 `dim_product.launch_date`。因此当前生产 `launch_date` 的实际来源应定性为：**2026-07-06 飞书 G 列人工回填为主 + 2026-07-07 起每日增量推导补空值**；该字段受“不可覆盖人工记录”铁律保护。
- 上架时间为空的产品，状态表不得据此判断“新品期/上升期”；应继续沿用既有规则：`launch_date` 为空时不判新品期/上升期，只做其他可用维度判断。
- 第 3 项抽样限制：生产 `raw_feishu_table.sheet_id='<REDACTED_FEISHU_SHEET_ID>'` 最新 1994 行镜像中，`row_json` 已退化为 `SKU/MSKU/col_8...` 这类无表头键名结构，最新快照里找不到 `商品ID`/`上架时间` 键，无法严格完成“`dim_product.launch_date` vs 最新 raw 快照 launch_date 列”5 条对照。可作为最近有效旁证的是 2026-07-06 回填结果 CSV：样本如 `19257917963/BG8001-1A=2026-04-29`、`19921265057/JJ2032-1A=2026-04-25`、`19941909440/JJ5024-1A=2026-04-17`、`19949824755/JJ5033-1A=2026-04-02`、`19307124352/JJ8006-1U=2026-04-04`，当时飞书 G 列解析值与 `dim_product.launch_date` 一致或被同步修正为一致。

`dim_product_business_state` 特别说明：它是 B 线规则统一输出层，`buildProductBusinessState.ts` 只读 DIM/FACT、只写该表；`/api/feishu-raw-sales/order-profit` 与 `/api/ops/analyze` 读取该表，保证页面和 GPT 状态字段同源。2026-07-08 Task H-1D 起，状态表源查询排除 `dim_product.product_management_status='archived'`，后续不再生成 archived 快照；已限定清理最新 `stat_date=2026-07-06` 的 427 行 archived 快照，历史快照保留。2026-07-08 Task F 起，CS 测品（`msku LIKE 'CS%'`）系统生命周期只输出 `测品期/测品结束`，不允许 NULL：按 `platform + store_id + item_id + msku` 取每个商品自己的 `fact_inventory_daily.MAX(snapshot_date)` 上 `available_stock`，`available_stock > 0` 为 `测品期`，`available_stock = 0` 或 NULL 为 `测品结束`。该库存口径与产品管理页“当前库存”同源，只用于 CS 生命周期判断；常规产品库存状态、库存周转、problem_tags、生命周期规则继续使用原有状态表口径。2026-07-09 合并部署后，常规产品经营指标窗口从近 30 天收紧为近 14 天，但字段名 `profit_rate_30d/ad_ratio_30d` 与相关 `*_30d` 历史命名保留不改，真实语义以 `extra_json.metrics_window_days=14` 和代码常量 `METRICS_WINDOW_DAYS=14` 为准；`ad_status='广告占比偏高'` 的阈值同步从 18% 统一到 15%。

`dim_feishu_member` 特别说明：2026-07-11 起该表正式承接公司通讯录花名册状态机。`employment_status='active'` 表示当前在册，`employment_status='left'` 表示不在册/离职；`last_seen_at` 记录最近一次在通讯录中确认在册时间，`left_detected_at` 记录最近一次被识别为离册的时间。`refreshFeishuMembers.ts` 是唯一正式写入口，且保留无姓名硬安全阀：只要姓名无法解析到 0，就必须 `exit 2` 且零写入。`POST /api/feishu-raw-sales/product-management/update-owner` 只允许读取该表中 `active` 人员作为可分配负责人；离职保留 7 天、第 8 天清空也以此表为唯一状态来源。

`biz_product_rule_signal_daily` 特别说明：它是分析层只读系统规则信号日快照，由 `src/buildProductRuleSignalsDaily.ts`（npm script `build:product-rule-signals`）生成。唯一键 `uk_rule_signal_day(signal_date,platform,store_key,item_id,msku,rule_code)`，其中 `store_key=store_id` 优先否则 `store_name`，仅作为去重锚点，标准 join 仍应优先使用 `store_id`。表内只存系统规则结果：`rule_code/rule_level/trigger_reason/suggested_action/notify_frequency_days/should_notify/source_metrics_json/ad_window_*`，固定 `signal_source='system_rule'`、`rule_version='v1'`。该表不写人工运营日志，不写 `biz_product_operation_log.ai_diagnosis`，前端/GPT 仅只读消费，不得反向篡改 RAW/DIM/FACT。1D 后最新状态表已不含 archived，因此本信号表天然不含 archived 信号。2026-07-09 合并部署后，常规产品 `trigger_reason` 统一加 `【近14天】` 前缀；`REGULAR_B_AD_RATIO_HIGH` 从“广告占比 >10%”收紧为“广告占比 >15%”，生产 `signal_date=2026-07-06` 的该规则触发数已由 24 降到 10；C级低毛利且广告占比正常时，`suggested_action` 改为“广告占比正常但毛利低，重点核查售价与成本”。

> `dim_product.walmart_publish_status`（2026-07-27）：领星 Walmart 发布状态 `status_name`（PUBLISHED/UNPUBLISHED/STAGE/IN PROGRESS/READY TO PUBLISH/SYSTEM PROBLEM）。迁移 `sql/025` 幂等加列；`syncLingxingDailyToDb.ts` 每日 RAW→DIM 刷新（空值不覆盖），不动人工字段。UNPUBLISHED 品：免匹配负责人、免绩效扣分、进待认领日报「建议归档」区（见 SYSTEM_MAP 2026-07-27 节）。

## FACT层

| 表名 | 用途 | 统计粒度 | 时间字段 | 唯一键/风险 | 最后核对 |
|---|---|---|---|---|---|
| `fact_sales_daily` | 每日销售事实 | 日 + 平台 + 店铺 + ItemID + MSKU | `stat_date` | `uq_fact_sales(...,msku(64))` 前缀索引 | 2026-07-07 |
| `fact_inventory_daily` | 每日库存快照 | 日 + 平台 + 店铺 + ItemID + MSKU | `snapshot_date` | `uq_fact_inventory(...,msku(64))` 前缀索引 | 2026-07-07 |
| `fact_ads_product_daily` | 商品广告事实（**按品广告费权威表**） | 日 + 平台 + advertiser/campaign/ad_group + ItemID | `stat_date` | 唯一键不含 MSKU；生产 `msku` 当前全空，必须按 item 级解释。**2026-08-03 探针13发票级审计通过**：由 syncLingxingDailyToDb 每日调 reportAdItemSpList（manual+auto）写入，CN2601 窗口1 $6059.69=实时API基准100.0%、自动活动5032288=$102.44=真实发票100%，auto 数据最早 2026-04-01 起、7月各店全覆盖（HK2614 07-17 起接入除外）。**AI财务/单品现金利润等一切"按ItemID算广告费"一律读本表**；订单利润Beta已用本表并做 item→MSKU 销售额占比分摊。 | 2026-08-03 |
| `fact_ads_keyword_daily` | 关键词/搜索词广告事实 | 日 + 平台 + 店铺/店名 + ItemID + normalized_keyword + match/source | `stat_date` | 生产唯一键含 `store_name(100)`，不是初版 SQL 的 `store_id` | 2026-07-07 |
| `fact_profit_daily` | 每日利润事实 | 日 + 平台 + 店铺 + ItemID + MSKU | `stat_date` | `uq_fact_profit(...,msku(64))`；`net_profit` 全为 0 非真实 | 2026-07-07 |
| `fact_refund_daily` | 每日退货退款事实（订单利润V2·退货数据链） | 日 + 平台 + 店铺 + MSKU（`item_id` 经 dim_product(店铺+MSKU) 映射，未映射留空待定性） | `refund_date`（售后申请日归因，接口返回美西站点时间即天然美西日界2026-08-18实证；当天只退货=当天负利润） | `uq_refund(platform,store_id,msku,refund_date)`；仅 `return_type='REFUND'` 入FACT，换货/预购留RAW | 2026-08-17 |
| `fact_promo_discount_daily` | 每日促销折扣事实（V2·收入修正列） | 日 + 平台 + 店铺 + MSKU（item_id映射同退货） | `discount_date`（订购日归因,**美西日界**America/Los_Angeles,2026-08-18与saleStat族对齐修订） | `uq_promo(platform,store_id,msku(64),discount_date)`；折扣存绝对额正值,页面展示负项；排除已取消(status=7)；历史仅可回补31天 | 2026-08-18 |
| `fact_storage_fee_daily` | 仓储费日摊派生表（V2·账单驱动） | 日 + 平台 + 店铺 + SKU(=MSKU) | `fee_date`（2026-08-19起按结算周实扣分段均摊,周缺/不守恒回退整期均摊） | `uq_storage_daily(platform,store_id,sku(64),fee_date)`；源=fact_wfs_storage_fee全量重展开,段/期末日吸收舍入差,逐期守恒断言；仓储费列=历史不回改的显式例外 | 2026-08-19 |
| `fact_storage_weekly_charge` | 仓储费结算周实扣（分段日摊依据） | 周 + 平台 + 店铺 | `period_start/end`（7天周期间，沃尔玛结算逐周扣款） | `uq_swc(platform,store_id,period_start,period_end)`；amount存正值(折扣后净额)；源=statement RAW `Service Fee|WFS StorageFee`行(periodStartDate/periodEndDate)；store_id取请求侧sids原文正则提取(响应行storeId经JSON double丢精度,2026-08-19探针实证禁用)；行级去重键(store,period,amount,report_key)防RAW重复留存；两周(特例期四周)合并=报告账期总额,±1分舍入(15组实证) | 2026-08-19 |
| `fact_purchase_daily` | 采购事实预留 | 采购单 + SKU | `purchase_date` | 当前 0 行 | 2026-07-07 |

`fact_profit_daily` 特别说明：来源为 `raw_feishu_table(order_profit_daily)` 的利润 ETL；口径是运营端毛利，已扣广告费，不含退款；`net_profit` 当前为默认 0，不能当财务净利；数据受上游 T-2 滞后影响。

`fact_ads_keyword_daily` 特别说明（2026-08-02 探针6~10 真账单核验定稿，样本店铺 CN2601-瑞盈龙盛/刘云龙，基准=Walmart Connect 官方 Sponsored Product 发票78430539/78597070/78597073 + 沃尔玛对账单CSV）：
- **手动/关键词型活动（精准/词组/广泛/手动/AI筛选词）花费与真实发票分毫不差**（按 campaign_name 核对，如 YC00017-精准-4.20-M=$121.57、JJ4035-手动-KY-5.12=$67.65 均 100% 吻合）。发票上活动名后括号里的数字是沃尔玛自己的编号体系，≠领星 `campaign_id`，**跨系统核对必须按活动名，禁止拿发票编号匹配 campaign_id**（探针7全军覆没就是这个坑）。
- **已知缺口①（结构性，待修）：自动投放(auto-targeting)型活动严重少算**。根因是 `syncManualAdKeywordDaily.ts` 两个接口的 `baseParams.campaignType=["sponsoredProducts-manual"]` 把 auto 型整个排除在请求范围外（样本 YC00029-自动-5.03：真实$102.44，表内仅$10.67）。探针10已实锤正确修法=campaignType 放宽为 `["sponsoredProducts-manual","sponsoredProducts-auto"]`（与 `["sponsoredProducts"]` 等价；不传/空数组=报"参数有误"），放宽后 reportAdItemSpList 对该活动返回 adSpend=$102.44=100.0% 吻合。改造涉及生产定时任务+须防与 `source_type='walmart_auto_csv'` 人工CSV导入双路重复计数，未经需求方拍板不得动。
- **已知缺口②（预期内，不修）：SBV(Sponsored Brand Video) 型活动不同步**，需求方已确认"SBV目前没有做广告数据，这个没错"（窗口1该类仅 YC00019-SBV-5.11-TEST 一个活动 $345.32）。
- **领星结算利润报表（/basicOpen/multiplatform/profit/report/msku）的 platformAdvertisingFee/semMarketingFee/advertisementAmount 字段不可用作广告费口径**：沃尔玛官方账单本身不按 item 出广告费（对账单CSV里广告费行 Partner Item Id 全空），结算报表这些字段实测仅真实发票的 0~1.4%。**单品现金利润等一切按品广告费口径一律读本表 `ad_spend`，禁止读结算报表广告字段**。
- **自动广告花费口径定稿（2026-08-02 探针11/12，需求方拍板）**：自动广告花费合计以 **API 商品级（reportAdItemSpList）为准**——发票100%验证、每行自带 itemId+adSpend=ITEMID原生归属非摊派。CSV路(walmart_auto_csv)结构性只含"搜索位"花费：日比率稳定在55.6%~79.7%（17天均值~71%），且各活动7%~100%不等（取决于搜索位vs商品页/浏览位的投放构成），**无法用固定系数修正**；缺的~30%=商品页/浏览位等无搜索词展示位的花费+低量词报表截断，钱都在活动/商品级总账里（发票=API=100%），只是永远进不了搜索词维度。CSV路角色固定=搜索词明细分析+14天出单归因刷新（每周2/4/6导近14天报表SOP，见 TASK_CHANGE_LOG 07-22 定稿条），**不计入广告费合计**（防同一笔钱两路重复计数）。
- **DATE字段时区教训（2026-08-02）**：mysql2 返回 DATE 列为服务器时区(+08:00)零点的 JS Date，`toISOString().slice(0,10)` 会显示成前一天（探针11因此误报"数据在07-14"，实际在07-15）。凡读 stat_date/snapshot_date 等 DATE 列的 JS/TS 代码，禁止直接 toISOString 切日期，必须先做时区偏移补正。CN2601 的 CSV 路自 2026-07-15 起每日连续无缺口，导入质量正常。

## EVENT层

实际表：`biz_event` 已存在，**2026-07-27 生产核实 834 行**（此前「0 行」已过期）；`event_product_owner_clear` 已于 2026-07-11 创建，用于“离职第 8 天自动清空负责人”审计。
结论：EVENT 层不再是纯预留，`event_product_owner_clear` 已正式承接离职自动清空事件审计。

`event_product_owner_clear` 特别说明：该表只增不改不删，记录 `clearDepartedOwners.ts --execute` 每次真正清空负责人的事件。关键字段：`event_time/source/task_run_id/platform/store_id/store_name/item_id/msku/old_owner/left_detected_at/action/created_at`；索引包括 `idx_epoc_time/item/owner/run`。只有在 `dim_product` 真正清空成功后才允许写入该表，审计后置，`auditRows` 必须与 `clearedProductRows` 一致。

## AI层

实际表：`ai_analysis_result` 已存在，当前 0 行。  
结论：AI 层结构已预留，但暂无独立 AI 分析结果数据。归属修正（2026-08-14）：`dim_product_business_state` 是按 `stat_date` 天粒度重算的状态快照，**逻辑归属 BIZ**，`dim_` 为历史前缀不改表名；它承担的是确定性规则产出供前端与 GPT 共读，**不是 AI 产物**。本库真正的 AI RESULT 仅 `ai_analysis_result`（0 行）、`ai_ops_log_review_item`、`ai_ops_log_review_summary` 三张；`ai_business_report` 与 `ai_monthly_issue_item` 名为 ai_ 实为 BIZ（零模型调用，2026-08-14 实证）。判定口径见 `PROJECT_CONTEXT.md`「数据分层与 AI 边界」。

### ai_analysis_result 结构现状（2026-08-14 sql/070 加固后）

- 当前行数：**0**（结构已就绪，尚无任何 AI 写入方接线）。
- 唯一键：`uq_ai_result(analysis_date, analysis_type, platform, store_id, item_id, msku, keyword(128))`。**只设 1 个唯一键**——多唯一键并存时 `ON DUPLICATE KEY UPDATE` 只按先命中者更新、行为不可预期（`ai_monthly_issue_item` 的 `uk_issue`+`uq_issue` 即反例）。
- 唯一键涉及列一律 `NOT NULL DEFAULT ''`（`platform`/`store_id`/`item_id`/`msku`/`keyword`）：MySQL 唯一索引对 NULL 不去重，允许 NULL 会让 UPSERT 幂等静默失效。
- 可追溯：`model_name`、`prompt_version`、`input_snapshot_json`（只写不读、不可 JOIN、不作规则真源）、`input_hash`（sha256，走 `idx_ai_input_hash` 普通索引，**不做唯一键**——同一对象换输入重算是合法的，重复付费由写入方查重挡）。
- 可评价：`review_state`（建议型 pending/adopted/rejected/ignored；生成型写 `n_a` 靠 `review_remark` 纠错）、`reviewed_by`、`reviewed_at`、`review_remark`（人工列，系统不覆盖）。
- 可审计：`superseded_by`（作废用标记不用删除）、`writer_type`、`updated_at`、`tokens_in`/`tokens_out`/`latency_ms`。
- ⚠️ **已知缺陷（第一个 AI 写入方上线前必须先修；修复脚本已定稿为 `sql/071_ai_analysis_result_dedup_key.sql`（v4，dedup_key BINARY(32) UNIQUE + 长度前缀编码 + 版本分支，md5 c31feca9）、**仍未执行**；v1/v2 草案已作废并移出 sql/ 目录）**：`uq_ai_result` 不含 `model_name`/`prompt_version`，同日同对象换模型重跑会就地覆盖旧结论，已 `adopted` 的审计记录会被静默销毁。修复脚本 `sql/071_ai_analysis_result_uq_add_model.sql` 已备妥但**未执行**；另有「已 adopted 行如何防覆盖」A/B 方案待拍板。详见 TASK_CHANGE_LOG 2026-08-14 同名条目。
- 备份：有效恢复点为 `backups/ai_analysis_result_schema_after070_20260814_224511.sql`（5298 字节）。**同目录下 `..._before_20260814_223727.sql` 为 0 字节无效备份，不可作恢复点。**

## 功能对应数据表

| 功能 | 页面 | 接口 | 读取表 | 写入表 | 备注 |
|---|---|---|---|---|---|
| 当日数据 | 历史隐藏 Tab | `/api/feishu-raw-sales/data?sheet_id=<REDACTED_FEISHU_SHEET_ID>` | `raw_feishu_table` | 无 | 前端已隐藏，接口保留审计 |
| 每日销售明细 | `#/feishu-raw-sales-data` 可见 Tab | `/api/feishu-raw-sales/data?sheet_id=<REDACTED_FEISHU_SHEET_ID>` | `raw_feishu_table` | 无 | RAW 查看器性质；接口仅对 `<REDACTED_FEISHU_SHEET_ID>` 做展示级 owner/MSKU 补齐，不写库 |
| ItemID负责人 | 历史隐藏 Tab | `/api/feishu-raw-sales/data?sheet_id=<REDACTED_FEISHU_SHEET_ID>` | `raw_feishu_table` | 无 | 已降级为历史镜像 |
| 近期利润广告 | 历史隐藏 Tab | `/api/feishu-raw-sales/data?sheet_id=<REDACTED_FEISHU_SHEET_ID>` | `raw_feishu_table` | 无 | 前端已隐藏 |
| 订单利润 Beta | 可见 Tab | `/api/feishu-raw-sales/order-profit` | `raw_feishu_table(order_profit_daily)`,`dim_product_business_state`,`dim_product` | 无 | 默认排除 archived；`product_management_status=all` 放开用于内部排查；状态字段读 B 线状态表；2026-07-08 展示层去重后仅保留最终 `生命周期` 与 `利润等级` |
| CS测品分析 Beta | 可见 Tab | `/api/feishu-raw-sales/cs-test-analysis` | `dim_product`,`fact_sales_daily`,`fact_ads_product_daily`,`fact_inventory_daily`,`cs_test_product_config` | 无 | CS 测品 DIM/FACT 聚合；`non_wfs_available_stock` 继续作为测品过程分析库存口径 |
| 产品管理 | 可见 Tab | `/api/feishu-raw-sales/product-management` | `dim_product`,`dim_product_cost_config`,`dim_product_business_state` | `dim_product`,`dim_product_cost_config` | 写负责人、WFS 配送费、产品管理状态、人工生命周期；2026-08-03 起展示「产品成本（¥）/头程运费（¥）」（读 dim_product_cost_config 最新行，只读，人民币）并支持成本状态筛选（pm_cost_status）；页面展示“系统生命周期/人工生命周期”双列，人工列默认展示系统生命周期但不写库，蓝色=人工主动覆盖且系统未变，红色=系统已变化需复核；`product_name` 已由领星本地产品详情回填，读空时仍 fallback 到 `item_name` |
| 运营日志 Tab | 可见 Tab | `GET /api/feishu-raw-sales/operation-log`、`POST /api/feishu-raw-sales/operation-log/update` | `biz_product_operation_log`,`biz_product_rule_signal_daily`,`dim_product` | `biz_product_operation_log` | GET 默认 recent7，窄化筛选查全历史；POST 是 `log_content` 唯一 UI 写入口，仅 `source='system_base' AND is_locked=0` 可写，更新 `updated_by='admin_ui'` 与 `updated_at`，迁移历史/锁定行 409 |
| 同步任务 | 历史隐藏 Tab | `/api/feishu-raw-sales/sync-tasks` | `raw_sync_tasks` | 无 | 前端入口隐藏，接口保留 |
| GPT广告查询 | Custom GPT | `/query/*` | `fact_ads_keyword_daily`,`fact_ads_product_daily`,`fact_sales_daily`,`fact_profit_daily`,`fact_inventory_daily`,`dim_product` 等白名单 | 无 | ads-ai-api 只读模板 |
| GPT经营分析 | Custom GPT | `/api/ops/analyze` | `fact_*`,`dim_product`,`dim_product_business_state` | 无 | Bearer 认证，响应 80KB 保险丝 |
| 利润ETL | 无页面 | `build_fact_profit_daily_from_raw_feishu.py` | `raw_feishu_table(order_profit_daily)` | `fact_profit_daily` | 19:30 cron，写账号限权 |
| 状态表计算 | 无页面 | `npm run build:product-business-state` | `dim_product`,`fact_profit_daily`,`fact_sales_daily`,`fact_inventory_daily`,`fact_ads_product_daily` | `dim_product_business_state` | 20:30 每日 crontab 已上线；Task H-1D 起源查询排除 archived |
| 不出单通报 | 飞书机器人 | `noOrderNotify.ts` | 领星 API + `dim_product.owner` | 飞书 webhook/操作日志 | 09:00 cron |
| 缺负责人/离职待移交/负责人冲突通报 | 飞书机器人 | `unmatchedOwnerNotify.ts` | `dim_product`,`dim_feishu_member`,`dim_product_owner` | 飞书 webhook/操作日志 | 09:10 cron |
| 离职第8天负责人清空 | 无页面 | `clearDepartedOwners.ts --execute` | `dim_feishu_member`,`dim_product`,`dim_product_owner` | `dim_product`,`dim_product_owner`,`event_product_owner_clear` | 09:00 cron |
| 经营日报/周报/月报 | 飞书机器人 | `performanceSummaryReport.ts` | `raw_feishu_table(order_profit_daily)` | 飞书 webhook/操作日志 | 已从飞书活表迁移到 MySQL |

## 数据库风险

1. 重复/备份表存在：`backup_dim_product_before_owner_fix_20260703072959`、`backup_dim_product_owner_before_owner_fix_20260703072959`、`dim_product_cost_config_cs_backup_20260707` 等，清理前必须确认。
2. 旧广告表存在：`walmart_ad_keyword_rows` 当前 0 行，`walmart_ad_tasks` 96 行；与新 `fact_ads_keyword_daily` 的边界需确认。
3. `tasks` 表当前 0 行，是否废弃需确认。
4. 多个唯一键使用前缀索引：`msku(64)`、`store_name(64/100)`、`normalized_keyword(100)`；长值存在潜在碰撞风险。
5. `fact_ads_product_daily.msku` 当前全空，按 MSKU 关联广告会失真。
6. `dim_product.product_name` 已于 2026-07-08 通过领星本地产品详情回填 1354 条，仍有 187 条未命中保持空并依赖 `item_name/sku/msku/item_id` fallback；`dim_product.store_name` 当前仍为空，需依赖其他来源。
7. （已解决 2026-07-08）`dim_product_business_state` 已推进到 2026-07-05，与 FACT 同步；20:30 每日 cron 已上线，2026-07-08 晚需复查首个 cron 触发日志。
8. `dim_feishu_member.name` 与 `dim_product.owner` 当前生产排序规则不同；凡跨表按姓名 `JOIN`/`EXISTS`/比较的 SQL，必须显式 `COLLATE utf8mb4_unicode_ci`，否则会触发 `Illegal mix of collations` 并导致离职待移交/清空链路降级。
9. `fact_ads_keyword_daily` 自动投放型广告花费系统性少算（campaignType 筛选排除 auto + CSV路仅搜索位~71%）——**2026-08-03 定性为"仅影响关键词分析维度，不影响任何算钱功能"**：全部算钱消费方（订单利润/状态表/规则信号/CS测品/GPT经营分析）实测走 `fact_ads_product_daily`（manual+auto 全，发票级审计通过），keyword 表只服务搜索词分析场景。原"V3改造"（keyword表补auto）**正式取消**，不再实施；keyword表的已知偏低作为长期已知特性记录，禁止用该表做金额汇总。

## 2026-07-09 运营日志写入口补充

- `biz_product_operation_log` 当前承担两类内容：
  - 系统基础行：`source='system_base'`，由 20:50 `build:operation-log-base` 生成/刷新基础字段。
  - 历史迁移行：`source='feishu_migration'`，保留迁移结果与人工内容。
- `log_content` 现有且仅有 1 个 UI 写入口：`POST /api/feishu-raw-sales/operation-log/update`。
  - SQL 边界：`UPDATE biz_product_operation_log SET log_content=?, updated_by='admin_ui', updated_at=NOW() WHERE id=? AND platform='walmart' AND source='system_base' AND is_locked=0`
  - 只改 `log_content/updated_by/updated_at`
  - 不改 `data_issue/solution/ai_diagnosis/owner/profit_level_snapshot/is_locked/source`
  - 锁定行或迁移历史行返回 409，不写库
- `data_issue/solution/ai_diagnosis` 当前仍无自动链路或前端入口写入；历史迁移数据保留，20:50 基础任务不覆盖这些人工字段。
- `biz_product_rule_signal_daily` 继续是只读规则信号表，仅供运营日志 Tab/GPT 展示“运营提醒”，不反向写回 `biz_product_operation_log`。

## 2026-07-08 页面数据缺失最小修复记录

- 产品管理 `product_name`：生产 `dim_product.product_name` 全空、`item_name` 全量存在。`/api/feishu-raw-sales/product-management` 已改为 SELECT `p.product_name,p.item_name`，响应 `product_name = product_name || item_name || ''`，中文“产品名称”同口径；只补响应，不写 `dim_product.product_name`。
- 2026-07-08 追加 Task D：`syncProductNameFromLingxing.ts --confirm-write` 已按 RAW-first 链路将领星 `batchGetProductInfo.data.product_name` 写入 `dim_product.product_name` 1354 条；`/api/feishu-raw-sales/product-management` 与 `/api/ops/analyze` 已能返回中文品名。未命中 187 条继续依赖 fallback。
- 产品管理 `sku`：生产 `dim_product.sku` 空 622 条，按 `platform + store_id + item_id + msku` 在 `fact_inventory_daily`、`fact_sales_daily` 未找到可回填 SKU 候选；本轮结案为“上游/FACT 无可用 SKU 来源”，不做自动回填。后续若要继续修复，应从领星 RAW/API 其他 SKU 字段重新探源，且一品多 MSKU 时必须标记 ambiguous，不得按 item 级自动写入。
- 2026-07-08 Task E 导出空 SKU 清单 `/opt/lingxing-auto/reports/empty_sku_products_20260708104804.csv`，行数 622；仅用于运营排查，未写 `dim_product.sku`，未用 MSKU/baseSku 修复 SKU。`taskD_match_status/taskD_skip_reason` 优先关联最新 Task D CSV，无法关联填 `unknown`。
- 每日销售明细 `owner`：`raw_feishu_table.sheet_id='<REDACTED_FEISHU_SHEET_ID>'` 中存在历史空值。接口已仅对 `<REDACTED_FEISHU_SHEET_ID>` 页面结果做展示级补齐：从 raw 行解析 `store_name/item_id/msku`，按 `store_name` 唯一映射 `store_id` 后批量查 `dim_product`；MSKU 存在时按全键取 owner，MSKU 为空时仅在 `store_id + item_id` 唯一 owner 时补齐；ambiguous/unresolved 保持空。该逻辑不写 RAW/DIM。
- 每日销售明细 `msku`：`syncLingxingToRawFeishu.ts` 原 `COALESCE(f.msku, a.msku, inv.msku, dp.msku, '')` 会被广告 FACT 空字符串截断，已改为 `COALESCE(NULLIF(...,''), ...)`。2026-07-08 已对 `<REDACTED_FEISHU_SHEET_ID>` 近 7 个业务日 `2026-06-29` 至 `2026-07-05` 执行明细 RAW 幂等重跑；重跑后 7 日共 5617 行，MSKU 空 308 行（约 44/日），这些为上游/维表仍无法解析的剩余空值。

## 2026-07-13 / 方案B与批C数据口径补充

- `raw_feishu_table` 日期字段口径存在 sheet 差异：`sheet_id='<REDACTED_FEISHU_SHEET_ID>'` 使用独立列 `data_date`；`sheet_id='<REDACTED_FEISHU_SHEET_ID>'`（每日销售明细）日期在 `row_json."日期"`，无独立 `data_date` 可用。跨 sheet 查询、对账或回溯验收不得混用这两个日期口径。该差异为 2026-07-12 快照对比时实测踩坑记录。
- `event_product_rule_signal_notify` 是批C规则信号通报 EVENT 层，当前 21 列，核心字段包括 `signal_fingerprint`、`send_status`、`notify_count`、`last_notified_at`。`signal_fingerprint` 用于同批次/跨批次去重，`notify_count` 与 `last_notified_at` 用于通知次数和最近通知时间判断；当前仅 2026-07-09 首批 355 行，`send_status='sent'`，批C仍处于手动试跑观察期，尚未转正接 cron。



## 2026-07-14 / WFS到货提醒数据表

新增三张表，来源链路遵循“外部数据 -> FACT/EVENT -> 通报脚本”分层，本阶段保留 WFS 货件头与商品明细快照、事件层幂等记录。

| 表 | 层级 | 主粒度 | 关键唯一键 | 写入方 | 说明 |
|---|---|---|---|---|---|
| `fact_wfs_shipment` | FACT | `platform + store_id + shipment_id` | `uq_wfs_shipment(platform,store_id,shipment_id)` | `syncWfsShipments.ts` | WFS 货件头快照，UPSERT 覆盖状态列；保存状态、状态时间、货件单号、API 更新时间等。 |
| `fact_wfs_shipment_item` | FACT | `platform + store_id + shipment_id + msku` | `uq_wfs_shipment_item(platform,store_id,shipment_id,msku(64))` | `syncWfsShipments.ts` | WFS 货件商品明细，保存申报量、发货量、签收量、损坏量、SKU/MSKU/GTIN。 |
| `event_arrival_notify` | EVENT | `event_type + biz_key` | `uq_arrival_event(event_type,biz_key)` | `syncWfsShipments.ts`、`buildArrivalEvents.ts`、`arrivalNotify.ts` | 到货提醒事件，`notify_status` 为 `pending/notified/skipped/failed`；通知脚本只允许回写 `notify_*` 字段。 |

事件类型当前包括：`wfs_shipment_receiving`、`wfs_shipment_closed`，后续 R2/R3/R4 由 `buildArrivalEvents.ts` 基于库存与广告数据生成。

### 清货审批与清货中心（2026-07-20 批①②）
| 表 | 层 | 业务键 | 唯一约束 | 写入方 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `event_clearance_approval` | EVENT | `platform + store_id + item_id`（应用层保证单 pending） | 无库级唯一（status流转） | `feishuRawSalesRoutes update-lifecycle`（写pending/cancelled）、`feishuCardCallbackRoutes`（approved/rejected）、`clearanceApprovalNotify`（notify_*） | 清货申请审批事件。status: pending/approved/rejected/cancelled/legacy（存量82个自动视为已审批）。metrics_json=申请时快照。⚠️必须 COLLATE utf8mb4_unicode_ci |
| `biz_clearance_other_channel` | BIZ(人工台账) | `platform + store_id + item_id` | `uq_item(platform,store_id,item_id)` | `clearanceCenterRoutes`（仅人工操作） | 其他渠道清货台账。channel_note/amazon_asin/remark 为人工字段禁止同步覆盖。status: active/done/removed |

审计事件类型新增：`pm_manual_change` 沿用（field=clearance_apply）、`clearance_manual_change`（清货台账操作）。

## 2026-07-23 / 飞书表格(raw_feishu_table)退役现状核查（只读实扫）

部署AI只读实扫，截至 last_pulled 2026-07-22。列名确认：`sheet_id/sheet_name/row_index/row_json/data_date/pulled_at/raw_hash/extra_json`。

| sheet_id | 用途 | rows | last_data_date | last_pulled | 结论 |
|---|---:|---:|---|---|---|
| `order_profit_daily` | 订单利润Beta系统快照 | 111850 | 2026-07-20 | 2026-07-22 16:56 | 在用(系统自造RAW,非真飞书) |
| `<REDACTED_FEISHU_SHEET_ID>` | 每日销售明细 | 67886 | NULL | 2026-07-22 16:55 | 在用(系统快照) |
| `<REDACTED_FEISHU_SHEET_ID>` | 当日数据 | 912 | NULL | 2026-07-22 16:55 | 仅系统快照,非可见主功能 |
| `<REDACTED_FEISHU_SHEET_ID>` | 近期利润与广告 | 931 | NULL | 2026-07-22 16:55 | 仅系统快照,非可见主功能 |
| `<REDACTED_FEISHU_SHEET_ID>` | 每日运营跟进日志 | 4518 | 2026-07-04 | 2026-07-08 17:03 | 已停用僵尸 |
| `<REDACTED_FEISHU_SHEET_ID>` | ItemID负责人 | 1994 | 2026-07-07 | 2026-07-07 16:31 | 已停用僵尸 |
| `<REDACTED_FEISHU_SHEET_ID>`(别名残留) | 销售明细历史别名 | 19992 | NULL | 2026-06-29 16:36 | 系统快照历史别名残留脏数据 |

要点：`order_profit_daily`/`<REDACTED_FEISHU_SHEET_ID>` 是系统自造快照仍在用；`<REDACTED_FEISHU_SHEET_ID>`/`<REDACTED_FEISHU_SHEET_ID>` 仍被 16:45 backfillDailyChain 刷新但非可见主功能；`<REDACTED_FEISHU_SHEET_ID>`(停2026-07-07)/`<REDACTED_FEISHU_SHEET_ID>`(停2026-07-08) 为僵尸。真飞书在线表无 active cron 写入。清理/退役需单独指令（不删历史）。详见 TASK_CHANGE_LOG 2026-07-23 节。

## 用户名/权限（应用登录，2026-07-25）

建表 DDL：`sql/022_app_auth_tables.sql`（全 IF NOT EXISTS，不动 `dim_access_password`）。下列字段以该 DDL 为准，部署AI已在生产执行。分层：`dim_app_user`/`dim_app_user_permission` 属 DIM，`biz_app_audit_log` 属审计（EVENT）；前端只读、AI 不写这些表。鉴权/登录流程见 SYSTEM_MAP「统一登录/SSO」节。

### dim_app_user（登录用户，DIM）
主键 `id`；唯一键 `uq_username(username)`；索引 `idx_member(feishu_member_id)`/`idx_role`/`idx_team`。
- `username` VARCHAR(64) 登录名（=飞书真名，唯一）
- `password_hash` VARCHAR(255) bcrypt，永不明文；占位值 `'!'` 表示未设密（需首登设置）
- `display_name` VARCHAR(128) 显示名
- `feishu_member_id` VARCHAR(64) 关联花名册（当前存 open_id；先留列不加 FK）
- `role` VARCHAR(32) 默认 member：admin/supervisor/team_lead/member
- `team_name` VARCHAR(64) 所属组（组织架构，未来数据可见性用）
- `is_active` TINYINT 停用即不可登录（离职置 0，不删行）
- `is_superadmin` TINYINT 超管，绕过一切权限
- `token_version` INT 默认 1；改密+1 使已签发 JWT 立即失效
- `must_change_password` TINYINT 首登强制改密
- `remark` VARCHAR(255) 人工备注（铁律：不可覆盖运营人工记录）
- `created_at` / `updated_at`

### dim_app_user_permission（操作权限映射，DIM）
主键 `id`；唯一键 `uq_user_perm(user_id, perm_key)`；索引 `idx_perm`。逐条授权 `(user_id, perm_key, granted_by, granted_at, remark)`。
- 已登记 perm_key：`clearance_approval` = 清货审批（授林翔）
- 预留 perm_key：`download`（数据下载）、`business_target`（业绩目标，仅林翔）、`clearance_exemption`（绩效台账豁免，尚未接）

### biz_app_audit_log（操作审计，EVENT）
主键 `id`(BIGINT)；索引 `idx_user_at(user_id,at)`/`idx_action_at(action,at)`。字段 `at, user_id, username, action, target, detail_json(JSON), ip, ua`。
- action 取值：login / login_fail / logout / change_password / reset_card_sent / download / target_edit …

env 变量（只读环境变量，禁硬编码）：`AUTH_JWT_SECRET`（JWT 密钥）、`AUTH_ENABLED`（=1 启网关）、`COOKIE_SECURE`（HTTPS 后置 1）、`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`。

## 2026-07-24 / CS测品异常预警 + 绩效台账人工层

### biz_cs_test_alert（EVENT层，CS测品异常预警台账）
- 唯一写入方 csTestAlertNotify.ts。触发：(测品天数>20 或 累计销量>11) 且 未结束(test_end_date NULL)，工作日检测。【2026-07-29放宽 AND→OR】
- 键：UNIQUE uq_cs_alert(platform,store_id,item_id,msku(64))，一产品一预警行。
- 列：owner_name；test_days_snapshot/sales_qty_snapshot/first_ad_date_snapshot(触发快照)；first_alert_date/last_sent_date/send_count(流程)；reason/reason_by/reason_at(人工填≥15字，系统不覆盖)；status enum('open','resolved','closed_test_ended')；penalty_count。
- reason 人工列：飞书卡或 CS测品分析页「预警原因」列填写，填即消警(status=resolved)。

### biz_perf_deduction_note（人工层，绩效台账逐笔说明+豁免）
- 一对一挂 biz_perf_deduction.id：UNIQUE uq_note_ref(ref_deduction_id)。biz_perf_deduction 保持 append-only 零改动。
- 列：ref_deduction_id；ym；explanation/explanation_by/explanation_at(本人填绩效说明)；exempt_status(1=已豁免不计合计)/exempt_by/exempt_at/exempt_reason。
- 豁免=exempt_status=1 不删原扣分行；绩效台账汇总"扣分合计/净分"排除已豁免。窗口：该扣分所属月的次月5号(含)前可填说明/豁免。

## 2026-07-27 / 产品管理提醒通知 绩效扣分状态机（3 张 EVENT 表）+ biz_perf_deduction 唯一键升级

唯一写入方 unmatchedOwnerNotify.ts(周一/四 09:10 cron)；镜像 event_owner_claim_alert：cycle_start_date→first_notified_at→second_notified_at(deduction_points=5)→owner_name/deducted_at→closed/void。均 append，remark 人工备注系统不覆盖，COLLATE utf8mb4_unicode_ci。

- event_wfs_fee_missing_alert（缺WFS配送费, SQL027）：active·非CS·人工(dim_product_cost_config.delivery_fee)与自动(dim_product_wfs_fee_auto.fee)均缺。UNIQUE uq_wfs_cycle(platform,store_id,item_id,msku(64),cycle_start_date)。归负责人。
- event_gpt_kw_missing_alert（缺GPT关键词链接, SQL028）：active·有负责人·未配 dim_product_gpt_link(link_type='keyword')。含CS。UNIQUE uq_kw_cycle(同上)。
- event_gpt_ads_missing_alert（缺GPT广告链接, SQL028）：active·有负责人·WFS库存连续14天>0(fact_inventory_daily 近14天 MIN(wfs_available_stock)>0 且覆盖14快照日)·未配 dim_product_gpt_link(link_type='ads')。UNIQUE uq_ads_cycle(同上)。
- biz_perf_deduction 唯一键升级(SQL027)：uq_perf_ref (ref_event_id)→(ref_event_id, biz_type)。原因：多EVENT表自增id重叠，仅ref_event_id会跨类型 INSERT IGNORE 静默丢扣分；加biz_type隔离，现有行无冲突。
- biz_perf_deduction.biz_type 取值：unclaimed_product / missing_wfs_fee / missing_gpt_keyword / missing_gpt_ads / monthly_plan_unfilled（2026-08 M3：月度规划未填每日扣分，每人每天5分·8号起，ref_event_id→event_monthly_plan_unfilled.id）。

### dim_app_user_permission 权限键登记
- clearance_approval = 清货审批(授林翔)。绩效台账豁免当前为软鉴别(前端选人)，用户名系统成熟后可换 perm_key=clearance_exemption。


## 2026-08-04 / 月度规划未填 每日扣分（M3，目标管理8月新规）
- `event_monthly_plan_unfilled`（EVENT，SQL029）：月度规划未填每日扣分事件，**每人每天一行**。唯一键 `uq_mpu_daily(deduction_date, platform, owner_name)`；字段 plan_month、deduction_date、platform、owner_name、unfilled_count(审计:当日该负责人未完成品数)、points(=5)。
- 唯一写入方 `checkMonthlyPlanDeduction.ts`（每日 09:25 --confirm-write，8号起）：扫描 在营·非CS·非新品·v5非豁免 且未完成(无 biz_monthly_plan 行 或 target_sales_amount 空) 的产品，按负责人 GROUP BY → 每负责人每天 INSERT event(ON DUP id=LAST_INSERT_ID) + INSERT IGNORE biz_perf_deduction(biz_type='monthly_plan_unfilled', ref_event_id=事件id, points=5)。**每人每天固定 5 分**(与未填个数无关、不封顶)。完成定义=有行且 target_sales_amount 非空(勾"正常运营"也需填)。
- 层级 EVENT→镜像 biz_perf_deduction(BIZ)；AI/同步禁改；append-only。

## 2026-08-10 / P7数据完整性哨兵（SQL040）
- `event_sentinel_alert`（EVENT，SQL040）：哨兵异常事件,报警/确认/执行/复查全程留痕。唯一键 `uq_sentinel(check_key,target_date)`;status(open/manual/resolved)、attempt_count(自动修复次数,满2转人工)、remind_count、remark人工列。
- 写入方：checkDataSentinel.ts(主检/提醒cron)+feishuCardCallbackRoutes(biz=sentinel_fix,确认/闭环)。
- 修复白名单(sentinelCore.runRepair,系统代码非AI)：sales_family_eq→重跑销量FACT+订单利润RAW+利润ETL;<REDACTED_FEISHU_SHEET_ID>_rows→明细重生成;inventory_snapshot→今日拉取/历史日以最新快照补录(source_system='sentinel_backfill',2026-07-18护栏的显式例外通道);channel_presence→渠道同步;msku_blank无自动修复(SOP:=未配对listing出单,处理=领星配对+回填)。

## 2026-08-10 / 销量统一口径定稿（需求方拍板，长期有效）
- **权威销量口径 = saleStat 族**：`fact_sales_daily`(saleStat) → <REDACTED_FEISHU_SHEET_ID>明细(派生)；订单利润RAW → `fact_profit_daily`(ETL)。族内日度数值**必须完全相等（零容差）**，P7哨兵不等即报警。与领星"销量统计"UI同源，为运营对账基准。
- **`fact_mp_sales_channel_daily` = WFS/非WFS判定专用**（v5豁免判定依赖其wfs_sales_qty），**禁止**用于销量/金额统计与跨源对比；与saleStat族存在日期归因口径差(月度±3%内)属两接口源特性，非数据缺陷。
- 6月数据结案：销量无真丢(归因差)；广告无缺口(补的全是零花费行)；<REDACTED_FEISHU_SHEET_ID>明细6/1-26已重生成(30天全)；库存快照7/16-17缺失为快照型不可修；渠道表6/1起、利润FACT 5月起，更早月份无对照。
- 命名治理B待执行(见PROJECT_CONTEXT待办5)：sheet_id '<REDACTED_FEISHU_SHEET_ID>'→语义名迁移，与订单利润V2同排期；迁移前文档一律「每日销售明细RAW(<REDACTED_FEISHU_SHEET_ID>)」双写。

## 2026-08-05 / 归档产品到货提醒（交互卡片）
- `event_archived_restock_alert`（EVENT，SQL039）：归档且最新快照 WFS>阈值(默认5,env ARCHIVED_RESTOCK_MIN_WFS) 的提醒事件。唯一键 `uq_ar_item(platform,store_id,item_id)` 每产品一行；decision(''/restore/keep)、decided_by/at、wfs_qty=最近提醒/确认时库存基线、remark 人工备注(系统不覆盖)。
- 写入方：checkArchivedRestockAlert.ts(每日09:40 --send,登记/刷新+发卡) + feishuCardCallbackRoutes(biz=archived_restock,仅写 decision/decided_by/at)。
- 规则：keep=暂停提醒；当日 WFS>基线 → 脚本 upsert 将 decision 清空(decided_by/at 留历史)重新发卡；restore → dim_product 转 active(source='card')。卡片按钮权限=负责人/超管。

## 考勤表（AI人力，2026-07-30）

- `raw_feishu_attendance`（RAW）：飞书考勤三接口原始响应留存。字段 api_type(user_tasks/user_flows/user_approvals)、date_from/to、payload_json、raw_hash(唯一去重)、pulled_at。
- `fact_attendance_daily`（FACT，派生）：每人每天一行。唯一键 `uq_day_user(stat_date, open_id)`。字段 stat_date、open_id、user_id、name、group_id、shift_id、is_scheduled(是否排班工作日)、check_in/out_time、last_punch_time、check_in/out_result、late_minutes、early_minutes、overtime_minutes(打卡超时)、leave_type、leave_hours、out_hours、day_status(正常/迟到/早退/缺卡/旷工/请假/休息/免打卡)。
- 层级：RAW→FACT；前端只读 FACT（禁直查 RAW）；AI 不写。同步 `syncFeishuAttendance.ts`（每日00:45 --daily --write）。口径见 SYSTEM_MAP 2026-07-30 节。
- 权限：`dim_app_user_permission` perm_key `hr_attendance`（授黄少如；超管绕过）。帮助 `dim_page_help(page_key=attendance)`。
- `event_attendance_lack_alert`（EVENT，缺卡通报，2026-07-30）：每人每天一条缺卡告警。唯一键 `uq_day_user(stat_date, open_id)`。字段 stat_date、open_id、user_id、name、lack_type(上班/下班/双缺)、ack_status(pending/confirmed/expired)、push_at、resend_at、confirmed_at、locked_at。员工确认态单独存(不改 FACT，每日同步会覆盖)；月度核算 LEFT JOIN 该表：缺卡 expired→计旷工。

## 表↔唯一写入方映射（2026-07-31 增量，7月下旬新增/活跃表）

规则（强制）：**每张新表建表时必须在本节登记「唯一写入方」与「禁止覆盖字段」**；出现第二写入方=设计缺陷，须先改设计。

| 表 | 层 | 唯一写入方 | 读取方 | 禁止覆盖/人工字段 |
| --- | --- | --- | --- | --- |
| raw_feishu_attendance | RAW | syncFeishuAttendance.ts(00:45) | 派生用 | 只追加不改 |
| fact_attendance_daily | FACT | syncFeishuAttendance.ts(00:45,当月+上月覆盖重算) | attendanceRoutes, attendanceLackAlert | 无人工字段(确认态在EVENT) |
| event_attendance_lack_alert | EVENT | attendanceLackAlert.ts(建卡/锁定/重发) + 回调lack_ack(仅ack_status/confirmed_at) | attendanceRoutes /monthly JOIN | 确认态不得被同步覆盖 |
| ai_ops_log_review_item/summary | AI | aiOpsLogReview.ts(周四23:00; --purge-week 需显式授权) | hrRoutes /perf/* | remark 人工列 |
| biz_monthly_plan | BIZ | aiBusinessRoutes POST /monthly-plan(页面单条+批量导入同接口) | 目标管理页/清货中心目标/催办 | 全表=人工录入,同步任务禁写 |
| biz_perf_deduction | BIZ | 绩效链(performanceSummaryReport/规则扣分)+hrRoutes manual-entry(biz_type=manual)+checkMonthlyPlanDeduction(biz_type=monthly_plan_unfilled) | 绩效台账页 | 人工录入行禁自动改 |
| event_monthly_plan_unfilled | EVENT | checkMonthlyPlanDeduction.ts(09:25 --confirm-write,8号起) | biz_perf_deduction 镜像 | 每人每天一行,append-only |
| event_archived_restock_alert | EVENT | checkArchivedRestockAlert.ts(09:40)+卡片回调(仅decision) | 提醒去重/基线 | remark 人工列;decision仅回调写 |
| event_sentinel_alert | EVENT | checkDataSentinel.ts(20:15/整点)+回调sentinel_fix | 哨兵提醒去重/审计 | remark 人工列 |
| biz_perf_cert | BIZ | hrRoutes manual-entry(凭证图LONGBLOB) | /perf/cert/:id(本人+超管/人事) | 只增 |
| event_clearance_approval | EVENT | clearanceApprovalNotify+回调clearance_approval | 清货中心 | 决策字段仅回调写 |
| event_clearance_card | EVENT | clearanceCardsNotify+回调clearance_card | 清货中心 | acted_* 仅回调写 |
| biz_cs_test_alert | BIZ | csTestAlertNotify(--detect)+回调cs_test_alert(reason) | 通报/审批人转发 | reason/reason_by 仅回调写 |
| dim_app_user / _permission / _role | DIM | authService/rosterRoutes(管理操作) | authMiddleware 全站 | password_hash/token_version 仅auth链 |
| dim_page_help | DIM | SQL迁移(人工,sql/0xx_help_*.sql) | HelpCenter | content_md 以迁移为准 |
| config/apiKeyProfiles.json(文件) | 配置 | apiKeyManager.ts(:3456,仅陈佳聪) | 同左+.env切换 | — |
| fact_storage_weekly_charge | FACT | expandStorageFeeDaily.ts(步骤0·RAW提取,导入钩子/手动触发) | expandStorageFeeDaily 分段日摊、结算对账 | 无人工字段;幂等upsert不删历史 |

既有核心表（dim_product 的 manual_lifecycle_*/product_management_status 人工保护、fact_* 链路写入方等）见上文各表详节，口径未变。

---

## 库存成本 · 双口径边界（2026-08-01 立规，运营AI×财务工程师协同）

> ⚠️ 库存成本有两套，**严禁混用**。库存一览表/PMC 等运营页用「固定值成本」，财务核算用「批次成本（实际发生）」。

### 口径一：固定值成本（运营口径，**非财务**）
- 表：`dim_product_cost_config`
- 字段：`purchase_cost`（采购成本·**不含头程**，来源领星 `batchGetProductInfo` 的 `cg_price`）、`first_mile_shipping_cost`（**头程**，来源 `product_logistics_relation[US_cg_transport_costs]`）、`delivery_fee`（WFS配送费）
- 键：`uq_dim_product_cost(platform, store_name(64), item_id, msku(64), effective_date)`
- 性质：**产品维度的固定配置/估算值**，来自产品管理，不随实际入库批次变化。
- 用途：PMC 库存一览表、运营端库存货值**估算**、决策参考。货值口径：已采购/本地仓库=数量×`purchase_cost`；在途/WFS在库=数量×(`purchase_cost`+`first_mile_shipping_cost`)。
- **禁止用于财务端核算**。凡运营页展示此货值，必须显式标注「按固定值成本估算，非财务口径」。
- 覆盖现状（2026-08-01 探测）：`dim_product_cost_config` 2026 行，`purchase_cost`/`first_mile_shipping_cost` 双非空 1711 行（84.45%），缺口多为新品未回填。

### 口径二：批次成本（**财务口径 · 实际发生**）
- API：领星「查询批次明细」`/erp/sc/routing/data/local_inventory/getBatchDetailList`（POST，令牌桶1）
- 请求参：`offset/length(≤400)/show_zero_stock/wids(仓库id)/stock_in_type_list(22采购入库,24调拨入库,23委外入库,25盘盈,16换标,17加工,18拆分,26退货,27移除,45赠品,19其他)/search_field/search_value`
- 关键返回字段：`batch_no`批次号、`source_batch_no`源头批次号、`order_sn`入库单号、`type/type_name`入库类型、`sku`、`store_id`、`purchase_in_time`入库时间、`purchase_price`采购单价、`head_stock_price`头程单价、`stock_price`库存成本单价、`head_stock_cost`头程、`stock_cost`库存成本、`amount`货值
- 性质：**逐批入库真实计价的实际发生成本**（批次×入库单×入库类型×入库时间粒度）。
- 用途：**财务端库存成本核算**（由财务工程师主导取值/定口径）。
- 分层落库（如接入）：先入 RAW(`raw_lingxing_api`) → 独立 FACT（表名/口径由财务工程师定，例如 `fact_inventory_batch_cost`）→ 财务端读取。**不得覆盖 `dim_product_cost_config`**，两表并存、各管一口径。

### 协同分工
- 运营AI（代码侧）：负责运营端「固定值成本」展示与库存一览表，配合财务对齐字段/边界。
- 财务工程师：负责「批次成本（实际）」取值、FACT 表设计与财务口径，**另在 context 记录**。
- 边界铁律：运营页货值只用固定值成本且须标注非财务；财务核算只用批次成本；两者不互相覆盖、不互相引用为准。


---

## 库存一览表 · 本地仓/采购归属与分摊口径（2026-08-01 立规）

- 本地仓库=`fact_local_inventory_daily.qty`、已采购=`fact_purchase_order_item.quantity_receive`，二者均为**本地SKU级共享池**（一个本地SKU 常对应多个 ITEMID/店铺 listing）。
- 归属 ITEMID 规则（库存一览表按 ITEMID→MSKU×店铺 展示时）：
  1. **已明确归属**：若该采购/本地库存已明确归属某 ITEMID（或该本地SKU 1:1 只对应单一 ITEMID）→ **直接归属该 ITEMID**，不分摊。
  2. **未明确**：该本地SKU 跨多个 ITEMID 时 → 按各 ITEMID **近30天销量**占比**分摊**共享池数量（销量口径与看板一致；近30天全为0时的兜底另议）。
- **CS测品**（`msku` 以 `CS` 开头）：一个本地SKU 可对应大量 item_id（探测见 1 SKU→422 item），**属正常非脏数据**，且 CS测品**无 WFS 库存**；库存一览表主视图以 WFS 业务为主，CS测品沿用既有 CS 口径单独处理，不并入常规 30 天销量分摊。
- **远期**：采购将改为按 **店铺+ITEMID** 直接提交采购需求，届时采购/在途天然带 ITEMID 归属，无需分摊（现状未实现，故当前用 30 天销量分摊过渡）。


---

## 库存一览表 · 四桶数据源与库存数量公式（2026-08-02 定稿；成本本期不做）

- **库存数量 = 已采购 + 本地仓库 + 在途 + WFS在库**；非WFS 独立展示（不计入库存数量）。四桶来源：
  - 本地仓库（SKU级共享池）：`fact_local_inventory_daily.qty`（最新快照，按 sku）。
  - 已采购/未到货（SKU级共享池）：`fact_purchase_order_item` Σ(quantity_real − quantity_receive)，WHERE quantity_real>quantity_receive AND 采购单 status_text 非作废 AND status_shipped_text<>'已到货'，按 sku（口径同现网 PMC「采购中」的采购部分）。
  - 在途（MSKU×店铺级）：`fact_wfs_shipment`(未完结: to_closed_time IS NULL AND to_cancelled_time IS NULL) JOIN `fact_wfs_shipment_item`，Σ max(declare_num − received_num,0)，按 store_id×msku，经 `dim_product` 映射 item_id。
  - WFS在库（MSKU×店铺级）：`fact_inventory_daily.wfs_available_stock`（最新快照，按 store×item×msku）。
  - 非WFS（MSKU×店铺级·独立）：`fact_inventory_daily.non_wfs_available_stock`。
- **归属/分摊**：SKU级两桶（本地仓/已采购）→ 1:1 直归对应 ITEMID；1:多按各 item 近30天销量(`fact_sales_daily.sales_qty`)占比分摊，30天全0时均摊兜底。在途/WFS/非WFS 天然 MSKU×店铺级、直接摊到子行、不分摊。
- **【在途×WFS 不重叠·已验证 2026-08-02，probeInTransitOverlap】**：在途已扣 `received_num`；签收即进 WFS（实测 received≈wfs_available，如 YC00010-1U 792=792、YC00019-1U 1273≈1272）。360 在途行中仅当天收货产生 7 行滞后红旗 + 9 行「已签收未上架」缺口，均单同步周期自愈、量级可忽略。→ **四桶相加无系统性双算，加法成立**。
- **排除**：虚拟品（XY2007/XY2038 等、sku 空）比照现网 PMC EXCLUDE_SKUS 排除；CS测品（msku CS 开头、无WFS）不并入常规视图。
- **成本/货值本期前端不做**，仅展示数量（四桶 + 库存数量 + 非WFS）；成本按已立规双口径（固定值/批次）后续接入。


## ⚠️ 字段语义陷阱：fact_purchase_order_item.quantity_receive = 待收/未到货量（不是已收量！）2026-08-03 核对领星确认
领星 purchaseOrderList 的 quantity_receive **实为"待收货/未到货量"**，非字面"已收货量"：
- 未到货单(status_shipped_text='未到货')：quantity_receive = quantity_real（全额待收）
- 全部到货单(status_shipped_text='全部到货')：quantity_receive = 0（无待收）
- 领星状态真实取值：status_text ∈ {已完成,待到货,已作废}；status_shipped_text ∈ {全部到货,未到货}（**无"已到货"这个值**）
正确「采购在途」口径：`SUM(quantity_receive) WHERE status_text NOT LIKE '%作废%'`（+可选90天防陈年脏单）。
反面教训：原 pmcRoutes/pmcInventoryRoutes 用 `SUM(quantity_real−quantity_receive) … status_shipped_text<>'已到货'`，双重错——全部到货单反被全额计入(YC00002 9660应为0)、未到货单被丢弃；全局虚高 24万+ vs 真实 7839。已两处修正。


## ⚠️ 本地仓陷阱：inventoryDetails 含"幽灵仓"，本地仓库只算有效仓（2026-08-03 核对领星）
领星 /erp/sc/routing/data/local_inventory/inventoryDetails 会按"SKU×仓库(wid)"返回，**含已删除/历史"幽灵仓"**（如 wid 26724/28030/27159 里有库龄百天的呆滞残留）。而领星「仓库列表」/erp/sc/data/local_inventory/warehouse **只有 2 个有效仓：惠州仓库 wid=16168、深圳仓 wid=27645**（type=1,is_delete=0）。
- 症状：某 SKU 本地仓库虚高，但领星仓库库存(筛惠州/深圳)为 0——差额全在幽灵仓。
- 修复：syncLocalInventory 聚合前先拉仓库列表取有效 wid(is_delete=0)，只汇总有效仓的 product_valid_num；幽灵仓一律不计。兜底 wid=[16168,27645]。
- fact_local_inventory_daily 只存按SKU汇总值(无wid)，故过滤必须在同步层，改后需重跑同步刷新当日快照。
## 2026-08-11 / dim_product_business_state 回填标注 & 哨兵第⑥检查
- 07-01/02/04 三天为哨兵近似回填行（各756行）：`extra_json.backfill='sentinel_20260811_approx'`。用当前 dim_product 清单/归档态回算，现已归档品无行（当时真实快照约1500行，需求方拍板接受边界不追补）。读取方区分真实快照与回填行以此标记为准。
- 该表 stat_date=构建当天的最新可用业务日（=当天T-2），非运行日；P7哨兵第⑥检查 business_state_snapshot 因此定 T-3（20:15 时点库内最新）。
## 2026-08-11 / ai_monthly_issue_item 唯一键+生成器upsert（9/4前上线完成）
- 唯一键 `uq_issue(plan_month, platform, store_id, item_id)`（2026-08-11 上线,加键前全表 dup=0）。
- 唯一写入方 `scripts/generate_monthly_report.py` register_all：INSERT→ON DUPLICATE KEY UPDATE（唯一键四列不刷；report_id/owner/msku/issue_reasons/suggested_action/metrics_json 六列就地刷新）+收尾 DELETE 同月 report_id≠本次 残留行→同月清单恒=最新一次生成。重跑真实月份仍需需求方批准。
- `ai_business_report` 保持追加不去重（运行史）。表列 DESCRIBE 核实无人工备注列，残留行 DELETE 安全。

---

## AI财务 / SEM / 权限层（2026-08 批7~13 补录）

> 最后核对：2026-08-13（本会话逐表 SHOW COLUMNS + 只读聚合探针实证）。
> 分层链路与 AI 边界：见 `PROJECT_CONTEXT.md`「数据分层与 AI 边界（唯一权威定义）」。本文件只引用、不复述（2026-08-14 收敛：此处原有第二套定义与 PROJECT_CONTEXT 冲突，且曾授权「AI 只写 AI/BIZ 层」，现已撤销——AI 不写 BIZ）。

### RAW层（新增）
| 表名 | 用途 | 来源 | 备注 |
|---|---|---|---|
| `raw_walmart_storage_csv` | WFS 仓储费报告原始行 | Seller Center WFS 仓储 CSV | 批4；row_no=0 为汇总/门禁行；task_id=WMSTOR-YYYYMMDD-序号 |
| `raw_walmart_inbound_csv` | WFS 入库运输报告原始行 | Seller Center WFS 入库运输 CSV | 批5；task_id=WMINB-YYYYMMDD-序号 |
| `raw_walmart_sem_csv` | SEM 广告 CSV 原始行 | 广告系统 SEM 导入 | csv_type 区分报表；task_id 关联 |
| `raw_lingxing_api` | 领星 API 响应留存 | 领星 | 汇率/批次/采购/发货单/结算同步均 RAW-first |

### DIM层（新增）
| 表名 | 核心字段 | 唯一键/口径 | 最后核对 |
|---|---|---|---|
| `dim_store_config` | `platform,store_id,store_name,advertiser_id,advertiser_name,commission_rate,is_active` | 领星侧店铺配置；**store_id 与 dim_store 同源同值**（批12b 实证 config↔dim 全 SAME）；结算/采购店铺归属以此为准 | 2026-08-13 |
| `dim_sem_campaign_item` | `platform,store_id,campaign_id,item_id,campaign_name,source` | SEM 广告位 campaign_id→item_id 映射（昨日新建） | 2026-08-13 |
| `dim_page_help` | `page_key,content_md,updated_by` | 帮助中心壳内文；page_key 幂等 upsert，不删历史 | 2026-08-13 |
| `dim_app_user` | `id,username,display_name,role,team_name,is_superadmin,is_active,token_version` | 账号；is_superadmin 或角色「超管」=超管 | 2026-08-13 |
| `dim_app_user_role` | `user_id,role_key,granted_by` | 角色：超管/运营主管/运营组员/财务/中台/人事 | 2026-08-13 |
| `dim_app_user_permission` | `user_id,perm_key,granted_by,remark` | 细粒度权限；perm_key 如 finance_fx(汇率写)/finance_import(仓储/入库导入白名单)/clearance_approval/hr_attendance | 2026-08-13 |

### FACT层（新增 · AI财务）
| 表名 | 核心字段 | 键/口径 | 最后核对 |
|---|---|---|---|
| `fact_lingxing_fx_rate` | `rate_month,currency_code,rate_org,my_rate,lx_update_time` | 领星汇率；**my_rate=主口径**（领星「我的汇率」，算 WFS 成本同源）；折算取归属月**上一月** my_rate，退 rate_org。312 行 | 2026-08-13 |
| `fact_lingxing_batch` | `sku,wh_name,batch_*,stock_cost,balance_num` | 领星批次成本；资产口径取 `wh_name='惠州仓库' Σstock_cost(balance_num>0)`；338批/217SKU 恒等自检0不符 | 2026-08-13 |
| `fact_purchase_cash` | `order_sn(UNI),order_time,create_time,date_source,status_text,amount_total,goods_amount,shipping_amount,creator,currency_code` | 采购单头（现金线）；记账日=order_time(空退 create_time)；status_text='已作废'排除。713单 | 2026-08-13 |
| `fact_purchase_cash_item` | `order_sn(MUL),sku,msku,product_name,sid,quantity,unit_price,amount` | 采购单品；CNY；**msku 100% 为空**（拆 item_id 需靠头程 delivery_num）；sid=0 为历史无店铺归属（新单8月起自带店铺），按发货单 sku 份额回填 | 2026-08-13 |
| `fact_shipping_first_let` | `shipping_code,store_id,cargo_code,msku,sku,gtin,item_id,delivery_num,value_source,per_first_let_cost,cash_date,match_status` | 头程分摊（发货单实际费用按品）；**带 item_id**；头程现金=cash_date≥切点 × matched × 非预估 × per_first_let_cost*delivery_num；CNY。920条 | 2026-08-13 |
| `fact_wfs_shipment` | `cargo_code,shipment_id,store_id,store_name,inbound_order_id,status,cargo_*_time` | WFS 货件头 | 2026-08-13 |
| `fact_wfs_shipment_item` | `shipment_id,store_id,msku,sku,gtin,product_name,declare_num,shipments_num,received_num` | WFS 货件明细；有 sku+msku+**gtin**（无 item_id 列，gtin→item_id 1:1）；shipments_num 可作 SKU→item_id 发货分摊依据 | 2026-08-13 |
| `fact_wfs_storage_fee` | `store_id,sku(实为MSKU),gtin,item_id,report_start/end,final_storage_fee,original_amount,discount_savings` | 仓储费；**item_id 100% 填充**；report_start 归月；守恒门禁 ΣFinal↔头部Total 差>$0.5拒。1522行 | 2026-08-13 |
| `fact_inbound_freight_alloc` | `store_id,cargo_code,shipment_id,settlement_month,msku,item_id,alloc_amount,alloc_basis,report_start/end` | 入库运输分摊；**item_id 100% 填充**；uq含report_start；同货件同账期重导先删后写。500行 | 2026-08-13 |
| `fact_settlement_msku_monthly` | `store_id,msku,item_id,settlement_month,sales_amount,sales_num,commission_amount,promotion_amount,refund_amount,wfs_shipment_fee,purchase_amount,transportation_amount,extra_json` | 领星结算月度；⚠️**item_id 列存在但实测0%填充(2026-08-14实测)，须按(store,msku)→item_id回填后方可按item取数**；⚠️**commission_amount 实测全为0.00，佣金未同步**；store_id 用请求侧 sid(批12b 修复精度损坏)；extra_json 存 localSku 及 200+全字段；1686行 | 2026-08-13 |
| `fact_reconciliation_item` | `store_id,period_start/end,item_id,gtin,msku,fee_category,amount,txn_count,currency_code` | 回款对账明细（USD）；Σ=账期 total_payable；sale 99.7%带item_id；赔付/广告/仓储/入库/sem/review 类目 item_id 全空（店铺级）；CATEGORY_MAP 见 syncWalmartBillDaily | 2026-08-13 |
| `fact_reconciliation_period` | `store_id,period_start/end,total_payable,...` | 回款账期汇总；守恒哨兵基准 | 2026-08-13 |
| `fact_ad_credit_detail` | 广告返还明细（行级，含 other:* 自发现类目） | 返还明细页 | 2026-08-13 |
| `fact_commission_saving` | 佣金折扣（账期聚合） | 返还明细页 | 2026-08-13 |
| `fact_sem_billing_daily` | `store_id,invoice_id,invoice_date,billing_from/to,charge_type,invoice_total,campaign_id,campaign_name,line_amount,item_id,pay_status` | **SEM 账单明细，带 item_id + line_amount**（昨日新建）；SEM 花费按 item_id 的权威源（区别于 fact_ads_product_daily campaign_type='sem'） | 2026-08-13 |
| `fact_ads_product_daily`（补充） | `campaign_type` 值：sponsoredProducts / video / **sem** | SEM 在此表 1595行(455空item_id/$2365)，另有账单表 fact_sem_billing_daily；item_id 空可经 store+item_id 或 campaign_id→dim_sem_campaign_item 退路 | 2026-08-13 |

### BIZ层（确定性计算 + 人工定稿层；AI 不写本层）
| 表名 | 核心字段 | 口径 | 最后核对 |
|---|---|---|---|
| `biz_finance_opening_cost` | `sku,cutoff_date,snap_qty_0501,opening_unit_cost,finance_fixed,finance_override` | 期初一刀成本；切点 2026-05-01；205 SKU；Σ(snap×unit)=¥1,576,231.25；FIFO 消耗防双算 | 2026-08-13 |
| `biz_finance_exchange_rate` | `rate_month,currency_pair,rate,remark,created_by,updated_by` | 财务人工汇率台账（历史留档）；页面已改只读、主口径转 fact_lingxing_fx_rate；/fx/upsert 保留不删 | 2026-08-13 |

### EVENT层（新增）
| 表名 | 用途 | 备注 |
|---|---|---|
| `event_sem_naming_alert` | SEM 命名不规范告警 | campaign 命名合规；owner/penalty/push 状态机 |
| `event_sem_naming_deduction` | SEM 命名扣分台账 | 绩效扣分 |

### 单品现金利润页 · item_id 维度口径（批13 定稿，2026-08-13）
- **主维度 = 店铺 × item_id**（item_id 唯一，同 item_id 跨店拆分）；SKU/MSKU/GTIN 作附属列。
- item_id 落行优先级：**GTIN → 店内 msku→item_id（干净1:1，dim_product 2079/8，recon 787/0）→ 兜底**。
- 各列来源：收入/退款/退货处理/WFS配送/按品其他=recon.item_id；广告=fact_ads_product_daily.item_id(+msku退路)；仓储/入库=各表 item_id(100%)；头程=fact_shipping_first_let.item_id；销量/期初消耗=fact_settlement_msku_monthly.item_id；**采购(唯一SKU级)=(店铺,sku)单item_id直落；多item_id按头程 delivery_num 份额拆(=按发货单分摊)**；赔付返还/SEM(recon)/测评/removal=店铺级；SEM 花费按 item_id 拟改用 fact_sem_billing_daily(待口径确认)；虚拟SKU(XY2007/DC001/QH888)整行豁免。
- 校验：item_id→sku 0 多义；GTIN↔item_id 784/1；(店铺,SKU)→item_id 分布 403单一/10双/1个5+。

### fact_sales_daily_dupblank_bak_20260813（留档备份表）
- 2026-08-13 双算治理备份：与 fact_sales_daily 同构，存删除前的247行msku空串重复行（qty+金额与同日同店同品非空msku行完全相等）。仅留档/回滚用，任何业务查询不得读取。


### fact_wfs_storage_fee 重要特性（2026-08-14 实锤）
- 唯一键 `uq_storage_fee(platform,store_id,sku,report_start,report_end)` **含账期起止** → 同SKU跨不同账期是**不同行**，重复导入仅在同账期幂等，**跨账期会累加不去重**；表内**无导入类型/账期类型区分列**（自定义时间导入与按账期导入进同一张表）。
- ⚠️**双算风险**：若同时导入"跨月账期"与"14天标准账期"，重叠时间段会被 ICP(单品现金利润) 全表SUM 双算。CN2601 实测虚高 $15,464.68（07-01~07-31 与 07-14~08-12 两条跨月账期）。
- 权威口径 = **14天标准账期序列**；跨月/自定义区间导入仅作核验，不应长期留在表内。
- 注意：账单(recon)账期边界与本表报告账期**不是同一套**（账单端点重叠、长度不等），**不可用 report_start=period_start 精确join对账**，须按时间区间聚合比对。

### 领星 Walmart statement RAW 解析口径（2026-08-14 实锤，写代码必读）
- `raw_lingxing_api.response_json` 中 **数据数组路径 = `$.list[*]`**（不是 `$.data`；顶层 keys = list/totalSum/totalCount）。此前误用 $.data 导致解析全空。
- 行级关键字段：`transactionType` × `amountType` 二维决定类目；`partnerItemId` = **MSKU**；`partnerGtin` = **GTIN**；`amount` = 实际入账额；佣金三件套 `originalCommission` / `commissionSaving` / `commissionRate`（满足 originalCommission + commissionSaving = amount）。
- **带item标识率（决定能否按ITEM_ID出数）**：`Sale/*` 与 `Refund/*` 与 `Adjustment/Fee-Reimbursement` = **100%带MSKU+GTIN**；`Service Fee/*` = 0.5%；`Adjustment/WFS Inventory Fee-Reimbursement`、`Other/*`、`Campaigns/SEM Marketing Fee` = **0%**（沃尔玛原始账单即按店铺整笔计，非我方未同步）。
- **佣金**：`Sale / Commission on Product` 57,956行 / -$90,894.92 / 100%带MSKU → 可按item展示；现被并入 recon 的 `sale` 类目（sale因此为净额）。要单列佣金只需在 CATEGORY_MAP 拆此 amountType，无需新增API。佣金为展示列，不进利润、不进守恒。

### 期初池 / 采购 拆分到 ITEM_ID 的口径（2026-08-14 需求方拍板）
- **一律按发货单 `fact_shipping_first_let.delivery_num` 实际发货数量拆，禁用销量占比/库存占比等比例估算。**
- 期初池 `biz_finance_opening_cost`（仅SKU级，无msku/item）：按该SKU在发货单中各(店铺,item_id)的发货量占比拆分；实测205个SKU中199个可拆、覆盖¥1,576,231.25全额（查无的6个SKU期初数量与金额均为0）；天然实现跨店拆分。
- 采购 `fact_purchase_cash_item`（sid多为0、msku 0%填充）：sid有效者直接归店；sid=0者经发货单定店定item，多item按发货量拆；发货单查无者多为新品采购尚未发货，发货后自动归属，不作缺陷处理。

## Schema 风险审计快照（2026-08-15 生产只读全量审计）

> **本节是 2026-08-15 的快照，不代表永久状态；当前不做 DDL 修复。**
> 三项均已收口，**后续开工不得重开为「疑似数据错误」**；重启调查须有新的生产证据。详细证据见 TASK_CHANGE_LOG 同日条目。

| # | 风险项 | 当前状态 | 结论 |
|---|---|---|---|
| 1 | `fact_shipping_first_let` 唯一键含 `delivery_num` | 100 组 / 203 行高召回候选，203/203 lineage 指向最新同步 | **【结构风险】当前未发现 stale row，不存在已证实现金利润双算** |
| 2 | VARCHAR 前缀 UNIQUE KEY | 44 列 / 34 把键，`over_prefix_rows` 全 0 | **【规范债务】当前有数据的前缀列均未发生截断；0 行表无数据可验证；当前无实际碰撞证据** |
| 3 | UNIQUE NULL bypass | 91 把非主键 UNIQUE 中 6 把含 nullable 列，实际 NULL 全 0 | **【结构风险】当前有数据表 NULL=0，未发现当前 bypass 实例或候选** |

### 1. `uq_first_let` 含 `delivery_num`
- 生产结构：`uq_first_let(platform, shipping_code, msku(64), delivery_num, cargo_code(64))`，五列全 NOT NULL。
- 唯一行级写入方 = `src/syncShippingOrders.ts`（UPSERT）；`sql/056` 建表、`sql/057` 仅 ADD COLUMN；**全系统无 DELETE / cleanup / rebuild**（含 `/opt/ads-ai-api`、crontab、systemd 已核）。
- 多行现象的实测形态 = 同一发货单同一 MSKU 拆多个 `cargo_code`（合法业务多行）。
- 【风险·未发生】数量若在源端就地修正，旧键行不会被删；【未知】2026-08-13 前源状态无 RAW 可还原。

### 2. VARCHAR 前缀 UNIQUE KEY（与 PROJECT_CONTEXT §5.4 的规范债务）
- 全库 **44 个前缀列 / 34 把唯一键**；`MAX(CHAR_LENGTH(col)) < SUB_PART` 全部成立。
- 前缀长度对 CHAR/VARCHAR 按**字符**计 → 判据一律用 `CHAR_LENGTH()`，**禁用 `LENGTH()`**（字节，utf8mb4 下会误判）。
- 余量最紧：`fact_ads_keyword_daily.normalized_keyword` 61/100、`biz_event.source_key` 90/200、`fact_ads_keyword_daily.item_id` 11/32、`raw_lingxing_api.api_path` 59/200、各表 `msku` 19/64。自由文本列随业务增长可能越线，**越线后碰撞是静默的**。
- **0 行表 = 【未知·无数据可测】，不得判为「无暴露」**：`ai_analysis_result`、`dim_keyword`、`fact_purchase_daily`。
- 【冲突】生产 `uq_ai_result` 第 7 列 `keyword(128)` 与 PROJECT_CONTEXT §5.1/§5.4 不一致；修法 `sql/071` v4 **已拍板冻结不执行**；该表 0 行。
- 留档备份表 `fact_sales_daily_dupblank_bak_20260813`、`fact_wfs_storage_fee_overlap_bak_20260814` 继承源表前缀键，**不计入现网风险面**。

### 3. UNIQUE NULL bypass
- 全库非主键 UNIQUE **91 把**；含 nullable 列 **6 把 / 8 列**；`任意唯一键列为 NULL 的行数` 全为 0。

| 唯一键 | 可空列 | 表行数 | 实际 NULL |
|---|---|---|---|
| `biz_event.uq_biz_event` | `source_key` | 2,438 | 0 |
| `biz_perf_deduction.uq_perf_ref` | `ref_event_id` | 368 | 0 |
| `dim_owner.uq_dim_owner` | `department` | 17 | 0 |
| `fact_ads_keyword_daily.uq_fact_ads_kw` | `store_name`、`item_id` | 121,098 | 0 / 0 |
| `fact_purchase_daily.uq_fact_purchase` | `sku` | **0**（无数据可测） | 【未知】 |
| `raw_lingxing_api.uq_raw_lingxing` | `data_date`、`raw_hash` | 69,074 | 0 / 0 |

- ⚠️ **空字符串 `''` 与 NULL 严格区分**：`NOT NULL DEFAULT ''` 的列（如 `fact_purchase_cash_item.msku`、`fact_shipping_first_let.cargo_code`）**不属于**本议题——空串在唯一索引中正常参与去重。
- 【风险·非事实】`biz_perf_deduction.uq_perf_ref` 仅两列且首列可空，若将来出现 `ref_event_id IS NULL` 的扣分行，同一 `biz_type` 下可无限插入而不冲突。

### 查这三类问题的固定顺序（不得跨级）
Schema → Writer/调度 → 异常候选（只用稳定业务身份召回，派生字段不进 GROUP BY）→ Source lineage（优先 `source_raw_id`）→ 财务消费。
前缀风险三层：`max_len ≤ SUB_PART`(无截断) → 存在超长值(截断暴露) → 同索引内其他完整键列相同且所有前缀截断值相同但原值不同(碰撞候选)。
唯一键问题一律**以 `INDEX_NAME` 为单位**分析；枚举入口用 `NON_UNIQUE=0`，**禁止用 `SUB_PART IS NOT NULL` 作入口**（会漏掉无前缀列的唯一键，本轮实证漏了 `biz_perf_deduction.uq_perf_ref`）。

## 2026-08-25 / SV视频广告 itemId='1001' 定案：SV素材行（三轮探测+需求方业务事实闭环，长期有效）

**定案**：`fact_ads_product_daily` 中 `item_id='1001'` 的行是 **SV 视频 campaign 的"素材侧投放统计行"**——非故障、非断货、非删链接、非引用断裂。证据链（probe3/5/6，产物 _deploy_tmp/prod_snapshot_20260824/sv1001_probe{3,4,5,6}.txt）：
- 每个 video campaign 实际开始投放的**第一天**起，报表即固定两行并存：商品行（真实 itemId、商品名、出订单）+ 1001 行（无商品身份、adName='--'、有曝光/点击/花费）。probe6 实证：出生日前全部零曝光零花费（行存在但空转），出生日两行同日开始投放。
- 各 campaign 的 1001 出生日 = campaign 名字中的日期 = 实际开始投放日（6/6 吻合：5.11→05-12、5.15→05-15/17、6.8→06-08×2、6.10→06-10/11）。名字建组即带（记计划投放日）。
- 需求方业务事实（2026-08-25）：开视频广告=加商品+加素材；素材侧投放数据无 itemId 可挂 → 接口回占位 1001。
- 已排除（probe5）：窗口内无 listing 消失（144 连续日快照、323 listing 全存活）；采样窗口内无改名（-TEST/-广泛 后缀为 6 月下旬后所加，与 1001 无关）。
- '1001' 占位值由沃尔玛还是领星生成属口径细节，不影响任何处置；如需官方确认可提领星**口径咨询**（非归责），可提可不提。

**消费方口径（长期）**：1001 行是真实增量花费（Connect 发票守恒审计内），**不得删除、不得过滤出算钱口径**；花费归属该广告组对应的商品（广告费用报表单9已按广告组前缀拆行归因，方向正确）；报表标注措辞应为「SV素材」语义（「[未绑定]」为定案前旧措辞，待小改单修正）。CS测品的首广日期推导（launch_date CS分支按首次广告花费日）不受影响——素材行与商品行同日首花。

**沃尔玛广告投放机制（需求方拍板，长期有效）**：断货（WFS 无库存）期间沃尔玛广告不投放，到货恢复可售后自动恢复；**禁止**建「归档/断货商品仍有广告花费」类告警规则（对正常断货补货节奏全量误报，已否决）。

**判读纪律**：短数字 itemId（≤5位纯数字）勿当真实商品ID关联 dim_product；video 报表两行结构勿当异常重查（本节即结论）；同一 walmart item_id 可挂多店铺多 msku（probe5 实证 19051502014 跨 CN2601/CN2501/CN2502），跨店按 store 维度隔离。

### 2026-08-25 落地补记：按品广告费统一口径（单10上线→同日晚性能事故整体回滚；SBSV独立应用已接入）— 现网状态以本节为准

- **计算处唯一**：`src/adsItemSpendAlloc.ts`（adjustedAdsFactSql 三分支UNION派生视图：非占位原行/占位×同日同组权重(花费→曝光→均分)/防御分支归组内历史最大商品）。改分摊规则只改此一处。守恒实证 454.16=454.16 差0。文件留在生产（c9d8cade）当前无引用，供单13修复版复用。
- **⚠️2026-08-25晚性能事故修正**（详见 TASK_CHANGE_LOG 同日事故条目）：该派生视图含窗口函数，MySQL 物化临时表、外层条件不下推，包 fact_ads_product_daily(46.7万行) 后每次查询全表扫 → SB/SV页500(252s) + 订单利润V2 nginx 超时。lingxing-admin 三消费方（报表/orderProfitV2 §5广告费/aiFinanceRoutes ICP②广告）**已整体回滚旧口径**（报表页 1001/[未绑定] 行临时回归=单9口径恢复在线）；修复版（单13：视图带日期窗口参数烤入内层+耗时断言验收）待需求方拍板后重新接入。
- **当前唯一在线的统一口径消费方**：SB/SV明细页后端（asin-kw-mvp `walmart_sbsv/router.py`=d55d2720，Python 版同规则视图+整行全并，范围 `platform='walmart' AND campaign_type IN ('sba','video')` 已烤入视图全部分支）。实测约11秒；待 `fact_ads_product_daily` 组合索引 `(platform, campaign_type)` 落地降至毫秒级（FACT DDL 提案待需求方授权，表现仅单列 idx_fapd_platform，EXPLAIN rows=231470）。
- **尚未接入（仍读原始表=不含素材分摊，差异量级每店每月数十美金，待单13落地后排期切换）**：订单利润Beta、buildProductBusinessState、buildProductRuleSignalsDaily、CS测品聚合(feishuRawSalesRoutes)、GPT经营分析(/opt/ads-ai-api)、internalReadonlyApi。新增按品广告费消费方一律 FROM adjustedAdsFactSql()（修复版），禁止再直读原始表做按品汇总。
- **按设计继续读原始表（对账基准，勿切换）**：reportV2Reconcile、发票对账链、P7哨兵、checkOnsiteAdsInvoiceSentinel。
- 前端 AdsFeeReport 纯数字精确搜索（a2174dc3）保留在线，未随回滚变动。
