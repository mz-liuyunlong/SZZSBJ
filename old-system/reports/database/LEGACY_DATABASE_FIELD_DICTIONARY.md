# 旧系统数据库字段字典

仅列出可从安全 CREATE TABLE 静态解析的字段；字符串默认值统一隐藏。

| 表名 | 字段名 | 字段类型 | Nullable | 默认值 | 字段注释 | 推测业务含义 | 来源 |
|---|---|---|---|---|---|---|---|
| `ai_analysis_result` | `analysis_date` | `DATE` | 否 | `未声明` | 分析日期 | 分析日期 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `analysis_id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `analysis_type` | `VARCHAR(64)` | 否 | `未声明` | 类型: sales_analysis/ads_keyword_analysis/inventory_analysis/profit_analysis/purchase_analysis | 类型: sales_analysis/ads_keyword_analysis/inventory_analysis/profit_analysis/purchase_analysis | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `conclusion` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 结论 | 结论 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `confidence` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 置信度 0~1 | 置信度 0~1 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `input_snapshot_json` | `JSON` | 否 | `未声明` | 分析输入快照 | 分析输入快照 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `item_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `keyword` | `VARCHAR(512)` | 是（未声明 NOT NULL） | `未声明` | 关键词 | 关键词 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `model_name` | `VARCHAR(128)` | 否 | `未声明` | 模型名称 | 模型名称 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `msku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `platform` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `prompt_version` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 提示词版本 | 提示词版本 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `recommendation` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 建议 | 建议 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `result_json` | `JSON` | 否 | `未声明` | 分析结果（结构化） | 分析结果（结构化） | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `risk_score` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 风险评分 0~1 | 风险评分 0~1 | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `source_event_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | 关联 biz_event.event_id | 关联 biz_event.event_id | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | `store_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `ai_business_report` | `completeness_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `filter_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 生成时的筛选条件（手动生成必填） | 生成时的筛选条件（手动生成必填） | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `generated_at` | `DATETIME` | 否 | `未声明` | 未声明 | 日期或时间 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `notify_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 群通知+私聊发送结果 | 群通知+私聊发送结果 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `out_dir` | `VARCHAR(255)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `period_key` | `VARCHAR(16)` | 否 | `未声明` | 2026-W28 / 2026-07 / 自定义 | 2026-W28 / 2026-07 / 自定义 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `report_type` | `VARCHAR(32)` | 否 | `未声明` | weekly/monthly/adhoc... | weekly/monthly/adhoc... | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `status` | `VARCHAR(16)` | 否 | `未声明` | success/failed/running | success/failed/running | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `trigger_source` | `VARCHAR(16)` | 否 | `未声明` | cron/manual | cron/manual | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `win_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | `win_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_monthly_issue_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `issue_reasons` | `JSON` | 否 | `未声明` | 命中的问题条件数组 | 命中的问题条件数组 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `metrics_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 判定基线快照：毛利率/销量/广告占比/库存/周转等 | 判定基线快照：毛利率/销量/广告占比/库存/周转等 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `owner` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `plan_month` | `VARCHAR(7)` | 否 | `未声明` | 需填规划的月份（报告月的次月） | 需填规划的月份（报告月的次月） | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `report_id` | `BIGINT UNSIGNED` | 否 | `未声明` | ai_business_report.id | ai_business_report.id | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | `suggested_action` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 建议方向（复用规则信号suggested_action） | 建议方向（复用规则信号suggested_action） | `月报系统/交付件/DDL_monthly.sql` |
| `ai_ops_log_review_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 商品标识 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `llm_model` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `log_date` | `DATE` | 否 | `未声明` | 未声明 | 日期或时间 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `log_excerpt` | `VARCHAR(1000)` | 否 | `<STRING_DEFAULT_REDACTED>` | 日志内容快照（截断），防原行后续变更影响追溯 | 日志内容快照（截断），防原行后续变更影响追溯 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `owner_name` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | 名称 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `reason` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | AI 判定理由 | AI 判定理由 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注（异议登记），系统不覆盖 | 人工备注（异议登记），系统不覆盖 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `signals_excerpt` | `VARCHAR(1000)` | 否 | `<STRING_DEFAULT_REDACTED>` | 当日运营提醒快照（截断） | 当日运营提醒快照（截断） | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `src_log_id` | `BIGINT UNSIGNED` | 否 | `未声明` | 关联 biz_product_operation_log.id（只读引用） | 关联 biz_product_operation_log.id（只读引用） | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 店铺标识 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `suggestion` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | AI 改进建议 | AI 改进建议 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `verdict` | `VARCHAR(10)` | 否 | `未声明` | good / bad | good / bad | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | `week_start` | `DATE` | 否 | `未声明` | 评估周的周一（上周一） | 评估周的周一（上周一） | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `ai_comment` | `VARCHAR(2000)` | 否 | `<STRING_DEFAULT_REDACTED>` | AI 对该负责人的本周点评 | AI 对该负责人的本周点评 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `bad_count` | `INT` | 否 | `0` | 未声明 | 数量 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `good_count` | `INT` | 否 | `0` | 未声明 | 数量 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `llm_model` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `owner_name` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | 名称 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注，系统不覆盖 | 人工备注，系统不覆盖 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `reviewed_logs` | `INT` | 否 | `0` | 实际送评条数（含截断说明） | 实际送评条数（含截断说明） | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `status` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | success / truncated / failed(LLM异常未出分) | success / truncated / failed(LLM异常未出分) | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `substantive_logs` | `INT` | 否 | `0` | 实质日志数（排除空/无运营话术） | 实质日志数（排除空/无运营话术） | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `total_logs` | `INT` | 否 | `0` | 窗口内该负责人日志行总数 | 窗口内该负责人日志行总数 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | `week_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `交付件/DDL_AI人事_日志评级.sql` |
| `biz_app_audit_log` | `action` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `detail_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `ip` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `target` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `ua` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `user_id` | `INT UNSIGNED` | 否 | `0` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | `username` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/022_app_auth_tables.sql` |
| `biz_business_target` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `created_by` | `VARCHAR(64)` | 否 | `未声明` | 首次设定人 | 首次设定人 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `metric` | `ENUM('sales','profit')` | 否 | `未声明` | 销售额/毛利润 | 销售额/毛利润 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `owner` | `VARCHAR(64)` | 否 | `未声明` | 负责人姓名（与周报owner口径一致） | 负责人姓名（与周报owner口径一致） | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `period_key` | `VARCHAR(10)` | 否 | `未声明` | 2026-07 或 2026-Q3 | 2026-07 或 2026-Q3 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `target_type` | `ENUM('monthly','quarterly')` | 否 | `未声明` | 月度/季度 | 月度/季度 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `target_value` | `DECIMAL(14,2)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | `updated_by` | `VARCHAR(64)` | 否 | `未声明` | 最近调整人 | 最近调整人 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `action` | `ENUM('create','update')` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `change_source` | `ENUM('manual','import')` | 否 | `未声明` | 手动修改/表格批量导入 | 手动修改/表格批量导入 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `changed_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 日期或时间 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `changed_by` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `metric` | `ENUM('sales','profit')` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `new_value` | `DECIMAL(14,2)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `old_value` | `DECIMAL(14,2)` | 是（未声明 NOT NULL） | `未声明` | 首次设定为NULL | 首次设定为NULL | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `owner` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `period_key` | `VARCHAR(10)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `platform` | `VARCHAR(20)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `target_id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | `target_type` | `ENUM('monthly','quarterly')` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_clearance_expect_date` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/018_clearance_expect_date.sql` |
| `biz_clearance_expect_date` | `expect_end` | `DATE` | 否 | `未声明` | 预计清货结束时间（人工选择） | 预计清货结束时间（人工选择） | `sql/018_clearance_expect_date.sql` |
| `biz_clearance_expect_date` | `row_key` | `VARCHAR(200)` | 否 | `未声明` | 未声明 | 待确认 | `sql/018_clearance_expect_date.sql` |
| `biz_clearance_expect_date` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/018_clearance_expect_date.sql` |
| `biz_clearance_expect_date` | `updated_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/018_clearance_expect_date.sql` |
| `biz_clearance_other_channel` | `added_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `amazon_asin` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 批⑤亚马逊销量匹配：人工填写优先于SKU自动匹配 | 批⑤亚马逊销量匹配：人工填写优先于SKU自动匹配 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `channel` | `VARCHAR(20)` | 否 | `未声明` | 清货渠道：亚马逊/希音（后续可扩展） | 清货渠道：亚马逊/希音（后续可扩展） | `sql/017_clearance_other_channel_v2.sql` |
| `biz_clearance_other_channel` | `channel_note` | `VARCHAR(200)` | 否 | `未声明` | 清货渠道（人工填写，同步不得覆盖） | 清货渠道（人工填写，同步不得覆盖） | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `manual_stock` | `INT` | 否 | `0` | 渠道库存数量（人工填写维护） | 渠道库存数量（人工填写维护） | `sql/017_clearance_other_channel_v2.sql` |
| `biz_clearance_other_channel` | `mskus` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `owner` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `platform_ref` | `VARCHAR(64)` | 否 | `未声明` | 平台识别号：亚马逊=ASIN，希音=平台SKC | 平台识别号：亚马逊=ASIN，希音=平台SKC | `sql/017_clearance_other_channel_v2.sql` |
| `biz_clearance_other_channel` | `remark` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `sku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `status` | `ENUM('active','done','removed')` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 店铺标识 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/016_clearance_center.sql` |
| `biz_cs_test_alert` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `first_ad_date_snapshot` | `date` | 是（未声明 NOT NULL） | `NULL` | 首次广告日期快照 | 首次广告日期快照 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `first_alert_date` | `date` | 是（未声明 NOT NULL） | `NULL` | 首次预警日 | 首次预警日 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `id` | `bigint unsigned` | 否 | `未声明` | 主键 | 主键 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `item_id` | `varchar(64)` | 否 | `未声明` | 沃尔玛ItemID | 沃尔玛ItemID | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `last_sent_date` | `date` | 是（未声明 NOT NULL） | `NULL` | 最近发送日 | 最近发送日 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `msku` | `varchar(128)` | 否 | `未声明` | MSKU（CS测品行维度） | MSKU（CS测品行维度） | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `owner_name` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 负责人（花名册姓名快照） | 负责人（花名册姓名快照） | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `penalty_count` | `int` | 否 | `<STRING_DEFAULT_REDACTED>` | 累计扣分次数（每次5分，从第2次未填发送起累加） | 累计扣分次数（每次5分，从第2次未填发送起累加） | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `platform` | `varchar(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `reason` | `varchar(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 预警原因（人工填，≥15字；人工可改，系统不覆盖） | 预警原因（人工填，≥15字；人工可改，系统不覆盖） | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `reason_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 填写时间 | 填写时间 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `reason_by` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 填写人 | 填写人 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `sales_qty_snapshot` | `int` | 是（未声明 NOT NULL） | `NULL` | 触发时累计销量快照 | 触发时累计销量快照 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `send_count` | `int` | 否 | `<STRING_DEFAULT_REDACTED>` | 已发送次数（每工作日最多+1） | 已发送次数（每工作日最多+1） | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `status` | `enum('open','resolved','closed_test_ended')` | 否 | `<STRING_DEFAULT_REDACTED>` | open=待处理 resolved=已填原因 closed_test_ended=测品已结束 | open=待处理 resolved=已填原因 closed_test_ended=测品已结束 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `store_id` | `varchar(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `test_days_snapshot` | `int` | 是（未声明 NOT NULL） | `NULL` | 触发时测品天数快照 | 触发时测品天数快照 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | `updated_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_event` | `ad_group_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告组ID | 广告组ID | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `campaign_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告活动ID | 广告活动ID | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `detected_by` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 检测方式 (rule/ai/manual) | 检测方式 (rule/ai/manual) | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `event_date` | `DATE` | 否 | `未声明` | 事件日期 | 事件日期 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `event_id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `event_type` | `VARCHAR(64)` | 否 | `未声明` | 类型: no_sales/low_stock/high_ad_spend/high_acos/profit_loss/purchase_delay/shipment_delay/owner_missing/data_mismatch | 类型: no_sales/low_stock/high_ad_spend/high_acos/profit_loss/purchase_delay/shipment_delay/owner_missing/data_mismatch | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `item_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `keyword` | `VARCHAR(512)` | 是（未声明 NOT NULL） | `未声明` | 关键词 | 关键词 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `msku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `owner` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 负责人 | 负责人 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `reason` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 触发原因 | 触发原因 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `resolved_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 解决时间 | 解决时间 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `severity` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 严重程度: info/warning/critical | 严重程度: info/warning/critical | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `source_key` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 来源记录标识 | 来源记录标识 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `source_table` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 来源表 | 来源表 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态: open/processing/resolved/ignored | 状态: open/processing/resolved/ignored | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `store_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `suggestion` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 处理建议 | 处理建议 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `title` | `VARCHAR(255)` | 否 | `未声明` | 事件标题 | 事件标题 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_finance_exchange_rate` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `created_by` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `currency_pair` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `rate` | `DECIMAL(12,6)` | 否 | `未声明` | 1美元兑人民币 | 1美元兑人民币 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `rate_month` | `CHAR(7)` | 否 | `未声明` | yyyy-MM | yyyy-MM | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注列 | 人工备注列 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | `updated_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_fixed_cost` | `amount` | `DECIMAL(18,4)` | 否 | `未声明` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `category` | `VARCHAR(64)` | 否 | `未声明` | 人工/场地/财务成本/公司日常/其他 | 人工/场地/财务成本/公司日常/其他 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `cost_month` | `CHAR(7)` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `created_by` | `VARCHAR(64)` | 否 | `未声明` | 录入人(超管/财务) | 录入人(超管/财务) | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `level` | `VARCHAR(16)` | 否 | `未声明` | company=公司级 / store=店铺级 | company=公司级 / store=店铺级 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `remark` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注列 | 人工备注列 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | level=store时必填 | level=store时必填 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | `updated_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_opening_cost` | `batch_unit_cost` | `DECIMAL(18,4)` | 是（未声明 NOT NULL） | `未声明` | 批次加权单价(参考,仅47个SKU有) | 批次加权单价(参考,仅47个SKU有) | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `created_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `cutoff_date` | `DATE` | 否 | `<STRING_DEFAULT_REDACTED>` | 一刀切点 | 一刀切点 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `firstmile_unit_cost` | `DECIMAL(18,4)` | 否 | `未声明` | 固定头程成本(CNY/件,财务定) | 固定头程成本(CNY/件,财务定) | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `opening_unit_cost` | `DECIMAL(18,4)` | 否 | `未声明` | 期初一刀单价=采购+头程 | 期初一刀单价=采购+头程 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `precut_purchase_qty` | `INT` | 否 | `0` | 切点前采购总量(导入时点) | 切点前采购总量(导入时点) | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `purchase_unit_cost` | `DECIMAL(18,4)` | 否 | `未声明` | 固定采购成本(CNY/件,财务定) | 固定采购成本(CNY/件,财务定) | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `remark` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注列,永不覆盖 | 人工备注列,永不覆盖 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `sku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `snap_qty_0501` | `INT` | 否 | `0` | 2026-05-01快照WFS可用数量(导入时点) | 2026-05-01快照WFS可用数量(导入时点) | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `updated_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | `value_source` | `VARCHAR(24)` | 否 | `未声明` | finance_fixed=批次无价财务定 / finance_override=财务覆盖批次价 | finance_fixed=批次无价财务定 / finance_override=财务覆盖批次价 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_review` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `data_hash` | `CHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 复核时数据指纹,变化即打回 | 复核时数据指纹,变化即打回 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `period_month` | `CHAR(7)` | 否 | `未声明` | 账单周期(月) | 账单周期(月) | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `remark` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注列 | 人工备注列 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `review_status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | pending=待复核 / reviewed=已复核(数据刷新自动打回pending) | pending=待复核 / reviewed=已复核(数据刷新自动打回pending) | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `reviewed_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `reviewed_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `biz_monthly_plan` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `created_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `deadline` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 完成期限，默认当月末 | 完成期限，默认当月末 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `indicator1_target` | `DECIMAL(14,2)` | 是（未声明 NOT NULL） | `未声明` | 量化目标：件/%/$/个/%（随指标类型） | 量化目标：件/%/$/个/%（随指标类型） | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `indicator1_type` | `ENUM('清货','提高毛利率','提升销售额','新增变体','调整广告')` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `indicator2_target` | `DECIMAL(14,2)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `indicator2_type` | `ENUM('清货','提高毛利率','提升销售额','新增变体','调整广告')` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `issue_text` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 问题确认（预填月报问题，可补充） | 问题确认（预填月报问题，可补充） | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `normal_operation` | `TINYINT(1)` | 否 | `0` | 1=本月无优化计划正常运营（已表态） | 1=本月无优化计划正常运营（已表态） | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `note` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 补充说明（GPT建议可贴此处） | 补充说明（GPT建议可贴此处） | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `owner` | `VARCHAR(64)` | 否 | `未声明` | 填报时的负责人 | 填报时的负责人 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `plan_month` | `VARCHAR(7)` | 否 | `未声明` | 规划月份 2026-08 | 规划月份 2026-08 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `updated_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `variant_actual` | `INT` | 是（未声明 NOT NULL） | `未声明` | 新增变体人工汇报的实际数量（对账期填写） | 新增变体人工汇报的实际数量（对账期填写） | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `variant_confirmed_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | `variant_confirmed_by` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `月报系统/交付件/DDL_monthly.sql` |
| `biz_owner_target_confirm` | `confirmed_by` | `VARCHAR(64)` | 否 | `未声明` | 确认人（由密码映射，非手填） | 确认人（由密码映射，非手填） | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `confirmed_profit` | `DECIMAL(14,2)` | 否 | `未声明` | 确认时毛利目标快照($) | 确认时毛利目标快照($) | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `confirmed_sales` | `DECIMAL(14,2)` | 否 | `未声明` | 确认时销售额目标快照($) | 确认时销售额目标快照($) | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `owner` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `period_key` | `VARCHAR(10)` | 否 | `未声明` | 2026-07 / 2026-Q3 | 2026-07 / 2026-Q3 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | `target_type` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | monthly/quarterly | monthly/quarterly | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_perf_cert` | `image_data` | `LONGBLOB` | 否 | `未声明` | 未声明 | 待确认 | `交付件/SQL_建表_人工绩效凭证_20260731.sql` |
| `biz_perf_cert` | `mime` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/SQL_建表_人工绩效凭证_20260731.sql` |
| `biz_perf_cert` | `ref_deduction_id` | `BIGINT` | 否 | `未声明` | 挂 biz_perf_deduction.id | 挂 biz_perf_deduction.id | `交付件/SQL_建表_人工绩效凭证_20260731.sql` |
| `biz_perf_cert` | `uploaded_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 日期或时间 | `交付件/SQL_建表_人工绩效凭证_20260731.sql` |
| `biz_perf_cert` | `uploaded_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/SQL_建表_人工绩效凭证_20260731.sql` |
| `biz_perf_deduction` | `biz_type` | `VARCHAR(40)` | 否 | `<STRING_DEFAULT_REDACTED>` | 扣分类型，预留其他绩效场景 | 扣分类型，预留其他绩效场景 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `created_by` | `VARCHAR(40)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `deduction_date` | `DATE` | 否 | `未声明` | 扣分落账日期（=认领公布所在日报日） | 扣分落账日期（=认领公布所在日报日） | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 商品标识 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `note` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注，人工可改，系统不覆盖 | 人工备注，人工可改，系统不覆盖 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `owner_name` | `VARCHAR(64)` | 否 | `未声明` | 承担人（认领人），与花名册姓名一致 | 承担人（认领人），与花名册姓名一致 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `points` | `INT` | 否 | `未声明` | 扣分值，正数记录（如5） | 扣分值，正数记录（如5） | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `ref_event_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 关联 event_owner_claim_alert.id，防同轮重复落账 | 关联 event_owner_claim_alert.id，防同轮重复落账 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 店铺标识 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction_note` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `exempt_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 豁免时间 | 豁免时间 | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `exempt_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 豁免人（限黄少如/林翔） | 豁免人（限黄少如/林翔） | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `exempt_reason` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 豁免理由（人工列） | 豁免理由（人工列） | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `exempt_status` | `TINYINT` | 否 | `0` | 0=正常计分 1=已豁免(该笔从合计免除，原扣分行保留) | 0=正常计分 1=已豁免(该笔从合计免除，原扣分行保留) | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `explanation` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 绩效说明（被扣分本人填，解释/纠误判；人工列） | 绩效说明（被扣分本人填，解释/纠误判；人工列） | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `explanation_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 说明填写/最近修改时间 | 说明填写/最近修改时间 | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `explanation_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 说明填写人（花名册姓名快照） | 说明填写人（花名册姓名快照） | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 主键 | 主键 | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `ref_deduction_id` | `BIGINT UNSIGNED` | 否 | `未声明` | =biz_perf_deduction.id，一对一 | =biz_perf_deduction.id，一对一 | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | `ym` | `CHAR(7)` | 否 | `未声明` | 扣分所属月 'YYYY-MM'（=deduction_date 归月，冗余便于窗口/月度过滤） | 扣分所属月 'YYYY-MM'（=deduction_date 归月，冗余便于窗口/月度过滤） | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_product_rule_signal_daily` | `ad_window_end` | `DATE` | 是（未声明 NOT NULL） | `NULL` | CS 规则近3天窗口止（实际业务日） | CS 规则近3天窗口止（实际业务日） | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `ad_window_start` | `DATE` | 是（未声明 NOT NULL） | `NULL` | CS 规则近3天窗口起（实际业务日） | CS 规则近3天窗口起（实际业务日） | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 商品标识 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `notify_frequency_days` | `INT` | 是（未声明 NOT NULL） | `NULL` | 规则静态属性；真正去重留第5期 | 规则静态属性；真正去重留第5期 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `owner` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `product_type` | `VARCHAR(32)` | 否 | `未声明` | cs_test / regular | cs_test / regular | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `rule_code` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `rule_group` | `VARCHAR(32)` | 否 | `未声明` | profit / inventory / ad / cs | profit / inventory / ad / cs | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `rule_level` | `VARCHAR(32)` | 否 | `未声明` | info / warning / critical / positive | info / warning / critical / positive | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `rule_name` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | 名称 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `rule_version` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `should_notify` | `TINYINT(1)` | 否 | `0` | v1 仅表示今日触发，非今日应发送 | v1 仅表示今日触发，非今日应发送 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `signal_date` | `DATE` | 否 | `未声明` | 信号业务日 = dim_product_business_state.stat_date | 信号业务日 = dim_product_business_state.stat_date | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `signal_source` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `source_metrics_json` | `JSON` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `source_state_date` | `DATE` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 日期或时间 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `source_state_id` | `BIGINT` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 店铺标识 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `store_key` | `VARCHAR(128)` | 否 | `未声明` | 唯一键锚点：store_id 优先，否则 store_name | 唯一键锚点：store_id 优先，否则 store_name | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `suggested_action` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `trigger_reason` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/011_biz_product_rule_signal_daily.sql` |
| `cs_test_product_config` | `config_key` | `VARCHAR(128)` | 否 | `未声明` | 配置项 | 配置项 | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | `config_type` | `VARCHAR(64)` | 否 | `未声明` | 配置类型 | 配置类型 | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | `config_value` | `TEXT` | 否 | `未声明` | 配置值 | 配置值 | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | `description` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 说明 | 说明 | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | `enabled` | `TINYINT(1)` | 否 | `1` | 是否启用 | 是否启用 | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | `id` | `BIGINT` | 否 | `未声明` | 未声明 | 记录主键 | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/007_cs_test_product_config.sql` |
| `data_reconcile_log` | `api_value` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | API数据值 | API数据值 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `diff_rate` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 差异率 | 差异率 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `diff_value` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 差值 | 差值 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `feishu_value` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 飞书数据值 | 飞书数据值 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `item_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `metric_name` | `VARCHAR(128)` | 否 | `未声明` | 指标名称 | 指标名称 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `msku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `mysql_value` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | MySQL数据值 | MySQL数据值 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `platform` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `reason` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 差异原因 | 差异原因 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `reconcile_date` | `DATE` | 否 | `未声明` | 对账日期 | 对账日期 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态: pending/matched/mismatch/ignored | 状态: pending/matched/mismatch/ignored | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | `store_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `dim_app_user` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `display_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `feishu_member_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `id` | `INT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `is_active` | `TINYINT(1)` | 否 | `1` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `is_superadmin` | `TINYINT(1)` | 否 | `0` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `must_change_password` | `TINYINT(1)` | 否 | `0` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `password_hash` | `VARCHAR(255)` | 否 | `未声明` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `role` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `team_name` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `token_version` | `INT UNSIGNED` | 否 | `1` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | `username` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 名称 | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | `granted_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 日期或时间 | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | `granted_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | `id` | `INT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | `perm_key` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | `user_id` | `INT UNSIGNED` | 否 | `未声明` | 未声明 | 待确认 | `sql/022_app_auth_tables.sql` |
| `dim_app_user_role` | `granted_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 授权时间 | 授权时间 | `sql/023_app_user_role.sql` |
| `dim_app_user_role` | `granted_by` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 授权人(登录名) | 授权人(登录名) | `sql/023_app_user_role.sql` |
| `dim_app_user_role` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/023_app_user_role.sql` |
| `dim_app_user_role` | `role_key` | `VARCHAR(32)` | 否 | `未声明` | 角色: 超管/人事/财务/中台/运营主管/运营组员 | 角色: 超管/人事/财务/中台/运营主管/运营组员 | `sql/023_app_user_role.sql` |
| `dim_app_user_role` | `user_id` | `BIGINT` | 否 | `未声明` | 关联 dim_app_user.id | 关联 dim_app_user.id | `sql/023_app_user_role.sql` |
| `dim_connect_account` | `account_number` | `VARCHAR(32)` | 否 | `未声明` | Connect广告账号(PDF头部Account Number) | Connect广告账号(PDF头部Account Number) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_connect_account` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_connect_account` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_connect_account` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `未声明` | 人工备注(系统不覆盖) | 人工备注(系统不覆盖) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_connect_account` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 归属店铺 | 归属店铺 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_connect_account` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 名称 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_connect_account` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_feishu_department` | `leader_open_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_to_delete/039_roster_profile_extend.sql` |
| `dim_feishu_department` | `member_count` | `INT` | 否 | `0` | 未声明 | 数量 | `_to_delete/039_roster_profile_extend.sql` |
| `dim_feishu_department` | `name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `_to_delete/039_roster_profile_extend.sql` |
| `dim_feishu_department` | `open_department_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `_to_delete/039_roster_profile_extend.sql` |
| `dim_feishu_department` | `parent_open_department_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_to_delete/039_roster_profile_extend.sql` |
| `dim_feishu_department` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `_to_delete/039_roster_profile_extend.sql` |
| `dim_keyword` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `first_seen_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 首次出现时间 | 首次出现时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `keyword_id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `keyword_text` | `VARCHAR(512)` | 否 | `未声明` | 原始关键词 | 原始关键词 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `keyword_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 类型: manual_keyword/auto_search_term/product_targeting/unknown | 类型: manual_keyword/auto_search_term/product_targeting/unknown | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `last_seen_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 最近出现时间 | 最近出现时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `normalized_keyword` | `VARCHAR(512)` | 否 | `未声明` | 标准化关键词（小写+trim） | 标准化关键词（小写+trim） | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `department` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 部门 | 部门 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `feishu_user_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 飞书用户ID | 飞书用户ID | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `owner_id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `owner_name` | `VARCHAR(128)` | 否 | `未声明` | 姓名 | 姓名 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `role_name` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 角色 | 角色 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态 | 状态 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `asin` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | ASIN | ASIN | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `brand` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 品牌 | 品牌 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `category` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 分类 | 分类 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `fulfillment_type` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 配送方式 (WFS/MFC) | 配送方式 (WFS/MFC) | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `item_name` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 商品名称（平台侧） | 商品名称（平台侧） | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `owner` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 负责人 | 负责人 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `product_key` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `product_name` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 商品名称 | 商品名称 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `sku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | SKU | SKU | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态 | 状态 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID（必填） | 店铺ID（必填） | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product_cost_config` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `delivery_fee` | `DECIMAL(10,4)` | 是（未声明 NOT NULL） | `未声明` | WFS/FBW 配送费（$） | WFS/FBW 配送费（$） | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `effective_date` | `DATE` | 否 | `未声明` | 生效日期 | 生效日期 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 平台商品ID | 平台商品ID | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `logistics_cost` | `DECIMAL(10,4)` | 是（未声明 NOT NULL） | `未声明` | 头程物流费（$） | 头程物流费（$） | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU | MSKU | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `purchase_cost` | `DECIMAL(10,4)` | 是（未声明 NOT NULL） | `未声明` | 采购成本（$） | 采购成本（$） | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `shipping_fee` | `DECIMAL(10,4)` | 是（未声明 NOT NULL） | `未声明` | 物流运费（$） | 物流运费（$） | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `sku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | SKU | SKU | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `source_raw_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 原始数据 raw_hash | 原始数据 raw_hash | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态 | 状态 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 店铺ID（可为空串） | 店铺ID（可为空串） | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `store_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 店铺名称 | 店铺名称 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_gpt_link` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `effective_from` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 版本生效时刻=保存时刻；日志行按 created_at>=effective_from 匹配最新版本 | 版本生效时刻=保存时刻；日志行按 created_at>=effective_from 匹配最新版本 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `link_type` | `VARCHAR(16)` | 否 | `未声明` | keyword=关键词分析 / ads=广告分析 | keyword=关键词分析 / ads=广告分析 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注，系统不覆盖 | 人工备注，系统不覆盖 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `updated_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | `url` | `VARCHAR(1000)` | 否 | `未声明` | GPT对话链接，必须 http(s):// 开头，非空（不允许清空只能替换） | GPT对话链接，必须 http(s):// 开头，非空（不允许清空只能替换） | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_identity` | `confidence` | `TINYINT` | 否 | `100` | 置信度 0-100 | 置信度 0-100 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 平台商品ID | 平台商品ID | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `lingxing_product_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 领星产品ID | 领星产品ID | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `local_sku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 本地SKU | 本地SKU | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU | MSKU | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `sku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | SKU | SKU | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `source_raw_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 原始数据 raw_hash | 原始数据 raw_hash | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态 | 状态 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 店铺ID（可为空串） | 店铺ID（可为空串） | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `store_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 店铺名称 | 店铺名称 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `effective_date` | `DATE` | 否 | `未声明` | 生效日期 | 生效日期 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `feishu_user_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 飞书用户ID | 飞书用户ID | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 平台商品ID | 平台商品ID | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU | MSKU | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `owner_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | 关联 dim_owner.owner_id | 关联 dim_owner.owner_id | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `owner_name` | `VARCHAR(128)` | 否 | `未声明` | 负责人姓名 | 负责人姓名 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `source_raw_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 原始数据 raw_hash | 原始数据 raw_hash | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态 active/inactive | 状态 active/inactive | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 店铺ID（可为空串） | 店铺ID（可为空串） | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `store_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 店铺名称 | 店铺名称 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_wfs_fee_auto` | `fee` | `DECIMAL(10,2)` | 是（未声明 NOT NULL） | `未声明` | 自动WFS费=窗口内非零物流费单件费率众数；NULL=样本不足回退人工 | 自动WFS费=窗口内非零物流费单件费率众数；NULL=样本不足回退人工 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `fee_rows` | `INT` | 否 | `0` | 窗口内非零物流费订单行数 | 窗口内非零物流费订单行数 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `mode_count` | `INT` | 否 | `0` | 众数出现次数 | 众数出现次数 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `sample_units` | `INT` | 否 | `0` | 窗口内销售件数（<10不生成fee） | 窗口内销售件数（<10不生成fee） | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `window_end` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | `window_start` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_sem_campaign_item` | `campaign_id` | `VARCHAR(64)` | 否 | `未声明` | SEM Campaign ID（唯一稳定键） | SEM Campaign ID（唯一稳定键） | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `campaign_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | 解析时的campaign名快照 | 解析时的campaign名快照 | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 归属ItemID | 归属ItemID | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `NULL` | 人工备注（系统不覆盖） | 人工备注（系统不覆盖） | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `source` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | auto_name=名字解析 / manual=人工兜底（系统永不覆盖） | auto_name=名字解析 / manual=人工兜底（系统永不覆盖） | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_store` | `advertiser_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告主ID | 广告主ID | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `country` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 国家 | 国家 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `currency` | `VARCHAR(16)` | 是（未声明 NOT NULL） | `未声明` | 货币 | 货币 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `owner` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 负责人 | 负责人 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态 | 状态 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 平台侧店铺ID（必填） | 平台侧店铺ID（必填） | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用，不做唯一键） | 店铺名称（展示用，不做唯一键） | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store_config` | `advertiser_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告主ID（无广告账户则空） | 广告主ID（无广告账户则空） | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `advertiser_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告主名称 | 广告主名称 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `auth_status` | `VARCHAR(32)` | 是（未声明 NOT NULL） | `未声明` | 领星店铺授权状态：normal/expired/failed | 领星店铺授权状态：normal/expired/failed | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `commission_rate` | `DECIMAL(6,4)` | 是（未声明 NOT NULL） | `未声明` | 交易费率（如 0.12） | 交易费率（如 0.12） | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `first_seen_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 首次发现时间 | 首次发现时间 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `is_active` | `TINYINT` | 否 | `1` | 是否纳入同步：1是 0否 | 是否纳入同步：1是 0否 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `last_seen_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 最近一次在领星出现的时间 | 最近一次在领星出现的时间 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `source` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源 | 来源 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 领星店铺ID | 领星店铺ID | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称 | 店铺名称 | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/009_create_dim_store_config.sql` |
| `event_archived_restock_alert` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `decided_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 日期或时间 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `decided_by` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 卡片操作人 | 卡片操作人 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `decision` | `varchar(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | 空=未处理 / restore=恢复在售 / keep=继续归档(不再提醒) | 空=未处理 / restore=恢复在售 / keep=继续归档(不再提醒) | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `first_alert_date` | `date` | 是（未声明 NOT NULL） | `NULL` | 首次提醒日 | 首次提醒日 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `id` | `bigint unsigned` | 否 | `未声明` | 未声明 | 记录主键 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `item_id` | `varchar(32)` | 否 | `未声明` | Walmart ItemID | Walmart ItemID | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `last_alert_date` | `date` | 是（未声明 NOT NULL） | `NULL` | 最近提醒日 | 最近提醒日 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `mskus` | `varchar(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | MSKU聚合串(展示用) | MSKU聚合串(展示用) | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `owner_name` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 提醒时负责人 | 提醒时负责人 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `platform` | `varchar(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `remark` | `varchar(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注,系统不覆盖 | 人工备注,系统不覆盖 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `store_id` | `varchar(32)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `updated_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | `wfs_qty` | `int` | 否 | `0` | 最近一次提醒时WFS库存 | 最近一次提醒时WFS库存 | `sql/039_event_archived_restock_alert.sql` |
| `event_arrival_notify` | `biz_key` | `VARCHAR(255)` | 否 | `未声明` | 业务幂等键，同一事件只存在一行 | 业务幂等键，同一事件只存在一行 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `event_date` | `DATE` | 否 | `未声明` | 事件业务日期（上海口径） | 事件业务日期（上海口径） | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `event_type` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 商品标识 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `msku` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `notify_error` | `VARCHAR(512)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `notify_status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | pending/notified/skipped/failed | pending/notified/skipped/failed | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `owner` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 事件生成时的 dim_product.owner 快照 | 事件生成时的 dim_product.owner 快照 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `payload_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 文案要素：数量对比/无广告天数/第M次提醒等 | 文案要素：数量对比/无广告天数/第M次提醒等 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `shipment_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 店铺标识 | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/010_wfs_shipment_tables.sql` |
| `event_attendance_lack_alert` | `ack_status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | pending/confirmed/expired | pending/confirmed/expired | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `confirmed_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `lack_type` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | 上班/下班/双缺 | 上班/下班/双缺 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `locked_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 24h锁定(逾期)时刻 | 24h锁定(逾期)时刻 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `open_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `push_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 首次推送时刻(24/12h起算) | 首次推送时刻(24/12h起算) | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `resend_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 12h重发时刻 | 12h重发时刻 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `stat_date` | `DATE` | 否 | `未声明` | 缺卡日 | 缺卡日 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | `user_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/034_event_attendance_lack_alert.sql` |
| `event_clearance_approval` | `applicant` | `VARCHAR(64)` | 否 | `未声明` | 页面操作人 operator_name | 页面操作人 operator_name | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `approver` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `decided_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `last_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `metrics_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 申请时快照：sales30/stock/inbound/turnoverDays | 申请时快照：sales30/stock/inbound/turnoverDays | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `mskus` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 该item全部msku快照，/分隔 | 该item全部msku快照，/分隔 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `notify_count` | `INT` | 否 | `0` | 进入09:33汇总卡的次数 | 进入09:33汇总卡的次数 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `owner` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 产品负责人（申请时快照） | 产品负责人（申请时快照） | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `reject_reason` | `VARCHAR(200)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `sku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 采购关联键 | 采购关联键 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `status` | `ENUM('pending','approved','rejected','cancelled','legacy')` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_card` | `acted_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `acted_by` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `action` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 继续清货/转稳定期/转上升期/确认归档/暂不归档 | 继续清货/转稳定期/转上升期/确认归档/暂不归档 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `biz_key` | `VARCHAR(200)` | 否 | `未声明` | tail/archive:type:store:item:发送日；revive:type:shipment:store:item | tail/archive:type:store:item:发送日；revive:type:shipment:store:item | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `card_type` | `ENUM('tail','archive','revive')` | 否 | `未声明` | 未声明 | 待确认 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `metrics_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 发送时快照：stock/daily7/daysToClear/zeroDays/shipmentId等 | 发送时快照：stock/daily7/daysToClear/zeroDays/shipmentId等 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `mskus` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `owner` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `sku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `status` | `ENUM('sent','acted','failed')` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `suppress_until` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 抑制截止：继续清货+14天，暂不归档+7天 | 抑制截止：继续清货+14天，暂不归档+7天 | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/019_event_clearance_card.sql` |
| `event_finance_sentinel_alert` | `actual_total` | `DECIMAL(18,4)` | 否 | `未声明` | 归属/分摊加总 | 归属/分摊加总 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `check_time` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 日期或时间 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `detail_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `diff_amount` | `DECIMAL(18,4)` | 否 | `未声明` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `diff_pct` | `DECIMAL(10,4)` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `equation` | `VARCHAR(32)` | 否 | `未声明` | fixed_alloc/ads/storage/freight/revenue 五等式 | fixed_alloc/ads/storage/freight/revenue 五等式 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `expected_total` | `DECIMAL(18,4)` | 否 | `未声明` | 账单/录入原额 | 账单/录入原额 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `period_month` | `CHAR(7)` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 店铺标识 | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | `threshold_hit` | `TINYINT` | 否 | `0` | 1=超阈值(>1%或>$50取大者)已报警 | 1=超阈值(>1%或>$50取大者)已报警 | `sql/041_ai_finance_tables.sql` |
| `event_gpt_ads_missing_alert` | `announced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `cycle_start_date` | `DATE` | 否 | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `deducted_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `deduction_points` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `first_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `owner_name` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 扣分承担人=落台账时负责人 | 扣分承担人=落台账时负责人 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `product_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注，系统不覆盖 | 人工备注，系统不覆盖 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `second_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `status` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | open=缺链接 closed=已补链接/退出清单 void=作废 | open=缺链接 closed=已补链接/退出清单 void=作废 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `supervisor_synced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `announced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `cycle_start_date` | `DATE` | 否 | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `deducted_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `deduction_points` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `first_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `owner_name` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 扣分承担人=落台账时负责人 | 扣分承担人=落台账时负责人 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `product_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注，系统不覆盖 | 人工备注，系统不覆盖 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `second_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `status` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | open=缺链接 closed=已补链接/结案 void=作废 | open=缺链接 closed=已补链接/结案 void=作废 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `supervisor_synced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_monthly_plan_unfilled` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | `deduction_date` | `date` | 否 | `未声明` | 扣分日（被判未填的当天，中国时区） | 扣分日（被判未填的当天，中国时区） | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | `id` | `bigint unsigned` | 否 | `未声明` | 未声明 | 记录主键 | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | `owner_name` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 负责人花名（扣分归属，与花名册一致） | 负责人花名（扣分归属，与花名册一致） | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | `plan_month` | `char(7)` | 否 | `未声明` | 规划月 YYYY-MM（=被扣的填报月） | 规划月 YYYY-MM（=被扣的填报月） | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | `platform` | `varchar(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | `points` | `int` | 否 | `5` | 当日扣分（固定5/人/天） | 当日扣分（固定5/人/天） | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | `unfilled_count` | `int` | 否 | `0` | 当日该负责人未完成品数（审计用；扣分固定5/人/天，与品数无关） | 当日该负责人未完成品数（审计用；扣分固定5/人/天，与品数无关） | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_ops_action_log` | `action_type` | `VARCHAR(40)` | 否 | `未声明` | price_change 售价调价 \| ad_bid_change 关键词出价 \| ad_budget_change 活动预算 \| ad_strategy_change 竞价策略 \| campaign_add/campaign_close 活动增关 \| group_add/group_close 广告组增关 \| key | price_change 售价调价 \| ad_bid_change 关键词出价 \| ad_budget_change 活动预算 \| ad_strategy_change 竞价策略 \| campaign_add/campaign_close 活动增关 \| group_add/group_close 广告组增关 \| key | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `checked_orders` | `INT` | 否 | `0` | 参与核对的订单行数(排除 order_status=7) | 参与核对的订单行数(排除 order_status=7) | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `detected_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 日期或时间 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `event_date` | `DATE` | 否 | `未声明` | 事件业务日=后一个快照日(**美西日界**) | 事件业务日=后一个快照日(**美西日界**) | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `highlight` | `TINYINT` | 否 | `0` | 1=红色加粗(仅 verify_status=inconsistent 时置1) | 1=红色加粗(仅 verify_status=inconsistent 时置1) | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 广告事件经 fact_ads_product_daily 映射;映射不到写空串,事件仍记。**不写NULL** | 广告事件经 fact_ads_product_daily 映射;映射不到写空串,事件仍记。**不写NULL** | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `log_content` | `TEXT` | 否 | `未声明` | 渲染好的中文句子,前端直接取用 | 渲染好的中文句子,前端直接取用 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `matched_orders` | `INT` | 否 | `0` | 成交单价与新价一致的订单行数 | 成交单价与新价一致的订单行数 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 同上,**不写NULL** | 同上,**不写NULL** | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `new_value` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `object_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 产品事件=msku;广告事件=campaign_id/ad_group_id/keyword_id | 产品事件=msku;广告事件=campaign_id/ad_group_id/keyword_id | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `object_name` | `VARCHAR(512)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `object_type` | `VARCHAR(24)` | 否 | `<STRING_DEFAULT_REDACTED>` | product / campaign / ad_group / keyword | product / campaign / ad_group / keyword | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `old_value` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `operator` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | **恒为空**:沃尔玛侧拿不到操作人。谁做的由运营在人工日志里写 | **恒为空**:沃尔玛侧拿不到操作人。谁做的由运营在人工日志里写 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `source` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 本期唯一来源。领星操作日志接口已否决(API_MAP §2.8),故无 lingxing_log 来源 | 本期唯一来源。领星操作日志接口已否决(API_MAP §2.8),故无 lingxing_log 来源 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `store_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `verify_status` | `VARCHAR(24)` | 否 | `<STRING_DEFAULT_REDACTED>` | consistent 一致 \| inconsistent 不一致(标红) \| no_order 无订单可核 \| 空=该事件类型不适用 | consistent 一致 \| inconsistent 不一致(标红) \| no_order 无订单可核 \| 空=该事件类型不适用 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | `verify_window` | `VARCHAR(24)` | 否 | `<STRING_DEFAULT_REDACTED>` | 实际用于核对的窗口:T0 / T0+T1 / 空 | 实际用于核对的窗口:T0 / T0+T1 / 空 | `sql/084_event_ops_action_log.sql` |
| `event_ops_inaction_alert` | `alert_date` | `DATE` | 否 | `未声明` | 未声明 | 日期或时间 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 记录主键 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `mskus` | `VARCHAR(200)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `owner` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `pool_reason` | `VARCHAR(100)` | 否 | `未声明` | 入池原因：7天不出单 / D级 / 7天不出单+D级 | 入池原因：7天不出单 / D级 / 7天不出单+D级 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `resolved_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `resolved_note` | `VARCHAR(200)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `rule_hit` | `VARCHAR(40)` | 否 | `未声明` | 触发规则：R1连续5天无动作 / R2近8天≥5天无动作 | 触发规则：R1连续5天无动作 / R2近8天≥5天无动作 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | `window_detail` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 判定明细：[{d:日志日,act:0/1}]，act=1为有实质动作 | 判定明细：[{d:日志日,act:0/1}]，act=1为有实质动作 | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_owner_claim_alert` | `announced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 认领+扣分随日报公布时间 | 认领+扣分随日报公布时间 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `claimed_by` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 认领人=扣分承担人（dim_product.owner 变为在册人员时检测写入） | 认领人=扣分承担人（dim_product.owner 变为在册人员时检测写入） | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `claimed_detected_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 检测到认领的时间 | 检测到认领的时间 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `cycle_start_date` | `DATE` | 否 | `未声明` | 本轮首次提醒日期=轮次锚点；清零重算=插入新行 | 本轮首次提醒日期=轮次锚点；清零重算=插入新行 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `deduction_points` | `INT` | 否 | `0` | 本轮扣分，二提时写5；首提期认领保持0 | 本轮扣分，二提时写5；首提期认领保持0 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `first_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 首次提醒发送时间 | 首次提醒发送时间 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `product_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 快照产品名，展示用 | 快照产品名，展示用 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注，系统任务不得覆盖 | 人工备注，系统任务不得覆盖 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `second_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 二次提醒发送时间；非空即已触发扣分 | 二次提醒发送时间；非空即已触发扣分 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `status` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | open=跟踪中 claimed=已认领待公布 closed=已公布结案 void=作废(归档/停用退出清单) | open=跟踪中 claimed=已认领待公布 closed=已公布结案 void=作废(归档/停用退出清单) | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 快照店铺名，展示用 | 快照店铺名，展示用 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `supervisor_synced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 扣分同步黄少如时间 | 扣分同步黄少如时间 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_sem_naming_alert` | `ack_status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | pending=待确认 / confirmed=已确认 | pending=待确认 / confirmed=已确认 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `campaign_id` | `VARCHAR(64)` | 否 | `未声明` | SEM Campaign ID | SEM Campaign ID | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `campaign_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | Campaign名称（随导入刷新） | Campaign名称（随导入刷新） | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `confirmed_at` | `DATETIME` | 是（未声明 NOT NULL） | `NULL` | 确认时间 | 确认时间 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `confirmed_by` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `NULL` | 确认人 | 确认人 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `first_seen_date` | `DATE` | 否 | `未声明` | 首次发现日 | 首次发现日 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `last_push_at` | `DATETIME` | 是（未声明 NOT NULL） | `NULL` | 最近一次推送时间（5h重发判据） | 最近一次推送时间（5h重发判据） | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `last_seen_date` | `DATE` | 否 | `未声明` | 最近仍不合规的数据日 | 最近仍不合规的数据日 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `owner_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 负责人（campaign名SKU前缀→dim_product唯一命中；空=无法归属） | 负责人（campaign名SKU前缀→dim_product唯一命中；空=无法归属） | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `owner_open_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 负责人open_id（发送时回填，回调校验用） | 负责人open_id（发送时回填，回调校验用） | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `push_count` | `INT` | 否 | `0` | 累计推送次数 | 累计推送次数 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `NULL` | 人工备注（系统不覆盖） | 人工备注（系统不覆盖） | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `resolved_at` | `DATETIME` | 是（未声明 NOT NULL） | `NULL` | 整改判定时间 | 整改判定时间 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | open=不合规 / resolved=改名归属成功 | open=不合规 / resolved=改名归属成功 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | 店铺名称 | 店铺名称 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `alert_count` | `INT` | 否 | `0` | 当日仍不合规campaign数 | 当日仍不合规campaign数 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `campaign_ids` | `VARCHAR(1000)` | 是（未声明 NOT NULL） | `NULL` | 涉及campaign_id清单（留档） | 涉及campaign_id清单（留档） | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `ded_date` | `DATE` | 否 | `未声明` | 扣分日 | 扣分日 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `NULL` | 本人私信通知时间 | 本人私信通知时间 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `owner_name` | `VARCHAR(128)` | 否 | `未声明` | 负责人 | 负责人 | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | `points` | `INT` | 否 | `5` | 扣分（每人每天固定5分，与月度规划同口径） | 扣分（每人每天固定5分，与月度规划同口径） | `sql/046_sem_naming_alert.sql` |
| `event_sentinel_alert` | `attempt_count` | `int` | 否 | `0` | 自动修复已执行次数(满2转人工) | 自动修复已执行次数(满2转人工) | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `check_key` | `varchar(32)` | 否 | `未声明` | sales_family_eq/cxec21_rows/inventory_snapshot/msku_blank/channel_presence | sales_family_eq/cxec21_rows/inventory_snapshot/msku_blank/channel_presence | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `detail` | `varchar(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 最近一次实测(期望vs实际) | 最近一次实测(期望vs实际) | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `first_alert_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 日期或时间 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `id` | `bigint unsigned` | 否 | `未声明` | 未声明 | 记录主键 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `last_remind_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 日期或时间 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `remark` | `varchar(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注,系统不覆盖 | 人工备注,系统不覆盖 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `remind_count` | `int` | 否 | `0` | 已提醒次数 | 已提醒次数 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `resolved_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 日期或时间 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `resolved_by` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | sentinel_auto/recheck_pass/卡片操作人 | sentinel_auto/recheck_pass/卡片操作人 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `status` | `varchar(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | open=待处理 manual=转人工 resolved=已闭环 | open=待处理 manual=转人工 resolved=已闭环 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `target_date` | `date` | 否 | `未声明` | 被检查的数据日期 | 被检查的数据日期 | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | `updated_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/040_event_sentinel_alert.sql` |
| `event_shipping_freight_alert` | `cargo_codes` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 涉及货件号 | 涉及货件号 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `cash_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `creator` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 发货单创建人(领星操作人) | 发货单创建人(领星操作人) | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `delivery_time` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `first_found_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 日期或时间 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `freight_cny` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `freight_usd` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `is_legacy` | `TINYINT(1)` | 否 | `0` | 1=起算日之前的历史遗留，只出清单不计绩效 | 1=起算日之前的历史遗留，只出清单不计绩效 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `last_penalty_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 最近一次扣分日，按天防重 | 最近一次扣分日，按天防重 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `last_push_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `logistics_channel_id` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `logistics_code` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `logistics_provider_id` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `note` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注列，同步永不覆盖 | 人工备注列，同步永不覆盖 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `other_cny` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `other_usd` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `owner_name` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 补录责任人(需求方定：统一刘晶晶) | 补录责任人(需求方定：统一刘晶晶) | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `penalty_points` | `DECIMAL(10,2)` | 否 | `0` | 累计已扣分 | 累计已扣分 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `push_count` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `resolved_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `shipping_code` | `VARCHAR(64)` | 否 | `未声明` | 发货单号 | 发货单号 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `shipping_status` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | open=待补录 / resolved=已补录 | open=待补录 / resolved=已补录 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `store_names` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 涉及店铺(可跨店) | 涉及店铺(可跨店) | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_wfs_fee_case` | `actual_fee` | `decimal(10,4)` | 否 | `0` | 实收单件费率(wfs_fee_auto.fee,结算众数) | 实收单件费率(wfs_fee_auto.fee,结算众数) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `approved_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 日期或时间 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `approved_by` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 审批人 | 审批人 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `case_nos` | `varchar(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工:Case号,逗号分隔可多个,转following必填 | 人工:Case号,逗号分隔可多个,转following必填 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `claim_amount` | `decimal(12,2)` | 是（未声明 NOT NULL） | `NULL` | 人工:索赔金额(完成时填) | 人工:索赔金额(完成时填) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 立案时间(默认排序键) | 立案时间(默认排序键) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `decided_by` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 运营操作人 | 运营操作人 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `done_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 未声明 | 日期或时间 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `est_recover` | `decimal(12,2)` | 否 | `0` | 预估追回=(actual-manual)*total_units | 预估追回=(actual-manual)*total_units | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `first_alert_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 首次发卡时间 | 首次发卡时间 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `follow_log` | `mediumtext` | 是（未声明 NOT NULL） | `未声明` | 人工:跟进日志(可编辑文本,系统不覆盖) | 人工:跟进日志(可编辑文本,系统不覆盖) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `id` | `bigint unsigned` | 否 | `未声明` | 未声明 | 记录主键 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `item_id` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 展示用ItemID | 展示用ItemID | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `log_updated_at` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 日志最后保存时间(周检查扣绩效依据) | 日志最后保存时间(周检查扣绩效依据) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `manual_fee` | `decimal(10,4)` | 否 | `0` | 人工WFS配送费(cost_config.delivery_fee) | 人工WFS配送费(cost_config.delivery_fee) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `msku` | `varchar(128)` | 否 | `未声明` | MSKU(判定粒度) | MSKU(判定粒度) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `owner_name` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 立案时负责人 | 立案时负责人 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `platform` | `varchar(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `reason` | `varchar(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工:不跟进/放弃理由(送审必填) | 人工:不跟进/放弃理由(送审必填) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `recovered_amount` | `decimal(12,2)` | 是（未声明 NOT NULL） | `NULL` | 人工:实际追回金额(完成时填) | 人工:实际追回金额(完成时填) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `remark` | `varchar(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注,系统不覆盖 | 人工备注,系统不覆盖 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `status` | `varchar(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | waiting待运营确认/following跟进中/approving待林翔审批/done已追回/closed已关闭不追 | waiting待运营确认/following跟进中/approving待林翔审批/done已追回/closed已关闭不追 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `store_id` | `varchar(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `store_name` | `varchar(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `total_units` | `int` | 否 | `0` | 全历史累计销量(fact_sales_daily) | 全历史累计销量(fact_sales_daily) | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | `updated_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_missing_alert` | `announced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 扣分随日报公布时间 | 扣分随日报公布时间 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `cycle_start_date` | `DATE` | 否 | `未声明` | 本轮首次提醒日期=轮次锚点；补费/归档退出后再缺=新行 | 本轮首次提醒日期=轮次锚点；补费/归档退出后再缺=新行 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `deducted_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 扣分落台账时间；非空即已落 biz_perf_deduction | 扣分落台账时间；非空即已落 biz_perf_deduction | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `deduction_points` | `INT` | 否 | `0` | 本轮扣分，二提时写5；首提期保持0 | 本轮扣分，二提时写5；首提期保持0 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `first_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 首次提醒发送时间 | 首次提醒发送时间 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `owner_name` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 扣分承担人=落台账时该产品负责人(dim_product.owner) | 扣分承担人=落台账时该产品负责人(dim_product.owner) | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `product_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 快照产品名，展示用 | 快照产品名，展示用 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注，系统任务不得覆盖 | 人工备注，系统任务不得覆盖 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `second_notified_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 二次提醒发送时间；非空即已触发扣分 | 二次提醒发送时间；非空即已触发扣分 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `status` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | open=跟踪中(缺费) closed=已补费/结案 void=作废(归档/停用退出清单) | open=跟踪中(缺费) closed=已补费/结案 void=作废(归档/停用退出清单) | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 快照店铺名，展示用 | 快照店铺名，展示用 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `supervisor_synced_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 扣分同步黄少如时间 | 扣分同步黄少如时间 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `fact_ad_credit_detail` | `amount` | `DECIMAL(18,4)` | 否 | `0` | 金额（正=返还入账，负=冲回） | 金额（正=返还入账，负=冲回） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `campaign_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 关联CampaignID（有则存） | 关联CampaignID（有则存） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 币种 | 币种 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `fee_category` | `VARCHAR(64)` | 否 | `未声明` | 类目: ad_credit/wfs_refund/lost_inventory/found_inventory/sem_credit | 类目: ad_credit/wfs_refund/lost_inventory/found_inventory/sem_credit | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `period_end` | `DATE` | 是（未声明 NOT NULL） | `NULL` | 所属账单周期结束 | 所属账单周期结束 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `period_start` | `DATE` | 是（未声明 NOT NULL） | `NULL` | 所属账单周期开始 | 所属账单周期开始 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `posted_date` | `DATE` | 否 | `未声明` | 入账日期 | 入账日期 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `NULL` | 人工备注（系统不覆盖） | 人工备注（系统不覆盖） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `source_ref` | `VARCHAR(128)` | 否 | `未声明` | 来源行唯一标识（statement=transactionKey / SEM=发票号拼接） | 来源行唯一标识（statement=transactionKey / SEM=发票号拼接） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `source_task_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `NULL` | 来源任务 | 来源任务 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `transaction_desc` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | 原transactionDescription | 原transactionDescription | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `transaction_type` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `NULL` | 原transactionType | 原transactionType | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ads_campaign_snapshot_daily` | `advertiser_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `bidding_strategy` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 实测 FIXED/DYNAMIC 有区分度(CN2502 191:9, CN2601 194:6) | 实测 FIXED/DYNAMIC 有区分度(CN2502 191:9, CN2601 194:6) | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `bidding_strategy_status` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `budget_type` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 实测全为 daily | 实测全为 daily | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `campaign_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `campaign_name` | `VARCHAR(512)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `campaign_status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | **实测枚举含 proposal**(SV 13行中7个),文档未列;做状态差分必须按实测枚举,不得照文档 | **实测枚举含 proposal**(SV 13行中7个),文档未列;做状态差分必须按实测枚举,不得照文档 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `campaign_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | API原生值:sponsoredProducts-manual/-auto/sba/video | API原生值:sponsoredProducts-manual/-auto/sba/video | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `daily_budget` | `DECIMAL(14,4)` | 是（未声明 NOT NULL） | `未声明` | 实测全有值 | 实测全有值 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `end_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 实测全空,与 budget_type=daily 一致 | 实测全空,与 budget_type=daily 一致 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `entity_create_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `rollover` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `row_json` | `JSON` | 否 | `未声明` | 接口原始行原样留存 | 接口原始行原样留存 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `snapshot_date` | `DATE` | 否 | `未声明` | 快照日(**美西日界**,laToday(0));配置是当前值,故快照日=业务日 | 快照日(**美西日界**,laToday(0));配置是当前值,故快照日=业务日 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `start_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `targeting_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `total_budget` | `DECIMAL(14,4)` | 是（未声明 NOT NULL） | `未声明` | 实测全空——与 budget_type 全为 daily 一致,属合理为空 | 实测全空——与 budget_type 全为 daily 一致,属合理为空 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `troas` | `DECIMAL(14,4)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `ad_group_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `ad_group_name` | `VARCHAR(512)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `ad_group_status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `advertiser_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `campaign_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `campaign_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `entity_create_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | ⚠️实测仅 20~39/200 有值 ⇒ **新增广告组不得靠本列判定,必须用 ad_group_id 首次出现日** | ⚠️实测仅 20~39/200 有值 ⇒ **新增广告组不得靠本列判定,必须用 ad_group_id 首次出现日** | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `row_json` | `JSON` | 否 | `未声明` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `snapshot_date` | `DATE` | 否 | `未声明` | 快照日(美西日界) | 快照日(美西日界) | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_daily` | `acos` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | ACoS | ACoS | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `ad_group_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告组ID | 广告组ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `ad_group_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告组名称 | 广告组名称 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `ad_spend` | `DECIMAL(18,4)` | 否 | `0` | 广告花费 | 广告花费 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `advertiser_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告主ID | 广告主ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `campaign_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告活动ID | 广告活动ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `campaign_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告活动名称 | 广告活动名称 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `campaign_type` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 广告类型 | 广告类型 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `clicks` | `INT` | 否 | `0` | 点击量 | 点击量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `conversion_rate` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 转化率 | 转化率 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `cpc` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | CPC | CPC | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `ctr` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 点击率 | 点击率 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `cvr` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | CVR | CVR | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `impressions` | `INT` | 否 | `0` | 曝光量 | 曝光量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `item_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `item_name` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 商品名称 | 商品名称 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `keyword` | `VARCHAR(512)` | 否 | `未声明` | 关键词原文 | 关键词原文 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `keyword_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 类型: manual_keyword/auto_search_term/product_targeting/unknown | 类型: manual_keyword/auto_search_term/product_targeting/unknown | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `match_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 匹配类型 | 匹配类型 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `msku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `normalized_keyword` | `VARCHAR(512)` | 否 | `未声明` | 标准化关键词（小写+trim） | 标准化关键词（小写+trim） | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `operator` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 操作人 | 操作人 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `orders` | `INT` | 否 | `0` | 广告订单数 | 广告订单数 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `roas` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | RoAS | RoAS | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | RAW层ID | RAW层ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `source_task_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 来源任务ID | 来源任务ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `source_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 数据来源: lingxing_keyword/walmart_auto_csv/frontend_auto_tool/feishu_manual/unknown | 数据来源: lingxing_keyword/walmart_auto_csv/frontend_auto_tool/feishu_manual/unknown | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `stat_date` | `DATE` | 否 | `未声明` | 统计日期 | 统计日期 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID（必填，不允许为空） | 店铺ID（必填，不允许为空） | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `total_add_to_cart` | `INT` | 否 | `0` | 加购数量 | 加购数量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `total_sales` | `DECIMAL(18,4)` | 否 | `0` | 广告销售额 | 广告销售额 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_snapshot_daily` | `ad_group_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `ad_group_status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `advertiser_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `campaign_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `campaign_status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `campaign_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `keyword_bid` | `DECIMAL(14,4)` | 是（未声明 NOT NULL） | `未声明` | 实测 200/200 有值。**这是当前出价,不随查询区间变**(两区间79个交集差异0) | 实测 200/200 有值。**这是当前出价,不随查询区间变**(两区间79个交集差异0) | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `keyword_id` | `VARCHAR(64)` | 否 | `未声明` | 实测 200/200 有值。**空值一律写空串,不写NULL**(唯一键内NULL不去重,2026-08-15 Schema审计) | 实测 200/200 有值。**空值一律写空串,不写NULL**(唯一键内NULL不去重,2026-08-15 Schema审计) | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `keyword_name` | `VARCHAR(512)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `keyword_state` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | **开关状态**(enabled/paused,实测193:7)。「关闭关键词」判定用本列 | **开关状态**(enabled/paused,实测193:7)。「关闭关键词」判定用本列 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `keyword_status` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | **审核状态**(实测 approved 全同值,无区分度)。⚠️不可用于开关判定,与上一列语义完全不同 | **审核状态**(实测 approved 全同值,无区分度)。⚠️不可用于开关判定,与上一列语义完全不同 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `match_type` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `row_json` | `JSON` | 否 | `未声明` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `snapshot_date` | `DATE` | 否 | `未声明` | 快照日(美西日界) | 快照日(美西日界) | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_platform_daily` | `acos` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | ACoS (%) | ACoS (%) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ad_group_id` | `VARCHAR(64)` | 否 | `未声明` | 广告组ID | 广告组ID | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ad_group_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告组名称 | 广告组名称 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ad_platform` | `VARCHAR(64)` | 否 | `未声明` | 投放平台: Desktop / Mobile | 投放平台: Desktop / Mobile | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ad_spend` | `DECIMAL(18,4)` | 否 | `0` | 广告花费 ($) | 广告花费 ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `advertised_sku_sales` | `DECIMAL(18,4)` | 否 | `0` | 直接归因销售额 ($) | 直接归因销售额 ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `advertised_sku_units` | `INT` | 否 | `0` | 直接归因销量 | 直接归因销量 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `advertiser_id` | `VARCHAR(64)` | 否 | `未声明` | 广告主ID (advertiserId) | 广告主ID (advertiserId) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `advertiser_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告主名称 (mpAdvertiserName) | 广告主名称 (mpAdvertiserName) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `aov` | `DECIMAL(18,4)` | 是（未声明 NOT NULL） | `未声明` | 平均订单值 AOV ($) | 平均订单值 AOV ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `bid` | `DECIMAL(18,4)` | 是（未声明 NOT NULL） | `未声明` | 当前竞价 ($) | 当前竞价 ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `campaign_id` | `VARCHAR(64)` | 否 | `未声明` | 广告活动ID | 广告活动ID | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `campaign_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告活动名称 | 广告活动名称 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `campaign_status` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 活动状态: enabled/paused/live/completed等 | 活动状态: enabled/paused/live/completed等 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `campaign_type` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 广告类型: sponsoredProducts/sba/video | 广告类型: sponsoredProducts/sba/video | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `clicks` | `INT` | 否 | `0` | 点击量 (numAdsClicks) | 点击量 (numAdsClicks) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `cpa` | `DECIMAL(18,4)` | 是（未声明 NOT NULL） | `未声明` | 平均订单成本 CPA ($) | 平均订单成本 CPA ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `cpc` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 点击成本 CPC ($) | 点击成本 CPC ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ctr` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 点击率 CTR (%) | 点击率 CTR (%) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `cvr` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 转化率 CVR (%) | 转化率 CVR (%) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段（含 inStore* 实体店低频数据） | 扩展字段（含 inStore* 实体店低频数据） | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `impressions` | `INT` | 否 | `0` | 曝光量 (numAdsShown) | 曝光量 (numAdsShown) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ntb_order_rate` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 品牌新买家订单转化率 (%) | 品牌新买家订单转化率 (%) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ntb_orders` | `INT` | 否 | `0` | 品牌新买家订单数 | 品牌新买家订单数 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ntb_orders_pct` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 新买家订单占比 (%) | 新买家订单占比 (%) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ntb_revenue` | `DECIMAL(18,4)` | 否 | `0` | 品牌新买家销售额 ($) | 品牌新买家销售额 ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ntb_revenue_pct` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 新买家销售额占比 (%) | 新买家销售额占比 (%) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ntb_units` | `INT` | 否 | `0` | 品牌新买家销量 | 品牌新买家销量 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `ntb_units_pct` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 新买家销量占比 (%) | 新买家销量占比 (%) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `orders` | `INT` | 否 | `0` | 归因广告订单数 | 归因广告订单数 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `other_sku_sales` | `DECIMAL(18,4)` | 否 | `0` | 间接/关联销售额 ($) | 间接/关联销售额 ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `other_sku_units` | `INT` | 否 | `0` | 间接/关联销量 | 间接/关联销量 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 电商平台，固定值 walmart | 电商平台，固定值 walmart | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `roas` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | RoAS | RoAS | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | RAW层ID (raw_lingxing_api.id) | RAW层ID (raw_lingxing_api.id) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `stat_date` | `DATE` | 否 | `未声明` | 统计日期 | 统计日期 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID（映射自 dim_store） | 店铺ID（映射自 dim_store） | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用，冗余） | 店铺名称（展示用，冗余） | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `total_sales` | `DECIMAL(18,4)` | 否 | `0` | 归因广告销售额 ($) | 归因广告销售额 ($) | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `units` | `INT` | 否 | `0` | 归因广告销量 | 归因广告销量 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_product_daily` | `acos` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | ACoS | ACoS | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `ad_group_id` | `VARCHAR(64)` | 否 | `未声明` | 广告组ID | 广告组ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `ad_group_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告组名称 | 广告组名称 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `ad_spend` | `DECIMAL(18,4)` | 否 | `0` | 广告花费 | 广告花费 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `advertiser_id` | `VARCHAR(64)` | 否 | `未声明` | 广告主ID | 广告主ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `campaign_id` | `VARCHAR(64)` | 否 | `未声明` | 广告活动ID | 广告活动ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `campaign_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 广告活动名称 | 广告活动名称 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `campaign_type` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 广告类型 (SP/SB/SV) | 广告类型 (SP/SB/SV) | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `clicks` | `INT` | 否 | `0` | 点击量 | 点击量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `cpc` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | CPC | CPC | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `ctr` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 点击率 | 点击率 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `cvr` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 转化率 | 转化率 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `impressions` | `INT` | 否 | `0` | 曝光量 | 曝光量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `msku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `orders` | `INT` | 否 | `0` | 广告订单数 | 广告订单数 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `roas` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | RoAS | RoAS | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | RAW层ID | RAW层ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `stat_date` | `DATE` | 否 | `未声明` | 统计日期 | 统计日期 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `total_sales` | `DECIMAL(18,4)` | 否 | `0` | 广告销售额 | 广告销售额 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_snapshot_status` | `api_code` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 接口业务码,0=成功 | 接口业务码,0=成功 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `api_path` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `api_total` | `INT` | 是（未声明 NOT NULL） | `未声明` | 接口自报总数(data.total);为NULL表示接口未返回该字段 | 接口自报总数(data.total);为NULL表示接口未返回该字段 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `campaign_type` | `VARCHAR(64)` | 否 | `未声明` | sp(manual+auto) / sba / video | sp(manual+auto) / sba / video | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `entity_type` | `VARCHAR(32)` | 否 | `未声明` | campaign / group / keyword | campaign / group / keyword | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `error_message` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 失败时原样存接口 message,不加工 | 失败时原样存接口 message,不加工 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `fetched_rows` | `INT` | 否 | `0` | 实际取回行数 | 实际取回行数 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `hit_page_cap` | `TINYINT` | 否 | `0` | 1=触顶分页上限,**必然不完整** | 1=触顶分页上限,**必然不完整** | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `is_complete` | `TINYINT` | 否 | `0` | 1=完整。判据:code=0 且 未触顶 且 (api_total为空 或 fetched_rows>=api_total) | 1=完整。判据:code=0 且 未触顶 且 (api_total为空 或 fetched_rows>=api_total) | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `pages_fetched` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `snapshot_date` | `DATE` | 否 | `未声明` | 快照日(美西日界) | 快照日(美西日界) | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `store_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/083_ads_config_snapshot.sql` |
| `fact_attendance_daily` | `check_in_result` | `VARCHAR(24)` | 否 | `<STRING_DEFAULT_REDACTED>` | Normal/Late/SeriousLate/Early/Lack | Normal/Late/SeriousLate/Early/Lack | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `check_in_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 实际上班打卡 | 实际上班打卡 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `check_out_result` | `VARCHAR(24)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `check_out_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 实际下班打卡(排班下班那次) | 实际下班打卡(排班下班那次) | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `day_status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | 正常/迟到/早退/缺卡/旷工/请假/休息 | 正常/迟到/早退/缺卡/旷工/请假/休息 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `early_minutes` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `group_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 考勤组 | 考勤组 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `is_scheduled` | `TINYINT(1)` | 否 | `0` | 当天是否排班(大小周由飞书排班定) | 当天是否排班(大小周由飞书排班定) | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `last_punch_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 当天最后一次打卡(含夜间加班) | 当天最后一次打卡(含夜间加班) | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `late_minutes` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `leave_hours` | `DECIMAL(6,2)` | 否 | `0` | 未声明 | 待确认 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `leave_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 事假/病假/年假等(i18n_names.ch) | 事假/病假/年假等(i18n_names.ch) | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `open_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `out_hours` | `DECIMAL(6,2)` | 否 | `0` | 外出时长 | 外出时长 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `overtime_minutes` | `INT` | 否 | `0` | 打卡超时=末次打卡-排班下班(无审批加班,纯打卡口径) | 打卡超时=末次打卡-排班下班(无审批加班,纯打卡口径) | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `remark` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `shift_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 班次 | 班次 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `stat_date` | `DATE` | 否 | `未声明` | 考勤日 | 考勤日 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | `user_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 飞书user_id(employee_id) | 飞书user_id(employee_id) | `sql/031_attendance_tables.sql` |
| `fact_channel_clearance_sales_daily` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `id` | `bigint` | 否 | `未声明` | 主键 | 主键 | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `local_sku` | `varchar(128)` | 否 | `未声明` | 领星本地SKU(=公司SKU)，订单 item_info.local_sku | 领星本地SKU(=公司SKU)，订单 item_info.local_sku | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `order_cnt` | `int` | 否 | `<STRING_DEFAULT_REDACTED>` | 当日订单数（按订单去重） | 当日订单数（按订单去重） | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `platform` | `varchar(32)` | 否 | `未声明` | 平台：amazon / shein | 平台：amazon / shein | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `platform_ref` | `varchar(128)` | 否 | `未声明` | 平台商品ID（亚马逊=ASIN/希音=SKC/TEMU/TikTok=平台商品ID），订单 item_info.product_no；聚合主键 | 平台商品ID（亚马逊=ASIN/希音=SKC/TEMU/TikTok=平台商品ID），订单 item_info.product_no；聚合主键 | `交付件/DDL_清货已清渠道销量事实表_v2按ASIN.sql` |
| `fact_channel_clearance_sales_daily` | `sales_qty` | `int` | 否 | `<STRING_DEFAULT_REDACTED>` | 当日该平台该SKU销量（跨店铺汇总，排除 status=7 取消/is_delete=1） | 当日该平台该SKU销量（跨店铺汇总，排除 status=7 取消/is_delete=1） | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `source_raw_id` | `bigint` | 是（未声明 NOT NULL） | `NULL` | RAW层ID（该日最后一页 raw_lingxing_api.id） | RAW层ID（该日最后一页 raw_lingxing_api.id） | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `source_system` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `stat_date` | `date` | 否 | `未声明` | 订购日期（global_purchase_time，北京时间） | 订购日期（global_purchase_time，北京时间） | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | `updated_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_commission_saving` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 币种 | 币种 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `incentive_program` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 激励计划（commissionIncentiveProgram，如New Seller Saving/PRO/Pro Listing） | 激励计划（commissionIncentiveProgram，如New Seller Saving/PRO/Pro Listing） | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | ItemID（dim_product唯一命中回填，可空） | ItemID（dim_product唯一命中回填，可空） | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | MSKU（partnerItemId） | MSKU（partnerItemId） | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `period_end` | `DATE` | 否 | `未声明` | 账单周期结束 | 账单周期结束 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `period_start` | `DATE` | 否 | `未声明` | 账单周期开始 | 账单周期开始 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `NULL` | 人工备注（系统不覆盖） | 人工备注（系统不覆盖） | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `saving_amount` | `DECIMAL(18,4)` | 否 | `0` | 佣金节省Σ（Sale行commissionSaving，激励中心口径） | 佣金节省Σ（Sale行commissionSaving，激励中心口径） | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `source_task_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `NULL` | 来源任务 | 来源任务 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `txn_count` | `INT` | 否 | `0` | 行数 | 行数 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_inbound_freight_alloc` | `alloc_amount` | `DECIMAL(18,4)` | 否 | `0` | =freight_total×declare_num占比 | =freight_total×declare_num占比 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `cargo_code` | `VARCHAR(128)` | 否 | `未声明` | 沃尔玛账单ShipmentID=货件单号(探针15实锤,WFA/WFB通配) | 沃尔玛账单ShipmentID=货件单号(探针15实锤,WFA/WFB通配) | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `declare_num` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `freight_total` | `DECIMAL(18,4)` | 否 | `0` | 该货件真实运费(账单) | 该货件真实运费(账单) | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 商品标识 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `settlement_month` | `CHAR(7)` | 否 | `未声明` | 费用归属结算月 | 费用归属结算月 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `shipment_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 领星货件id | 领星货件id | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `fact_inventory_daily` | `available_stock` | `INT` | 否 | `0` | 可用库存 | 可用库存 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `inbound_stock` | `INT` | 否 | `0` | 在途库存 | 在途库存 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `non_wfs_available_stock` | `INT` | 否 | `0` | 非WFS可售库存 | 非WFS可售库存 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `reserved_stock` | `INT` | 否 | `0` | 预留库存 | 预留库存 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `sku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | SKU | SKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `snapshot_date` | `DATE` | 否 | `未声明` | 快照日期 | 快照日期 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | RAW层ID | RAW层ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `stock_days` | `DECIMAL(18,4)` | 是（未声明 NOT NULL） | `未声明` | 库存天数 | 库存天数 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `warehouse_stock` | `INT` | 否 | `0` | 仓库库存 | 仓库库存 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | `wfs_available_stock` | `INT` | 否 | `0` | WFS可用库存 | WFS可用库存 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_item_landed_cost` | `cost_month` | `CHAR(7)` | 否 | `未声明` | 归集月 | 归集月 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `cost_source` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | collected=自算归集 / batch_api=批次成本接口回补(历史缺失) | collected=自算归集 / batch_api=批次成本接口回补(历史缺失) | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `firstmile_unit_cost` | `DECIMAL(18,4)` | 否 | `0` | 头程单价(发货单归集) | 头程单价(发货单归集) | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 商品标识 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `landed_unit_cost` | `DECIMAL(18,4)` | 否 | `0` | =采购+头程 | =采购+头程 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `purchase_unit_cost` | `DECIMAL(18,4)` | 否 | `0` | 采购单价(采购单归集) | 采购单价(采购单归集) | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `sku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 可空=跨店共享SKU成本 | 可空=跨店共享SKU成本 | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `fact_lingxing_batch` | `amount` | `DECIMAL(18,4)` | 否 | `0` | 批次货款(purchase_price×total) | 批次货款(purchase_price×total) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `bad_num` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `balance_num` | `INT` | 否 | `0` | 结存数量 | 结存数量 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `batch_no` | `VARCHAR(64)` | 否 | `未声明` | 批次号 | 批次号 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `batch_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `fee` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 金额或费用 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `good_num` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `head_stock_cost` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 金额或费用 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `head_stock_price` | `DECIMAL(18,4)` | 否 | `0` | 头程单价 | 头程单价 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `inventory_age` | `INT` | 否 | `0` | 未声明 | 库存相关字段 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `lx_update_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `order_sn` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源单据号(入库/调拨等) | 来源单据号(入库/调拨等) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `other_price` | `DECIMAL(18,4)` | 否 | `0` | 其他单价(接口字段名 price) | 其他单价(接口字段名 price) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `product_id` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 产品标识 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `product_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `purchase_in_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 入库时间(期初切点判定用) | 入库时间(期初切点判定用) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `purchase_price` | `DECIMAL(18,4)` | 否 | `0` | 采购单价(CNY) | 采购单价(CNY) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `purchase_sns_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | purchase_order_sns 数组 | purchase_order_sns 数组 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `sku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `source_batch_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | source_batch_no 数组(调拨链路) | source_batch_no 数组(调拨链路) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `stock_cost` | `DECIMAL(18,4)` | 否 | `0` | 结存成本=stock_price×balance_num | 结存成本=stock_price×balance_num | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `stock_price` | `DECIMAL(18,4)` | 否 | `0` | 库存单价=采购+其他+头程(恒等已实证) | 库存单价=采购+其他+头程(恒等已实证) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 实测多为"0"，批次不绑店 | 实测多为"0"，批次不绑店 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `supplier_names` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `total` | `INT` | 否 | `0` | 批次入库总量 | 批次入库总量 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `transit_balance_num` | `INT` | 否 | `0` | 在途结存 | 在途结存 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `type` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `type_name` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 采购入库/调拨入库/其他入库… | 采购入库/调拨入库/其他入库… | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `wh_name` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 仓库名(WFS虚拟仓/美西ON仓等) | 仓库名(WFS虚拟仓/美西ON仓等) | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | `wid` | `INT` | 否 | `未声明` | 仓库id | 仓库id | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_fx_rate` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `currency_code` | `VARCHAR(8)` | 否 | `未声明` | 币种代码，如 USD/CNY | 币种代码，如 USD/CNY | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `currency_name` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 币种名 | 币种名 | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `icon` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 币种符号 | 币种符号 | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `lx_update_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 领星侧更新时间 | 领星侧更新时间 | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `my_rate` | `DECIMAL(20,10)` | 否 | `0` | 我的汇率(财务在领星录入;领星算成本优先用它)=主口径 | 我的汇率(财务在领星录入;领星算成本优先用它)=主口径 | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `rate_month` | `CHAR(7)` | 否 | `未声明` | 汇率年月 yyyy-MM（接口 data>>date） | 汇率年月 yyyy-MM（接口 data>>date） | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `rate_org` | `DECIMAL(20,10)` | 否 | `0` | 官方汇率(中国银行) | 官方汇率(中国银行) | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/058_lingxing_fx_rate.sql` |
| `fact_local_inventory_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/021_local_inventory.sql` |
| `fact_local_inventory_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/021_local_inventory.sql` |
| `fact_local_inventory_daily` | `qty` | `INT` | 否 | `0` | 本地仓可用库存（字段侦测：product_valid_num 等候选） | 本地仓可用库存（字段侦测：product_valid_num 等候选） | `sql/021_local_inventory.sql` |
| `fact_local_inventory_daily` | `sku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/021_local_inventory.sql` |
| `fact_local_inventory_daily` | `snapshot_date` | `DATE` | 否 | `未声明` | 拉取当日（实时库存打拉取日标签，同 fact_inventory_daily 口径教训） | 拉取当日（实时库存打拉取日标签，同 fact_inventory_daily 口径教训） | `sql/021_local_inventory.sql` |
| `fact_local_inventory_daily` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/021_local_inventory.sql` |
| `fact_local_inventory_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/021_local_inventory.sql` |
| `fact_mp_sales_channel_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `NULL` | 扩展字段 | 扩展字段 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 商品ID，经 dim_product(platform,store_id,msku) 反查；未命中为空串（订单接口 product_no 实测为空） | 商品ID，经 dim_product(platform,store_id,msku) 反查；未命中为空串（订单接口 product_no 实测为空） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `mixed_sales_qty` | `INT` | 否 | `0` | 混合销量：delivery_type=1 中转值（2026-06 实测0单，列保留） | 混合销量：delivery_type=1 中转值（2026-06 实测0单，列保留） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU（订单商品行 msku，聚合主键之一） | MSKU（订单商品行 msku，聚合主键之一） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `non_wfs_order_cnt` | `INT` | 否 | `0` | 非WFS订单数（非取消） | 非WFS订单数（非取消） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `non_wfs_sales_qty` | `INT` | 否 | `0` | 非WFS销量：delivery_type=2 自发货，排除取消单 | 非WFS销量：delivery_type=2 自发货，排除取消单 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `NULL` | RAW层ID（该日最后一页 raw_lingxing_api.id） | RAW层ID（该日最后一页 raw_lingxing_api.id） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `stat_date` | `DATE` | 否 | `未声明` | 订购日期（global_purchase_time，北京时间） | 订购日期（global_purchase_time，北京时间） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID（订单顶层 store_id） | 店铺ID（订单顶层 store_id） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | 店铺名称（展示用） | 店铺名称（展示用） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `wfs_order_cnt` | `INT` | 否 | `0` | WFS订单数（非取消） | WFS订单数（非取消） | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | `wfs_sales_qty` | `INT` | 否 | `0` | WFS销量：delivery_type=3 平台发货，排除 status=7 取消单 | WFS销量：delivery_type=3 平台发货，排除 status=7 取消单 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_onsite_ads_invoice_head` | `account_number` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | Connect广告账号(PDF头部) | Connect广告账号(PDF头部) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `charge_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 实际扣款日 | 实际扣款日 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `invoice_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 开票日 | 开票日 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `invoice_number` | `VARCHAR(40)` | 否 | `未声明` | 发票号 | 发票号 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `line_count` | `INT` | 否 | `0` | 未声明 | 数量 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `payment_method` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | Seller Center(余额,进statement)/Credit Card(不进statement) | Seller Center(余额,进statement)/Credit Card(不进statement) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `period_end` | `DATE` | 否 | `未声明` | 账期止(含) | 账期止(含) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `period_start` | `DATE` | 否 | `未声明` | 账期起 | 账期起 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `未声明` | 人工备注(系统不覆盖) | 人工备注(系统不覆盖) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `source_task_id` | `VARCHAR(40)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 名称 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `subtotal` | `DECIMAL(18,2)` | 否 | `0` | 明细小计 | 明细小计 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `total_ad_spend` | `DECIMAL(18,2)` | 否 | `0` | 广告花费总额(对账日绩效用这个,勿用实扣额) | 广告花费总额(对账日绩效用这个,勿用实扣额) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `total_charged` | `DECIMAL(18,2)` | 否 | `0` | 实扣额=AdSpend+Credit | 实扣额=AdSpend+Credit | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `total_credits_applied` | `DECIMAL(18,2)` | 否 | `0` | 发票内credit抵扣(负数;店铺账单看不到这类credit) | 发票内credit抵扣(负数;店铺账单看不到这类credit) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `amount` | `DECIMAL(18,2)` | 否 | `0` | 未声明 | 金额或费用 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `campaign_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 名称 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `campaign_ref_id` | `VARCHAR(64)` | 否 | `未声明` | 发票括号内ID(Connect内部编码,与日绩效campaign_id不同套) | 发票括号内ID(Connect内部编码,与日绩效campaign_id不同套) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `invoice_number` | `VARCHAR(40)` | 否 | `未声明` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 归属ItemID(批2回填) | 归属ItemID(批2回填) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `matched_campaign_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 名称匹配日绩效campaign_id(批2回填) | 名称匹配日绩效campaign_id(批2回填) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `period_end` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `period_start` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `未声明` | 人工备注(系统不覆盖) | 人工备注(系统不覆盖) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `section` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 发票分区(SV/SB出现独立分区时自动承接) | 发票分区(SV/SB出现独立分区时自动承接) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `source_task_id` | `VARCHAR(40)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_profit_daily` | `ad_spend` | `DECIMAL(18,4)` | 否 | `0` | 广告花费 | 广告花费 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `gross_profit` | `DECIMAL(18,4)` | 否 | `0` | 毛利润 | 毛利润 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `logistics_cost` | `DECIMAL(18,4)` | 否 | `0` | 物流成本 | 物流成本 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `net_profit` | `DECIMAL(18,4)` | 否 | `0` | 净利润 | 净利润 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `platform_fee` | `DECIMAL(18,4)` | 否 | `0` | 平台费用 | 平台费用 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `product_cost` | `DECIMAL(18,4)` | 否 | `0` | 货品成本 | 货品成本 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `profit_rate` | `DECIMAL(18,6)` | 是（未声明 NOT NULL） | `未声明` | 利润率 | 利润率 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `refund_amount` | `DECIMAL(18,4)` | 否 | `0` | 退款金额 | 退款金额 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `sales_amount` | `DECIMAL(18,4)` | 否 | `0` | 销售额 | 销售额 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | RAW层ID | RAW层ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `stat_date` | `DATE` | 否 | `未声明` | 统计日期 | 统计日期 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_promo_discount_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `discount_amount` | `DECIMAL(12,2)` | 否 | `0` | 折扣绝对额(正值),页面展示为负项 | 折扣绝对额(正值),页面展示为负项 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `discount_date` | `DATE` | 否 | `未声明` | 归因日=订购日 | 归因日=订购日 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `discount_orders` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `discount_qty` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 经dim_product(店铺+MSKU)映射,未映射空串 | 经dim_product(店铺+MSKU)映射,未映射空串 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `source_system` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_purchase_cash` | `amount_hash` | `CHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `amount_total` | `DECIMAL(18,4)` | 否 | `0` | 采购单总额(每周复核窗口内可被刷新) | 采购单总额(每周复核窗口内可被刷新) | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `order_sn` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `order_time` | `DATE` | 否 | `未声明` | 现金支出记账日=下单日 | 现金支出记账日=下单日 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `review_close_at` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 复核收口日=下单次月末,过期不再刷新 | 复核收口日=下单次月末,过期不再刷新 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `status_text` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `amount` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `order_sn` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `quantity` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `sku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `unit_price` | `DECIMAL(18,4)` | 否 | `0` | item_list.price真实单价(探针1验证) | item_list.price真实单价(探针1验证) | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `expected_arrival_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 预计到货日期 | 预计到货日期 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `item_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `msku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `platform` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `purchase_amount` | `DECIMAL(18,4)` | 否 | `0` | 采购金额 | 采购金额 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `purchase_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 采购日期 | 采购日期 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `purchase_order_no` | `VARCHAR(128)` | 否 | `未声明` | 采购单号 | 采购单号 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `purchase_qty` | `INT` | 否 | `0` | 采购数量 | 采购数量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `received_qty` | `INT` | 否 | `0` | 已到货数量 | 已到货数量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `sku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | SKU | SKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | RAW层ID | RAW层ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态 | 状态 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `store_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `supplier_id` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 供应商ID | 供应商ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `supplier_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 供应商名称 | 供应商名称 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_order` | `auditor_time` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 日期或时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `create_time` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 日期或时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `order_sn` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `order_time` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 日期或时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `status_shipped` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `status_shipped_text` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `status_text` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `update_time` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 日期或时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | `ware_house_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `expect_arrive_time` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 日期或时间 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `order_sn` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `product_name` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `quantity_entry` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `quantity_real` | `INT` | 否 | `0` | 计划采购量 | 计划采购量 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `quantity_receive` | `INT` | 否 | `0` | 已收货量 | 已收货量 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `sku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/020_purchase_order.sql` |
| `fact_reconciliation_item` | `amount` | `DECIMAL(18,4)` | 否 | `0` | 该品该周期该类目净额(账单符号原样:收入正/扣费负) | 该品该周期该类目净额(账单符号原样:收入正/扣费负) | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `fee_category` | `VARCHAR(64)` | 否 | `未声明` | 分类键:sale/shipping/tax_net/commission/refund_keepit/refund_return/wfs_fulfillment/ad_platform/sem/storage/inbound_transport/removal/lost_inventory/found_inventor | 分类键:sale/shipping/tax_net/commission/refund_keepit/refund_return/wfs_fulfillment/ad_platform/sem/storage/inbound_transport/removal/lost_inventory/found_inventor | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `gtin` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | Partner Item Id;店铺级类目行为空串 | Partner Item Id;店铺级类目行为空串 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 经dim_product/GTIN映射回填 | 经dim_product/GTIN映射回填 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `period_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `period_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `source_task_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `txn_count` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `confirmed_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `confirmed_by` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工确认人(超管/财务) | 人工确认人(超管/财务) | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `import_task_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `payment_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 回款日期(可延迟) | 回款日期(可延迟) | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `period_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `period_start` | `DATE` | 否 | `未声明` | 账单周期起(每两周一期,起止不固定) | 账单周期起(每两周一期,起止不固定) | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `period_status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | imported=已导入 / confirmed=人工确认可核算 / closed=已核算收口 | imported=已导入 / confirmed=人工确认可核算 / closed=已核算收口 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `remark` | `VARCHAR(500)` | 否 | `<STRING_DEFAULT_REDACTED>` | 人工备注列 | 人工备注列 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `total_payable` | `DECIMAL(18,4)` | 否 | `0` | 账单Total Payable(守恒基准) | 账单Total Payable(守恒基准) | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/042_ai_finance_reconciliation.sql` |
| `fact_refund_daily` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `id` | `bigint unsigned` | 否 | `未声明` | 未声明 | 记录主键 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `item_id` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 经dim_product(店铺+MSKU)映射,未映射为空 | 经dim_product(店铺+MSKU)映射,未映射为空 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `msku` | `varchar(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `platform` | `varchar(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `refund_amount` | `decimal(12,2)` | 否 | `0` | 退款金额(含税净额) | 退款金额(含税净额) | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `refund_date` | `date` | 否 | `未声明` | 售后申请日(归因日) | 售后申请日(归因日) | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `refund_orders` | `int` | 否 | `0` | 退款单数 | 退款单数 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `refund_qty` | `int` | 否 | `0` | 退款件数 | 退款件数 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `source_system` | `varchar(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `store_id` | `varchar(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | `updated_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/047_walmart_refund_tables.sql` |
| `fact_sales_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `currency` | `VARCHAR(16)` | 是（未声明 NOT NULL） | `未声明` | 货币 | 货币 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 商品ID | 商品ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `msku` | `VARCHAR(128)` | 否 | `未声明` | MSKU | MSKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `order_count` | `INT` | 否 | `0` | 订单数 | 订单数 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `platform` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `refund_amount` | `DECIMAL(18,4)` | 否 | `0` | 退款金额 | 退款金额 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `refund_qty` | `INT` | 否 | `0` | 退款数量 | 退款数量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `sales_amount` | `DECIMAL(18,4)` | 否 | `0` | 销售金额 | 销售金额 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `sales_qty` | `INT` | 否 | `0` | 销售数量 | 销售数量 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `sku` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | SKU | SKU | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `source_raw_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | RAW层ID | RAW层ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `stat_date` | `DATE` | 否 | `未声明` | 统计日期 | 统计日期 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_fast_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 经 dim_product(店铺+MSKU) 映射；未映射写空串，**不写NULL**（唯一键内 NULL 不去重，见2026-08-15 Schema审计） | 经 dim_product(店铺+MSKU) 映射；未映射写空串，**不写NULL**（唯一键内 NULL 不去重，见2026-08-15 Schema审计） | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `order_cnt` | `INT` | 否 | `0` | **真实订单数**=COUNT(DISTINCT platform_order_no)。注意 fact_sales_daily.order_count 是 sales_qty 的拷贝(syncLingxingDailyToDb:452)，不是订单数，两者不可互相印证 | **真实订单数**=COUNT(DISTINCT platform_order_no)。注意 fact_sales_daily.order_count 是 sales_qty 的拷贝(syncLingxingDailyToDb:452)，不是订单数，两者不可互相印证 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `sales_amount` | `DECIMAL(18,4)` | 否 | `0` | 折前商品金额合计(口径=item_price_amount之和) | 折前商品金额合计(口径=item_price_amount之和) | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `sales_qty` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `source_system` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `stat_date` | `DATE` | 否 | `未声明` | 业务日=订购日(美西日界) | 业务日=订购日(美西日界) | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_orders_early` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `item_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 商品标识 | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `order_count` | `INT` | 否 | `0` | 订单量（result_type=2） | 订单量（result_type=2） | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `pull_slot` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 拉取时点：1625=正式 / 2000=观察期完整度对照 | 拉取时点：1625=正式 / 2000=观察期完整度对照 | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | raw_lingxing_api.id 留痕 | raw_lingxing_api.id 留痕 | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `stat_date` | `DATE` | 否 | `未声明` | 订单归属日（saleStat date_collect 键，站点时区口径，观察期核验） | 订单归属日（saleStat date_collect 键，站点时区口径，观察期核验） | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/012_order_drop_tables.sql` |
| `fact_sem_billing_daily` | `additional_info` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | Additional Info | Additional Info | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `billing_from` | `DATE` | 否 | `未声明` | 账单开始日（=SEM花费日） | 账单开始日（=SEM花费日） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `billing_to` | `DATE` | 是（未声明 NOT NULL） | `NULL` | 账单结束日（跨天发票才不同于from） | 账单结束日（跨天发票才不同于from） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `campaign_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | Campaign ID（返还行=NA） | Campaign ID（返还行=NA） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `campaign_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | Campaign/Reimbursement Name | Campaign/Reimbursement Name | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `charge_type` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | DEBIT=扣费 / AD_CREDIT=返还 | DEBIT=扣费 / AD_CREDIT=返还 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 币种 | 币种 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `invoice_date` | `DATE` | 是（未声明 NOT NULL） | `NULL` | 发票日期 | 发票日期 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `invoice_id` | `VARCHAR(40)` | 否 | `未声明` | SEM发票ID | SEM发票ID | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `invoice_total` | `DECIMAL(18,4)` | 是（未声明 NOT NULL） | `NULL` | 发票总额（Total Amount） | 发票总额（Total Amount） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 归属ItemID（campaign名解析；解析失败留空） | 归属ItemID（campaign名解析；解析失败留空） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `line_amount` | `DECIMAL(18,4)` | 否 | `0` | 行金额（Line Item Amount） | 行金额（Line Item Amount） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `pay_status` | `VARCHAR(20)` | 是（未声明 NOT NULL） | `NULL` | Status（SUCCESS等） | Status（SUCCESS等） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `payment_mode` | `VARCHAR(20)` | 是（未声明 NOT NULL） | `NULL` | Payment Mode（SETTLEMENT等） | Payment Mode（SETTLEMENT等） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台 | 平台 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `remark` | `VARCHAR(500)` | 是（未声明 NOT NULL） | `NULL` | 人工备注（系统不覆盖） | 人工备注（系统不覆盖） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `source_task_id` | `VARCHAR(40)` | 是（未声明 NOT NULL） | `NULL` | 导入任务ID | 导入任务ID | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID | 店铺ID | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_settlement_msku_monthly` | `amount_hash` | `CHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 金额指纹，变化=账期刷新+复核打回 | 金额指纹，变化=账期刷新+复核打回 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `commission_amount` | `DECIMAL(18,4)` | 否 | `0` | productCommission等佣金 | productCommission等佣金 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 该msku该月list原始行全量留存 | 该msku该月list原始行全量留存 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 经dim_product映射，可空待回填 | 经dim_product映射，可空待回填 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `last_synced_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 账期更新时间(前端展示) | 账期更新时间(前端展示) | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `other_platform_fee` | `DECIMAL(18,4)` | 否 | `0` | 其余平台费净额 | 其余平台费净额 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `promotion_amount` | `DECIMAL(18,4)` | 否 | `0` | walmartPromoCode等促销合计(负) | walmartPromoCode等促销合计(负) | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `purchase_amount` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `refund_amount` | `DECIMAL(18,4)` | 否 | `0` | 退款相关合计(负) | 退款相关合计(负) | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `sales_amount` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `sales_num` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `settlement_month` | `CHAR(7)` | 否 | `未声明` | 结算月 yyyy-MM（接口settlementDate为月粒度） | 结算月 yyyy-MM（接口settlementDate为月粒度） | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `tax_net_amount` | `DECIMAL(18,4)` | 否 | `0` | 税费净额(代收代缴通常≈0) | 税费净额(代收代缴通常≈0) | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `transportation_amount` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `wfs_inbound_fee` | `DECIMAL(18,4)` | 否 | `0` | wfsWarehousFee入仓费 | wfsWarehousFee入仓费 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `wfs_prep_fee` | `DECIMAL(18,4)` | 否 | `0` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | `wfs_shipment_fee` | `DECIMAL(18,4)` | 否 | `0` | WFS配送费 | WFS配送费 | `sql/041_ai_finance_tables.sql` |
| `fact_shipping_first_let` | `actual_delivery_time` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 冗余自发货单头，按月归集用 | 冗余自发货单头，按月归集用 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `aux_stock_price` | `DECIMAL(18,4)` | 否 | `0` | UI:单位辅料费用 | UI:单位辅料费用 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `cargo_code` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 货件号，串联 WFS货件/入库运输费 | 货件号，串联 WFS货件/入库运输费 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `delivery_num` | `INT` | 否 | `0` | 发货量 | 发货量 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `gtin` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `head_stock_price` | `DECIMAL(18,4)` | 否 | `0` | UI:单位出库头程 | UI:单位出库头程 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | dim_product 唯一命中才回填 | dim_product 唯一命中才回填 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `match_status` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | matched=唯一命中货件 / ambiguous=同msku同数量多货件(不猜) / unmatched=无命中 | matched=唯一命中货件 / ambiguous=同msku同数量多货件(不猜) / unmatched=无命中 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `outbound_price` | `DECIMAL(18,4)` | 否 | `0` | UI:单位出库费用 (API字段名 price) | UI:单位出库费用 (API字段名 price) | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `per_first_let_cost` | `DECIMAL(18,4)` | 否 | `0` | UI:单位头程费用 | UI:单位头程费用 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `per_tax` | `DECIMAL(18,4)` | 否 | `0` | UI:单位税费 | UI:单位税费 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `purchase_price` | `DECIMAL(18,4)` | 否 | `0` | UI:采购单价 | UI:采购单价 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `shipping_code` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `sku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 取自 shipping_goods 反查(发货单可跨店) | 取自 shipping_goods 反查(发货单可跨店) | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `value_source` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 取值来源，如「实际费用」 | 取值来源，如「实际费用」 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | `wfs_stock_price` | `DECIMAL(18,4)` | 否 | `0` | UI:单位WFS入库成本(=以上各项之和) | UI:单位WFS入库成本(=以上各项之和) | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `actual_delivery_time` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 实际发货时间=头程现金记账日(需求方拍板) | 实际发货时间=头程现金记账日(需求方拍板) | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `alloc_diff` | `DECIMAL(18,4)` | 否 | `0` | =alloc_sum-transportation_cost，守恒哨兵用 | =alloc_sum-transportation_cost，守恒哨兵用 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `alloc_sum` | `DECIMAL(18,4)` | 否 | `0` | 按品分摊回加总Σ(单位头程×发货量) | 按品分摊回加总Σ(单位头程×发货量) | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `arrival_time` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 到货时间(预计值,会变) | 到货时间(预计值,会变) | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `creator` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `currency_code` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `delivery_time` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 发货时间 | 发货时间 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `expected_arrival_time` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 预计到港 | 预计到港 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `first_let_rows` | `INT` | 否 | `0` | 头程分摊明细行数 | 头程分摊明细行数 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `gmt_create` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 发货单创建时间 | 发货单创建时间 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `head_fee_type` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 领星分摊方式，如「按计费重」 | 领星分摊方式，如「按计费重」 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `logistics_code` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 物流中心编码，如 LAX2T | 物流中心编码，如 LAX2T | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `other_cost` | `DECIMAL(18,4)` | 否 | `0` | 整单其他费用Σ | 整单其他费用Σ | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `sail_time` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 开船时间 | 开船时间 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `shipping_code` | `VARCHAR(64)` | 否 | `未声明` | 发货单号 SP… | 发货单号 SP… | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `shipping_status` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 状态 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `transportation_cost` | `DECIMAL(18,4)` | 否 | `0` | 整单真实头程运费Σ(shipping_logistics) | 整单真实头程运费Σ(shipping_logistics) | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `unmatched_rows` | `INT` | 否 | `0` | 未能反查到货件/店铺的明细行数 | 未能反查到货件/店铺的明细行数 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | `warehouse_id` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_storage_fee_daily` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `days_in_period` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `fee_date` | `DATE` | 否 | `未声明` | 未声明 | 日期或时间 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `gtin` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 沿用源表item_id映射 | 沿用源表item_id映射 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `report_end` | `DATE` | 否 | `未声明` | 溯源:账期止 | 溯源:账期止 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `report_start` | `DATE` | 否 | `未声明` | 溯源:账期起 | 溯源:账期起 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `sku` | `VARCHAR(128)` | 否 | `未声明` | =MSKU(源表sku列) | =MSKU(源表sku列) | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `source_system` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `storage_fee` | `DECIMAL(18,5)` | 否 | `0` | 日摊额;末日吸收舍入差保账期守恒 | 日摊额;末日吸收舍入差保账期守恒 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_weekly_charge` | `amount` | `DECIMAL(12,2)` | 否 | `0.00` | 该周仓储实扣额(正值,折扣后净额) | 该周仓储实扣额(正值,折扣后净额) | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `period_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `period_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `report_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 结算报告日期 | 结算报告日期 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `report_key` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 结算报告key(溯源,多行取首个) | 结算报告key(溯源,多行取首个) | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `txn_rows` | `INT` | 否 | `1` | 去重后参与求和的RAW行数 | 去重后参与求和的RAW行数 | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/074_storage_weekly_charge.sql` |
| `fact_wfs_shipment` | `cargo_code` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 货件单号 | 货件单号 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `cargo_create_date` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `cargo_status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台货件状态文本 | 平台货件状态文本 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `cargo_sync_status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 货件本地状态（如 已申报） | 货件本地状态（如 已申报） | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `cargo_update_date` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | API update_date | API update_date | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `inbound_order_id` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 入库订单编号 | 入库订单编号 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `logistics_code` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `shipment_id` | `VARCHAR(64)` | 否 | `未声明` | 领星WFS货件id（records.id） | 领星WFS货件id（records.id） | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | raw_lingxing_api.id 留痕回溯 | raw_lingxing_api.id 留痕回溯 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `status` | `TINYINT` | 否 | `未声明` | 0待发货详情 1待送达 2接收中 3已关闭 4已取消 | 0待发货详情 1待送达 2接收中 3已关闭 4已取消 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `status_name` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `store_name` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `system_update_date` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | API system_update_date（probe实测新增，增量锚点） | API system_update_date（probe实测新增，增量锚点） | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `to_await_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 进入AWAITING_DELIVERY时间 | 进入AWAITING_DELIVERY时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `to_cancelled_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 日期或时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `to_closed_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 进入CLOSED时间（R3窗口起点） | 进入CLOSED时间（R3窗口起点） | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `to_pending_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 进入PENDING_SHIPMENT_DETAILS时间 | 进入PENDING_SHIPMENT_DETAILS时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `to_receive_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 进入RECEIVING_IN_PROGRESS时间（R1触发） | 进入RECEIVING_IN_PROGRESS时间（R1触发） | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `damaged_qty` | `INT` | 否 | `0` | 损坏数量（API字段拼写为dameged_qty） | 损坏数量（API字段拼写为dameged_qty） | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `declare_num` | `INT` | 否 | `0` | 申报量（安全转数，禁止NaN/负值直写） | 申报量（安全转数，禁止NaN/负值直写） | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `gtin` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `msku` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `platform` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `product_name` | `VARCHAR(512)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 名称 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `received_num` | `INT` | 否 | `0` | 签收数量 | 签收数量 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `shipment_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `shipments_num` | `INT` | 否 | `0` | 已发货数量 | 已发货数量 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `sku` | `VARCHAR(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `source_raw_id` | `BIGINT UNSIGNED` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_storage_fee` | `avg_units_longterm` | `DECIMAL(12,3)` | 否 | `0` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `avg_units_standard` | `DECIMAL(12,3)` | 否 | `0` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `days_in_period` | `INT` | 否 | `0` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `discount_savings` | `DECIMAL(18,5)` | 否 | `0` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `final_storage_fee` | `DECIMAL(18,5)` | 否 | `0` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `gtin` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 经dim_product映射回填 | 经dim_product映射回填 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `original_amount` | `DECIMAL(18,5)` | 否 | `0` | 未声明 | 金额或费用 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `platform` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `report_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `report_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `sku` | `VARCHAR(128)` | 否 | `未声明` | 报告SKU列=MSKU | 报告SKU列=MSKU | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `source_task_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/041_ai_finance_tables.sql` |
| `raw_feishu_attendance` | `api_type` | `VARCHAR(32)` | 否 | `未声明` | user_tasks/user_flows/user_approvals | user_tasks/user_flows/user_approvals | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | `date_from` | `INT` | 否 | `未声明` | 窗口起(yyyymmdd 或 unix秒) | 窗口起(yyyymmdd 或 unix秒) | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | `date_to` | `INT` | 否 | `未声明` | 窗口止 | 窗口止 | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | `payload_json` | `JSON` | 否 | `未声明` | 接口原样返回 | 接口原样返回 | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | `pulled_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 日期或时间 | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | `raw_hash` | `VARCHAR(64)` | 否 | `未声明` | 去重哈希 | 去重哈希 | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | `user_count` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/031_attendance_tables.sql` |
| `raw_feishu_table` | `app_token` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 飞书 app_token | 飞书 app_token | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `data_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 数据日期 | 数据日期 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `pulled_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 拉取时间 | 拉取时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `raw_hash` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 去重哈希 | 去重哈希 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `row_index` | `INT` | 否 | `未声明` | 行号 | 行号 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `row_json` | `JSON` | 否 | `未声明` | 原始行数据 | 原始行数据 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `sheet_id` | `VARCHAR(128)` | 否 | `未声明` | sheet ID | sheet ID | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `sheet_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | sheet 名称 | sheet 名称 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `spreadsheet_token` | `VARCHAR(128)` | 否 | `未声明` | 表格 token | 表格 token | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `file_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 文件名 | 文件名 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `file_path` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 文件路径 | 文件路径 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `operator` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 操作人 | 操作人 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `row_count` | `INT` | 是（未声明 NOT NULL） | `未声明` | 行数 | 行数 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `source_tool` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 来源工具 | 来源工具 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `upload_status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 上传状态 | 上传状态 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `upload_type` | `VARCHAR(64)` | 否 | `未声明` | 上传类型 (walmart_ads_csv / feishu_export / manual) | 上传类型 (walmart_ads_csv / feishu_export / manual) | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | `uploaded_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 上传时间 | 上传时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `api_path` | `VARCHAR(255)` | 否 | `未声明` | 接口路径 | 接口路径 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `data_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 数据日期 | 数据日期 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `error_message` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 错误信息 | 错误信息 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `is_success` | `TINYINT` | 否 | `0` | 是否成功 1=是 0=否 | 是否成功 1=是 0=否 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `pulled_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 拉取时间 | 拉取时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `raw_hash` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 去重哈希 (md5) | 去重哈希 (md5) | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `request_method` | `VARCHAR(16)` | 否 | `<STRING_DEFAULT_REDACTED>` | 请求方法 | 请求方法 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `request_params_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 请求参数 | 请求参数 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `response_code` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 响应码 | 响应码 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `response_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 原始响应 | 原始响应 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `source_system` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_settlement_order` | `capture_batch` | `VARCHAR(7)` | 否 | `未声明` | 抓取批次 YYYY-MM（每月一跑） | 抓取批次 YYYY-MM（每月一跑） | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | `msku_query` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 查询用的msku | 查询用的msku | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | `row_index` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 接口 rowIndex（与uniqueId组合唯一） | 接口 rowIndex（与uniqueId组合唯一） | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | `row_json` | `JSON` | 否 | `未声明` | 订单行原样留存 | 订单行原样留存 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | `unique_id` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 接口 uniqueId | 接口 uniqueId | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_walmart_listing` | `capture_date` | `DATE` | 否 | `未声明` | 抓取日期 | 抓取日期 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | `item_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 商品标识 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | `msku` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | SKU/MSKU 商品编码 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | `row_json` | `JSON` | 否 | `未声明` | 接口原始行，原样留存 | 接口原始行，原样留存 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 店铺标识 | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_mp_order_discount` | `capture_batch` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `currency` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | amount_currency | amount_currency | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `discount_amount` | `DECIMAL(12,2)` | 否 | `0` | 折扣额,接口原符号(负值=优惠) | 折扣额,接口原符号(负值=优惠) | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `global_order_no` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 领星系统单号 | 领星系统单号 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `item_price_amount` | `DECIMAL(12,2)` | 否 | `0` | 商品金额(折前) | 商品金额(折前) | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `order_item_no` | `VARCHAR(64)` | 否 | `未声明` | 订单明细单号(商品行唯一) | 订单明细单号(商品行唯一) | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `order_status` | `INT` | 否 | `0` | 领星系统订单状态,7=已取消/不发货(FACT排除) | 领星系统订单状态,7=已取消/不发货(FACT排除) | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `platform_order_no` | `VARCHAR(64)` | 否 | `未声明` | 平台单号 | 平台单号 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `purchase_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 归因日=订购日(北京时区) | 归因日=订购日(北京时区) | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `purchase_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 订购时间(北京时区换算) | 订购时间(北京时区换算) | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `quantity` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `row_json` | `JSON` | 否 | `未声明` | {order:单头精简,item:商品行原样} | {order:单头精简,item:商品行原样} | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_item` | `capture_batch` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `currency` | `VARCHAR(8)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `discount_amount` | `DECIMAL(12,2)` | 否 | `0` | 折扣额,接口原符号(负值=优惠);0=全价单 | 折扣额,接口原符号(负值=优惠);0=全价单 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `global_order_no` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 领星系统单号 | 领星系统单号 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `item_price_amount` | `DECIMAL(12,2)` | 否 | `0` | 商品金额(折前)。**这就是订单级成交金额，调价核对的判据** | 商品金额(折前)。**这就是订单级成交金额，调价核对的判据** | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `msku` | `VARCHAR(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `order_item_no` | `VARCHAR(64)` | 否 | `未声明` | 订单明细单号(商品行唯一) | 订单明细单号(商品行唯一) | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `order_status` | `INT` | 否 | `0` | 领星订单状态,7=已取消/不发货(聚合时排除) | 领星订单状态,7=已取消/不发货(聚合时排除) | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `platform_order_no` | `VARCHAR(64)` | 否 | `未声明` | 平台单号 | 平台单号 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `purchase_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 归因日=订购日(**美西日界**，与 saleStat 族同源) | 归因日=订购日(**美西日界**，与 saleStat 族同源) | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `purchase_time` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 订购时间(**美西**，走 usPacific) | 订购时间(**美西**，走 usPacific) | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `quantity` | `INT` | 否 | `0` | 未声明 | 数量 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `row_json` | `JSON` | 否 | `未声明` | {order:单头精简, item:商品行原样} | {order:单头精简, item:商品行原样} | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 经 storeIdNorm 修复精度后的店铺ID | 经 storeIdNorm 修复精度后的店铺ID | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_sync_tasks` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `error_message` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 错误信息 | 错误信息 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `finished_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 完成时间 | 完成时间 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `inserted_count` | `INT` | 否 | `0` | 新增行数 | 新增行数 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `row_count` | `INT` | 是（未声明 NOT NULL） | `未声明` | 飞书总行数 | 飞书总行数 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `sheet_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 飞书 Sheet ID | 飞书 Sheet ID | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `sheet_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 飞书 Sheet 名称 | 飞书 Sheet 名称 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `skipped_count` | `INT` | 否 | `0` | 跳过行数 | 跳过行数 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `source_name` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 来源名称 | 来源名称 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `source_type` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 来源类型 | 来源类型 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `started_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 开始时间 | 开始时间 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `status` | `VARCHAR(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | running/success/failed | running/success/failed | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `sync_task_id` | `VARCHAR(64)` | 否 | `未声明` | 任务唯一ID (UUID) | 任务唯一ID (UUID) | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | `updated_count` | `INT` | 否 | `0` | 更新行数 | 更新行数 | `sql/005_raw_sync_tasks.sql` |
| `raw_walmart_ads_csv` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `operator` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 操作人 | 操作人 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `raw_hash` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 去重哈希 | 去重哈希 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `report_date` | `DATE` | 是（未声明 NOT NULL） | `未声明` | 报表日期 | 报表日期 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `row_index` | `INT` | 否 | `未声明` | 行号 | 行号 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `row_json` | `JSON` | 否 | `未声明` | 原始行数据 | 原始行数据 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 店铺ID（必填，不允许为空） | 店铺ID（必填，不允许为空） | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 店铺名称（展示用） | 店铺名称（展示用） | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `task_id` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 任务ID | 任务ID | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `updated_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 更新时间 | 更新时间 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | `upload_id` | `BIGINT` | 是（未声明 NOT NULL） | `未声明` | 关联 raw_frontend_upload.id | 关联 raw_frontend_upload.id | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_connect_invoice` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `csv_type` | `VARCHAR(20)` | 否 | `<STRING_DEFAULT_REDACTED>` | 固定connect_invoice | 固定connect_invoice | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `invoice_number` | `VARCHAR(40)` | 否 | `<STRING_DEFAULT_REDACTED>` | 发票号 | 发票号 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `operator` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 待确认 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `raw_hash` | `VARCHAR(64)` | 否 | `未声明` | 行内容sha256前64 | 行内容sha256前64 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `row_index` | `INT` | 否 | `未声明` | 0=发票头部摘要,1..n=PDF原文行 | 0=发票头部摘要,1..n=PDF原文行 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `row_json` | `JSON` | 否 | `未声明` | 原文行/头部摘要 | 原文行/头部摘要 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 导入时所选店铺(已过门禁) | 导入时所选店铺(已过门禁) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `未声明` | 未声明 | 名称 | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | `task_id` | `VARCHAR(40)` | 否 | `未声明` | 导入任务ID(WMCINV-*) | 导入任务ID(WMCINV-*) | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_inbound_csv` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `operator` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `raw_hash` | `CHAR(32)` | 否 | `未声明` | 未声明 | 待确认 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `report_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `report_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `row_json` | `JSON` | 否 | `未声明` | CSV原始行 | CSV原始行 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `row_no` | `INT` | 否 | `未声明` | 未声明 | 待确认 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | `task_id` | `VARCHAR(64)` | 否 | `未声明` | 导入批次 WMINB-yyyymmdd-nnnn | 导入批次 WMINB-yyyymmdd-nnnn | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_reconciliation_csv` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `operator` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 导入人(超管/财务) | 导入人(超管/财务) | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `period_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `period_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `raw_hash` | `CHAR(32)` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `row_json` | `JSON` | 否 | `未声明` | CSV原始行(含Transaction Key/Type/Amount Type等全字段) | CSV原始行(含Transaction Key/Type/Amount Type等全字段) | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `row_no` | `INT` | 否 | `未声明` | 未声明 | 待确认 | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | `task_id` | `VARCHAR(64)` | 否 | `未声明` | 导入批次 WMRECON-yyyymmdd-nnnn | 导入批次 WMRECON-yyyymmdd-nnnn | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_return_order` | `capture_batch` | `varchar(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `created_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `customer_order_id` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 订单标识 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `id` | `bigint unsigned` | 否 | `未声明` | 未声明 | 记录主键 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `item_status` | `varchar(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | INITIATED/DELIVERED/COMPLETED | INITIATED/DELIVERED/COMPLETED | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `line_total_amount` | `decimal(12,2)` | 否 | `0` | 退款金额(含税) | 退款金额(含税) | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `msku` | `varchar(128)` | 否 | `未声明` | 未声明 | SKU/MSKU 商品编码 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `purchase_order_id` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 平台订单号 | 平台订单号 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `purchase_time` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 原订单下单时间 | 原订单下单时间 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `quantity` | `int` | 否 | `0` | 未声明 | 数量 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `refund_status` | `varchar(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | REFUND_COMPLETED/NOT_REFUNDED等 | REFUND_COMPLETED/NOT_REFUNDED等 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `return_description` | `varchar(255)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `return_order_date` | `datetime` | 是（未声明 NOT NULL） | `NULL` | 售后申请时间(归因日) | 售后申请时间(归因日) | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `return_order_id` | `varchar(64)` | 否 | `未声明` | 售后单号(平台RMA) | 售后单号(平台RMA) | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `return_reason` | `varchar(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `return_type` | `varchar(32)` | 否 | `<STRING_DEFAULT_REDACTED>` | REFUND/REPLACEMENT/PREORDER | REFUND/REPLACEMENT/PREORDER | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `row_json` | `json` | 否 | `未声明` | 接口原样(单头+该明细) | 接口原样(单头+该明细) | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `store_id` | `varchar(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | `updated_at` | `datetime` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 更新时间 | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_sem_csv` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `csv_type` | `VARCHAR(20)` | 否 | `未声明` | CSV类型: sem_daily=每日报表 / sem_billing=账单历史 | CSV类型: sem_daily=每日报表 / sem_billing=账单历史 | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `operator` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `NULL` | 导入操作人 | 导入操作人 | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `raw_hash` | `VARCHAR(64)` | 否 | `未声明` | 行内容hash | 行内容hash | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `report_date` | `VARCHAR(20)` | 是（未声明 NOT NULL） | `NULL` | 行内日期（sem_daily=Date列 / sem_billing=Billing From） | 行内日期（sem_daily=Date列 / sem_billing=Billing From） | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `row_index` | `INT` | 否 | `未声明` | CSV行号（0起） | CSV行号（0起） | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `row_json` | `JSON` | 否 | `未声明` | 原始行JSON | 原始行JSON | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `store_id` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 店铺ID | 店铺ID | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `store_name` | `VARCHAR(255)` | 是（未声明 NOT NULL） | `NULL` | 店铺名称 | 店铺名称 | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | `task_id` | `VARCHAR(40)` | 否 | `未声明` | 导入任务ID（WMSEM-YYYYMMDD-XXXX） | 导入任务ID（WMSEM-YYYYMMDD-XXXX） | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_storage_csv` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 未声明 | 创建时间 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `id` | `BIGINT UNSIGNED` | 否 | `未声明` | 未声明 | 记录主键 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `operator` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `raw_hash` | `CHAR(32)` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `report_end` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `report_start` | `DATE` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `row_json` | `JSON` | 否 | `未声明` | CSV原始行 | CSV原始行 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `row_no` | `INT` | 否 | `未声明` | 未声明 | 待确认 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `store_id` | `VARCHAR(64)` | 否 | `未声明` | 未声明 | 店铺标识 | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | `task_id` | `VARCHAR(64)` | 否 | `未声明` | 导入批次 WMSTOR-yyyymmdd-nnnn | 导入批次 WMSTOR-yyyymmdd-nnnn | `sql/041_ai_finance_tables.sql` |
| `schema_change_log` | `change_type` | `VARCHAR(64)` | 否 | `未声明` | 类型: add_table/add_column/modify_column/deprecate_column/drop_column_request/index_change | 类型: add_table/add_column/modify_column/deprecate_column/drop_column_request/index_change | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `changed_by` | `VARCHAR(128)` | 否 | `<STRING_DEFAULT_REDACTED>` | 变更人 | 变更人 | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `column_name` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 字段名 | 字段名 | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `created_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 创建时间 | 创建时间 | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `new_definition` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 新定义 | 新定义 | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `old_definition` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 旧定义 | 旧定义 | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `reason` | `TEXT` | 否 | `未声明` | 变更原因 | 变更原因 | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | `table_name` | `VARCHAR(128)` | 否 | `未声明` | 表名 | 表名 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `error_message` | `TEXT` | 是（未声明 NOT NULL） | `未声明` | 错误信息 | 错误信息 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `extra_json` | `JSON` | 是（未声明 NOT NULL） | `未声明` | 扩展字段 | 扩展字段 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `failed_count` | `INT` | 否 | `0` | 失败行数 | 失败行数 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `finished_at` | `DATETIME` | 是（未声明 NOT NULL） | `未声明` | 结束时间 | 结束时间 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `inserted_count` | `INT` | 否 | `0` | 插入行数 | 插入行数 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `pulled_count` | `INT` | 否 | `0` | 拉取行数 | 拉取行数 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `source_system` | `VARCHAR(64)` | 是（未声明 NOT NULL） | `未声明` | 来源系统 | 来源系统 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `started_at` | `DATETIME` | 否 | `CURRENT_TIMESTAMP` | 开始时间 | 开始时间 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `status` | `VARCHAR(64)` | 否 | `<STRING_DEFAULT_REDACTED>` | 状态: running/success/failed | 状态: running/success/failed | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `target_table` | `VARCHAR(128)` | 是（未声明 NOT NULL） | `未声明` | 目标表 | 目标表 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `task_id` | `BIGINT` | 否 | `未声明` | 主键 | 主键 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `task_name` | `VARCHAR(128)` | 否 | `未声明` | 任务名称 | 任务名称 | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | `updated_count` | `INT` | 否 | `0` | 更新行数 | 更新行数 | `sql/001_create_data_warehouse_tables.sql` |

已解析字段数：1809；未出现于安全 CREATE TABLE 的字段标记为待确认，未在此表中臆造。
