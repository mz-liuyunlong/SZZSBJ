# 旧系统数据库关系图

## 主键、唯一键与索引

| 表名 | 类型 | 名称 | 字段 | 来源 |
|---|---|---|---|---|
| `ai_analysis_result` | INDEX | `idx_ai_date_type` | `analysis_date`, `analysis_type` | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | INDEX | `idx_ai_input_hash` | 待确认 | `sql/071_ai_analysis_result_dedup_key.sql` |
| `ai_analysis_result` | INDEX | `idx_ai_input_hash` | `input_hash`, `model_name`, `prompt_version` | `_to_delete/071_ai_analysis_result_uq_add_model_SUPERSEDED_20260814.sql` |
| `ai_analysis_result` | INDEX | `idx_ai_store_date` | `store_id`, `analysis_date` | `sql/002_add_indexes.sql` |
| `ai_analysis_result` | INDEX | `idx_ai_store_item` | `store_id`, `item_id` | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | PRIMARY KEY | `PRIMARY` | `analysis_id` | `sql/001_create_data_warehouse_tables.sql` |
| `ai_analysis_result` | UNIQUE | `uq_ai_result` | 待确认 | `_to_delete/071_ai_analysis_result_uq_add_model_SUPERSEDED_20260814.sql` |
| `ai_business_report` | INDEX | `idx_generated` | `generated_at` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | INDEX | `idx_type_period` | `report_type`, `period_key` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_business_report` | PRIMARY KEY | `PRIMARY` | `id` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `ai_monthly_issue_item` | INDEX | `idx_month_owner` | `plan_month`, `owner` | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | PRIMARY KEY | `PRIMARY` | `id` | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | UNIQUE | `uk_issue` | `report_id`, `platform`, `store_id`, `item_id`, `msku` | `月报系统/交付件/DDL_monthly.sql` |
| `ai_monthly_issue_item` | UNIQUE | `uq_issue` | `plan_month`, `platform`, `store_id`, `item_id` | `sql/041_ai_monthly_issue_item_unique.sql` |
| `ai_ops_log_review_item` | INDEX | `idx_ri_owner` | `week_start`, `owner_name` | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | INDEX | `idx_ri_verdict` | `week_start`, `verdict` | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_item` | UNIQUE | `uq_review_item` | `week_start`, `src_log_id` | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | INDEX | `idx_rs_week` | `week_start` | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_AI人事_日志评级.sql` |
| `ai_ops_log_review_summary` | UNIQUE | `uq_review_summary` | 待确认 | `交付件/DDL_AI人事_日志评级.sql` |
| `biz_app_audit_log` | INDEX | `idx_action_at` | `action`, `at` | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | INDEX | `idx_user_at` | `user_id`, `at` | `sql/022_app_auth_tables.sql` |
| `biz_app_audit_log` | PRIMARY KEY | `PRIMARY` | `id` | `sql/022_app_auth_tables.sql` |
| `biz_business_target` | INDEX | `idx_period` | `period_key` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | PRIMARY KEY | `PRIMARY` | `id` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target` | UNIQUE | `uk_target` | `target_type`, `period_key`, `platform`, `owner`, `metric` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | INDEX | `idx_period_owner` | `period_key`, `owner` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | INDEX | `idx_target` | `target_id` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_business_target_change_log` | PRIMARY KEY | `PRIMARY` | `id` | `AI经营分析报告/正式系统/DDL_draft.sql` |
| `biz_clearance_other_channel` | INDEX | `idx_status` | `status` | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | INDEX | `idx_status` | `status` | `sql/017_clearance_other_channel_v2.sql` |
| `biz_clearance_other_channel` | UNIQUE | `uq_item` | `platform`, `store_id`, `item_id` | `sql/016_clearance_center.sql` |
| `biz_clearance_other_channel` | UNIQUE | `uq_sku_channel` | `sku`, `channel` | `sql/017_clearance_other_channel_v2.sql` |
| `biz_cs_test_alert` | INDEX | `idx_owner` | `owner_name` | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | INDEX | `idx_status` | `status` | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_CS测品预警台账.sql` |
| `biz_cs_test_alert` | UNIQUE | `uq_cs_alert` | 待确认 | `交付件/DDL_CS测品预警台账.sql` |
| `biz_event` | INDEX | `idx_event_status` | `status`, `event_date` | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | INDEX | `idx_event_store_date` | `store_id`, `event_date` | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | PRIMARY KEY | `PRIMARY` | `event_id` | `sql/001_create_data_warehouse_tables.sql` |
| `biz_event` | UNIQUE | `uq_biz_event` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `biz_finance_exchange_rate` | PRIMARY KEY | `PRIMARY` | `id` | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_exchange_rate` | UNIQUE | `uq_fx_month` | `rate_month`, `currency_pair` | `sql/042_ai_finance_reconciliation.sql` |
| `biz_finance_fixed_cost` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `biz_finance_fixed_cost` | UNIQUE | `uq_fixed_cost` | `cost_month`, `level`, `store_id`, `category` | `sql/041_ai_finance_tables.sql` |
| `biz_finance_opening_cost` | PRIMARY KEY | `PRIMARY` | `id` | `sql/062_finance_opening_cost.sql` |
| `biz_finance_opening_cost` | UNIQUE | `uq_opening_sku` | 待确认 | `sql/062_finance_opening_cost.sql` |
| `biz_finance_review` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `biz_finance_review` | UNIQUE | `uq_fin_review` | `platform`, `store_id`, `item_id`, `period_month` | `sql/041_ai_finance_tables.sql` |
| `biz_monthly_plan` | INDEX | `idx_month_owner` | `plan_month`, `owner` | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | PRIMARY KEY | `PRIMARY` | `id` | `月报系统/交付件/DDL_monthly.sql` |
| `biz_monthly_plan` | UNIQUE | `uk_plan` | `plan_month`, `platform`, `store_id`, `item_id`, `msku` | `月报系统/交付件/DDL_monthly.sql` |
| `biz_owner_target_confirm` | INDEX | `idx_period_owner` | `target_type`, `period_key`, `platform`, `owner`, `id` | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_owner_target_confirm` | PRIMARY KEY | `PRIMARY` | `id` | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `biz_perf_deduction` | INDEX | `idx_perf_owner_date` | `owner_name`, `deduction_date` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | INDEX | `idx_perf_type` | `biz_type` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction` | UNIQUE | `uq_perf_ref` | `ref_event_id` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `biz_perf_deduction_note` | INDEX | `idx_note_exempt` | `exempt_status` | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | INDEX | `idx_note_ym` | `ym` | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_perf_deduction_note` | UNIQUE | `uq_note_ref` | `ref_deduction_id` | `交付件/DDL_绩效台账人工层_说明豁免.sql` |
| `biz_product_rule_signal_daily` | INDEX | `idx_owner` | `owner` | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | INDEX | `idx_rule_code` | `rule_code` | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | INDEX | `idx_should_notify` | `signal_date`, `should_notify` | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | INDEX | `idx_signal_date` | `signal_date` | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | INDEX | `idx_store_item` | `store_id`, `item_id` | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/011_biz_product_rule_signal_daily.sql` |
| `biz_product_rule_signal_daily` | UNIQUE | `uk_rule_signal_day` | `signal_date`, `platform`, `store_key`, `item_id`, `msku`, `rule_code` | `sql/011_biz_product_rule_signal_daily.sql` |
| `cs_test_product_config` | PRIMARY KEY | `PRIMARY` | `id` | `sql/007_cs_test_product_config.sql` |
| `cs_test_product_config` | UNIQUE | `uq_cs_test_product_config` | `config_type`, `config_key` | `sql/007_cs_test_product_config.sql` |
| `data_reconcile_log` | INDEX | `idx_reconcile_date` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `data_reconcile_log` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `dim_app_user` | INDEX | `idx_member` | `feishu_member_id` | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | INDEX | `idx_role` | `role` | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | INDEX | `idx_team` | `team_name` | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | PRIMARY KEY | `PRIMARY` | `id` | `sql/022_app_auth_tables.sql` |
| `dim_app_user` | UNIQUE | `uq_username` | `username` | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | INDEX | `idx_perm` | `perm_key` | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | PRIMARY KEY | `PRIMARY` | `id` | `sql/022_app_auth_tables.sql` |
| `dim_app_user_permission` | UNIQUE | `uq_user_perm` | `user_id`, `perm_key` | `sql/022_app_auth_tables.sql` |
| `dim_app_user_role` | INDEX | `idx_role` | `role_key` | `sql/023_app_user_role.sql` |
| `dim_app_user_role` | PRIMARY KEY | `PRIMARY` | `id` | `sql/023_app_user_role.sql` |
| `dim_app_user_role` | UNIQUE | `uq_user_role` | `user_id`, `role_key` | `sql/023_app_user_role.sql` |
| `dim_connect_account` | PRIMARY KEY | `PRIMARY` | `account_number` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_connect_account` | UNIQUE | `uq_dca_store` | `store_id` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `dim_feishu_department` | PRIMARY KEY | `PRIMARY` | `open_department_id` | `_to_delete/039_roster_profile_extend.sql` |
| `dim_keyword` | PRIMARY KEY | `PRIMARY` | `keyword_id` | `sql/001_create_data_warehouse_tables.sql` |
| `dim_keyword` | UNIQUE | `uq_dim_keyword` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | PRIMARY KEY | `PRIMARY` | `owner_id` | `sql/001_create_data_warehouse_tables.sql` |
| `dim_owner` | UNIQUE | `uq_dim_owner` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | INDEX | `idx_dim_prod_item` | `item_id` | `sql/002_add_indexes.sql` |
| `dim_product` | INDEX | `idx_dim_prod_platform` | `platform` | `sql/002_add_indexes.sql` |
| `dim_product` | INDEX | `idx_dim_prod_store` | `store_id` | `sql/002_add_indexes.sql` |
| `dim_product` | INDEX | `idx_dim_product_pm_status` | `product_management_status` | `sql/010_product_management_status.sql` |
| `dim_product` | PRIMARY KEY | `PRIMARY` | `product_key` | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product` | UNIQUE | `uq_dim_product` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `dim_product_cost_config` | INDEX | `idx_dpcc_date` | `effective_date` | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | INDEX | `idx_dpcc_item_id` | `item_id` | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | INDEX | `idx_dpcc_store` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | PRIMARY KEY | `PRIMARY` | `id` | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_cost_config` | UNIQUE | `uq_dim_product_cost` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_gpt_link` | INDEX | `idx_gpt_link_lookup` | `platform`, `item_id`, `link_type`, `effective_from` | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_gpt_link` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_产品GPT链接.sql` |
| `dim_product_identity` | INDEX | `idx_dpi_item_id` | `item_id` | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | INDEX | `idx_dpi_msku` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | INDEX | `idx_dpi_store` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | PRIMARY KEY | `PRIMARY` | `id` | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_identity` | UNIQUE | `uq_dim_product_identity` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | INDEX | `idx_dpo_item_id` | `item_id` | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | INDEX | `idx_dpo_owner` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | INDEX | `idx_dpo_store` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | PRIMARY KEY | `PRIMARY` | `id` | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_owner` | UNIQUE | `uq_dim_product_owner` | 待确认 | `sql/003_product_identity_owner_cost_tables.sql` |
| `dim_product_wfs_fee_auto` | PRIMARY KEY | `PRIMARY` | `id` | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | PRIMARY KEY | `PRIMARY` | `id` | `sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | UNIQUE | `uk_msku` | `platform`, `msku` | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `dim_product_wfs_fee_auto` | UNIQUE | `uk_msku` | `platform`, `msku` | `sql/DDL_WFS费用自动化.sql` |
| `dim_sem_campaign_item` | INDEX | `idx_sem_camp_item` | `item_id` | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_sem_campaign_item` | UNIQUE | `uq_sem_camp_item` | `platform`, `store_id`, `campaign_id` | `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` |
| `dim_store` | INDEX | `idx_dim_store_plat` | `platform` | `sql/002_add_indexes.sql` |
| `dim_store` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store` | UNIQUE | `uq_dim_store` | `platform`, `store_id` | `sql/001_create_data_warehouse_tables.sql` |
| `dim_store_config` | INDEX | `idx_active` | `is_active` | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | PRIMARY KEY | `PRIMARY` | `id` | `sql/009_create_dim_store_config.sql` |
| `dim_store_config` | UNIQUE | `uq_dim_store_config` | `platform`, `store_id` | `sql/009_create_dim_store_config.sql` |
| `event_archived_restock_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/039_event_archived_restock_alert.sql` |
| `event_archived_restock_alert` | UNIQUE | `uq_ar_item` | `platform`, `store_id`, `item_id` | `sql/039_event_archived_restock_alert.sql` |
| `event_arrival_notify` | INDEX | `idx_arrival_pending` | `notify_status`, `event_date` | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | INDEX | `idx_arrival_shipment` | `shipment_id` | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | PRIMARY KEY | `PRIMARY` | `id` | `sql/010_wfs_shipment_tables.sql` |
| `event_arrival_notify` | UNIQUE | `uq_arrival_event` | `event_type`, `biz_key` | `sql/010_wfs_shipment_tables.sql` |
| `event_attendance_lack_alert` | INDEX | `idx_date` | `stat_date` | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | INDEX | `idx_status` | `ack_status` | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/034_event_attendance_lack_alert.sql` |
| `event_attendance_lack_alert` | UNIQUE | `uq_day_user` | `stat_date`, `open_id` | `sql/034_event_attendance_lack_alert.sql` |
| `event_clearance_approval` | INDEX | `idx_item` | `platform`, `store_id`, `item_id` | `sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | INDEX | `idx_item` | `platform`, `store_id`, `item_id` | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | INDEX | `idx_status` | `status` | `sql/015_event_clearance_approval.sql` |
| `event_clearance_approval` | INDEX | `idx_status` | `status` | `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` |
| `event_clearance_card` | INDEX | `idx_item` | `card_type`, `store_id`, `item_id`, `created_at` | `sql/019_event_clearance_card.sql` |
| `event_clearance_card` | UNIQUE | `uq_type_key` | `card_type`, `biz_key` | `sql/019_event_clearance_card.sql` |
| `event_finance_sentinel_alert` | INDEX | `idx_sentinel_eq` | `equation`, `period_month` | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | INDEX | `idx_sentinel_hit` | `threshold_hit`, `check_time` | `sql/041_ai_finance_tables.sql` |
| `event_finance_sentinel_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `event_gpt_ads_missing_alert` | INDEX | `idx_ads_item` | `item_id` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | INDEX | `idx_ads_owner` | `owner_name` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | INDEX | `idx_ads_status` | `status` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_ads_missing_alert` | UNIQUE | `uq_ads_cycle` | 待确认 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | INDEX | `idx_kw_item` | `item_id` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | INDEX | `idx_kw_owner` | `owner_name` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | INDEX | `idx_kw_status` | `status` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_gpt_kw_missing_alert` | UNIQUE | `uq_kw_cycle` | 待确认 | `sql/028_event_gpt_link_missing_alert.sql` |
| `event_monthly_plan_unfilled` | INDEX | `idx_mpu_month` | `plan_month` | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | INDEX | `idx_mpu_owner` | `owner_name`, `deduction_date` | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | PRIMARY KEY | `PRIMARY` | `id` | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_monthly_plan_unfilled` | UNIQUE | `uq_mpu_daily` | `deduction_date`, `platform`, `owner_name` | `sql/029_event_monthly_plan_unfilled.sql` |
| `event_ops_action_log` | INDEX | `idx_ops_date` | `event_date` | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | INDEX | `idx_ops_msku_date` | 待确认 | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | INDEX | `idx_ops_store_item_date` | `store_id`, `item_id`, `event_date` | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | INDEX | `idx_ops_verify` | `event_date`, `verify_status` | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | PRIMARY KEY | `PRIMARY` | `id` | `sql/084_event_ops_action_log.sql` |
| `event_ops_action_log` | UNIQUE | `uq_ops_action` | 待确认 | `sql/084_event_ops_action_log.sql` |
| `event_ops_inaction_alert` | INDEX | `idx_item` | `platform`, `store_id`, `item_id` | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | INDEX | `idx_open` | `platform`, `resolved_at` | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_ops_inaction_alert` | UNIQUE | `uk_alert` | `platform`, `store_id`, `item_id`, `alert_date` | `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` |
| `event_owner_claim_alert` | INDEX | `idx_oca_claimed` | `claimed_by` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | INDEX | `idx_oca_item` | `item_id` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | INDEX | `idx_oca_status` | `status` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_owner_claim_alert` | UNIQUE | `uq_claim_cycle` | 待确认 | `交付件/DDL_绩效状态机_待认领扣分.sql` |
| `event_sem_naming_alert` | INDEX | `idx_sem_naming_owner` | `owner_name` | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | INDEX | `idx_sem_naming_status` | `status`, `ack_status` | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_alert` | UNIQUE | `uq_sem_naming` | `platform`, `store_id`, `campaign_id` | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | PRIMARY KEY | `PRIMARY` | `id` | `sql/046_sem_naming_alert.sql` |
| `event_sem_naming_deduction` | UNIQUE | `uq_sem_ded` | `ded_date`, `owner_name` | `sql/046_sem_naming_alert.sql` |
| `event_sentinel_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/040_event_sentinel_alert.sql` |
| `event_sentinel_alert` | UNIQUE | `uq_sentinel` | `check_key`, `target_date` | `sql/040_event_sentinel_alert.sql` |
| `event_shipping_freight_alert` | INDEX | `idx_freight_alert_owner` | `owner_name`, `status` | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | INDEX | `idx_freight_alert_status` | `status`, `is_legacy` | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_shipping_freight_alert` | UNIQUE | `uq_freight_alert` | `platform`, `shipping_code` | `sql/057_shipping_currency_and_freight_alert.sql` |
| `event_wfs_fee_case` | INDEX | `idx_status_created` | `status`, `created_at` | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | PRIMARY KEY | `PRIMARY` | `id` | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_case` | UNIQUE | `uq_wfs_case` | `platform`, `store_id`, `msku` | `sql/042_event_wfs_fee_case.sql` |
| `event_wfs_fee_missing_alert` | INDEX | `idx_wfs_item` | `item_id` | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | INDEX | `idx_wfs_owner` | `owner_name` | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | INDEX | `idx_wfs_status` | `status` | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | PRIMARY KEY | `PRIMARY` | `id` | `sql/027_event_wfs_fee_missing_alert.sql` |
| `event_wfs_fee_missing_alert` | UNIQUE | `uq_wfs_cycle` | 待确认 | `sql/027_event_wfs_fee_missing_alert.sql` |
| `fact_ad_credit_detail` | INDEX | `idx_credit_category` | `fee_category` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | INDEX | `idx_credit_posted` | `store_id`, `posted_date` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | PRIMARY KEY | `PRIMARY` | `id` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ad_credit_detail` | UNIQUE | `uq_credit_detail` | `platform`, `store_id`, `source_ref` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_ads_campaign_snapshot_daily` | INDEX | `idx_camp_snap_date` | `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | INDEX | `idx_camp_snap_store_date` | `store_id`, `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_campaign_snapshot_daily` | UNIQUE | `uq_camp_snap` | `platform`, `store_id`, `campaign_id`, `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | INDEX | `idx_group_snap_camp` | `store_id`, `campaign_id`, `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | INDEX | `idx_group_snap_date` | `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_group_snapshot_daily` | UNIQUE | `uq_group_snap` | `platform`, `store_id`, `ad_group_id`, `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_daily` | INDEX | `idx_fakd_date` | `stat_date` | `sql/002_add_indexes.sql` |
| `fact_ads_keyword_daily` | INDEX | `idx_fakd_item` | `item_id` | `sql/002_add_indexes.sql` |
| `fact_ads_keyword_daily` | INDEX | `idx_fakd_platform` | `platform` | `sql/002_add_indexes.sql` |
| `fact_ads_keyword_daily` | INDEX | `idx_fakd_source_type` | `source_type` | `sql/002_add_indexes.sql` |
| `fact_ads_keyword_daily` | INDEX | `idx_fakd_store` | `store_id` | `sql/002_add_indexes.sql` |
| `fact_ads_keyword_daily` | INDEX | `idx_fakd_store_date` | `store_id`, `stat_date` | `sql/002_add_indexes.sql` |
| `fact_ads_keyword_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_daily` | UNIQUE | `uq_fact_ads_kw` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_keyword_snapshot_daily` | INDEX | `idx_kw_snap_date` | `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | INDEX | `idx_kw_snap_group` | `store_id`, `ad_group_id`, `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_keyword_snapshot_daily` | UNIQUE | `uq_kw_snap` | `platform`, `store_id`, `keyword_id`, `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_platform_daily` | INDEX | `idx_ad_platform` | `ad_platform`, `stat_date` | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | INDEX | `idx_campaign` | `campaign_id`, `stat_date` | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | INDEX | `idx_stat_date` | `stat_date` | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | INDEX | `idx_store_date` | `store_id`, `stat_date` | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_platform_daily` | UNIQUE | `uq_ads_platform` | `stat_date`, `platform`, `store_id`, `advertiser_id`, `campaign_id`, `ad_group_id`, `ad_platform` | `sql/009_ads_platform_pagetype_tables.sql` |
| `fact_ads_product_daily` | INDEX | `idx_fapd_advertiser` | `advertiser_id` | `sql/006_lingxing_daily_required_indexes.sql` |
| `fact_ads_product_daily` | INDEX | `idx_fapd_date` | `stat_date` | `sql/002_add_indexes.sql` |
| `fact_ads_product_daily` | INDEX | `idx_fapd_item` | `item_id` | `sql/002_add_indexes.sql` |
| `fact_ads_product_daily` | INDEX | `idx_fapd_platform` | `platform` | `sql/002_add_indexes.sql` |
| `fact_ads_product_daily` | INDEX | `idx_fapd_raw_id` | `source_raw_id` | `sql/006_lingxing_daily_required_indexes.sql` |
| `fact_ads_product_daily` | INDEX | `idx_fapd_store` | `store_id` | `sql/002_add_indexes.sql` |
| `fact_ads_product_daily` | INDEX | `idx_fapd_store_date` | `store_id`, `stat_date` | `sql/002_add_indexes.sql` |
| `fact_ads_product_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_product_daily` | UNIQUE | `uq_fact_ads_product` | `stat_date`, `platform`, `advertiser_id`, `campaign_id`, `ad_group_id`, `item_id` | `sql/001_create_data_warehouse_tables.sql` |
| `fact_ads_snapshot_status` | INDEX | `idx_snap_status_date` | `snapshot_date`, `is_complete` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | PRIMARY KEY | `PRIMARY` | `id` | `sql/083_ads_config_snapshot.sql` |
| `fact_ads_snapshot_status` | UNIQUE | `uq_snap_status` | `platform`, `store_id`, `entity_type`, `campaign_type`, `snapshot_date` | `sql/083_ads_config_snapshot.sql` |
| `fact_attendance_daily` | INDEX | `idx_month` | `stat_date` | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | INDEX | `idx_name` | `name` | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/031_attendance_tables.sql` |
| `fact_attendance_daily` | UNIQUE | `uq_day_user` | `stat_date`, `open_id` | `sql/031_attendance_tables.sql` |
| `fact_channel_clearance_sales_daily` | INDEX | `idx_fccs_date` | `stat_date` | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | INDEX | `idx_fccs_date` | `stat_date` | `交付件/DDL_清货已清渠道销量事实表_v2按ASIN.sql` |
| `fact_channel_clearance_sales_daily` | INDEX | `idx_fccs_platform_ref` | 待确认 | `交付件/DDL_清货已清渠道销量事实表_v2按ASIN.sql` |
| `fact_channel_clearance_sales_daily` | INDEX | `idx_fccs_platform_sku` | 待确认 | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_清货已清渠道销量事实表_v2按ASIN.sql` |
| `fact_channel_clearance_sales_daily` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | UNIQUE | `uq_fccs` | 待确认 | `交付件/DDL_清货已清渠道销量事实表.sql` |
| `fact_channel_clearance_sales_daily` | UNIQUE | `uq_fccs` | 待确认 | `交付件/DDL_清货已清渠道销量事实表_v2按ASIN.sql` |
| `fact_commission_saving` | INDEX | `idx_comm_saving_item` | `item_id` | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | INDEX | `idx_comm_saving_program` | `incentive_program` | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | INDEX | `idx_comm_saving_store` | `store_id`, `period_start` | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | PRIMARY KEY | `PRIMARY` | `id` | `sql/045_ai_finance_commission_saving.sql` |
| `fact_commission_saving` | UNIQUE | `uq_comm_saving` | 待确认 | `sql/045_ai_finance_commission_saving.sql` |
| `fact_inbound_freight_alloc` | INDEX | `idx_freight_month` | `store_id`, `settlement_month` | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `fact_inbound_freight_alloc` | UNIQUE | `uq_freight_alloc` | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_inventory_daily` | INDEX | `idx_fid_date` | `snapshot_date` | `sql/002_add_indexes.sql` |
| `fact_inventory_daily` | INDEX | `idx_fid_item` | `item_id` | `sql/002_add_indexes.sql` |
| `fact_inventory_daily` | INDEX | `idx_fid_raw_id` | `source_raw_id` | `sql/006_lingxing_daily_required_indexes.sql` |
| `fact_inventory_daily` | INDEX | `idx_fid_store` | `store_id` | `sql/002_add_indexes.sql` |
| `fact_inventory_daily` | INDEX | `idx_fid_store_date` | `store_id`, `snapshot_date` | `sql/002_add_indexes.sql` |
| `fact_inventory_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `fact_inventory_daily` | UNIQUE | `uq_fact_inventory` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_item_landed_cost` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `fact_item_landed_cost` | UNIQUE | `uq_landed_cost` | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_lingxing_batch` | INDEX | `idx_lx_batch_balance` | `balance_num` | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | INDEX | `idx_lx_batch_sku` | 待确认 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | PRIMARY KEY | `PRIMARY` | `id` | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_batch` | UNIQUE | `uq_lx_batch` | 待确认 | `sql/061_lingxing_batch.sql` |
| `fact_lingxing_fx_rate` | INDEX | `idx_lx_fx_code` | `currency_code`, `rate_month` | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | PRIMARY KEY | `PRIMARY` | `id` | `sql/058_lingxing_fx_rate.sql` |
| `fact_lingxing_fx_rate` | UNIQUE | `uq_lx_fx` | `rate_month`, `currency_code` | `sql/058_lingxing_fx_rate.sql` |
| `fact_local_inventory_daily` | INDEX | `idx_sku` | `sku` | `sql/021_local_inventory.sql` |
| `fact_local_inventory_daily` | UNIQUE | `uq_date_sku` | `snapshot_date`, `sku` | `sql/021_local_inventory.sql` |
| `fact_mp_sales_channel_daily` | INDEX | `idx_fmc_date` | `stat_date` | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | INDEX | `idx_fmc_item` | `item_id` | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | INDEX | `idx_fmc_store_date` | `store_id`, `stat_date` | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | PRIMARY KEY | `PRIMARY` | `id` | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_mp_sales_channel_daily` | UNIQUE | `uq_fact_mp_channel` | 待确认 | `交付件/DDL_WFS销量渠道事实表.sql` |
| `fact_onsite_ads_invoice_head` | INDEX | `idx_foai_head_period` | `store_id`, `period_start` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | PRIMARY KEY | `PRIMARY` | `id` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_head` | UNIQUE | `uq_foai_head` | `store_id`, `invoice_number` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | INDEX | `idx_foai_line_period` | `store_id`, `period_start` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | PRIMARY KEY | `PRIMARY` | `id` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_onsite_ads_invoice_line` | UNIQUE | `uq_foai_line` | `store_id`, `invoice_number`, `campaign_ref_id` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `fact_profit_daily` | INDEX | `idx_fpd_date` | `stat_date` | `sql/002_add_indexes.sql` |
| `fact_profit_daily` | INDEX | `idx_fpd_item` | `item_id` | `sql/002_add_indexes.sql` |
| `fact_profit_daily` | INDEX | `idx_fpd_store` | `store_id` | `sql/002_add_indexes.sql` |
| `fact_profit_daily` | INDEX | `idx_fpd_store_date` | `store_id`, `stat_date` | `sql/002_add_indexes.sql` |
| `fact_profit_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `fact_profit_daily` | UNIQUE | `uq_fact_profit` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_promo_discount_daily` | INDEX | `idx_promo_date` | `discount_date` | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | INDEX | `idx_promo_store_item` | `store_id`, `item_id` | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/048_promo_discount_storage_daily.sql` |
| `fact_promo_discount_daily` | UNIQUE | `uq_promo` | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_purchase_cash` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash` | UNIQUE | `uq_pcash_order` | `order_sn` | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_cash_item` | UNIQUE | `uq_pcash_item` | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_purchase_daily` | INDEX | `idx_fpud_date` | `purchase_date` | `sql/002_add_indexes.sql` |
| `fact_purchase_daily` | INDEX | `idx_fpud_item` | `item_id` | `sql/002_add_indexes.sql` |
| `fact_purchase_daily` | INDEX | `idx_fpud_store` | `store_id` | `sql/002_add_indexes.sql` |
| `fact_purchase_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_daily` | UNIQUE | `uq_fact_purchase` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_purchase_order` | INDEX | `idx_status` | `status_text` | `sql/020_purchase_order.sql` |
| `fact_purchase_order` | UNIQUE | `uq_order` | `order_sn` | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | INDEX | `idx_sku` | `sku` | `sql/020_purchase_order.sql` |
| `fact_purchase_order_item` | UNIQUE | `uq_order_sku` | `order_sn`, `sku`, `msku` | `sql/020_purchase_order.sql` |
| `fact_reconciliation_item` | INDEX | `idx_recon_item_item` | `store_id`, `item_id` | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | PRIMARY KEY | `PRIMARY` | `id` | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_item` | UNIQUE | `uq_recon_item` | `platform`, `store_id`, `period_start`, `period_end`, `item_id`, `fee_category` | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | INDEX | `idx_recon_period_status` | `period_status` | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | PRIMARY KEY | `PRIMARY` | `id` | `sql/042_ai_finance_reconciliation.sql` |
| `fact_reconciliation_period` | UNIQUE | `uq_recon_period` | `platform`, `store_id`, `period_start`, `period_end` | `sql/042_ai_finance_reconciliation.sql` |
| `fact_refund_daily` | INDEX | `idx_refund_date` | `refund_date` | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/047_walmart_refund_tables.sql` |
| `fact_refund_daily` | UNIQUE | `uq_refund` | `platform`, `store_id`, `msku`, `refund_date` | `sql/047_walmart_refund_tables.sql` |
| `fact_sales_daily` | INDEX | `idx_fsd_date` | `stat_date` | `sql/002_add_indexes.sql` |
| `fact_sales_daily` | INDEX | `idx_fsd_item` | `item_id` | `sql/002_add_indexes.sql` |
| `fact_sales_daily` | INDEX | `idx_fsd_platform` | `platform` | `sql/002_add_indexes.sql` |
| `fact_sales_daily` | INDEX | `idx_fsd_raw_id` | `source_raw_id` | `sql/006_lingxing_daily_required_indexes.sql` |
| `fact_sales_daily` | INDEX | `idx_fsd_store` | `store_id` | `sql/002_add_indexes.sql` |
| `fact_sales_daily` | INDEX | `idx_fsd_store_date` | `store_id`, `stat_date` | `sql/002_add_indexes.sql` |
| `fact_sales_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_daily` | UNIQUE | `uq_fact_sales` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `fact_sales_fast_daily` | INDEX | `idx_fast_date` | `stat_date` | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | INDEX | `idx_fast_store_item` | `store_id`, `item_id` | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_fast_daily` | UNIQUE | `uq_fast_sales` | 待确认 | `sql/082_order_item_and_fast_sales.sql` |
| `fact_sales_orders_early` | INDEX | `idx_orders_early_item` | `platform`, `store_id`, `item_id` | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | PRIMARY KEY | `PRIMARY` | `id` | `sql/012_order_drop_tables.sql` |
| `fact_sales_orders_early` | UNIQUE | `uq_orders_early` | `stat_date`, `platform`, `store_id`, `item_id`, `pull_slot` | `sql/012_order_drop_tables.sql` |
| `fact_sem_billing_daily` | INDEX | `idx_sem_billing_from` | `store_id`, `billing_from` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | INDEX | `idx_sem_billing_item` | `item_id` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | INDEX | `idx_sem_billing_type` | `charge_type` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_sem_billing_daily` | UNIQUE | `uq_sem_billing` | `store_id`, `invoice_id`, `campaign_id`, `charge_type` | `sql/044_ai_finance_sem_and_credits.sql` |
| `fact_settlement_msku_monthly` | INDEX | `idx_settle_item` | `store_id`, `item_id`, `settlement_month` | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `fact_settlement_msku_monthly` | UNIQUE | `uq_settle_month` | 待确认 | `sql/041_ai_finance_tables.sql` |
| `fact_shipping_first_let` | INDEX | `idx_first_let_cargo` | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | INDEX | `idx_first_let_store_sku` | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | PRIMARY KEY | `PRIMARY` | `id` | `sql/056_shipping_first_let.sql` |
| `fact_shipping_first_let` | UNIQUE | `uq_first_let` | 待确认 | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | INDEX | `idx_shipping_actual` | `actual_delivery_time` | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | PRIMARY KEY | `PRIMARY` | `id` | `sql/056_shipping_first_let.sql` |
| `fact_shipping_order` | UNIQUE | `uq_shipping_order` | `platform`, `shipping_code` | `sql/056_shipping_first_let.sql` |
| `fact_storage_fee_daily` | INDEX | `idx_storage_daily_date` | `fee_date` | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | INDEX | `idx_storage_daily_item` | `store_id`, `item_id` | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | PRIMARY KEY | `PRIMARY` | `id` | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_fee_daily` | UNIQUE | `uq_storage_daily` | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `fact_storage_weekly_charge` | INDEX | `idx_swc_period` | `period_start` | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | PRIMARY KEY | `PRIMARY` | `id` | `sql/074_storage_weekly_charge.sql` |
| `fact_storage_weekly_charge` | UNIQUE | `uq_swc` | `platform`, `store_id`, `period_start`, `period_end` | `sql/074_storage_weekly_charge.sql` |
| `fact_wfs_shipment` | INDEX | `idx_wfs_shipment_closed` | `to_closed_time` | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | INDEX | `idx_wfs_shipment_status` | `status` | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | PRIMARY KEY | `PRIMARY` | `id` | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment` | UNIQUE | `uq_wfs_shipment` | `platform`, `store_id`, `shipment_id` | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | INDEX | `idx_wfs_item_msku` | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | PRIMARY KEY | `PRIMARY` | `id` | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_shipment_item` | UNIQUE | `uq_wfs_shipment_item` | 待确认 | `sql/010_wfs_shipment_tables.sql` |
| `fact_wfs_storage_fee` | INDEX | `idx_storage_fee_item` | `store_id`, `item_id` | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `fact_wfs_storage_fee` | UNIQUE | `uq_storage_fee` | 待确认 | `sql/041_ai_finance_tables.sql` |
| `raw_feishu_attendance` | INDEX | `idx_api_date` | `api_type`, `date_from` | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | PRIMARY KEY | `PRIMARY` | `id` | `sql/031_attendance_tables.sql` |
| `raw_feishu_attendance` | UNIQUE | `uq_hash` | `raw_hash` | `sql/031_attendance_tables.sql` |
| `raw_feishu_table` | INDEX | `idx_feishu_sheet` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_feishu_table` | INDEX | `idx_raw_fei_date` | `data_date` | `sql/002_add_indexes.sql` |
| `raw_feishu_table` | INDEX | `idx_raw_fei_pulled` | `pulled_at` | `sql/002_add_indexes.sql` |
| `raw_feishu_table` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | INDEX | `idx_upload_type_time` | `upload_type`, `uploaded_at` | `sql/001_create_data_warehouse_tables.sql` |
| `raw_frontend_upload` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | INDEX | `idx_raw_ling_date` | `data_date` | `sql/002_add_indexes.sql` |
| `raw_lingxing_api` | INDEX | `idx_raw_ling_path` | 待确认 | `sql/002_add_indexes.sql` |
| `raw_lingxing_api` | INDEX | `idx_raw_ling_success` | `is_success`, `data_date` | `sql/002_add_indexes.sql` |
| `raw_lingxing_api` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_api` | UNIQUE | `uq_raw_lingxing` | 待确认 | `sql/001_create_data_warehouse_tables.sql` |
| `raw_lingxing_settlement_order` | INDEX | `idx_msku` | `msku_query`, `capture_batch` | `sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | INDEX | `idx_msku` | `msku_query`, `capture_batch` | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | PRIMARY KEY | `PRIMARY` | `id` | `sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | PRIMARY KEY | `PRIMARY` | `id` | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | UNIQUE | `uk_row` | `unique_id`, `row_index` | `sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_settlement_order` | UNIQUE | `uk_row` | `unique_id`, `row_index` | `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` |
| `raw_lingxing_walmart_listing` | INDEX | `idx_item` | `item_id` | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | PRIMARY KEY | `PRIMARY` | `id` | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_lingxing_walmart_listing` | UNIQUE | `uk_capture` | `capture_date`, `store_id`, `item_id`, `msku` | `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` |
| `raw_mp_order_discount` | INDEX | `idx_discount_pdate` | `purchase_date` | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | INDEX | `idx_discount_store_msku` | 待确认 | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | PRIMARY KEY | `PRIMARY` | `id` | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_discount` | UNIQUE | `uq_discount_item` | `platform_order_no`, `order_item_no` | `sql/048_promo_discount_storage_daily.sql` |
| `raw_mp_order_item` | INDEX | `idx_oi_pdate` | `purchase_date` | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | INDEX | `idx_oi_store_date` | `store_id`, `purchase_date` | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | INDEX | `idx_oi_store_msku` | 待确认 | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | PRIMARY KEY | `PRIMARY` | `id` | `sql/082_order_item_and_fast_sales.sql` |
| `raw_mp_order_item` | UNIQUE | `uq_order_item` | `platform_order_no`, `order_item_no` | `sql/082_order_item_and_fast_sales.sql` |
| `raw_sync_tasks` | INDEX | `idx_rst_sheet` | `source_type`, `sheet_id`, `started_at` | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | INDEX | `idx_rst_task_id` | `sync_task_id` | `sql/005_raw_sync_tasks.sql` |
| `raw_sync_tasks` | PRIMARY KEY | `PRIMARY` | `id` | `sql/005_raw_sync_tasks.sql` |
| `raw_walmart_ads_csv` | INDEX | `idx_raw_wads_date` | `report_date` | `sql/002_add_indexes.sql` |
| `raw_walmart_ads_csv` | INDEX | `idx_raw_wads_upload` | `upload_id` | `sql/002_add_indexes.sql` |
| `raw_walmart_ads_csv` | INDEX | `idx_wads_store_date` | `store_id`, `report_date` | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_ads_csv` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `raw_walmart_connect_invoice` | INDEX | `idx_rwci_inv` | `invoice_number` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | INDEX | `idx_rwci_store` | `store_id` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | PRIMARY KEY | `PRIMARY` | `id` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_connect_invoice` | UNIQUE | `uq_rwci` | `task_id`, `row_index` | `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` |
| `raw_walmart_inbound_csv` | INDEX | `idx_inbound_raw_store` | `store_id`, `report_end` | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | PRIMARY KEY | `PRIMARY` | `id` | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_inbound_csv` | UNIQUE | `uq_inbound_raw` | `task_id`, `row_no` | `sql/053_inbound_freight_import.sql` |
| `raw_walmart_reconciliation_csv` | INDEX | `idx_recon_raw_store` | `store_id`, `period_end` | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | PRIMARY KEY | `PRIMARY` | `id` | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_reconciliation_csv` | UNIQUE | `uq_recon_raw` | `task_id`, `row_no` | `sql/042_ai_finance_reconciliation.sql` |
| `raw_walmart_return_order` | INDEX | `idx_return_date` | `return_order_date` | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | INDEX | `idx_store_msku` | `store_id`, `msku` | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | PRIMARY KEY | `PRIMARY` | `id` | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_return_order` | UNIQUE | `uq_return_item` | `return_order_id`, `msku` | `sql/047_walmart_refund_tables.sql` |
| `raw_walmart_sem_csv` | INDEX | `idx_sem_raw_store_date` | `store_id`, `report_date` | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | INDEX | `idx_sem_raw_type` | `csv_type` | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | PRIMARY KEY | `PRIMARY` | `id` | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_sem_csv` | UNIQUE | `uq_sem_raw` | `task_id`, `row_index` | `sql/044_ai_finance_sem_and_credits.sql` |
| `raw_walmart_storage_csv` | INDEX | `idx_storage_raw_store` | `store_id`, `report_end` | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | PRIMARY KEY | `PRIMARY` | `id` | `sql/041_ai_finance_tables.sql` |
| `raw_walmart_storage_csv` | UNIQUE | `uq_storage_raw` | `task_id`, `row_no` | `sql/041_ai_finance_tables.sql` |
| `schema_change_log` | INDEX | `idx_schema_change_table` | `table_name`, `created_at` | `sql/001_create_data_warehouse_tables.sql` |
| `schema_change_log` | PRIMARY KEY | `PRIMARY` | `id` | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | INDEX | `idx_sync_task_name` | `task_name`, `started_at` | `sql/001_create_data_warehouse_tables.sql` |
| `sync_task_log` | PRIMARY KEY | `PRIMARY` | `task_id` | `sql/001_create_data_warehouse_tables.sql` |

## 显式与疑似关系

| 源表 | 源字段 | 目标表/关联域 | 目标字段 | 依据 | 来源 |
|---|---|---|---|---|---|
| `biz_event`, `fact_ads_group_snapshot_daily`, `fact_ads_keyword_daily`, `fact_ads_keyword_snapshot_daily`, `fact_ads_platform_daily`, `fact_ads_product_daily` | `ad_group_id` | 同名字段关联域 | `ad_group_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `dim_store`, `dim_store_config`, `fact_ads_campaign_snapshot_daily`, `fact_ads_group_snapshot_daily`, `fact_ads_keyword_daily`, `fact_ads_keyword_snapshot_daily` 等 | `advertiser_id` | 同名字段关联域 | `advertiser_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `biz_event`, `dim_sem_campaign_item`, `event_sem_naming_alert`, `fact_ad_credit_detail`, `fact_ads_campaign_snapshot_daily`, `fact_ads_group_snapshot_daily` 等 | `campaign_id` | 同名字段关联域 | `campaign_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `dim_owner`, `dim_product_owner` | `feishu_user_id` | 同名字段关联域 | `feishu_user_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `ai_analysis_result`, `ai_monthly_issue_item`, `ai_ops_log_review_item`, `biz_clearance_other_channel`, `biz_cs_test_alert`, `biz_event` 等 | `item_id` | 同名字段关联域 | `item_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `dim_keyword`, `fact_ads_keyword_snapshot_daily` | `keyword_id` | 同名字段关联域 | `keyword_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `ai_analysis_result`, `ai_monthly_issue_item`, `ai_ops_log_review_item`, `biz_cs_test_alert`, `biz_event`, `biz_monthly_plan` 等 | `msku` | 同名字段关联域 | `msku` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `event_attendance_lack_alert`, `fact_attendance_daily` | `open_id` | 同名字段关联域 | `open_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `dim_owner`, `dim_product_owner` | `owner_id` | 同名字段关联域 | `owner_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `biz_perf_cert`, `biz_perf_deduction_note` | `ref_deduction_id` | 同名字段关联域 | `ref_deduction_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `raw_feishu_table`, `raw_sync_tasks` | `sheet_id` | 同名字段关联域 | `sheet_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `event_arrival_notify`, `fact_inbound_freight_alloc`, `fact_wfs_shipment`, `fact_wfs_shipment_item` | `shipment_id` | 同名字段关联域 | `shipment_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `biz_clearance_other_channel`, `biz_finance_opening_cost`, `dim_product`, `dim_product_cost_config`, `dim_product_identity`, `event_clearance_approval` 等 | `sku` | 同名字段关联域 | `sku` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `dim_product_cost_config`, `dim_product_identity`, `dim_product_owner`, `fact_ads_keyword_daily`, `fact_ads_platform_daily`, `fact_ads_product_daily` 等 | `source_raw_id` | 同名字段关联域 | `source_raw_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `fact_ad_credit_detail`, `fact_ads_keyword_daily`, `fact_commission_saving`, `fact_onsite_ads_invoice_head`, `fact_onsite_ads_invoice_line`, `fact_reconciliation_item` 等 | `source_task_id` | 同名字段关联域 | `source_task_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `ai_analysis_result`, `ai_monthly_issue_item`, `ai_ops_log_review_item`, `biz_clearance_other_channel`, `biz_cs_test_alert`, `biz_event` 等 | `store_id` | 同名字段关联域 | `store_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `raw_walmart_ads_csv`, `raw_walmart_connect_invoice`, `raw_walmart_inbound_csv`, `raw_walmart_reconciliation_csv`, `raw_walmart_sem_csv`, `raw_walmart_storage_csv` 等 | `task_id` | 同名字段关联域 | `task_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |
| `biz_app_audit_log`, `dim_app_user_permission`, `dim_app_user_role`, `event_attendance_lack_alert`, `fact_attendance_daily` | `user_id` | 同名字段关联域 | `user_id` | 字段命名推测，待确认 | 安全 CREATE TABLE 字段集合 |

说明：除明确 FOREIGN KEY 外，其余关系均为字段命名推测，不应直接作为迁移约束。
