# Listing 自动评级与生命周期只读试算：数据源决策调查（待负责人确认）

- 日期：2026-10-26
- 目标接口：拟议 `GET /api/listings/evaluation-preview`（尚未开发，路径待审批）
- 用途：按可访问店铺、Listing 标识和 LA 业务截止日计算等级与生命周期，并解释证据不足原因
- **接口总体状态：BLOCKED_BY_OWNER_DECISION**
- 是否包含 `NEED_OWNER_DECISION`：**是**
- 负责人批准状态：**待确认**
- 本文件仅做仓库代码/文档只读调查；没有连接真实数据库、旧库或外部 API

## 2026-11-02 负责人已明确的部分口径

- 本轮正式评级和生命周期只覆盖 WFS；FBM 不参与，普通 Listing 浏览仍可显示 FBM。
- 销售业务日结束后，美国次日 00:00 的最后一次同步必须成功，才能把没有销售记录认证为零。每次评级以洛杉矶执行日的 T-2 为截止业务日，直接使用“每日销售”已算好的多日销售额和利润；广告费、退款已由每日销售处理，评级模块不再分别查询或重算。
- 负责人进一步确认：评级窗口内若某账号任一完整业务日的每日销售广告费合计为 0，则视为该日广告数据尚未同步，不能评级。试算从每日销售按账号、LA 业务日汇总 `ad_spend_amount + sem_ad_spend_amount`；缺少当日数据同样不能证明同步完成。单个 Listing 的广告费为 0 不单独阻断同账号其他 Listing。
- 人工生命周期调整优先于自动计算；正式评级希望证据齐全后自动生效、执行时间可配置。权限、审计、人工覆盖保护、完整性水位及生产启用仍需另行闭环。
- 页面上架时间采用新 Listing 开始监测后首次观察到 WFS 库存至少为 1 的日期；旧 Listing 无该证据时显示待核实。保留 ERP 原始值，不将其转换或回填成标准时间。

以上只解决部分业务定义。T-2 是计算截止日，不能单凭日期推断每日销售同步成功。每日销售自身的完成状态、历史事件来源和正式发布 PRP 仍缺失，故本接口总体状态继续为 `BLOCKED_BY_OWNER_DECISION`。

## 现有可复用证据（不是接口实施授权）

| 资源 | 现有位置 | 能支持的内容 | 当前不能推断 |
|---|---|---|---|
| Listing 当前映射 | `backend/app/modules/data_pages/models.py::ListingManagementCurrentMart` | 店铺、Item ID、MSKU、生命周期当前状态 | 历史状态、历史审批证据 |
| ERP 每日销售 MART | `backend/app/modules/data_pages/models.py::DailySalesItemDayMart` | `business_date_la`、`source_account_ref`、`store_id`、`item_id`、`msku`、`gross_profit_amount`、`cost_status`、`calculation_warnings_json` | T-2 每日销售是否已成功同步并完成计算 |
| 每日销售事实口径 | `docs/data-sources/decisions/data-pages-daily-sales-listing-order-profit-decision.md` | 严格业务键 `business_date + store_id + item_id + msku`；`net_sales_amount` 和 `order_profit` 公式 | 无销售行能否由每日销售完成状态确认是真零 |
| WFS 每日库存 | `backend/app/modules/data_pages/repository.py` 已引用 `WalmartListingInventoryDailyFact` | 可以继续调查每日库存快照及关联条件 | 不得用当前 WFS 量推断历史连续断货 |
| 纯函数计算 | `backend/app/modules/listing_rule_config/evaluation.py` | `FinancialDay`、`BusinessDay`、`grade_listing`、`lifecycle_listing`、LA T-2 | **没有真实数据采集适配、批量接口、快照表** |
| 配置版本 | `backend/app/modules/listing_rule_config/service.py` | 规则版本与审计 | 不能代表计算结果已保存/应用 |

## 旧系统/上游强制前置调查

| 调查项 | 当前结论 |
|---|---|
| 旧页面 / 旧 API / 旧接口位置 | 未读取；本次不触碰 `old-system/**`，依项目边界待授权或注明不适用 |
| 读取表 / 写入方 | 新系统上述 MART；具体日事实写入管线与完成标识待逐项核对 |
| cron / 脚本 / 外部 API | 按 DATA-PAGES-1 已有同步治理框架调查；本次不调用 |
| 人工写库入口 | 评级结果不允许通过只读试算写库；未来结果写入审批独立 PRP |
| 外部平台重新获取可能性 | 依现有同步任务；禁止接口中实时拉取平台 |
| 少量配置数据可行性 | 规则版本走新系统配置；无需重复建立配置源 |
| 短期 / 长期策略 | 先只读现有 MART 与显式完整性证明；长期留痕的结果快照为独立 NEW_SYSTEM_OWNED 模块 |

## 待确认数据集与权威分类

| 数据集或字段组 | 候选分类 | 推荐来源 | 状态与风险 |
|---|---|---|---|
| Listing 当前状态与归属 | REBUILD_SYNC（沿用 DATA-PAGES-1） | Listing MART | 必须校验操作人 account_refs/data-scope；不可只靠 store_id |
| 按 LA 天的销售额、利润 | REBUILD_SYNC（沿用 DATA-PAGES-1） | DailySalesItemDayMart | 必须严格匹配 `source_account_ref/store_id/item_id/msku`，避免重复归集 |
| WFS 每日历史库存 | REBUILD_SYNC（待单独审核） | 已有库存 FACT 及历史快照 | 需验证无快照日、断货历史是否够用 |
| 评级财务数据源 | **负责人已确认：每日销售** | `DailySalesItemDayMart` 已算好的销售额、利润及完成状态 | 不为评级另建广告或退款聚合；每日销售 T-2 未成功完成或成本状态不完整时输出“待评级” |
| 历史划线价/购物车异常 | APPROVED_SOURCE | `std_walmart_monitor_listing_observations` 按 LA 日的监控观察 | 仅使用明确观察；缺失日保持未知，不推断连续异常 |
| 清货/归档审批事件 | **NEED_OWNER_DECISION** | 现有审批记录及事件顺序 | 审批状态优先级必须可追溯 |
| 自动评级结果历史快照 | NEW_SYSTEM_OWNED（未来切片） | 新系统唯一写入源 | 需新表、权限、审计、回滚、迁移 PRP |
| C/D 运营跟进记录 | NEW_SYSTEM_OWNED（未来切片） | 现有运营日志/待办模块 | 关联键、跨日去重、完成口径需确认 |

## 只读 API 契约（拟议，非批准版本）

- 入参：允许的店铺/Listing 标识、业务截止日期、页长/游标；不接受客户端 `upstream_confirmed`。
- 先做权限+数据作用域限制，再查询单店铺 Listing 维度日事实；仅查询所需的14天财务与约30天库存区间。
- 日级别以 `business_date_la` 聚合；零销售有完整费用证明的日期与缺数日期严格区分。
- 没有核实完整性证明的日期显式输出 `invalid_dates` / `missing_evidence`，不返回乐观 A/B 等级。
- 计算结果带规则版本、LA 截止日期、7/14有效日期、算式输入、来源新鲜度；不把任何计算结果写入数据库。
- 禁止跨店铺兜底、模糊 MSKU 匹配、合并不同币种、跳过字段权限。

## 最终建议

- **BLOCKED_BY_OWNER_DECISION**：评级财务来源已确定为每日销售，且已增加“账号业务日广告费为零或缺日”试算门禁；但正数广告费也不能独立证明 T-2 成功完成，WFS 历史证据和审批事件仍未闭环，因此正式发布与生产定时任务继续阻塞。
- 独立 PRP 后按顺序：只读数据适配/试算 → 结果快照 → C/D日志联动 → Celery调度及灰度。
- 审批前可完成前端 mock E2E、纯计算测试、业务规则说明与后端数据血缘调查。
- 本文件不构成数据库连接、迁移、执行 Celery 或部署授权。
