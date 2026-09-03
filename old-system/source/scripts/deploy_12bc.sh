#!/bin/bash
exec > /tmp/deploy_12bc.log 2>&1
set +e
cd /opt/lingxing-auto
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }
imp(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" < "$1"; }
echo "批12b+12c部署(base64) $(date +%F_%T)"

echo "== 0 生产文件 md5（须与交付一致）=="
md5sum src/aiFinanceRoutes.ts admin-frontend/src/AiFinanceItemCashProfit.tsx src/syncSettlementMonthly.ts admin-frontend/src/AiFinanceTools.tsx sql/064_help_item_cash_profit_v2.sql sql/065_fix_settlement_store_id.sql sql/066_finance_import_grants.sql

echo "== 1 DB 连通自检（应输出 1）=="
q "SELECT 1 AS ok;"

echo "== 2 后端 tsc（本批文件 0 报错；存量缺模块告警无关）=="
npx tsc --noEmit -p tsconfig.json 2>&1 | grep -iE "aiFinanceRoutes|syncSettlement"; echo "backend tsc done"

echo "== 3 SQL 065 修复前 未匹配店铺 =="
q "SELECT store_id, MAX(store_name) nm, COUNT(*) c FROM fact_settlement_msku_monthly WHERE store_id NOT IN (SELECT store_id FROM dim_store WHERE platform='walmart') GROUP BY store_id;"
imp sql/065_fix_settlement_store_id.sql; echo "065 rc=$?"
echo "== 065 修复后（应只剩晶彩绝伦 …259264）=="
q "SELECT store_id, MAX(store_name) nm, COUNT(*) c FROM fact_settlement_msku_monthly WHERE store_id NOT IN (SELECT store_id FROM dim_store WHERE platform='walmart') GROUP BY store_id;"

imp sql/064_help_item_cash_profit_v2.sql; echo "064 rc=$?"
q "SELECT page_key, CHAR_LENGTH(content_md) len, updated_by FROM dim_page_help WHERE page_key='finance-item-cash-profit';"

echo "== 066 翁骏白名单：执行前 =="
q "SELECT id, is_superadmin FROM dim_app_user WHERE id=3;"
q "SELECT role_key FROM dim_app_user_role WHERE user_id=3;"
q "SELECT perm_key FROM dim_app_user_permission WHERE user_id=3;"
imp sql/066_finance_import_grants.sql; echo "066 rc=$?"
echo "== 066 执行后（翁骏 is_superadmin=0、无超管/财务、有 finance_import；财务仍陈玉/陈虹霓）=="
q "SELECT id, is_superadmin FROM dim_app_user WHERE id=3;"
q "SELECT role_key FROM dim_app_user_role WHERE user_id=3;"
q "SELECT perm_key FROM dim_app_user_permission WHERE user_id=3;"
q "SELECT u.id, u.display_name FROM dim_app_user_role r JOIN dim_app_user u ON u.id=r.user_id WHERE r.role_key='财务';"

echo "== 4 前端 build =="
( cd admin-frontend && npm run build 2>&1 | tail -6 )
echo "新 bundle:"; ls -t admin-frontend/dist/assets/index-*.js 2>/dev/null | head -1

echo "== 5 重启 + 端口就绪 =="
sudo systemctl restart lingxing-admin.service
for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:3001/ && break; sleep 1; done
systemctl is-active lingxing-admin.service

echo "== 6 冒烟（未登录 401 JSON 正常）=="
curl -s "http://127.0.0.1:3001/api/finance/item-cash-profit?from=2026-05&to=2026-07" | head -c 200; echo
curl -s "http://127.0.0.1:3001/api/finance/fx/lingxing?currency=USD" | head -c 200; echo
echo "DONE"
