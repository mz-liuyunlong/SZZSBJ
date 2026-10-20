-- Navicat: 连接「SZZSBJ 本地开发55432」，数据库下拉选择 szzsbj_dev，再执行。
-- 全部只读；不是在 postgres / szzsbj_test / 生产库执行。
SELECT current_database() AS database_name, inet_server_port() AS server_port;

SELECT 'dwd_purchase_plan' AS table_name, count(*) AS row_count FROM public.dwd_purchase_plan
UNION ALL SELECT 'dwd_purchase_order', count(*) FROM public.dwd_purchase_order
UNION ALL SELECT 'dwd_purchase_order_line_item', count(*) FROM public.dwd_purchase_order_line_item
UNION ALL SELECT 'dws_purchase_board', count(*) FROM public.dws_purchase_board
UNION ALL SELECT 'dws_purchase_sku_cycle', count(*) FROM public.dws_purchase_sku_cycle
UNION ALL SELECT 'dws_purchase_pending', count(*) FROM public.dws_purchase_pending
UNION ALL SELECT 'ods_lingxing_purchase_plans', count(*) FROM public.ods_lingxing_purchase_plans
UNION ALL SELECT 'ods_lingxing_purchase_orders', count(*) FROM public.ods_lingxing_purchase_orders
UNION ALL SELECT 'ods_lingxing_purchase_order_items', count(*) FROM public.ods_lingxing_purchase_order_items
UNION ALL SELECT 'ods_lingxing_receipt_orders', count(*) FROM public.ods_lingxing_receipt_orders
UNION ALL SELECT 'ods_lingxing_receipt_order_items', count(*) FROM public.ods_lingxing_receipt_order_items
UNION ALL SELECT 'dim_lingxing_stores', count(*) FROM public.dim_lingxing_stores
UNION ALL SELECT 'dim_walmart_listings', count(*) FROM public.dim_walmart_listings
UNION ALL SELECT 'dwd_lingxing_sku_identity_index', count(*) FROM public.dwd_lingxing_sku_identity_index
UNION ALL SELECT 'dwd_lingxing_sku_product_info_current', count(*) FROM public.dwd_lingxing_sku_product_info_current
UNION ALL SELECT 'products', count(*) FROM public.products
UNION ALL SELECT 'rule_purchase_thresholds', count(*) FROM public.rule_purchase_thresholds
UNION ALL SELECT 'manual_purchase_cycle_override', count(*) FROM public.manual_purchase_cycle_override
ORDER BY table_name;

-- 采购看板应为867行，周期652条，重算后待处理711条；DWS待处理不是待采购计划API条数。
-- 数据源时间与本地重算时间分开核对。
SELECT count(*) AS board_rows,
       count(DISTINCT owner_uid) AS board_owners,
       max(calculated_at) AS local_calculated_at
FROM public.dws_purchase_board;
SELECT max(source_observed_at) AS purchase_source_observed_at
FROM public.dwd_purchase_order;
SELECT stage_code, count(*) AS row_count
FROM public.dws_purchase_board GROUP BY stage_code ORDER BY stage_code;

-- 验证接口实际读取的明细；含业务数据，仅在本地查看。
SELECT order_sn AS purchase_order_sn, sku, store_id, owner_uid, owner_name,
       stage_code, quantity_allocated, quantity_received, overdue_days, calculated_at
FROM public.dws_purchase_board
ORDER BY order_date DESC NULLS LAST, order_sn LIMIT 50;

-- 原国内仓1454行和用户29人应保留。正常登录可能产生本地会话，不固定会话数量。
SELECT (SELECT count(*) FROM public.mart_domestic_inbound_batch_board) AS domestic_rows,
       (SELECT count(*) FROM public.app_users) AS users,
       (SELECT count(*) FROM public.gov_integration_sync_configs WHERE is_enabled OR schedule_enabled) AS enabled_sync_configs;
