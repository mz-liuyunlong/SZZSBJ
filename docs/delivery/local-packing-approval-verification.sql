-- 占位名称说明：`LOCAL_DATABASE_NAME` 与 `ISOLATED_TEST_DATABASE_NAME` 分别表示负责人已批准的本地开发库和隔离测试库；执行前必须与获批本地配置中的实际数据库名逐字核对，并同时核对环境、host、port及连接后数据库身份。占位名称不是可直接执行的数据库名，也不授权其他本地库或生产库。历史数量、指纹及备份哈希保持原记录。
-- Navicat连接本地55432，数据库选择LOCAL_DATABASE_NAME。以下全部只读。
SELECT current_database() AS database_name, inet_server_port() AS server_port;
SELECT version_num FROM public.alembic_version;
SELECT 'ops_domestic_pk_sequences' AS table_name,count(*) AS row_count FROM public.ops_domestic_pk_sequences
UNION ALL SELECT 'ops_domestic_packing_orders',count(*) FROM public.ops_domestic_packing_orders
UNION ALL SELECT 'ops_domestic_packing_allocations',count(*) FROM public.ops_domestic_packing_allocations
UNION ALL SELECT 'evt_domestic_packing_events',count(*) FROM public.evt_domestic_packing_events;
SELECT id,pk,status,qty,is_test,source_account_ref,warehouse_id,inbound_order_sn,sku,store_id,item_id,actor_uid,note,created_at
FROM public.ops_domestic_packing_orders ORDER BY created_at DESC;
SELECT o.pk,o.status,a.qty AS allocated_qty,o.source_publication_id,o.source_board_id
FROM public.ops_domestic_packing_orders o LEFT JOIN public.ops_domestic_packing_allocations a ON a.order_id=o.id ORDER BY o.created_at DESC;
SELECT event_kind,actor_uid,order_version,occurred_at FROM public.evt_domestic_packing_events ORDER BY occurred_at DESC;
-- 当前有效版本应仍有1454行；旧发布保留，因此MART总行数会大于1454。
SELECT p.id,p.is_current,p.builder_version,count(b.id) AS board_rows
FROM public.gov_domestic_board_publications p LEFT JOIN public.mart_domestic_inbound_batch_board b ON b.publication_id=p.id
GROUP BY p.id,p.is_current,p.builder_version ORDER BY p.is_current DESC;
SELECT count(*) AS active_inbound_rows FROM public.mart_domestic_inbound_batch_board b
JOIN public.gov_domestic_board_publications p ON p.id=b.publication_id WHERE p.is_current;
SELECT permission_key FROM public.app_permissions WHERE permission_key IN
('action:pmc:domestic-warehouse-board:packing-approve','action:pmc:domestic-warehouse-board:packing-reject');
