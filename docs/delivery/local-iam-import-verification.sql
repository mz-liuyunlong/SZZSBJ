-- 占位名称说明：`LOCAL_DATABASE_NAME` 与 `ISOLATED_TEST_DATABASE_NAME` 分别表示负责人已批准的本地开发库和隔离测试库；执行前必须与获批本地配置中的实际数据库名逐字核对，并同时核对环境、host、port及连接后数据库身份。占位名称不是可直接执行的数据库名，也不授权其他本地库或生产库。历史数量、指纹及备份哈希保持原记录。
-- 在 Navicat 选择本地连接：127.0.0.1:55432 -> LOCAL_DATABASE_NAME。
-- 以下只有只读查询，不输出密码哈希或登录令牌。

-- 1. 确认查询环境：database_name 应为 LOCAL_DATABASE_NAME，server_port 应为 55432。
SELECT current_database() AS database_name,
       inet_server_addr() AS server_address,
       inet_server_port() AS server_port;

-- 2. 核对本次导入后的行数。matches_expected 应全部为 true。
WITH counts(table_name, actual_rows, expected_rows) AS (
    SELECT 'app_users', count(*), 29 FROM public.app_users
    UNION ALL
    SELECT 'app_roles', count(*), 6 FROM public.app_roles
    UNION ALL
    SELECT 'app_user_roles', count(*), 29 FROM public.app_user_roles
    UNION ALL
    SELECT 'app_permissions', count(*), 160 FROM public.app_permissions
    UNION ALL
    SELECT 'app_role_permissions', count(*), 112 FROM public.app_role_permissions
    UNION ALL
    SELECT 'app_role_data_scopes', count(*), 5 FROM public.app_role_data_scopes
    UNION ALL
    SELECT 'app_user_data_scopes', count(*), 0 FROM public.app_user_data_scopes
    UNION ALL
    SELECT 'ods_lingxing_domestic_warehouse_statements', count(*), 1296
    FROM public.ods_lingxing_domestic_warehouse_statements
    UNION ALL
    SELECT 'ods_lingxing_domestic_batches', count(*), 1541
    FROM public.ods_lingxing_domestic_batches
    UNION ALL
    SELECT 'gov_domestic_board_publications', count(*), 1
    FROM public.gov_domestic_board_publications
    UNION ALL
    SELECT 'mart_domestic_inbound_batch_board', count(*), 1454
    FROM public.mart_domestic_inbound_batch_board
)
SELECT table_name, actual_rows, expected_rows,
       actual_rows = expected_rows AS matches_expected
FROM counts ORDER BY table_name;

-- 3. 查看用户及角色；不查询或输出 password_hash。
-- 预期：29 行，28 个启用用户，1 个超级管理员。
SELECT u.id, u.username, u.display_name,
       u.is_active, u.is_super_admin,
       COALESCE(string_agg(r.name, ' / ' ORDER BY r.name), '') AS role_names
FROM public.app_users AS u
LEFT JOIN public.app_user_roles AS ur ON ur.user_id = u.id
LEFT JOIN public.app_roles AS r ON r.id = ur.role_id
GROUP BY u.id, u.username, u.display_name, u.is_active, u.is_super_admin
ORDER BY u.id;

-- 4. 用户状态汇总：total=29，active=28，super_admin=1。
SELECT count(*) AS total_users,
       count(*) FILTER (WHERE is_active = 1) AS active_users,
       count(*) FILTER (WHERE is_super_admin = 1) AS super_admin_users
FROM public.app_users;

-- 5. 当前发布版本及其批次条数：应返回1行、board_rows=1454。
SELECT p.id AS publication_id, p.source_account_ref,
       p.source_warehouse_id, p.is_current,
       p.coverage_start, p.coverage_end, p.source_observed_at,
       count(b.id) AS board_rows
FROM public.gov_domestic_board_publications AS p
LEFT JOIN public.mart_domestic_inbound_batch_board AS b ON b.publication_id = p.id
WHERE p.is_current = true AND p.status = 'published'
GROUP BY p.id, p.source_account_ref, p.source_warehouse_id, p.is_current,
         p.coverage_start, p.coverage_end, p.source_observed_at;

-- 注：production会话未迁移；app_sessions在用户登录后才新增，不应要求一直为0。
-- app_permissions本地160条，源快照159条：本地额外1个权限定义被保留。
-- 角色授权、用户授权及数据范围按源快照核对，没有因保留定义而额外授予权限。
