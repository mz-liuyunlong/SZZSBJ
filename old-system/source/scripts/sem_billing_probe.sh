#!/bin/bash
exec > /tmp/sem_billing_probe.log 2>&1
cd /opt/lingxing-auto
set -a; . ./.env; set +a
q(){ echo; echo "== $1 =="; MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$2"; }
echo "sem_billing_probe $(date +%F_%T)"

q "M1 账单总览(行/金额/日期/item_id填充/发票/campaign/店铺)" "SELECT COUNT(*) rows_cnt, ROUND(SUM(line_amount),2) line_sum, MIN(invoice_date) min_d, MAX(invoice_date) max_d, SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) empty_item_rows, ROUND(SUM(CASE WHEN COALESCE(item_id,'')='' THEN line_amount ELSE 0 END),2) empty_item_amt, COUNT(DISTINCT invoice_id) invoices, COUNT(DISTINCT campaign_id) campaigns, COUNT(DISTINCT store_id) stores FROM fact_sem_billing_daily;"

q "M2 按 charge_type(金额/item_id填充/币种)" "SELECT charge_type, COUNT(*) rows_cnt, ROUND(SUM(line_amount),2) line_sum, SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) empty_item, MAX(currency_code) cur FROM fact_sem_billing_daily GROUP BY charge_type ORDER BY line_sum;"

q "M3 按店铺(金额/item_id填充/日期)" "SELECT store_id, MAX(store_name) nm, COUNT(*) rows_cnt, ROUND(SUM(line_amount),2) line_sum, SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) empty_item, MIN(invoice_date) min_d, MAX(invoice_date) max_d FROM fact_sem_billing_daily GROUP BY store_id ORDER BY line_sum;"

q "M4 发票头 invoice_total vs 明细 Σline_amount(抽10张看是否等)" "SELECT invoice_id, MAX(invoice_total) inv_total, ROUND(SUM(line_amount),2) lines_sum, COUNT(*) lines, MAX(pay_status) pay FROM fact_sem_billing_daily GROUP BY invoice_id ORDER BY invoice_id LIMIT 10;"

q "M5 dim_sem_campaign_item 映射覆盖" "SELECT COUNT(*) map_rows, COUNT(DISTINCT campaign_id) campaigns, COUNT(DISTINCT item_id) items, COUNT(DISTINCT store_id) stores, MAX(source) src FROM dim_sem_campaign_item;"

q "M6 账单里 item_id 空的 campaign 能否经 dim_sem_campaign_item 补上(待人工的量)" "SELECT COUNT(*) empty_rows, ROUND(SUM(b.line_amount),2) empty_amt, SUM(CASE WHEN m.item_id IS NOT NULL THEN 1 ELSE 0 END) mappable_rows, ROUND(SUM(CASE WHEN m.item_id IS NOT NULL THEN b.line_amount ELSE 0 END),2) mappable_amt, COUNT(DISTINCT CASE WHEN m.item_id IS NULL THEN b.campaign_id END) need_manual_campaigns FROM fact_sem_billing_daily b LEFT JOIN dim_sem_campaign_item m ON m.store_id=b.store_id AND m.campaign_id=b.campaign_id WHERE COALESCE(b.item_id,'')='';"

q "M7 三源 SEM 对照(判双算): 账单 vs recon.sem vs ads.sem" "SELECT 'sem_billing_daily' src, ROUND(SUM(line_amount),2) amt, MIN(invoice_date) min_d, MAX(invoice_date) max_d FROM fact_sem_billing_daily UNION ALL SELECT 'recon.sem', ROUND(SUM(amount),2), MIN(period_start), MAX(period_end) FROM fact_reconciliation_item WHERE fee_category='sem' UNION ALL SELECT 'ads.sem', ROUND(SUM(ad_spend),2), MIN(stat_date), MAX(stat_date) FROM fact_ads_product_daily WHERE platform='walmart' AND campaign_type='sem';"

q "M8 raw_walmart_sem_csv 按 csv_type(喂了哪些报表)" "SELECT csv_type, COUNT(*) rows_cnt, MIN(report_date) min_d, MAX(report_date) max_d, COUNT(DISTINCT task_id) tasks FROM raw_walmart_sem_csv GROUP BY csv_type;"

q "M9 账单样本 6 行" "SELECT store_name, invoice_id, invoice_date, charge_type, campaign_id, campaign_name, item_id, line_amount, pay_status FROM fact_sem_billing_daily ORDER BY invoice_date DESC LIMIT 6;"
