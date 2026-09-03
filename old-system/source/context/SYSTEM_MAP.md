# SYSTEM_MAP

最后核对：2026-07-31  
核对来源：本地仓库、2026-07-31 生产只读采集（crontab/systemd/监听面）。新人先读下方「模块视图」总览，再按需读各模块详节。

## 模块视图（2026-07-31 总览）

正在生产运行的模块一览（详节在本文件后文与 TASK_CHANGE_LOG 对应日期条目）：

| 板块 | 模块/页面 | 前端入口(key) | 后端 | 主要表 | 定时 |
| --- | --- | --- | --- | --- | --- |
| 运营中心 | 数据看板 | sales-dashboard | 聚合API | fact_* | — |
| 运营中心 | 每日销售明细/CS测品/产品管理/运营日志 | feishu-raw:* | feishuRawSalesRoutes | raw_feishu_table, dim_product, biz_product_operation_log | 数据链见 PIPELINE_MAP |
| 运营中心 | 订单利润 Beta | feishu-raw:order_profit_daily | 同上 | raw_feishu_table(order_profit_daily) | 19:00/19:30 链 |
| 运营中心 | 目标管理(月度规划,2026-08 新规) | monthly-plan | aiBusinessRoutes /monthly-plan | biz_monthly_plan, event_monthly_plan_unfilled | 催办09:20/扣分09:25(8号起)/月报清单06:00 |
| 运营中心 | 经营分析(周报/月报/目标) | business-analysis | aiBusinessRoutes | ai_business_report, biz_monthly_plan | 周四23:00评/周报确认链/月报链 |
| 运营中心 | 清货中心 | feishu-raw:__clearance__ | clearanceCenterRoutes | event_clearance_approval/card, dim_product | 清货三卡+审批通报 |
| 广告系统 | 广告页(:3000 Next.js) | ads:* | walmart-ads-data | fact_ads_* | 18:10/周日04:30 |
| 智能PMC | PMC 看板 | feishu-raw:__pmc__ | aiBusinessRoutes | biz_product_rule_signal_daily | 20:55 |
| AI人力 | 绩效台账+人工录入+凭证 | hr-performance | hrRoutes | biz_perf_deduction, biz_perf_cert | 绩效日报10:00 |
| AI人力 | AI 运营日志评级(周) | hr-performance#review | hrRoutes /perf/log-review | ai_ops_log_review_item/summary | 周四23:00 aiOpsLogReview |
| AI人力 | 考勤(月度核算,2026-07-30) | attendance | attendanceRoutes(hr_attendance权限) | raw_feishu_attendance, fact_attendance_daily | 00:45 同步 |
| AI人力 | 考勤缺卡通报(2026-07-31) | (飞书卡片) | attendanceLackAlert + 回调lack_ack | event_attendance_lack_alert | 09:50推/21:50重发 |
| AI人力 | 用户管理(原花名册,2026-08-04改名) | roster | rosterRoutes | dim_feishu_member, dim_app_user* | 02:30花名册/02:35自动开户(默认角色运营组员) |
| AI工具 | 会议分析 | meeting(iframe :8081) | 独立静态+后端 | — | — |
| AI工具 | LLM 模型切换(2026-07-31 并入SSO仅陈佳聪) | llm(iframe :3456) | apiKeyManager.ts 独立服务 | .env AI_* + config/apiKeyProfiles.json | — |
| AI工具 | API 接口文档(2026-07-28) | api-doc | apiDocRoutes(超管+白名单) | — | — |
| AI工具 | 帮助中心 | help | helpRoutes | dim_page_help | — |
| AI工具 | AI广告分析/AI关键词文案 | 外链 ChatGPT | — | — | — |
| 对外 | internal-readonly 只读API(同事) | giginana.com 经海外中转 | internalReadonlyApi | 只读 | — |
| 对外 | Custom GPT 经营分析 | GPT→中转→隧道 | ads-ai-api /api/ops/analyze | 只读+fact_profit_daily | 19:30 ETL |
| 基础 | 统一登录 SSO(:80/:8081/:3000/:3456) | login.html | authRoutes/authMiddleware | dim_app_user*(+audit) | — |
| 通知族 | 不出单/缺负责人/低毛利/到货/订单下滑/CS测品/运营不动作/UNPUBLISHED归档/归档到货卡09:40/数据哨兵20:15等 | (飞书) | 各 notify 脚本+feishuNotify | biz_event 等 | 见 PIPELINE_MAP |

## 已实现模块

### 销售原始数据查看器

- 前端入口：`/admin/#/feishu-raw-sales-data`
- 前端文件：`/opt/lingxing-auto/admin-frontend/src/FeishuRawSalesData.tsx`
- 后端挂载：`/api/feishu-raw-sales`，文件 `/opt/lingxing-auto/src/feishuRawSalesRoutes.ts`
- 当前可见 Tab：每日销售明细、订单利润 Beta、CS测品分析 Beta、产品管理。
- 隐藏但接口保留 Tab：当日数据、ItemID负责人、近期利润广告、同步任务。
- 2026-07-08 最小修复：每日销售明细 `<REDACTED_FEISHU_SHEET_ID>` 接口增加响应级 owner/MSKU 补齐；产品管理接口增加 `product_name -> item_name` fallback。Task D 随后通过领星本地产品详情 RAW-first 链路回填 `dim_product.product_name` 1354 条，未命中 187 条继续 fallback。

7 个历史 Tab：
- 当日数据：`sheet_id=<REDACTED_FEISHU_SHEET_ID>`，读 `raw_feishu_table`，当前前端隐藏。
- 每日销售明细：`sheet_id=<REDACTED_FEISHU_SHEET_ID>`，读 `raw_feishu_table`，当前前端可见。
- ItemID负责人：`sheet_id=<REDACTED_FEISHU_SHEET_ID>`，读 `raw_feishu_table`，当前前端隐藏，降级为历史镜像。
- 近期利润广告：`sheet_id=<REDACTED_FEISHU_SHEET_ID>`，读 `raw_feishu_table`，当前前端隐藏。
- 订单利润 Beta：`sheet_id=order_profit_daily`，读 RAW 快照 + `dim_product_business_state`。
- CS测品分析 Beta：读 DIM/FACT/配置表聚合。
- 同步任务：读 `raw_sync_tasks`，当前前端隐藏。

### 订单利润 Beta

- 前端：`FeishuRawSalesData.tsx`
- 接口：`GET /api/feishu-raw-sales/order-profit`
- 代码：`src/feishuRawSalesRoutes.ts`、`src/syncOrderProfitDaily.ts`
- 涉及表：`raw_feishu_table(order_profit_daily)`、`dim_product_business_state`、`dim_product`、`dim_product_cost_config`
- 数据流：FACT/DIM -> `syncOrderProfitDaily.ts` -> RAW 快照；B 线状态由 `dim_product_business_state` JOIN 透出。
- B 线升级：返回产品类型、利润等级、生命周期、库存状态、广告状态、问题标签、状态日期等中文展示字段。
- Task H-1D 起默认排除 `dim_product.product_management_status='archived'`；`product_management_status=all` 用于内部排查时放开 archived。无法匹配产品状态的 RAW 聚合行默认保留，避免误删。
- 定时：18:30 `npm run sync:order-profit-daily -- --date T-2`。

### CS测品分析 Beta

- 前端：`FeishuRawSalesData.tsx`
- 接口：`GET /api/feishu-raw-sales/cs-test-analysis`
- 代码：`src/feishuRawSalesRoutes.ts`
- 涉及表：`dim_product`、`fact_sales_daily`、`fact_ads_product_daily`、`fact_inventory_daily`、`cs_test_product_config`
- 数据流：DIM/FACT 聚合 -> API -> 前端。
- 规则：MSKU 以 `CS` 开头；首广日期 >= 2026-06-01；测款成本是 CS 诊断口径，不能当常规利润亏损解释。
- 口径（2026-07-25）：广告类指标（广告订单数/广告销售额/累计广告费/曝光/点击/CTR/CPC/CVR/ACOS）改为**全历史累计**，与销售类（累计销量/销售额/自然订单数）同口径。此前 `ad` 子查询按 `stat_date` dateStart~dateEnd 单日窗口聚合，销售类却是全历史 → 广告订单数恒 0、自然订单比例恒 100%、「累计广告费」名不符实。改法：`ad` 子查询 WHERE 去掉日期过滤，用两个 `IFNULL(?, '')` 占位保参数序=全历史。测款成本公式不变（`销售额×0.85 − 广告费 − 销售额 − 订单数×5`，需求方定稿），因吃到全历史广告费而自动纠正。
- 排序（2026-07-25）：所有数值/日期列支持表头排序（升→降→取消）。后端 `resolveSortSql` 白名单 + 前端 `SORTABLE_COLUMNS_BY_TAB[cs_test]` 同步扩列，sort_field 映射到 agg 别名（ad_orders/ad_sales/ctr_pct/natural_order_ratio_pct/test_cost 等）。

### 产品管理

- 前端：`FeishuRawSalesData.tsx` 的 `product_management` Tab，默认可见。
- 接口：`/api/feishu-raw-sales/product-management` 及 `update-owner`、`update-wfs-fee`、`update-status`、`owner-options`。
- 涉及表：`dim_product`、`dim_owner`、`dim_feishu_member`、`dim_product_cost_config`、`dim_product_business_state`。
- 写入规则：负责人写 `dim_product.owner`；WFS 配送费写 `dim_product_cost_config.delivery_fee`；产品状态写 `dim_product.product_management_status*`。
- 生命周期人工确认：`POST /api/feishu-raw-sales/product-management/update-lifecycle` 写 `dim_product.manual_lifecycle_stage/manual_lifecycle_by/manual_lifecycle_at/manual_lifecycle_system_snapshot`，要求 `operator_name` 非空，并按产品类型分流白名单。CS 测品（`msku LIKE 'CS%'`）只允许 `测品期/测品结束/空值`；常规产品只允许 `新品期/上升期/稳定期/清货期/空值`；跨类型值返回 400 且不写库。（2026-07-25：操作人优先取登录用户 `req.user.username`，`operator_name` 退为兜底；前端「更多筛选」已移除手填操作人。）snapshot 由后端读取最新状态表 `system_lifecycle_stage` 后写入，前端不得传入。页面显示“系统生命周期”和“人工生命周期”两列；人工列默认展示系统值但不写库；系统列蓝色表示人工主动覆盖且系统未变，红色表示系统判断已变化或历史人工值无基线。
- 产品名称：优先读 `dim_product.product_name`。该字段 2026-07-08 已由 `syncProductNameFromLingxing.ts` 从领星本地产品详情回填 1354 条；为空时接口仍 fallback 到 `dim_product.item_name`。
- 归档门槛（2026-07-25 放宽）：`update-status` 归档前旁查 `fact_inventory_daily` 最新快照，`SUM(available_stock) ≥ 5` 或 `SUM(inbound_stock) > 0` 一律拦截回 400（库存口径对齐列表「当前库存」列）；仅库存 < 5 且无在途可归档。前端 `saveProductStatus` 同口径本地预检+提示。人工 `archived` 仍优先，系统脚本不覆盖人工归档。
- 更多筛选（2026-07-25）：移除「操作人」输入（原为 lifecycle 操作人手填，现由登录用户提供）；新增「人工生命周期」下拉，查询参数 `manual_lifecycle` 精确匹配 `dim_product.manual_lifecycle_stage`，`__unset__`=未设置人工值（`IS NULL OR TRIM=''`），空=不限。
- 展示口径：`product_name` 当前读取 `dim_product.product_name`，为空时 fallback 到 `dim_product.item_name`；`item_name` 单独保留原始系统字段。`sku` 仍只展示 `dim_product.sku`，本轮未自动回填。

### 运营日志 Tab（Stage2.1~3.2 已上线）

- 前端入口：`/admin/#/feishu-raw-sales-data`
- Tab：`运营日志`
- 接口：`GET /api/feishu-raw-sales/operation-log`
- 鉴权：继承 Admin / Nginx Basic Auth
- 数据源：`biz_product_operation_log`（人工运营日志主表）+ 只读关联 `biz_product_rule_signal_daily`（系统规则信号）
- 关联口径：`log_date=signal_date AND platform AND store_key AND item_id AND msku`；后端先按页内日期批量取规则，再在 JS 中按全键精确匹配
- 默认行为：默认视图改为最近 7 个 `log_date`（生产 recent7=`2026-06-28~2026-07-06`，total=1549），默认排除 archived；`include_archived=1` 可用于内部排查。有窄化筛选（关键词/MSKU/ItemID/店铺/负责人/利润等级/规则）时不限日期，查全历史。
- 筛选：`GET /api/feishu-raw-sales/operation-log` 支持 `keyword/msku/item_id/store/owner/profit_level/date/date_start/date_end/rule_level/rule_code/has_rule/include_archived`；`GET /api/feishu-raw-sales/filter-options?sheet_id=operation_log` 返回 `stores/owners/profit_levels`，其中利润等级筛选项已剔除裸 `A/B/C/D`，仅保留 4 个完整中文等级。
- 展示形态：运营日志列已收敛为 8 列：`日期/负责人/店铺/Item ID/MSKU/利润等级/运营提醒/运营日志`。`运营提醒` 合并系统规则、系统建议、产品数据问题；无提醒显示「暂无提醒」；运营提醒列加宽（前端 `minWidth 520`）并支持换行。
- 前端边界：运营日志 Tab 不再显示 `SKU`、毛利率、广告占比筛选；其它 Tab 保持原筛选不变。利润等级下拉仅在运营日志 Tab 显示。
- 写入：`POST /api/feishu-raw-sales/operation-log/update` 已上线，只允许更新 `biz_product_operation_log.log_content`，并写 `updated_by='admin_ui'`、`updated_at=NOW()`；只允许 `source='system_base' AND is_locked=0` 的行，迁移历史 `source='feishu_migration'` 或锁定行 `is_locked=1` 返回 409。`GET /operation-log` 返回隐藏字段 `_id/_editable` 供前端判断可编辑性。
- 写入边界：系统规则信号仍只读展示，不写回 `biz_product_operation_log`；`data_issue/solution/ai_diagnosis` 不通过该 UI 写入口修改。20:50 `build:operation-log-base` 只刷 owner/profit_level_snapshot 等基础字段，不碰 `log_content`。

### ItemID负责人同步

- 代码：`src/syncFeishuItemOwnerToMysql.ts`
- 当前定位：飞书 `<REDACTED_FEISHU_SHEET_ID>` RAW 历史镜像/初始化备份/排查对账。
- 已知生产现状：2026-07-07 已恢复 09:30 自动任务，cron 行为 `npm run sync:feishu-item-owner -- --confirm-write`。
- 当前脚本 dry-run 明确显示 RAW-only：只写 `raw_feishu_table`，不会写 `dim_product` / `dim_product_owner` / `dim_product_cost_config`，不会覆盖产品管理页面维护的负责人、WFS 配送费、产品状态。

### GPT经营分析链路

- Custom GPT：
  - 「Ads广告分析工具」：广告关键词数据查询，使用 `/auth-check`、`/query/ads_keyword_lookup` 等。
  - 「运营经营分析助手」：经营分析，使用 `/api/ops/analyze`。
- 公网域名：`https://gpt-api.giginana.com`
- ads-ai-api 服务：`company-ai:/opt/ads-ai-api/main.py`
- systemd：`ads-ai-api.service`，WorkingDirectory `/opt/ads-ai-api`，uvicorn 启动，host/port 来自 `/opt/ads-ai-api/.env`。
- 认证：Bearer Token；Token 指针为 `/opt/ads-ai-api/.env` 的 `ADS_AI_API_TOKEN`。
- 查询模板：`/query/{template_name}`，白名单表包括 `dim_product`、`dim_product_owner`、`dim_store`、`fact_ads_keyword_daily`、`fact_ads_product_daily`、`fact_sales_daily`、`fact_profit_daily`、`fact_inventory_daily`。
- `/api/ops/analyze`：当前为 v7 状态表驱动版本，读取 `dim_product_business_state`，产品名来自 `dim_product.product_name` 并有 fallback，利润四分类由状态表驱动；GET 可用，POST 会返回 405。Task H-1D 后最新状态表不再含 archived；Task H v6 起，A线分类在 `product_base_sql` 层也显式排除 `archived`，避免 archived 商品继续落入 excellent/ad_waste/no_sales/stockout/slow_moving。响应顶层保留 `queried_product_states`；当请求带 `item_id` 或 `msku` 时，若状态表有快照则返回完整状态字段并标记 `state_source='dim_product_business_state'`；若状态表无行则兜底查 `dim_product`，返回最小状态结构，归档品显式 `archived=true` 且 note 说明“已归档，不作为问题产品推荐”，非归档则提示暂无当日快照。Task H v7 起，无过滤 `company_summary_only` 模式除汇总计数外，额外附带 `priority_problem_products` 前 10 条；为供 priority 排序取材，`ad_waste/no_sales/stockout/slow_moving` 四个 A 线问题分类在无过滤模式下也执行聚合查询，因此 `category_counts` 不再恒为 0，而产品数组本身仍保持空列表，继续满足 80KB 保险丝。
- `/api/ops/analyze`：当前生产版本为 `api_version=v7.3.1`。在 v7.2 起，响应体积统一按 **UTF-8 字节数** 计算，红线固定 `50000` 字节，不再按 Python 字符串字符数估算。v7.3 新增参数 `product_type=cs`（仅支持 `cs`，大小写归一；非法值返回 400），命中后进入 `data_scope='cs_detail'`。CS 模式新增返回字段 `cs_summary`、`cs_attention_products`、`truncation_note`，并继续返回 `metrics_window`；常规九分类与 `priority_problem_products` 在 CS 模式下一律为空数组。CS 数据来源为 `dim_product`、`dim_product_business_state`、`dim_product.launch_date`、`fact_sales_daily`、`fact_ads_product_daily`、`fact_inventory_daily`、`biz_product_rule_signal_daily`。CS 模式不使用 `profit_level`、A/B/C/D 利润等级、`gross_profit`、`gross_margin` 作为评估依据；v7.3.1 起已将 `summary.gross_profit/gross_margin` 置空，并以 `profit_caliber` 明示“CS测品不适用毛利指标”。CS 响应体积超限时走专属降级链 `24 -> 12 -> 6 -> 3 -> 1`。非 CS 查询继续保持 v7.2/v7.3 的原有行为。
- 生命周期字段同页面读取同一状态表：`lifecycle_stage` 为人工确认优先后的最终值，`system_lifecycle_stage` 为系统建议。
- 2026-07-08 Task F 起 CS 测品系统生命周期只输出 `测品期/测品结束`，不再允许 NULL；口径与产品管理页“当前库存”同源：按每个商品自己的 `fact_inventory_daily.MAX(snapshot_date)` 读取 `available_stock`，`>0` 为 `测品期`，`=0/NULL` 为 `测品结束`。CS Beta `non_wfs_available_stock` 继续用于测品过程分析，不和产品管理生命周期混用。
- 2026-07-08 Task H-1E 起，AI 诊断已退役，由系统规则判断替代：`src/buildProductRuleSignalsDaily.ts` 读取状态表 + FACT 生成确定性规则信号，写入 `biz_product_rule_signal_daily`。`src/aiDailyDiagnosis.ts` 代码保留，但已不再作为自动链路；1C 已停 `runDailyAutomation` 中 `ai:daily` 自动入口，且 crontab 未接入。人工运营日志仍由 `biz_product_operation_log` 维护（人工三列，前端可编辑），系统规则信号只读，二者互不覆盖。Admin 运营日志 Tab / GPT 后续可读取 `biz_product_rule_signal_daily`。
- 中转机 Nginx：输入材料确认 `gpt-api.giginana.com` 在 `38.244.59.150`，HTTPS + Let's Encrypt，location 包含 `/ads-ai-api/`、`/auth-check`、`/api/`、`/privacy.html`，转发到 `127.0.0.1:18090`；本次未直接登录中转机核验 Nginx 文件，需确认。
- SSH 反向隧道：`company-ai` 上 `gpt-api-tunnel.service`，`-R 127.0.0.1:18090:127.0.0.1:8090 root@38.244.59.150`，自动重启。
- 安全边界：8090/MySQL 不对公网开放；18090 仅监听中转机本地回环；日志不记录 Token 值。

### GPT广告查询

- 服务：`/opt/ads-ai-api/main.py`
- 接口：`GET/POST /query/{template_name}`、`GET /queries`、`GET /auth-check`。
- 典型模板：`schema_overview`、`ads_keyword_sample`、`ads_keyword_lookup`、`ads_product_sample`、`sales_sample`、`profit_sample`、`product_summary`、`item_ads_sales_profit`。
- 数据流：Custom GPT -> Bearer -> 海外 Nginx -> SSH 隧道 -> ads-ai-api -> MySQL 只读。
- 旧广告接口标准回归样例（2026-07-09 更新）：`/query/ads_keyword_lookup?date_start=2026-07-07&date_end=2026-07-07&item_id=18865320723&keyword=fruit%20tray`，预期 `row_count=1`。该样例在 `fact_ads_keyword_daily` 的底表覆盖范围为 `2026-06-23 ~ 2026-07-07`，共 57 行，属于稳定高频词。
- 回归纪律：旧广告接口样例必须使用 `date_start + date_end` 参数，不能再用单个 `date=`；样例日期必须保持在最近 7~14 天内，过期即更换，避免把历史老样例误判为系统漂移。

### 每日销售明细 RAW viewer

- 入口：`/api/feishu-raw-sales/data?sheet_id=<REDACTED_FEISHU_SHEET_ID>`，前端读取返回列名展示。
- 数据源：`raw_feishu_table.sheet_id='<REDACTED_FEISHU_SHEET_ID>'`，由 `syncLingxingToRawFeishu.ts` 生成。
- 2026-07-08 修复：同步脚本的 MSKU 表达式改为 `COALESCE(NULLIF(f.msku,''), NULLIF(a.msku,''), NULLIF(inv.msku,''), NULLIF(dp.msku,''), '')`，避免广告 FACT 的空字符串截断库存/维表 MSKU fallback。
- 2026-07-08 展示补齐：接口只对 `<REDACTED_FEISHU_SHEET_ID>` 页面行批量查询 `dim_store/dim_product`，对空 owner/MSKU 做响应级补齐；`store_name + item_id` 多候选或无候选时保持空并计入 `supplement_stats`，不影响 `<REDACTED_FEISHU_SHEET_ID>` 等历史 Tab。

### 数据同步管道

当前生产 crontab（Asia/Shanghai）：
- 02:30 `refreshFeishuMembers.ts --write`：刷新飞书成员映射。
- 03:00 `syncWalmartStores.ts`：店铺发现。
- 09:00 `noOrderNotify.ts --send`：不出单通报。
- 09:30 `sync:feishu-item-owner`：已于 2026-07-07 按退役口径注释停用，crontab 保留注释行。
- 10:00 `unmatchedOwnerNotify.ts --send`：缺负责人通报。
- 10:00 `report:performance -- --mode=daily`：经营日报。
- 16:10 `checkAutoAdSearchTermImport.ts --send`：自动广告导入检查。
- 16:45 `sync:lingxing-daily -- --date T-2` + `syncLingxingToRawFeishu.ts T-2`：领星日数据与 RAW viewer。
- 17:00 周一 `report:performance -- --mode=weekly`：经营周报。
- 16:00 每月 3 日 `report:performance -- --mode=monthly`：经营月报。
- 18:10 `syncManualAdKeywordDaily.ts`：手动广告词。
- 18:30 `sync:order-profit-daily -- --date T-2`：订单利润 Beta。
- 19:00 `sync:product-cost -- --confirm-write --date=T-2`：产品成本。
- 19:30 `/opt/ads-ai-api/scripts/build_fact_profit_daily_from_raw_feishu.py --execute`：利润 ETL。
- 20:15 `derive:launch-date -- --confirm-write`：launch_date 增量补空（2026-07-07 上线）。
- 20:30 `build:product-business-state -- --confirm-write`：状态表每日构建（2026-07-07 上线）。
- 20:50 `build:operation-log-base -- --confirm-write`：运营日志基础行 MySQL 链路，写 `biz_product_operation_log`；旧 `sync:daily-operation-log-base` 飞书链路已注释停用。
- 周一/周四 08:00 `lowProfitNotify.ts --send`：低毛利通报。
- 2026-07-08 21:30 一次性 cron validation 已于 Task H-1C 删除。

核心时序依赖链：

`16:45 领星日数据(T-2) -> 18:10 手动广告词 -> 18:30 订单利润 -> 19:00 产品成本 -> 19:30 利润ETL -> 20:15 launch_date推导 -> 20:30 状态表计算`

09:30 负责人 RAW-only 镜像已于 2026-07-07 按退役口径注释停用，不再在依赖链中。
20:50 运营日志基础行已于 2026-07-08 切到 `build:operation-log-base` MySQL 链路；`runDailyAutomation.ts` 不再触发旧 `sync:daily-operation-log-base` 或 `ai:daily`。`aiDailyDiagnosis.ts` 内部仍保留写飞书 <REDACTED_FEISHU_SHEET_ID> 的代码，但无自动入口，待 Task H-1E 改为系统规则写 MySQL。

T-2 特性：16:45、18:30、19:00 均显式使用 `date -d "2 days ago"`；利润 ETL 回填 `4 days ago` 到 `yesterday`，最终 FACT 最大日期当前为 2026-07-05。

### B线规则引擎

- 代码：`/opt/lingxing-auto/src/buildProductBusinessState.ts`
- npm script：`npm run build:product-business-state`
- 输入：`dim_product`、`fact_profit_daily`、`fact_sales_daily`、`fact_inventory_daily`、`fact_ads_product_daily`
- 输出：`dim_product_business_state`
- 规则版本：`rule_version='v1.0'`
- 运行参数：`--dry-run` 默认只读；`--confirm-write` 才写入；`--date=YYYY-MM-DD` 可指定数据可用截止日，默认取 `fact_profit_daily.MAX(stat_date)`。
- 规则要点：
  - 毛利只从 `fact_profit_daily` 聚合，不重算毛利公式。
  - CS 测品不参与利润等级和生命周期判断。
  - `launch_date` 只读 `dim_product.launch_date`，禁用 `created_at` 代替上架日期。
  - `manual_lifecycle_stage` 只读 `dim_product`，trim 后非空才覆盖系统生命周期；状态表任务不得写回 `dim_product.manual_lifecycle_*`。
  - `product_management_status='archived'` 的产品不再生成状态快照；最新快照已清理 archived，历史快照保留。
  - 库存状态单值优先级：缺货风险 > 库存积压严重 > 库存偏高 > 正常；多重命中写入 `problem_tags`。
  - 广告状态单值优先级：广告浪费 > 广告无转化 > 广告占比偏高 > 广告无花费 > 广告正常。
- 当前生产状态：20:30 每日 crontab 已上线（2026-07-07）；Task H-1D 后 `MAX(stat_date)=2026-07-06`，最新快照 1127 行，archived=0。

### 系统规则信号 v1

- 代码：`/opt/lingxing-auto/src/buildProductRuleSignalsDaily.ts`
- npm script：`npm run build:product-rule-signals`
- 输入：`dim_product_business_state`、`fact_ads_product_daily`、`fact_sales_daily`
- 输出：`biz_product_rule_signal_daily`
- 定位：替代旧 AI 诊断自动链路的确定性规则引擎。常规产品规则直接读状态表；CS 测品规则读最新状态表中的 CS 池 + 近 3 天 item 级广告/销售事实，CVR/CPC/ACOS 由窗口内 sum 现算。
- 写入边界：只写 `biz_product_rule_signal_daily`；不写飞书、不写 `biz_product_operation_log.ai_diagnosis`、不碰 `biz_product_operation_log` 人工三列、不改状态表/FACT。
- 运行参数：`--dry-run`、`--confirm-write`、`--date=YYYY-MM-DD`、`--allow-stale`；含 stale guard，默认 `signal_date=dim_product_business_state.MAX(stat_date)`。
- 当前状态：Task H-1E 已完成一次生产 dry-run + confirm-write + 幂等重跑；`signal_date=2026-07-06` 产出 434 条系统规则信号。cron 未接入，后续若上线每日调度，应放在 `20:30 build:product-business-state` 之后。

### 飞书机器人/通知与报表

- `noOrderNotify.ts`：不出单产品通报，09:00 cron。
- `unmatchedOwnerNotify.ts`：缺负责人通报，10:00 cron。
- `lowProfitNotify.ts`：低毛利通报，周一/周四 08:00 cron。
- `performanceSummaryReport.ts`：日报/周报/月报，当前读 `raw_feishu_table(order_profit_daily)`。
- `checkAutoAdSearchTermImport.ts`：自动广告导入检查，16:10 cron。
- `syncYuesiTestProductAnalysis.ts`：悦斯测品相关飞书机器人通知能力。

## 基础设施

### 国内服务器

- 生产别名：`company-ai`
- 主路径：`/opt/lingxing-auto`、`/opt/ads-ai-api`
- Admin 服务：`lingxing-admin.service`，端口 3001。2026-07-09 Stage3.2 核查确认：服务监听 `0.0.0.0:3001`，且 `http://42.193.254.170:3001/` 可从公网直连返回 200；当前 app 层 `ADMIN_PASSWORD` 未启用，主要鉴权依赖上游 Nginx / 调用链控制。
- ads-ai-api：`ads-ai-api.service`，本地 8090，供 SSH 隧道转发。
- SSH 隧道：`gpt-api-tunnel.service`，将中转机 `127.0.0.1:18090` 反向映射到国内 `127.0.0.1:8090`。

#### `/api/internal-readonly/` 链路

- 核验时间：2026-07-07 23:05 CST。
- 国内监听：`ss -lntp | grep 3001` 显示 `0.0.0.0:3001`，进程为 `node /opt/lingxing-auto/node_modules/.bin/ts-node src/adminServer.ts`。
- 国内服务环境：`READONLY_DB_HOST=127.0.0.1`、`DB_HOST=127.0.0.1`、`NODE_ENV=production`；`INTERNAL_READONLY_API_TOKEN` 存在但值不得写入文档。
- 代码入口：`src/adminServer.ts` 先挂载 `internalReadonlyApi` 到 `/` 和 `/api/internal-readonly`，再进入 Admin Basic Auth 中间件；因此 internal-readonly 自己承担鉴权。
- 2026-07-09 Task H-Stage3.1/3.2 网关修复：`src/internalReadonlyApi.ts` 顶层对 `/api/feishu-raw-sales/`、`/api/lingxing-sales/`、`/api/admin/` 这些 Admin 业务前缀执行 `next("router")`，避免路径中含 `update/sync` 被误判成只读管辖；但若命中这些前缀且带 `Authorization: Bearer ...`，则直接返回 403 `readonly_admin is not allowed for admin business routes`，防止 readonly Bearer 穿透到 Admin 写接口。
- 鉴权与限制：`src/internalReadonlyApi.ts` 要求 `Authorization: Bearer ${INTERNAL_READONLY_API_TOKEN}`；缺失或错误返回 401；非 GET 或 sync/import/upload/update/delete 类路径返回 403；不执行调用方传入 SQL；返回前会按字段名脱敏 password/token/secret/authorization/cookie/file_path/server_path/env 等敏感字段。
- 已开放接口：`/lingxing-sales/daily-overview`、`/lingxing-sales/sync-tasks`、`/ads/product-daily`、`/ads/keyword-daily`、`/inventory/daily`、`/products`、`/owners`、`/keywords`、`/events`、`/ai-analysis`、`/raw/feishu`、`/raw/lingxing`。
- 读取表：`fact_sales_daily`、`fact_ads_product_daily`、`fact_inventory_daily`、`dim_product_owner`、`dim_product_cost_config`、`sync_task_log`、`dim_product`、`dim_owner`、`dim_keyword`、`biz_event`、`ai_analysis_result`、`raw_feishu_table`、`raw_lingxing_api`。
- 正式调用入口：`docs/internal_api_readonly.md` 写明同事使用 `https://giginana.com/api/internal-readonly`，经海外中转反向代理到 `42.193.254.170:3001`；同事不直接使用裸 IP。
- 中转机 Nginx：`/api/internal-readonly/` 代理到 `http://42.193.254.170:3001/api/internal-readonly/`，并透传 `Authorization`。
- 公网可达证据：从海外中转机直接请求 `http://42.193.254.170:3001/api/internal-readonly/products?page=1&page_size=1` 返回 401；2026-07-09 再次从外网探测 `http://42.193.254.170:3001/` 返回 200，说明 3001 端口不仅 TCP/HTTP 可达，而且根路径可被公网直接访问。
- 本机防火墙：`firewalld` 为 inactive；未发现本机 iptables 对 3001 的显式 INPUT 限制。
- 腾讯云安全组：本次未取得控制台/API 规则全文；但结合 `0.0.0.0:3001` 监听、firewalld inactive、海外机裸 IP 请求返回 401，当前风险按“3001 对公网可达”处理。
- 决策建议：优先在腾讯云安全组将 3001 入站收紧到仅海外中转机 IP `38.244.59.150`；替代方案是将 internal-readonly 收编进 SSH 隧道，例如中转机本地 `127.0.0.1:18091` 反向映射到国内 `127.0.0.1:3001`，再把 Nginx upstream 改为 `127.0.0.1:18091`。如继续保留公网直连，还应补 `ADMIN_PASSWORD` 启用 app 层认证。用户在 Task H-Stage3.2 已明确暂缓这些安全动作，本轮未执行。

- 2026-07-27 只读核查 + Mac↔生产对账（`internalReadonlyApi.ts` sha256 一致）：internal-readonly 实测 **15 个 GET 接口**——`/lingxing-sales/daily-overview`(date必填)、`/lingxing-sales/sync-tasks`、`/ads/product-daily`、`/walmart-ads/list`、`/ads/keyword-daily`(含 keyword_bid)、`/inventory/daily`、`/products`、`/owners`、`/keywords`、`/events`(生产 834 行)、`/ai-analysis`(0 行)、`/sales-detail/list`、`/raw/feishu`、`/feishu-raw-sales/data`、`/raw/lingxing`。接口文档见 `交付件/internal_readonly_api_接口文档_20260727.md`。
- 2026-07-27 已在 Mac 修复、待部署 AI scp 上线（生产尚为旧版，以部署后为准）：①`/lingxing-sales/sync-tasks` 因 `isWriteLikePath` 正则把 `sync-` 误判为写类而恒 403 → 已显式豁免；②三个 RAW 接口传 `store/store_id/item_id/msku` 触发 `Unknown column` 500 → 新增 `rejectRawBusinessParams` 提前返回 **400**(`unsupported_params`)，RAW 不承载业务列过滤（业务筛选走 `/sales-detail/list`）。
### 海外中转机

- IP：`38.244.59.150`
- 主机名：`ecs-2ow6b`
- 系统/组件：CentOS Linux 7 (Core)，内核 `4.11.8-1.el7.elrepo.x86_64`，Nginx + certbot，`gpt-api.giginana.com`。
- 核验时间：2026-07-07 22:40 CST。
- 用途：海外 HTTPS 反向代理入口；`/ads-ai-api/`、`/auth-check`、`/api/` 经本机 `127.0.0.1:18090` SSH 反向隧道进入国内 ads-ai-api；`/api/internal-readonly/` 代理到国内 `42.193.254.170:3001`。
- Nginx 状态：`active`。
- 运行服务：`nginx.service`、`sshd.service`、`crond.service`、`chronyd.service`、`NetworkManager.service`、`rsyslog.service`、`auditd.service`、`postfix.service`、`qemu-guest-agent.service`、`x-ui.service` 等；未见 `docker`、`node`、`pm2` 常驻服务。
- 监听状态：`*:80`、`[::]:80`、`*:443` 由 Nginx 监听；`*:22`、`[::]:22` 由 sshd 监听；`127.0.0.1:18090` 由 sshd 监听，未暴露到公网网卡；另有 `127.0.0.1:25`、`127.0.0.1:62789`、`[::]:15000`、`[::]:56031`。
- 证书：`/etc/letsencrypt/live/gpt-api.giginana.com/fullchain.pem`，到期时间 `2026-09-30 13:23:12+00:00`，核验时剩余 84 天。
- certbot dry-run：`certbot renew --dry-run --no-random-sleep-on-renew --non-interactive` 已成功，输出 `Congratulations, all simulated renewals succeeded`。
- certbot timer：`certbot-renew.timer` 存在但 `disabled`，`systemctl list-timers | grep -i certbot` 无 active timer。
- 自动续期补救：root crontab 已增加 `0 3 * * * certbot renew --quiet --deploy-hook "systemctl reload nginx"`。
- `/opt` 项目目录：海外机 `/opt` 下未发现业务项目目录；主要配置在 `/etc/nginx/`、`/etc/letsencrypt/`、日志在 `/var/log/nginx/` 和 systemd journal。
- 资源状态：根分区 19G，已用 2.5G，使用率 13%；内存 991M，可用约 595M；运行时间约 58 天。
- 自动任务：root crontab 仅见 certbot 续期任务；systemd timers 仅见 `systemd-tmpfiles-clean.timer` 和 inactive 的 `systemd-readahead-done.timer`。
- 日志风险：Nginx error log 有大量互联网扫描路径，包括 `.env`、`.git/config`、`phpunit`、`wp-*`、`xmlrpc.php`；journal 有 root SSH 连续认证失败。SSH 连接提示未使用 post-quantum key exchange algorithm，属于远期 SSH 加固项。
- 资产报告：`/opt/lingxing-auto/reports/overseas_proxy_server_asset_report.md`。

Nginx 配置全文：`/etc/nginx/conf.d/gpt-api.conf`

```nginx
server {
    listen 80;
    server_name gpt-api.giginana.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name gpt-api.giginana.com;

    ssl_certificate /etc/letsencrypt/live/gpt-api.giginana.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/gpt-api.giginana.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

location /api/internal-readonly/ {
    proxy_pass http://42.193.254.170:3001/api/internal-readonly/;

    proxy_http_version 1.1;
    proxy_set_header Host 42.193.254.170;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;
}

    location /ads-ai-api/ {
        proxy_pass http://127.0.0.1:18090/;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header Connection "";

        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
    }

    location = /auth-check {
        proxy_pass http://127.0.0.1:18090/auth-check;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header Connection "";

        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:18090/api/;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header Connection "";

        proxy_read_timeout 15s;
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
    }

    location = /privacy.html {
        root /usr/share/nginx/html;
        default_type text/html;
    }
}
```

### 账号体系

- `ads_ai_reader`：ads-ai-api 只读查询账号，用途只读。
- `ads_etl_writer`：利润 ETL 写账号，用途限权写 `fact_profit_daily`。
- lingxing-auto 写账号：同步脚本写 RAW/DIM/FACT/状态表。
- Nginx Basic Auth：原保护 Admin/中转入口，账号密码不写入 context。**（2026-07-25 主站 :80 与数据中心 :8081 已由「统一登录/SSO」取代，见下节；海外中转入口暂仍保留）**

## 统一登录 / SSO 架构（2026-07-25）

站点级用户名+密码登录，取代原 Nginx Basic Auth 与下载密码（`dim_access_password` 保留作废、历史不删）。目标：谁登录、谁操作可审计；账号从飞书花名册自动同步。表结构见 DATABASE_MAP「用户名/权限」节。

### 会话与令牌
- Cookie：`app_session`，httpOnly + sameSite=lax；secure 由 env `COOKIE_SECURE` 控制（当前纯 HTTP 站点默认关，上 HTTPS 置 1）。
- 令牌：JWT HS256，密钥只读 env `AUTH_JWT_SECRET`（禁硬编码）；payload = { uid, un, tv }。
- 不设过期（需求「登录态不过期」）；吊销靠 `token_version`——改密时 `dim_app_user.token_version+1`，旧 JWT 立即失效（resolveUser 校验 tv 与库一致）。
- 密码：bcrypt（rounds=12，bcryptjs），永不存明文。

### 后端网关与鉴权（src/，隔离新模块）
- `authService.ts`：bcrypt 哈希/校验、JWT 签发/校验、用户/权限/审计数据访问、登录失败锁定（内存 username+ip 维度，5 次起递增退避 30s→30min）、飞书改密一次性 reset token（内存 10min）。
- `authMiddleware.ts`：`resolveUser(req)` 验 cookie JWT→查库确认 is_active 且 token_version 匹配→注入 `req.user`(id/username/display_name/role/team_name/isSuperadmin/permissions:Set)，返回 bool、不发响应（供全站网关）；`requireAuth`（失败即 401）；`requirePermission(permKey)`（超管绕过，否则 403「无操作权限」）。COOKIE_NAME=`app_session`。
- `authRoutes.ts`（挂 `/api/auth`）：POST `/login`（锁定+审计+下发 cookie）、`/logout`、GET `/me`、POST `/change-password`、POST `/request-reset`（飞书名→花名册精确解析→发改密卡）、GET `/verify`（requireAuth，供 nginx auth_request，200/401）。
- `adminServer.ts` 全站网关：env `AUTH_ENABLED=1` 启用（关闭时同现状）；放行 `/login`、`/login.html`、`/api/auth/*`、`/favicon.ico`（internal-readonly 与飞书回调各自在上游已鉴权）；其余未登录：`/api/*` 返回 401 JSON，页面 302 跳 `/login.html`。

### 三端统一（SSO，同域名共享 cookie）
- **:80 主站**（lingxing-admin, 3001）：app 层网关（上），移除 server 级 auth_basic；`/` 与 `/index.html` → 302 `/admin/`；`/login` `/login.html` `/api/auth/` → 3001。
- **:8081 数据中心**（静态 app）：nginx `auth_request` → 代理 3001 `/api/auth/verify` 并透传 Cookie；未登录 `error_page 401` → 302 主站 `/login.html`。
- **:3000 广告应用**（walmart-ads-data, Next.js）：edge middleware（jose 验 app_session HS256），无效 → 302 `/login.html`；matcher 排除 `_next/static`。
- 三端同 host（42.193.254.170）共享 `app_session` cookie，一次登录全站通。
- **:3457 会议分析服务**（walmart-meeting-server.service，跑在 /opt/walmart-ai-data-center/backend，独立于 lingxing-auto 仓库）：飞书妙记(lark-cli jim profile 用户令牌,scope minutes:minutes.search:read)+附件 → AI 分析。2026-08-08 起单元文件加 `EnvironmentFile=/opt/lingxing-auto/.env`（排自身 .env 之后,同名以切换器为准）,AI_* 跟随 LLM 切换器;切换后需 restart 本服务。令牌失效修复:Jim 本人 `lark-cli --profile jim auth login --scope minutes:minutes.search:read --domain vc`。
- **:3456 LLM 切换器**（apiKeyManager，2026-07-31 并入 SSO）：原独立 `admin123` 密码已废除，改读同域 `app_session` cookie 验签（AUTH_JWT_SECRET）+查 `dim_app_user` 核对 token_version/is_active，仅放行 `LLM_MANAGER_ALLOW`（默认「陈佳聪」，匹配 username 或 display_name；陈佳聪 uid=22，两者皆等于「陈佳聪」）。页面加载先打 `/api/whoami` 判权，所有读写接口 403 网关。该页管理 .env 的 `AI_BASE_URL/AI_MODEL/AI_API_KEY` 与 `config/apiKeyProfiles.json`（多套配置）。cookie 跨端口共享，故 :3456 无需单独登录。

### 飞书自助改密（首次登录 / 忘记密码，同一套）
- 登录页「首次登录/忘记密码」→ 输真实飞书名 → 后端花名册精确解析（0 个或重名都返回「错误，请联系人事」）→ 给本人飞书发卡片 JSON 2.0（form+input+form_submit，携一次性 token）。
- 卡内输入密码提交 → `/api/feishu-card-callback` 验 token/openId → setPassword（bcrypt）→ 回执成功卡、原卡失效；token 一次性、10min。

### 权限与审计
- 角色 `dim_app_user.role`：admin/supervisor/team_lead/member；`is_superadmin` 绕过一切。
- 细粒度授权 `dim_app_user_permission(user_id, perm_key)`；如 `clearance_approval`（清货审批，授林翔）。
- 审计 `biz_app_audit_log`：login/login_fail/logout/change_password/reset_card_sent 等，记 user/ip/ua/detail。
- 账号同步 `src/syncAppUsersFromMembers.ts`：从 `dim_feishu_member`(active) 同步→`dim_app_user`（username=真名，password_hash='!' 占位待首登设密，must_change_password=1）；离职→is_active=0，不删历史（`--confirm-write` 守卫）。

分层归属：`dim_app_user` / `dim_app_user_permission` 属 DIM，`biz_app_audit_log` 属审计（EVENT）；前端只读、AI 不写这些表。

## 规划中模块

已实现与规划必须分开，防止后续 AI 误判。

| 模块 | 当前状态 | 证据路径 |
|---|---|---|
| AI智能PMC | 部分代码已存在并有 dry-run 记录；不是完整中台闭环 | `src/ai_pmc/`、`reports/product_management_v1_2_downstream_migration_report.md`、`reports/feishu_mention_mapping_probe_report.md` |
| AI财务 | 仅方向/规划；财务净利和退款口径等待业务立项 | `项目总结_GPT经营分析系统_2026-07.md` |
| AI人事 | 仅方向/规划；未发现独立实现模块 | `context/PROJECT_CONTEXT.md` 历史记录 |
| 飞书通报机器人（B线后续） | 已有多个通知脚本；B线第 5 期类“经营状态通报”未作为独立模块实现 | `src/noOrderNotify.ts`、`src/unmatchedOwnerNotify.ts`、`src/lowProfitNotify.ts`、`B线第1期/第1期实施_完整提示词.md` |
| 采购/已采购库存接入 PMC | B 线第 1 期明确不做，状态表 `purchased_stock` 当前为 0 | `B线第1期/第1期实施_完整提示词.md`、`dim_product_business_state.purchased_stock` |

## 需要确认

1. （已解决 2026-07-08）`dim_product_business_state` 20:30 每日 crontab 已上线且数据同步到 2026-07-05；剩余动作：2026-07-08 晚复查 20:15/20:30 首次 cron 触发日志。
2. `/api/ops/analyze` 是否需要支持 POST；当前生产 GET 可用，POST 405。
3. 生产 `dim_product.product_name` 已于 2026-07-08 回填 1354 条，仍有 187 条未命中；`dim_product.store_name` 仍为空，后续如需修复需另行探源。
4. 备份/旧表是否保留：`backup_*`、`walmart_ad_*`、`tasks`。


## 2026-07-14 / WFS到货提醒系统

模块定位：WFS 到货提醒覆盖 R1 货件到仓、R2 库存 0->非0、R3 已接收无广告、R4 长时间无广告升级提醒。设计依据为 `docs/wfs_arrival_notify_design.md` v1.1+R4。

生产文件：
- `src/notifyRules/wfsArrivalRule.ts`：规则纯函数与文案构造。
- `src/notifyRules/wfsArrivalRule.test.ts`：规则测试。
- `src/syncWfsShipments.ts`：WFS货件同步与R1事件生成。
- `src/buildArrivalEvents.ts`：R2/R3/R4事件检测。
- `src/arrivalNotify.ts`：到货提醒发送；测试模式只发测试群且不回写事件状态。

数据表：`fact_wfs_shipment`、`fact_wfs_shipment_item`、`event_arrival_notify`。事件表唯一键为 `event_type + biz_key`，用于幂等；通知状态由 `notify_status/notified_at/notify_error` 表达。

阶段状态：阶段1已完成建表、首次90天回填、事件检测和测试群通报；阶段2 cron 转正尚未授权，生产群和负责人真实触达尚未开启。
### WFS到货提醒阶段2

- 发送脚本：`src/arrivalNotify.ts`
- 群通道：生产当前走 `FEISHU_ARRIVAL_CHAT_ID` 应用机器人群；代码已支持 `FEISHU_ARRIVAL_WEBHOOK_URL` 外部群 webhook 回退，两者同配时优先 chat_id。
- 依赖事件表：`event_arrival_notify`
- 依赖构建链：`syncWfsShipments.ts -> buildArrivalEvents.ts -> arrivalNotify.ts`
- 发送纪律：人工阶段仅允许 1 条链路验证消息；正式发送只允许由 14:00 cron `notify:arrival:send` 触发。

### WFS到货提醒 / 广告组静默扩展（R5/R6）
- 事件类型：`ad_group_silent`（连续 5 个数据日 0 花费且 0 曝光）、`ad_group_no_spend`（连续 7 个数据日 0 花费）
- 收敛护栏：
  - `freshGrace=5`：仅首个跨阈值后 5 天内的静默段允许入事件，防止首跑积压
  - `AD_SILENCE_ACTIVITY_WINDOW=7`：静默段前 7 天内必须有活跃，否则视为历史死组/无效段
  - `库存为0剔除`：关联商品当前总可售库存为 0 时不提醒
- 当前默认口径：R3 `wfs_no_ads_daily` 已停用（仅计数不写入）；R4 升级扣绩效仅针对“无任何广告行”；R5/R6 用于覆盖“已创建但未投放/持续静默”。

### 广告组静默发送状态（2026-07-15）
- `ad_group_silent` / `ad_group_no_spend` 事件仍写入 `event_arrival_notify`，用于误报分析和后续专属通道设计。
- `src/arrivalNotify.ts` 当前仅对白名单 `wfs_*` 事件发送；`ad_group_*` 不进入发送队列。
- 当前策略：事件生成保留、发送暂停、禁止直接复用到货通报通道。

### 清货审批链路（2026-07-20 批①上线）
- 产品管理页"设为清货期"→ 申请制：写 event_clearance_approval(pending)，dim_product 不变，页面显示"清货审批中"角标；改其他状态自动撤销申请。
- 每日 09:33 `clearanceApprovalNotify --send`：🧹汇总卡（逐条同意/驳回按钮，CHUNK=10拆卡）发 CLEARANCE_APPROVER（默认林翔）。
- 回调 `feishuCardCallbackRoutes` biz=clearance_approval：验签+仅审批人+幂等；同意=事务内按 item_id 批量写 manual_lifecycle_stage='清货期'+审计；驳回=审计+异步私信申请人。
- 通用层新增 `sendCardToTarget`（feishuNotify）：卡片发群/个人（open_id），失败降级文本+镜像+dry-run。
- 清货中心（批②）：adminServer 挂载 /api/clearance-center（clearanceCenterRoutes 新模块）；前端 FeishuRawSalesData 顶部 Tab "__clearance__"→ ClearanceCenter.tsx 新组件。
- ⚠️工程纪律：feishuRawSalesRoutes.ts 与 admin-frontend/FeishuRawSalesData.tsx 本地与生产分叉，只允许锚点补丁部署，禁止整文件覆盖。
- 页面审批入口（2026-07-25）：清货中心「待审批」行「操作」列新增「同意/驳回」按钮。
  后端 clearanceCenterRoutes.ts 新增 POST /api/clearance-center/approve {id}、/reject {id,reason?}，
  鉴权 requireAuth + requirePermission("clearance_approval")（超管绕过）；审批人取 req.user.username。
  同意=事务内 UPDATE dim_product 设清货期(manual_lifecycle_by="林翔(页面审批)") + event_clearance_approval status=approved + 审计(biz_event event_type=clearance_approval_web) + 异步私信申请人；
  驳回=status=rejected + reject_reason + 私信申请人（理由可空）。逻辑与飞书卡回调 feishuCardCallbackRoutes 同款。
  /list 的待审批行透传 approval_id(=event_clearance_approval.id) 供前端调用。
  飞书卡（09:33）作为兜底不变：未在页面处理的申请次日仍推送审批人。
- 权限键：clearance_approval（授予林翔；见 dim_app_user_permission）。用户名系统鉴权，非授权者点击返回 403「无操作权限」。

## 2026-07-23 / 飞书表格退役现状（只读核查）

部署AI只读实扫结论：active cron 中已无任务写“真飞书在线表格”，飞书在线表全部停写。仍持续更新的“飞书表”是 `raw_feishu_table` 系统自造快照：核心在用 `<REDACTED_FEISHU_SHEET_ID>`(每日销售明细)、`order_profit_daily`(订单利润Beta)；`<REDACTED_FEISHU_SHEET_ID>/<REDACTED_FEISHU_SHEET_ID>` 仍被 16:45 backfillDailyChain 刷新但为隐藏历史 Tab、非可见主功能；`<REDACTED_FEISHU_SHEET_ID>/<REDACTED_FEISHU_SHEET_ID>` 为已停用僵尸。
前端可见 Tab=`<REDACTED_FEISHU_SHEET_ID>/order_profit_daily/cs_test_analysis/product_management/operation_log`，直读 RAW 仅前两者。生产 live ads-ai-api（`/query/*`、`/api/ops/analyze`）均不读 `raw_feishu_table`。未调度的遗留写飞书脚本（`syncNoMovingProducts/syncYuesiTestProductAnalysis/syncRecentProfitAndAds/aiDailyDiagnosis/syncDailyOperationLogBase`）仍保留 FeishuSheetWriter 能力但无 cron。本次仅记录，未改动。详见 DATABASE_MAP / TASK_CHANGE_LOG 2026-07-23 节。

## 2026-07-24 / CS测品异常预警系统
- 检测(csTestAlertNotify.ts --detect[--execute])：逐字复刻 cs-test-analysis 生产聚合，筛 (test_days>20 或 total_sales_qty>11) 且 test_end_date NULL【2026-07-29放宽:AND→OR,未结束仍硬前提】 → upsert biz_cs_test_alert。
- 通知(--notify[--test-send/--send])：负责人收飞书2.0输入卡(填原因≥15字=消警+转发林翔；卡上写明绩效规则)；主管(林翔/陈佳聪=CS_ALERT_SUPERVISORS)收汇总卡；扣分明细同步黄少如(CS_ALERT_PENALTY_NOTIFY，人事稽核)。
- 累计扣分：第2次提醒起每工作日未填原因扣5分(biz_perf_deduction biz_type=cs_test_alert，ref_event_id=(测试3e9/正式2e9)+id*1e4+send_count 防重放【2026-07-29:测试/正式独立命名空间,修测试行撞键吞正式扣分】)；同日护栏(last_sent_date==当日整行跳过)；测试模式扣分行 created_by=..._TEST + note【测试】。
- 回调(feishuCardCallbackRoutes cs_test_alert 分支)：form_value.reason≥15 → 写 reason+status=resolved+转发林翔(测试→测试群)。
- 前端：CS测品分析页(FeishuRawSalesData)「预警原因」列，被预警产品可编辑(≥15字保存即消警)、非预警显「—」；后端 cs-test-analysis 旁查 biz_cs_test_alert 透传 _cs_alert_id/_cs_alert_editable；写接口 POST /api/feishu-raw-sales/cs-test/save-alert-reason。

## 2026-07-24 / 绩效台账改造（月度+说明+豁免）
- HrPerformance 绩效台账 Tab：按月(deduction_date 归月)；明细在上/汇总在下；项目中文化(BIZ_TYPE_LABEL)；统一工具条(复用共享件 LxToolbar/LxMultiSelect，产品管理同款，不自造)。
- 逐笔绩效说明(被扣分本人填)+豁免(黄少如/林翔任一，exempt_status=1 免扣合计)，落 biz_perf_deduction_note；biz_perf_deduction 零改动。窗口：次月5号前。
- 后端 hrRoutes.ts：deductions 加 month + LEFT JOIN note + 合计排除豁免；POST /api/hr/perf/note/save、/perf/exempt(env PERF_EXEMPT_APPROVERS=黄少如,林翔；窗口校验)。


## 2026-07-27 / 领星Walmart发布状态入库 + UNPUBLISHED规则

领星「Walmart在线商品列表」接口 `status`（Walmart发布状态）现已入库并驱动下架品处理。
- 状态枚举（领星原样 `status_name`）：PUBLISHED(在售) / READY TO PUBLISH(待发布) / IN PROGRESS(处理中) / UNPUBLISHED(已下架) / STAGE(草稿) / SYSTEM PROBLEM(系统错误)。
- 入库：`syncLingxingDailyToDb.ts` 每日拉 walmart/list 全状态，原始入 RAW，派生写 `dim_product.walmart_publish_status`（空值不覆盖）。字段见 DATABASE_MAP。
- UNPUBLISHED（已下架）三条规则：
  1. 免匹配负责人：`syncMissingItemOwners.ts` 不把 UNPUBLISHED 推进飞书「ItemID负责人」待认领候选。
  2. 免催认领/免绩效扣分：`unmatchedOwnerNotify.ts` 待认领选品排除 UNPUBLISHED（不进首/二次提醒、不扣分）。
  3. 提醒归档：`unmatchedOwnerNotify.ts` 待认领日报新增「🗄 建议归档（已下架 UNPUBLISHED）」区，列出所有 active 的 UNPUBLISHED（含负责人），提醒去产品管理页归档；已归档的不再提醒；仅提醒、零扣分、零状态写入。

**2026-07-27 升级（unmatchedOwnerNotify.ts）**：整卡改名「待认领产品日报」→「产品管理提醒通知」。同卡新增三类绩效扣分区（首次不扣/二次扣5分/归负责人，独立 EVENT 表见 DATABASE_MAP 2026-07-27 节）：缺WFS配送费(missing_wfs_fee)、缺GPT关键词链接(missing_gpt_keyword,含CS)、缺GPT广告链接(missing_gpt_ads,需WFS连续14天有库存)。归档不算。另有一次性过渡脚本 gptKwOwnerSummary.ts(按负责人汇总、不扣分、起表；一次性，不入档)。
- CS测品异常预警扣分（csTestAlertNotify）本次未纳入，维持原状。
- 提交：296cd05(存状态+三规则) / 5261053(归档口径放宽为全部 active UNPUBLISHED + 显示负责人)。


## 2026-07-30 / AI人力·考勤模块（月度核算）

飞书假勤（熵基飞书版考勤机）→ 飞书考勤 OpenAPI，AI人力新增「考勤」页（月度核算）。仅超管/人事可见。
- 数据源三接口（employee_type=employee_id，user_ids 用通讯录 open_id→user_id 换出）：
  - 打卡结果 `attendance/v1/user_tasks/query`（check_date_from/to 整数）：正常/迟到Late/严重迟到SeriousLate/早退Early/缺卡Lack；休息日 shift_id="0" 且 result="NoNeedCheck"。
  - 打卡流水 `user_flows/query`（check_time_from/to 秒）：算加班超时（末次打卡−排班下班，30分钟宽限）。
  - 考勤审批 `user_approvals/query`：请假 leaves / 外出 outs（i18n_names.ch 类型 + interval 秒时长）。
- 分层：`syncFeishuAttendance.ts` → RAW `raw_feishu_attendance` 原样留存 → 派生 FACT `fact_attendance_daily`（每人每天）→ 月度聚合。前端只读 FACT。
- 口径（用户拍板）：应出勤=飞书排班工作日（大小周由排班定；公司非工作日=多数打卡员工都没打卡的排班日，自动排除）；实出勤=排班日有打卡；免打卡=整月0打卡（管理层，应出勤=0不计旷工）；加班=打卡超时（公司无加班审批）。
- 接口：`/api/hr/attendance/{months,monthly}`（attendanceRoutes.ts，`requireAuth`+`requirePermission("hr_attendance")`，超管绕过；人事黄少如授权）。monthly 返回 kpi+items+latest_sync_time。
- 前端：`Attendance.tsx`（AppShell AI人力「考勤」；UI_STANDARDS 合规：LxToolbar 工具条/壳内帮助/列宽可拖/列配置/筛选；仅 Google 配色）。帮助文 dim_page_help(page_key=attendance)。
- 定时：每日 00:45 `npm run sync:attendance -- --daily --write`（当月+上月，覆盖补卡/审批滞后）。生产 crontab。
- 迁移：sql/031(建表+授权) / 032(帮助文) / 033(帮助排期) / 034(缺卡事件表) / 035(帮助文补缺卡通报)。异常通报一期=缺卡通报(见下)；其余类型(迟到汇总等)二期。

## 2026-07-31 / AI人力·考勤缺卡通报（EVENT，异常通报一期）

飞书缺卡（fact_attendance_daily.day_status=缺卡：上班/下班/双缺漏打）→ 次日 09:50 推提醒卡到本人私信 + 人事群（oc_149a50a2c1bf2dfc861dbf0236833aed）。
- 脚本 `attendanceLackAlert.ts`：`--push`(次日通报；先锁 push_at 超24h 的 pending→expired，再检测昨日缺卡建卡+发个人+人事群日报) / `--remind`(push_at 在12~24h 且未确认未重发的重发一次)；默认 dry-run，`--test`(仅测试群零写库)，`--send`(真发+写库)；`--date=YYYY-MM-DD` 覆盖(默认昨日，历史缺卡日验卡用)。
- 分层：读 FACT `fact_attendance_daily` → 写 EVENT `event_attendance_lack_alert`；发送复用 `feishuNotify.sendCardToTarget`。确认态存 EVENT，不改 FACT(每日同步会覆盖)。
- 口径(用户拍板)：确认=知悉(不改考勤结果)；从推送时刻起 24h 有效；满 12h 未确认重发一次；满 24h 未确认锁定、不可再确认，该缺卡在月度核算按旷工计(`attendanceRoutes` /monthly LEFT JOIN `event_attendance_lack_alert`，expired→旷工，lack/absent/present 联动)；上班/下班/双缺都报；人事可线下补卡(系统只锁员工自助确认这一步)。
- 回调：`feishuCardCallbackRoutes` biz=`lack_ack`(仅本人 open_id 可确认；已确认幂等；超24h或已锁则拒并置 expired；确认/失效即时更新卡片，schema 1.0 与原卡一致)。个人卡 `test:1` 分支只 toast 不写库。
- 定时：每日 09:50 `--push --send` / 21:50 `--remind --send`（生产 crontab）。
- 生产补验(2026-07-31)：`--date=2026-07-29`(2人缺卡) 测试群收到 2 红头个人卡+1 蓝头人事群日报，回调 toast 正常，test:1 零写库。


## 2026-08 目标管理 8 月新规（M1–M8 总览，2026-08-04）
- **填报周期**：7号23:59截止、8号起每人每天扣5分(不封顶)；过8号运营锁定、超管(林翔/陈佳聪)代填。
- **谁填**：全量在营(非CS·非新品·非豁免)均需填并定目标；考核=全量(非"只看问题产品")。完成=有 biz_monthly_plan 行且 target_sales_amount 非空(勾正常运营也必填)。
- **豁免 v5**：上月整月 WFS 库存 MAX=0 且 WFS 销量=0 且 WFS 在途=0；清货期不豁免；新品(上架月=规划月)走公司公式、不填不扣。
- **越权闸门(M1)**：仅可填本人；超管任意人/任意时间。**每日扣分(M3)**：event_monthly_plan_unfilled + biz_perf_deduction(monthly_plan_unfilled)，cron 09:25。**催办(M3.5)** 09:20 对齐 v5。
- **清货填报(M4)**：清货期指标锁"清货"+必填清货数量/销售额，利润自动=销售额×(−10%)。**清货中心(M5)**：目标同一张表、仅超管可写运营只读、无目标每日提醒林翔(09:35 8号起)。**经营分析(M6)** 含/不含清货切换。**导入导出(M7)** 表头名匹配+导出免密。**月报生成(M8)** 4日06:00、豁免同步 v5。
- 前端瓦片(目标管理页)：在营需填报(剔除新品)/问题产品/清货产品/未填(全量非新品未填=扣分口径)/新品/豁免。
- 涉及表：biz_monthly_plan(人工)、event_monthly_plan_unfilled(EVENT)、biz_perf_deduction(镜像)、ai_monthly_issue_item(AI层清单)。详见 DATABASE_MAP / PIPELINE_MAP / TASK_CHANGE_LOG。
## 2026-08-05~10 / 归档到货提醒卡 + P7 数据完整性哨兵 + 销量统一口径

**归档产品到货提醒卡（2026-08-05 上线，长期机制）**
- `src/checkArchivedRestockAlert.ts`（cron 09:40）：归档品 WFS>5（env `ARCHIVED_RESTOCK_MIN_WFS`）→ 每产品一张交互卡（按钮：恢复在售 / 继续归档（暂停提醒））；晶彩绝伦(110652398125259264,授权过期)排除。
- 事件表 `event_archived_restock_alert`（sql/039，uq_ar_item=平台+店铺+ItemID，wfs_qty=确认基线，remark 人工列）。
- 回调 `feishuCardCallbackRoutes` biz=`archived_restock`：restore→dim_product 转 active(source='card')；keep→暂停提醒，但库存超上次确认基线自动复提（复提卡显示"上次确认X件→现Y件"，并清空 keep）；test:1 只 toast 零写库。

**P7 数据完整性哨兵（2026-08-10 上线，v4 定稿）**
- `src/sentinelCore.ts`（共享核心：检查注册表/只读校验/修复白名单执行器/事件CRUD/卡片构造）+ `src/checkDataSentinel.ts`（CLI --check/--remind/--weekly）+ `event_sentinel_alert`（sql/040，uq_sentinel=check_key+target_date）。
- cron：20:15 主检（6项：①saleStat族三表恒等 T-2~T-4 零容差【2026-08-11 起加销量表 rows>0 守卫，堵三源全空 0=0=0 漏报洞】 ②<REDACTED_FEISHU_SHEET_ID> 行数≥600 ③当日库存快照存在 ④msku空串近7天增量=0 ⑤渠道表仅查有无 ⑥经营状态快照 T-3 存在【构建器写 stat_date=最新可用业务日(当天T-2)，20:15 时点最新=T-3；修复=builder --date 重建,近似历史】）；`0 9-23 * * *` 整点提醒（先复查，通过即静默+闭环卡）；周一 09:00 周报。仅通报陈佳聪（SENTINEL_NOTIFY）。
- 闭环：异常发修复确认卡 → 点确认后**系统代码白名单**执行修复（非AI；execFile npx ts-node/python3，15min 超时）→ 立即复查 → 通过发完成卡 / 失败再弹卡（满 2 次 MAX_AUTO_ATTEMPTS 转人工橙卡）；未闭环当天整点提醒至 23:59，次日 09:00 起继续。
- 库存快照修复=以最新快照补录缺失日（source_system='sentinel_backfill'，为 2026-07-18"snapshot_date恒为拉取当日"护栏的显式例外）；msku空串无自动修复（SOP：=未配对 listing 出单，处理=领星配对+回填）。
- 首捕实战：msku 空串增量 1 行（CS421-1A 未配对），已配对+回填 88 行闭环，recent_blank=0。
- 运维口径：哨兵 dry-run 白天手动跑会对 T-2族/当日库存报预期内异常（16:45 backfillDailyChain 才写入），验收一律以 20:15 cron 后日志为准。
- dim_product_business_state 07-01/02/04 已于 2026-08-11 近似回填（各756行,extra_json.backfill 标注；用当前维表回算,现已归档品无行,需求方拍板接受不追补）。

**销量统一口径（2026-08-10 需求方拍板，长期有效）**
- 权威=saleStat 族：`fact_sales_daily`(saleStat) → <REDACTED_FEISHU_SHEET_ID> 明细(派生)；订单利润 RAW → `fact_profit_daily`(ETL)。族内日度必须完全相等【零容差】，P7 哨兵每日校验。
- `fact_mp_sales_channel_daily` 降级为 WFS/非WFS 判定专用（v5 豁免依赖），**禁止**用于销量金额统计对比；两源日期归因差为源特性非缺陷。权威细则见 DATABASE_MAP「2026-08-10 销量统一口径定稿」节。

