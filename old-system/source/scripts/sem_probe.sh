#!/bin/bash
exec > /tmp/sem_probe.log 2>&1
cd /opt/lingxing-auto
set -a; . ./.env; set +a
q(){ echo; echo "== $1 =="; MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" -e "$2"; }
echo "sem_probe $(date +%F_%T)  DB=${DB_NAME:-walmart_ai_data}"

q "S0 所有库" "SHOW DATABASES;"

q "S1 当前库含 sem/ad 的表 + 列名" "SELECT table_name, GROUP_CONCAT(column_name ORDER BY ordinal_position) cols FROM information_schema.columns WHERE table_schema=DATABASE() AND (table_name LIKE '%sem%' OR table_name LIKE '%ad%') GROUP BY table_name ORDER BY table_name;"

q "S2 全库中列名含 item_id 且表名含 sem 的表" "SELECT table_schema, table_name, GROUP_CONCAT(column_name ORDER BY ordinal_position) cols FROM information_schema.columns WHERE table_name LIKE '%sem%' GROUP BY table_schema, table_name ORDER BY table_schema, table_name;"

q "S3 fact_ads_product_daily 按 campaign_type(item_id填充/花费/最近日期)" "SELECT campaign_type, COUNT(*) rows_cnt, SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) empty_item, ROUND(SUM(ad_spend),2) spend, MIN(stat_date) min_d, MAX(stat_date) max_d FROM walmart_ai_data.fact_ads_product_daily WHERE platform='walmart' GROUP BY campaign_type ORDER BY spend;"

q "S4 fact_ads_product_daily 昨天(2026-08-12/13)新增行按类型" "SELECT campaign_type, COUNT(*) rows_cnt, SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) empty_item, ROUND(SUM(ad_spend),2) spend FROM walmart_ai_data.fact_ads_product_daily WHERE DATE(created_at)>='2026-08-12' GROUP BY campaign_type ORDER BY spend;"
