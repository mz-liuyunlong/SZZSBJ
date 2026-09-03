#!/usr/bin/env bash
# storage_gap_audit.sh —— 清理后「是否有漏」全面体检（只读，零写入）
exec > /tmp/storage_gap_audit.log 2>&1
echo "storage_gap_audit $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "=============== 【一】账期断档检测（清理后）==============="
echo "--- 1.1 仓储费：上期止+1 <> 下期起 即断档（负数=重叠，应已归零）---"
q "SELECT d.store_name AS 店铺, 上期止, 下期起, DATEDIFF(下期起,上期止)-1 AS 缺口天数 FROM (
     SELECT s.store_id, DATE_FORMAT(s.report_end,'%Y-%m-%d') AS 上期止,
            DATE_FORMAT(LEAD(s.report_start) OVER (PARTITION BY s.store_id ORDER BY s.report_start),'%Y-%m-%d') AS 下期起,
            s.report_end AS re, LEAD(s.report_start) OVER (PARTITION BY s.store_id ORDER BY s.report_start) AS nx
       FROM (SELECT DISTINCT store_id, report_start, report_end FROM fact_wfs_storage_fee) s) t
   LEFT JOIN dim_store d ON d.store_id=t.store_id
  WHERE nx IS NOT NULL AND DATEDIFF(nx,re)<>1 ORDER BY d.store_name, 上期止;"

echo ""
echo "--- 1.2 入库运输：同法 ---"
q "SELECT d.store_name AS 店铺, 上期止, 下期起, DATEDIFF(下期起,上期止)-1 AS 缺口天数 FROM (
     SELECT i.store_id, DATE_FORMAT(i.report_end,'%Y-%m-%d') AS 上期止,
            DATE_FORMAT(LEAD(i.report_start) OVER (PARTITION BY i.store_id ORDER BY i.report_start),'%Y-%m-%d') AS 下期起,
            i.report_end AS re, LEAD(i.report_start) OVER (PARTITION BY i.store_id ORDER BY i.report_start) AS nx
       FROM (SELECT DISTINCT store_id, report_start, report_end FROM fact_inbound_freight_alloc) i) t
   LEFT JOIN dim_store d ON d.store_id=t.store_id
  WHERE nx IS NOT NULL AND DATEDIFF(nx,re)<>1 ORDER BY d.store_name, 上期止;"

echo ""
echo "=============== 【二】按天摊平精确对账（清理后重跑，权威口径）==============="
echo "--- 2.1 仓储费 ---"
q "WITH RECURSIVE dates AS (
     SELECT DATE('2026-03-01') AS d UNION ALL SELECT d+INTERVAL 1 DAY FROM dates WHERE d < '2026-08-31'),
   pipe_day AS (
     SELECT s.store_id, dt.d, s.final_storage_fee/(DATEDIFF(s.report_end,s.report_start)+1) AS amt
       FROM fact_wfs_storage_fee s JOIN dates dt ON dt.d BETWEEN s.report_start AND s.report_end),
   bill AS (
     SELECT store_id, MIN(period_start) AS lo, MAX(period_end) AS hi,
            SUM(CASE WHEN fee_category='storage' THEN -amount ELSE 0 END) AS bill_amt
       FROM fact_reconciliation_item GROUP BY store_id)
   SELECT ds.store_name AS 店铺, b.lo AS 账单起, b.hi AS 账单止,
          ROUND(b.bill_amt,2) AS 账单, ROUND(SUM(p.amt),2) AS 管道摊入同区间,
          ROUND(SUM(p.amt)-b.bill_amt,2) AS 差额,
          CASE WHEN ABS(SUM(p.amt)-b.bill_amt) <= GREATEST(30,ABS(b.bill_amt)*0.05) THEN '✅一致'
               WHEN SUM(p.amt) > b.bill_amt THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
     FROM bill b JOIN pipe_day p ON p.store_id=b.store_id AND p.d BETWEEN b.lo AND b.hi
     LEFT JOIN dim_store ds ON ds.store_id=b.store_id
    GROUP BY ds.store_name, b.store_id, b.lo, b.hi, b.bill_amt ORDER BY ds.store_name;"

echo ""
echo "--- 2.2 入库运输 ---"
q "WITH RECURSIVE dates AS (
     SELECT DATE('2026-03-01') AS d UNION ALL SELECT d+INTERVAL 1 DAY FROM dates WHERE d < '2026-08-31'),
   pipe_day AS (
     SELECT i.store_id, dt.d, i.alloc_amount/(DATEDIFF(i.report_end,i.report_start)+1) AS amt
       FROM fact_inbound_freight_alloc i JOIN dates dt ON dt.d BETWEEN i.report_start AND i.report_end),
   bill AS (
     SELECT store_id, MIN(period_start) AS lo, MAX(period_end) AS hi,
            SUM(CASE WHEN fee_category='inbound_transport' THEN -amount ELSE 0 END) AS bill_amt
       FROM fact_reconciliation_item GROUP BY store_id)
   SELECT ds.store_name AS 店铺, ROUND(b.bill_amt,2) AS 账单, ROUND(SUM(p.amt),2) AS 管道摊入同区间,
          ROUND(SUM(p.amt)-b.bill_amt,2) AS 差额,
          CASE WHEN ABS(SUM(p.amt)-b.bill_amt) <= GREATEST(30,ABS(b.bill_amt)*0.05) THEN '✅一致'
               WHEN SUM(p.amt) > b.bill_amt THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
     FROM bill b JOIN pipe_day p ON p.store_id=b.store_id AND p.d BETWEEN b.lo AND b.hi
     LEFT JOIN dim_store ds ON ds.store_id=b.store_id
    GROUP BY ds.store_name, b.store_id, b.bill_amt ORDER BY ds.store_name;"

echo ""
echo "=============== 【三】该导未导：管道最新 vs 账单最新 ==============="
q "SELECT d.store_name AS 店铺,
          p.bill_max AS 账单最新账期止,
          s.pipe_max AS 仓储表最新, DATEDIFF(p.bill_max, s.pipe_max) AS 仓储滞后天数,
          i.inb_max AS 入库表最新, DATEDIFF(p.bill_max, i.inb_max) AS 入库滞后天数,
          CASE WHEN s.pipe_max IS NULL THEN '❗仓储表无数据'
               WHEN s.pipe_max < p.bill_max THEN '❗仓储该导未导'
               ELSE '✅仓储已跟上' END AS 仓储判定,
          CASE WHEN i.inb_max IS NULL THEN '(入库表无数据·可能本就无货件)'
               WHEN i.inb_max < p.bill_max THEN '⚠️入库落后(需核账单是否有费用)'
               ELSE '✅入库已跟上' END AS 入库判定
     FROM (SELECT store_id, MAX(period_end) AS bill_max FROM fact_reconciliation_period GROUP BY store_id) p
     LEFT JOIN (SELECT store_id, MAX(report_end) AS pipe_max FROM fact_wfs_storage_fee GROUP BY store_id) s
            ON s.store_id=p.store_id
     LEFT JOIN (SELECT store_id, MAX(report_end) AS inb_max FROM fact_inbound_freight_alloc GROUP BY store_id) i
            ON i.store_id=p.store_id
     LEFT JOIN dim_store d ON d.store_id=p.store_id ORDER BY d.store_name;"

echo ""
echo "=============== 【四】三个遗留尾巴定性 ==============="
echo "--- 4.1 HK2612 仓储 +164.54：逐账期对照账单 ---"
q "SELECT '仓储表' AS 源, report_start AS 期起, report_end AS 期止,
          COUNT(*) AS 行数, ROUND(SUM(final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee WHERE store_id='110704872940532224'
    GROUP BY report_start, report_end ORDER BY report_start;"
q "SELECT '账单' AS 源, period_start AS 期起, period_end AS 期止, ROUND(-SUM(amount),2) AS 金额
     FROM fact_reconciliation_item
    WHERE store_id='110704872940532224' AND fee_category='storage'
    GROUP BY period_start, period_end ORDER BY period_start;"

echo ""
echo "--- 4.2 CN2603 入库 -106.18（疑漏导）：逐账期对照 ---"
q "SELECT '入库表' AS 源, report_start AS 期起, report_end AS 期止,
          COUNT(*) AS 行数, ROUND(SUM(alloc_amount),2) AS 金额
     FROM fact_inbound_freight_alloc WHERE store_id='110704863834580480'
    GROUP BY report_start, report_end ORDER BY report_start;"
q "SELECT '账单' AS 源, period_start AS 期起, period_end AS 期止, ROUND(-SUM(amount),2) AS 金额
     FROM fact_reconciliation_item
    WHERE store_id='110704863834580480' AND fee_category='inbound_transport'
    GROUP BY period_start, period_end ORDER BY period_start;"

echo ""
echo "--- 4.3 HK2615 入库 +351.34（账单为0而管道有值）：逐账期对照 ---"
q "SELECT '入库表' AS 源, report_start AS 期起, report_end AS 期止,
          COUNT(*) AS 行数, ROUND(SUM(alloc_amount),2) AS 金额
     FROM fact_inbound_freight_alloc WHERE store_id='110711146247224320'
    GROUP BY report_start, report_end ORDER BY report_start;"
q "SELECT '账单' AS 源, period_start AS 期起, period_end AS 期止, ROUND(-SUM(amount),2) AS 金额
     FROM fact_reconciliation_item
    WHERE store_id='110711146247224320' AND fee_category='inbound_transport'
    GROUP BY period_start, period_end ORDER BY period_start;"

echo ""
echo "=============== 【五】余差归因：管道超出账单窗口的部分 ==============="
q "SELECT '账单窗口外(07-25之后)的管道金额' AS chk, ROUND(SUM(final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee WHERE report_start > '2026-07-25';"
q "SELECT d.store_name AS 店铺, s.report_start AS 期起, s.report_end AS 期止,
          ROUND(SUM(s.final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee s LEFT JOIN dim_store d ON d.store_id=s.store_id
    WHERE s.report_start > '2026-07-25'
    GROUP BY d.store_name, s.report_start, s.report_end ORDER BY d.store_name;"
echo "---- done ----"
