#!/bin/bash
exec > /tmp/sem_dedup_probe.log 2>&1
cd /opt/lingxing-auto
set -a; . ./.env; set +a
q(){ echo; echo "== $1 =="; MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$2"; }
echo "sem_dedup_probe $(date +%F_%T)"

q "D1 账单表唯一键/索引" "SHOW INDEX FROM fact_sem_billing_daily;"
q "D2 账单重复检测(invoice_id+campaign_id 出现>1)" "SELECT COUNT(*) dup_groups, COALESCE(SUM(c-1),0) extra_rows FROM (SELECT invoice_id, campaign_id, COUNT(*) c FROM fact_sem_billing_daily GROUP BY invoice_id, campaign_id HAVING COUNT(*)>1) t;"
q "D3 账单按发票核对(头Total vs Σ明细,抽近8张)" "SELECT invoice_id, MAX(invoice_total) inv_total, ROUND(SUM(line_amount),2) lines_sum, COUNT(*) lines, MAX(charge_type) ctype FROM fact_sem_billing_daily GROUP BY invoice_id ORDER BY MAX(invoice_date) DESC LIMIT 8;"
q "D4 账单净额(DEBIT-CREDIT)+近7/14天窗口" "SELECT ROUND(SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE 0 END),2) debit_sum, ROUND(SUM(CASE WHEN charge_type='AD_CREDIT' THEN line_amount ELSE 0 END),2) credit_sum, ROUND(SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE -line_amount END),2) net_all FROM fact_sem_billing_daily;"

q "D5 SEM日绩效落表唯一键(fact_ads_product_daily)" "SHOW INDEX FROM fact_ads_product_daily WHERE Key_name<>'PRIMARY';"
q "D6 SEM日绩效重复检测(sem 类型 stat_date+campaign 出现>1)" "SELECT COUNT(*) dup_groups, COALESCE(SUM(c-1),0) extra_rows FROM (SELECT stat_date, item_id, msku, campaign_id, COUNT(*) c FROM fact_ads_product_daily WHERE platform='walmart' AND campaign_type='sem' GROUP BY stat_date, item_id, msku, campaign_id HAVING COUNT(*)>1) t;"
q "D6b SEM日绩效 有无 campaign_id 列" "SHOW COLUMNS FROM fact_ads_product_daily LIKE '%campaign%';"

q "D7 raw_walmart_sem_csv 任务+去重(raw_hash 重复=同行重导)" "SELECT csv_type, COUNT(*) rows_cnt, COUNT(DISTINCT raw_hash) distinct_hash, COUNT(DISTINCT task_id) tasks, MIN(report_date) min_d, MAX(report_date) max_d FROM raw_walmart_sem_csv GROUP BY csv_type;"
q "D8 raw 任务清单" "SELECT task_id, csv_type, COUNT(*) rows_cnt, MIN(report_date) min_d, MAX(report_date) max_d, MAX(operator) op, MAX(created_at) uploaded FROM raw_walmart_sem_csv GROUP BY task_id, csv_type ORDER BY MAX(created_at);"
