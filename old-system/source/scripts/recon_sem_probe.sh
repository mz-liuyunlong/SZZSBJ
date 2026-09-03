#!/bin/bash
exec > /tmp/recon_sem_probe.log 2>&1
cd /opt/lingxing-auto
set -a; . ./.env; set +a
q(){ echo; echo "== $1 =="; MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$2"; }
echo "recon_sem_probe $(date +%F_%T)"

q "R1 recon.sem 按店铺+账期明细" "SELECT store_id, period_start, period_end, ROUND(SUM(amount),2) amt, COUNT(*) rows_cnt FROM fact_reconciliation_item WHERE fee_category='sem' GROUP BY store_id, period_start, period_end ORDER BY period_end;"

q "R2 账单净额 按店铺+月(billing_from月)" "SELECT store_id, DATE_FORMAT(billing_from,'%Y-%m') m, ROUND(SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE -line_amount END),2) net, ROUND(SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE 0 END),2) debit, ROUND(SUM(CASE WHEN charge_type='AD_CREDIT' THEN line_amount ELSE 0 END),2) credit FROM fact_sem_billing_daily GROUP BY store_id, m ORDER BY m;"

q "R3 月度对齐: recon.sem vs 账单净额(同店 CN2601)" "SELECT m, ROUND(SUM(recon_sem),2) recon_sem, ROUND(SUM(bill_net),2) bill_net FROM ( SELECT DATE_FORMAT(period_end,'%Y-%m') m, SUM(amount) recon_sem, 0 bill_net FROM fact_reconciliation_item WHERE fee_category='sem' GROUP BY m UNION ALL SELECT DATE_FORMAT(billing_from,'%Y-%m') m, 0, SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE -line_amount END) FROM fact_sem_billing_daily GROUP BY m ) t GROUP BY m ORDER BY m;"

q "R4 recon 广告相关类目总额(sem/ad_platform/ad_credit)" "SELECT fee_category, store_id, ROUND(SUM(amount),2) amt, COUNT(*) c, MIN(period_start) min_d, MAX(period_end) max_d FROM fact_reconciliation_item WHERE fee_category IN ('sem','ad_platform','ad_credit') GROUP BY fee_category, store_id ORDER BY fee_category, amt;"

q "R5 账单 payment_mode/charge_type 分布(判是否走结算=进回款)" "SELECT charge_type, payment_mode, COUNT(*) c, ROUND(SUM(line_amount),2) amt FROM fact_sem_billing_daily GROUP BY charge_type, payment_mode;"

q "R6 CN2601 账单每日DEBIT(看规模,对比 recon.sem 全期 -694)" "SELECT DATE_FORMAT(billing_from,'%Y-%m') m, ROUND(SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE 0 END),2) debit, COUNT(DISTINCT invoice_id) invoices FROM fact_sem_billing_daily GROUP BY m ORDER BY m;"
