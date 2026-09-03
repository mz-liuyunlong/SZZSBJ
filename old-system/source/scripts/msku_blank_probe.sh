#!/bin/bash
exec > /tmp/msku_blank_probe.log 2>&1
cd /opt/lingxing-auto
set -a; . ./.env; set +a
q(){ echo; echo "== $1 =="; MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$2"; }
echo "msku_blank_probe $(date +%F_%T)"
q "近7天(T-7~T-2) msku空串明细(哪个店/ItemID/日期/销量)" "SELECT stat_date, store_id, store_name, item_id, sku, msku, sales_qty, sales_amount FROM fact_sales_daily WHERE platform='walmart' AND msku='' AND stat_date BETWEEN DATE_SUB(CURDATE(),INTERVAL 7 DAY) AND DATE_SUB(CURDATE(),INTERVAL 2 DAY) ORDER BY stat_date, item_id;"
q "这些 ItemID 全时段是否有销量/最近出现" "SELECT item_id, MAX(store_name) nm, COUNT(*) rows_cnt, MIN(stat_date) min_d, MAX(stat_date) max_d FROM fact_sales_daily WHERE platform='walmart' AND msku='' GROUP BY item_id ORDER BY max_d DESC;"
q "这些 ItemID 在 dim_product 是否已存在(配对线索)" "SELECT DISTINCT s.item_id, s.store_id, CASE WHEN p.item_id IS NULL THEN '产品维表也没有' ELSE CONCAT('维表有:',COALESCE(p.msku,''),'/',COALESCE(p.sku,'')) END AS dim_state FROM (SELECT DISTINCT store_id, item_id FROM fact_sales_daily WHERE platform='walmart' AND msku='' AND stat_date BETWEEN DATE_SUB(CURDATE(),INTERVAL 7 DAY) AND DATE_SUB(CURDATE(),INTERVAL 2 DAY)) s LEFT JOIN dim_product p ON p.platform='walmart' AND p.store_id=s.store_id AND p.item_id=s.item_id;"
