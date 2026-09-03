#!/usr/bin/env bash
# sem_sentinel_diag.sh —— SEM哨兵告警诊断（只读，零写入）
# 问题：2026-08-11 账单 vs 日绩效 差 $-229.73。判定是「账单未导到该日(滞后)」还是「真实数据缺失」
exec > /tmp/sem_sentinel_diag.log 2>&1
echo "sem_sentinel_diag $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "===== 1. 账单表覆盖到哪天（按店铺，看是否根本没导到08-11）====="
q "SELECT b.store_id, d.store_name, COUNT(DISTINCT b.invoice_id) AS 发票数,
          MIN(b.billing_from) AS 账单最早, MAX(b.billing_to) AS 账单最晚,
          MAX(b.invoice_date) AS 最新发票日
     FROM fact_sem_billing_daily b LEFT JOIN dim_store d ON d.store_id=b.store_id
    GROUP BY b.store_id, d.store_name ORDER BY d.store_name;"

echo ""
echo "===== 2. 日绩效覆盖到哪天（对照）====="
q "SELECT f.store_id, d.store_name, MIN(f.stat_date) AS 日绩效最早, MAX(f.stat_date) AS 日绩效最晚,
          COUNT(DISTINCT f.stat_date) AS 天数
     FROM fact_ads_product_daily f LEFT JOIN dim_store d ON d.store_id=f.store_id
    WHERE f.platform='walmart' AND f.campaign_type='sem'
    GROUP BY f.store_id, d.store_name ORDER BY d.store_name;"

echo ""
echo "===== 3. 【关键】2026-08-11 当天 逐店对照（差额来自哪个店）====="
q "SELECT COALESCE(b.store_id,f.store_id) AS store_id, d.store_name,
          ROUND(COALESCE(b.bill,0),2) AS 账单DEBIT净额,
          ROUND(COALESCE(f.daily,0),2) AS 日绩效花费,
          ROUND(COALESCE(b.bill,0)-COALESCE(f.daily,0),2) AS 差额
     FROM (SELECT store_id,
                  SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE -line_amount END) AS bill
             FROM fact_sem_billing_daily WHERE billing_from='2026-08-11' GROUP BY store_id) b
     LEFT JOIN (SELECT store_id, SUM(ad_spend) AS daily FROM fact_ads_product_daily
                 WHERE platform='walmart' AND campaign_type='sem' AND stat_date='2026-08-11'
                GROUP BY store_id) f ON f.store_id=b.store_id
     LEFT JOIN dim_store d ON d.store_id=b.store_id
    UNION
    SELECT f.store_id, d.store_name, 0, ROUND(f.daily,2), ROUND(-f.daily,2)
     FROM (SELECT store_id, SUM(ad_spend) AS daily FROM fact_ads_product_daily
            WHERE platform='walmart' AND campaign_type='sem' AND stat_date='2026-08-11'
           GROUP BY store_id) f
     LEFT JOIN dim_store d ON d.store_id=f.store_id
    WHERE f.store_id NOT IN (SELECT DISTINCT store_id FROM fact_sem_billing_daily WHERE billing_from='2026-08-11');"

echo ""
echo "===== 4. 近14天逐日对照（看是不是从某天起账单就断了=滞后特征）====="
q "SELECT d.d AS 日期,
          ROUND(COALESCE(b.bill,0),2) AS 账单DEBIT净额,
          ROUND(COALESCE(f.daily,0),2) AS 日绩效花费,
          ROUND(COALESCE(b.bill,0)-COALESCE(f.daily,0),2) AS 差额,
          CASE WHEN b.bill IS NULL AND f.daily IS NOT NULL THEN '❗账单无此日(滞后或漏导)'
               WHEN b.bill IS NOT NULL AND f.daily IS NULL THEN '⚠️日绩效无此日'
               WHEN ABS(COALESCE(b.bill,0)-COALESCE(f.daily,0))<0.01 THEN '✅一致'
               ELSE '⚠️有差额' END AS 判定
     FROM (SELECT DISTINCT stat_date AS d FROM fact_ads_product_daily
            WHERE platform='walmart' AND campaign_type='sem' AND stat_date>=DATE_SUB(CURDATE(),INTERVAL 20 DAY)
           UNION SELECT DISTINCT billing_from FROM fact_sem_billing_daily
            WHERE billing_from>=DATE_SUB(CURDATE(),INTERVAL 20 DAY)) d
     LEFT JOIN (SELECT billing_from AS d,
                       SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE -line_amount END) AS bill
                  FROM fact_sem_billing_daily GROUP BY billing_from) b ON b.d=d.d
     LEFT JOIN (SELECT stat_date AS d, SUM(ad_spend) AS daily FROM fact_ads_product_daily
                 WHERE platform='walmart' AND campaign_type='sem' GROUP BY stat_date) f ON f.d=d.d
    ORDER BY d.d DESC;"

echo ""
echo "===== 5. 最近的SEM导入任务（看账单是哪天导的、导了哪个区间）====="
q "SELECT task_id, store_id, csv_type, COUNT(*) AS 行数,
          MIN(report_date) AS 数据最早, MAX(report_date) AS 数据最晚, MAX(created_at) AS 导入时间
     FROM raw_walmart_sem_csv
    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    GROUP BY task_id, store_id, csv_type ORDER BY MAX(created_at) DESC LIMIT 15;" 2>/dev/null \
|| q "SHOW COLUMNS FROM raw_walmart_sem_csv;"

echo ""
echo "===== 6. 08-11 差额是否集中在某几个campaign ====="
q "SELECT COALESCE(b.campaign_id,f.campaign_id) AS campaign_id,
          COALESCE(b.cname,f.cname) AS campaign名,
          ROUND(COALESCE(b.bill,0),2) AS 账单, ROUND(COALESCE(f.daily,0),2) AS 日绩效,
          ROUND(COALESCE(b.bill,0)-COALESCE(f.daily,0),2) AS 差额
     FROM (SELECT campaign_id, MAX(campaign_name) AS cname,
                  SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE -line_amount END) AS bill
             FROM fact_sem_billing_daily WHERE billing_from='2026-08-11' GROUP BY campaign_id) b
     LEFT JOIN (SELECT campaign_id, MAX(campaign_name) AS cname, SUM(ad_spend) AS daily
                  FROM fact_ads_product_daily WHERE platform='walmart' AND campaign_type='sem'
                   AND stat_date='2026-08-11' GROUP BY campaign_id) f ON f.campaign_id=b.campaign_id
    WHERE ABS(COALESCE(b.bill,0)-COALESCE(f.daily,0)) >= 0.01
    ORDER BY ABS(COALESCE(b.bill,0)-COALESCE(f.daily,0)) DESC LIMIT 20;"
echo "---- done ----"
