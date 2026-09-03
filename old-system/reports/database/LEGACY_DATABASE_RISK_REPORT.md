# 旧系统数据库提取风险报告

未复制原始 SQL，未执行 SQL，未连接数据库；所有 DML 数据行均未写入 clean 产物。

## SQL 文件逐项结果

| SQL 文件 | DML/真实数据风险 | 疑似备份 | 安全结构候选 | 已提取结构 | 无法安全提取/备注 |
|---|---|---|---:|---:|---|
| `AI经营分析报告/正式系统/DDL_draft.sql` | 未发现 DML 关键字 | 否 | 3 | 3 | 无 |
| `AI经营分析报告/正式系统/交付件/DDL_单品目标与主管确认.sql` | 未发现 DML 关键字 | 否 | 4 | 4 | 无 |
| `AI经营分析报告/正式系统/交付件/event_ops_inaction_alert.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `_asin_kw_mirror/SQL_connect发票建表_20260819.sql` | 未发现 DML 关键字 | 否 | 4 | 4 | 无 |
| `_deploy_tmp/prod_snapshot_20260824/prod_copy/sql/015_event_clearance_approval.sql` | INSERT INTO | 是 | 1 | 1 | 无 |
| `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/DDL_WFS费用自动化.sql` | 未发现 DML 关键字 | 是 | 2 | 2 | 无 |
| `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/SQL_手动广告比率归一与全零清理.sql` | DELETE FROM, UPDATE | 是 | 2 | 0 | CREATE/ALTER AS SELECT 可能复制数据 |
| `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/alter_naming_lastcheck_20260819.sql` | 未发现 DML 关键字 | 是 | 1 | 1 | 无 |
| `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/alter_storage_unitfee_20260819.sql` | 未发现 DML 关键字 | 是 | 1 | 1 | 无 |
| `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/help_feedetail_20260818.sql` | INSERT INTO | 是 | 0 | 0 | 未发现可提取结构，待确认 |
| `_deploy_tmp/prod_snapshot_20260824/pull_only_prod/sql/help_storage_unitfee_20260819.sql` | UPDATE | 是 | 0 | 0 | 未发现可提取结构，待确认 |
| `_to_delete/039_roster_profile_extend.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `_to_delete/071_ai_analysis_result_uq_add_model_SUPERSEDED_20260814.sql` | 未发现 DML 关键字 | 否 | 3 | 3 | 无 |
| `sql/001_create_data_warehouse_tables.sql` | 未发现 DML 关键字 | 否 | 19 | 19 | 无 |
| `sql/002_add_indexes.sql` | 未发现 DML 关键字 | 否 | 12 | 12 | 无 |
| `sql/003_product_identity_owner_cost_tables.sql` | 未发现 DML 关键字 | 否 | 6 | 6 | 无 |
| `sql/004_add_cost_columns.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `sql/005_raw_sync_tasks.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/006_lingxing_daily_required_indexes.sql` | 未发现 DML 关键字 | 否 | 4 | 4 | 无 |
| `sql/007_cs_test_product_config.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/008_add_non_wfs_available_stock.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/009_ads_platform_pagetype_tables.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/009_create_dim_store_config.sql` | INSERT INTO | 否 | 1 | 1 | 无 |
| `sql/010_product_management_status.sql` | UPDATE | 否 | 1 | 1 | 无 |
| `sql/010_wfs_shipment_tables.sql` | 未发现 DML 关键字 | 否 | 3 | 3 | 无 |
| `sql/011_biz_product_rule_signal_daily.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/012_order_drop_tables.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/013_backfill_keyword_msku.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/014_backfill_auto_msku.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/015_event_clearance_approval.sql` | INSERT INTO | 否 | 1 | 1 | 无 |
| `sql/016_clearance_center.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/017_clearance_other_channel_v2.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/018_clearance_expect_date.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/019_event_clearance_card.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/020_purchase_order.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `sql/021_local_inventory.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/022_app_auth_tables.sql` | 未发现 DML 关键字 | 否 | 3 | 3 | 无 |
| `sql/023_app_user_role.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/024_seed_roles_bootstrap.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/025_dim_product_walmart_status.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/025_help_role_guide.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/026_help_center_ai人力合并_精准跳转_补齐版块.sql` | INSERT INTO, UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/027_event_wfs_fee_missing_alert.sql` | UPDATE | 否 | 1 | 1 | 无 |
| `sql/028_event_gpt_link_missing_alert.sql` | UPDATE | 否 | 2 | 2 | 无 |
| `sql/029_event_monthly_plan_unfilled.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/029_help_notify_template_rename.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/030_help_notify_template_card_img.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/031_attendance_tables.sql` | INSERT INTO | 否 | 2 | 2 | 无 |
| `sql/032_help_attendance.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/033_help_attendance_schedule.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/034_event_attendance_lack_alert.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/035_help_attendance_lack_alert.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/036_help_pmc_inventory.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/037_help_product_cost_columns.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/038_help_user_mgmt_rename.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/039_event_archived_restock_alert.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/040_event_sentinel_alert.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/041_ai_finance_tables.sql` | 未发现 DML 关键字 | 否 | 10 | 10 | 无 |
| `sql/041_ai_monthly_issue_item_unique.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/042_ai_finance_reconciliation.sql` | 未发现 DML 关键字 | 否 | 4 | 4 | 无 |
| `sql/042_event_wfs_fee_case.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/043_ai_finance_fix_recon_keys.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/043_help_pmc_wfs_fee.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/044_ai_finance_sem_and_credits.sql` | UPDATE | 否 | 3 | 3 | 无 |
| `sql/044_help_pmc_wfs_fee_v2.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/045_ai_finance_commission_saving.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/045_help_wfs_log_rules.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/046_help_wfs_sop_link.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/046_sem_naming_alert.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `sql/047_sem_naming_penalty_cols.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/047_walmart_refund_tables.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `sql/048_promo_discount_storage_daily.sql` | 未发现 DML 关键字 | 否 | 3 | 3 | 无 |
| `sql/049_help_finance_credits.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/050_fee_category_official_names.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/051_help_finance_tools.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/052_help_finance_tools_v2.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/053_inbound_freight_import.sql` | UPDATE | 否 | 1 | 1 | 无 |
| `sql/054_inbound_unmatched_reallocate.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/055_freight_alloc_uq_period.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/056_shipping_first_let.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `sql/057_shipping_currency_and_freight_alert.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/058_lingxing_fx_rate.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/059_help_fx_lingxing.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/060_purchase_cash_cols.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/061_lingxing_batch.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/062_finance_opening_cost.sql` | INSERT INTO | 否 | 1 | 1 | 无 |
| `sql/063_help_item_cash_profit.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/064_help_item_cash_profit_v2.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/065_fix_settlement_store_id.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/066_finance_import_grants.sql` | DELETE FROM, INSERT INTO, UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/067_help_sem.sql` | INSERT INTO, UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/068_help_finance_tools_v4.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/069_fix_help_finance_tools_dup.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/070_ai_analysis_result_hardening.rollback.sql` | 未发现 DML 关键字 | 否 | 4 | 4 | 无 |
| `sql/070_ai_analysis_result_hardening.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/071_ai_analysis_result_dedup_key.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `sql/072_help_order_profit_v2.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/073_help_ads_fee_report.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/073_help_order_profit_v2_v2.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/074_help_ads_fee_report_v2.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/074_storage_weekly_charge.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/075_help_ads_fee_split.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/076_help_ads_fee_report_v4.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/077_help_ads_fee_batchfix.sql` | INSERT INTO, UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/078_help_ads_fee_sem_recon_faq.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/079_help_ads_sem_data.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/080_help_ads_sbsv_data.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/081_help_ads_group_merge.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/082_order_item_and_fast_sales.sql` | UPDATE | 否 | 2 | 2 | 无 |
| `sql/083_ads_config_snapshot.sql` | 未发现 DML 关键字 | 是 | 4 | 4 | 无 |
| `sql/084_event_ops_action_log.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/085_ops_action_log_group_matchtype.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/DDL_WFS费用自动化.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `sql/SQL_手动广告比率归一与全零清理.sql` | DELETE FROM, UPDATE | 否 | 2 | 0 | CREATE/ALTER AS SELECT 可能复制数据 |
| `sql/alter_naming_lastcheck_20260819.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/alter_storage_unitfee_20260819.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `sql/help_feedetail_20260818.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `sql/help_storage_unitfee_20260819.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/DDL_AI人事_日志评级.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `交付件/DDL_CS测品预警台账.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/DDL_WFS销量渠道事实表.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/DDL_产品GPT链接.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/DDL_清货已清渠道销量事实表.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/DDL_清货已清渠道销量事实表_v2按ASIN.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/DDL_清货渠道目标列.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/DDL_绩效台账人工层_说明豁免.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/DDL_绩效状态机_待认领扣分.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |
| `交付件/SQL_CS预警切正式前清测试残留_20260724.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_TEMU台账9行改MSKU并加回_20260803.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_仓储费单件费率尺寸加列_20260819.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/SQL_命名台账加列_last_open_check_date_20260819.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/SQL_回填_多MSKU发布状态传播_20260730.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助中心_运营提醒规则与扣绩效_20260722.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助文章_AI人事_20260723.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助文章_API接口文档_20260728.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助新增_仓储费入库运输明细_20260818.sql` | INSERT INTO | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_AI人事两要素_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_AI人事周四周期_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_AI人事抽查口径_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_CS测品广告口径与排序_20260725.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_CS测品异常预警_20260725.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_CS测品预警规则放宽_20260729.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_GPT分析链接_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_TEMU自动录入台账_20260803.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_产品管理优化_20260725.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_产品管理利润等级GPT筛选_20260729.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_产品管理批量操作_20260728.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_仓储费分段日摊_20260819.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_仓储费单件费率尺寸_20260819.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_仓储费周期FAQ_20260819.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_会议分析授权与LLM切换生效_20260808.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_周报问题信号改仍存在_20260813.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_归档门槛与豁免_20260730.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_批量导入xlsx口径_20260724.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_新品待到货与KPI瓦片_20260805_v2.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_新品待到货与问题瓦片_20260805.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_月度规划批量导入_20260724.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_每日明细当日库存口径_20260811.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_清货中心渠道月份筛选_20260803.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_清货产品维度与批量导入_20260724.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_清货审批入口_20260725.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_目标管理8月新规_20260804.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_绩效台账_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_绩效台账改造_20260724.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助更新_豁免WFS口径_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助纠偏_二提即扣_20260722.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_帮助迁移_运营提醒规则入运营日志_20260722.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_建表_人工绩效凭证_20260731.sql` | 未发现 DML 关键字 | 否 | 1 | 1 | 无 |
| `交付件/SQL_授权林翔清货审批_20260725.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_摘无动作观察期标注_20260722.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_绩效台账升级_20260723.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_通报总览_0910行更新_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_通报总览同步_20260722.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_通报模板入帮助_20260723.sql` | INSERT INTO, UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/SQL_通报模板图片化_20260723.sql` | UPDATE | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/walmart_sem_delivery/backend/048_sem_campaign_item_map.sql` | UPDATE | 否 | 1 | 1 | 无 |
| `交付件/只读核对_归档8品UNPUBLISHED状态_20260730.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/只读统计_缺GPT关键词广告链接_20260731.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/只读诊断_CS测品预警扣分现状_20260729.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/只读诊断_TEMU清货销量为0_20260803.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/只读诊断_缺GPT链接剔除归档_20260803.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `交付件/只读诊断_缺WFS待认领扣分为何未产出_20260730.sql` | 未发现 DML 关键字 | 否 | 0 | 0 | 未发现可提取结构，待确认 |
| `月报系统/交付件/DDL_monthly.sql` | 未发现 DML 关键字 | 否 | 2 | 2 | 无 |

## 汇总

- SQL 清单文件数：183；成功读取：183；缺失/越界：0。
- 含 INSERT/REPLACE/UPDATE/DELETE/COPY/LOAD/LOCK 等 DML 风险的文件：100。这些文件未复制数据行。
- 存在结构候选但至少一段无法安全提取的文件：2。
- 未发现结构语句、仅查询/数据操作或需人工判定的 SQL 文件：102。
- schema-only 唯一结构语句数：161。
- 所有原始 SQL 均保持在原目录；clean source 不含 `.sql`。
- schema-only 仅作参考，不是可直接执行的迁移包；执行前必须人工排序、去重、检查破坏性 ALTER 与环境差异。
