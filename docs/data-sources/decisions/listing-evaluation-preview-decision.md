# Listing 自动评级与生命周期只读试算：数据源决策调查（待负责人确认）

- 日期：2026-10-26
- 目标接口：现有 `GET /api/listings/evaluation-preview`（只读诊断，默认禁用）
- 用途：按可访问店铺、Listing 标识和 LA 业务截止日计算等级与生命周期，并解释证据不足原因
- **正式评级发布决策：BLOCKED_BY_OWNER_DECISION**（只读诊断接口已有代码）
- 是否包含 `NEED_OWNER_DECISION`：**是**
- 负责人批准状态：**待确认**
- 本文件记录源码中的数据源边界，不批准正式评级发布、生产调度或历史回填

## 2026-11-02 负责人已明确的部分口径

- 本轮正式评级和生命周期只覆盖 WFS；FBM 不参与，普通 Listing 浏览仍可显示 FBM。
- 销售业务日结束后，美国次日 00:00 的最后一次同步必须成功，才能把没有销售记录认证为零。每次评级以洛杉矶执行日的 T-2 为截止业务日，直接使用“每日销售”已算好的多日销售额和利润；广告费、退款已由每日销售处理，评级模块不再分别查询或重算。
- 负责人进一步确认：广告完整性信号看领星广告报表接口返回的**同账号、同 LA 业务日全部广告行**；只有整批广告费均为零或缺失才阻断，不要求当前 SKU 有广告费。试算读取该接口已入库的 `fact_walmart_ad_item_sp_daily` 全部账号日行（包括未关联当前 Listing 的行），不拿每日销售 MART 的单品广告费代替接口整批结果。每日销售仍是评级销售额和利润的来源，且必须有日级完成证据。
- 人工生命周期调整优先于自动计算；正式评级希望证据齐全后自动生效、执行时间可配置。权限、审计、人工覆盖保护、完整性水位及生产启用仍需另行闭环。
- 页面上架时间采用新 Listing 开始监测后首次观察到 WFS 库存至少为 1 的日期；旧 Listing 无该证据时显示待核实。保留 ERP 原始值，不将其转换或回填成标准时间。
- 负责人于 2026-11-03 确认：WFS 库存完整性从功能上线后记录每日采集完成标记；旧日期没有标记时继续待评级，不补造历史完成证明，并单独批准本地标记切片。PR #277 本地代码已按逐页 `pulled_at` 写库存日事实，仅在分页总量一致、业务键唯一有效且所有页属于同一 LA 日时，随库存事务写账号业务日完成事件。此前生产同步无此事件，不能倒推“完整采集”；跨洛杉矶午夜、总量未核实、跳过无身份行或分页失败仍保持未知。正式评级消费事件及生产启用未获批准。

以上只解决部分业务定义。T-2 是计算截止日，不能单凭日期推断每日销售同步成功。新同步运行会为每个账号业务日记录 `SYNC_SALESTAT_DAY_PENDING` / `SYNC_SALESTAT_DAY_VALIDATED`；只认次日 00:00（洛杉矶时间）之后、且最新事件为 validated 的业务日。旧运行没有该事件时保持待评级，不补造历史完成记录。当前只读试算接口和诊断快照代码已存在，均不等于正式评级可以发布。历史阶段来源和正式发布 PRP 仍缺失，故正式发布决策继续为 `BLOCKED_BY_OWNER_DECISION`。

## 现有可复用证据（不是接口实施授权）

| 资源 | 现有位置 | 能支持的内容 | 当前不能推断 |
|---|---|---|---|
| Listing 当前映射 | `backend/app/modules/data_pages/models.py::ListingManagementCurrentMart` | 店铺、Item ID、MSKU、生命周期当前状态 | 历史状态、历史审批证据 |
| ERP 每日销售 MART | `backend/app/modules/data_pages/models.py::DailySalesItemDayMart` | `business_date_la`、`source_account_ref`、`store_id`、`item_id`、`msku`、`gross_profit_amount`、`cost_status`、`calculation_warnings_json` | T-2 每日销售是否已成功同步并完成计算 |
| 每日销售事实口径 | `docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md` | 严格业务键 `business_date + store_id + item_id + msku`；`net_sales_amount` 和 `order_profit` 公式 | 无销售行能否由每日销售完成状态确认是真零 |
| WFS 每日库存 | `backend/app/modules/data_pages/repository.py` 已引用 `WalmartListingInventoryDailyFact` | 可以继续调查每日库存快照及关联条件 | 不得用当前 WFS 量推断历史连续断货 |
| 计算与只读适配 | `backend/app/modules/listing_rule_config/evaluation.py`、`preview.py`、`preview_router.py` | 纯函数、账号限定的 MART/库存/监控证据读取、单条和最多 50 条的只读试算接口 | 缺失的历史事件、完整性证据和正式发布权限不能由试算补造；接口默认禁用 |
| 配置与诊断快照 | `backend/app/modules/listing_rule_config/service.py`、`models.py`、`batch.py` | 规则版本、诊断运行和未发布快照 | 诊断结果不写回 Listing 正式等级，也不代表正式发布 |

## 旧系统/上游强制前置调查

| 调查项 | 当前结论 |
|---|---|
| 旧页面 / 旧 API / 旧接口位置 | 未读取；本次不触碰 `old-system/**`，依项目边界待授权或注明不适用 |
| 读取表 / 写入方 | 新系统上述 MART；具体日事实写入管线与完成标识待逐项核对 |
| cron / 脚本 / 外部 API | 按 DATA-PAGES-1 已有同步治理框架调查；本次不调用 |
| 人工写库入口 | 只读试算不写库；现有诊断批次只存未发布快照，正式等级写回仍需独立 PRP |
| 外部平台重新获取可能性 | 依现有同步任务；禁止接口中实时拉取平台 |
| 少量配置数据可行性 | 规则版本走新系统配置；无需重复建立配置源 |
| 短期 / 长期策略 | 先只读现有 MART 与显式完整性证明；长期留痕的结果快照为独立 NEW_SYSTEM_OWNED 模块 |

## 待确认数据集与权威分类

| 数据集或字段组 | 候选分类 | 推荐来源 | 状态与风险 |
|---|---|---|---|
| Listing 当前状态与归属 | REBUILD_SYNC（沿用 DATA-PAGES-1） | Listing MART | 必须校验操作人 account_refs/data-scope；不可只靠 store_id |
| 按 LA 天的销售额、利润 | REBUILD_SYNC（沿用 DATA-PAGES-1） | DailySalesItemDayMart | 必须严格匹配 `source_account_ref/store_id/item_id/msku`，避免重复归集 |
| WFS 每日历史库存 | REBUILD_SYNC（本地标记切片获批；正式评级仍阻断） | 已有库存 FACT 及未来成功的全分页采集完成标记 | 旧日无水位、跨 LA 午夜、未核实总量、跳过身份行或失败分页均保持未知；未部署前无生产标记 |
| 评级财务数据源 | **负责人已确认：每日销售** | `DailySalesItemDayMart` 已算好的销售额、利润及完成状态 | 不为评级另建广告或退款聚合；每日销售 T-2 未成功完成或成本状态不完整时输出“待评级” |
| 历史划线价/购物车异常 | APPROVED_SOURCE | `std_walmart_monitor_listing_observations` 按 LA 日的监控观察 | 仅使用明确观察；缺失日保持未知，不推断连续异常 |
| 清货/归档审批事件 | **NEED_OWNER_DECISION** | 现有审批记录及事件顺序 | 审批状态优先级必须可追溯 |
| 自动评级结果历史快照 | NEW_SYSTEM_OWNED（已有诊断快照） | `ListingEvaluationRun` / `ListingEvaluationSnapshot` | 现有快照未发布；正式生效、覆盖保护和回滚仍需获批 PRP |
| C/D 运营跟进记录 | NEW_SYSTEM_OWNED（未来切片） | 现有运营日志/待办模块 | 关联键、跨日去重、完成口径需确认 |

## 现有只读诊断 API 与正式发布边界

- 现有 `GET /api/listings/evaluation-preview` 接收 Listing UUID 与可选 LA 截止日；`POST /api/listings/evaluation-preview/batch` 最多接收 50 个 UUID；均要求 Listing 页面权限、账号数据范围与 `LISTING_EVALUATION_PREVIEW_ENABLED` 开关，不接受客户端 `upstream_confirmed`。
- 先做权限+数据作用域限制，再查询匹配账号、店铺、Item ID 和可空 MSKU 的日事实及库存观察。
- 日级别以 `business_date_la` 聚合；零销售有完整费用证明的日期与缺数日期严格区分。
- 没有核实完整性证明的日期显式输出 `invalid_dates` / `missing_evidence`，不返回乐观 A/B 等级。
- 试算结果带规则版本、LA 截止日期、有效日和缺证据代码；`published=false`，不把试算结果写回正式 Listing 字段。
- 禁止跨店铺兜底、模糊 MSKU 匹配、合并不同币种、跳过字段权限。

## 最终建议

- **BLOCKED_BY_OWNER_DECISION**：评级财务来源已确定为每日销售；广告完整性信号使用领星广告报表已入库的同账号日全量行，试算还要求每日销售次日 00:00 后的日级同步完成事件。旧数据缺日级事件时保守阻断；WFS 历史证据和审批事件仍未闭环，因此正式发布与生产定时任务继续阻塞。
- 只读数据适配和未发布诊断快照已有代码；仍需独立获批 PRP 才能做正式结果写回、C/D 跟进、Celery 调度及灰度。
- 审批前可完成前端 mock E2E、纯计算测试、业务规则说明与后端数据血缘调查。
- 本文件不构成数据库连接、迁移、执行 Celery 或部署授权。
