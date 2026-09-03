#!/usr/bin/env bash
# inbound_reimport_audit.sh —— CN2501 入库运输全量重导后的体检 + 「导入偶发报错」取证（只读，零写入）
# 触发：需求方 2026-08-14 把 CN2501(掌上便捷) 全部入库运输报告重导一遍；其中 7.14 文件第一次报
#       "Failed to execute 'json' on 'Response': Unexpected end of JSON input"，第二次正常。
#       该报错=响应体为空(非JSON)，与「后端拒收(400 JSON)」不是一回事，须查服务日志定性。
# 全程只允许 SELECT / journalctl 只读，禁止 INSERT/UPDATE/DELETE/DDL。
exec > /tmp/inbound_reimport_audit.log 2>&1
echo "inbound_reimport_audit $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

# store_id 一律从 dim_store 反查，禁止臆测硬编码
CN2501=$(MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -N -B \
        -e "SELECT store_id FROM dim_store WHERE platform='walmart' AND store_name LIKE 'CN2501%' LIMIT 1")
echo "CN2501 store_id = [$CN2501]"
[ -z "$CN2501" ] && { echo "❗未在 dim_store 找到 CN2501，终止"; exit 1; }

echo "=============== 【一】服务日志取证：空响应到底是崩溃还是重启窗口 ==============="
echo "--- 1.1 服务当前状态与本次启动时间 ---"
systemctl show lingxing-admin -p ActiveState -p SubState -p ExecMainStartTimestamp -p NRestarts 2>&1
echo ""
echo "--- 1.2 今日该服务的启动/停止/异常退出记录 ---"
journalctl -u lingxing-admin --since "today" --no-pager 2>&1 | grep -Ei "Started|Stopping|Stopped|Main process exited|Failed|Scheduled restart|killed" | tail -40
echo ""
echo "--- 1.3 11:50~12:30 全量日志（导入报错时段），只看异常关键字 ---"
journalctl -u lingxing-admin --since "2026-08-14 11:50" --until "2026-08-14 12:30" --no-pager 2>&1 \
  | grep -Ei "error|exception|unhandled|rejection|ECONNRESET|ER_|Duplicate|syntax|at Object|at async" | tail -60
echo ""
echo "--- 1.4 同时段 nginx 对 /api/finance/inbound-import 的响应码（有则打印，无该日志文件则跳过）---"
for f in /var/log/nginx/access.log /var/log/nginx/access.log.1; do
  [ -f "$f" ] && grep "inbound-import" "$f" 2>/dev/null | tail -30
done
echo "(nginx 日志段结束)"

echo ""
echo "=============== 【二】CN2501 入库运输：全部批次现状（RAW 批次为准）==============="
echo "--- 2.1 逐批次：报告期 / RAW明细行 / 事实分摊行 / 金额 / 导入时间 ---"
q "SELECT b.task_id AS 批次, DATE_FORMAT(b.report_start,'%Y-%m-%d') AS 期起,
          DATE_FORMAT(b.report_end,'%Y-%m-%d') AS 期止,
          (SELECT COUNT(*) FROM raw_walmart_inbound_csv x WHERE x.task_id=b.task_id AND x.row_no>0) AS RAW明细行,
          COALESCE(f.rows_cnt,0) AS 分摊行, COALESCE(f.amt,0) AS 运费, b.operator AS 导入人,
          b.created_at AS 导入时间
     FROM raw_walmart_inbound_csv b
     LEFT JOIN (SELECT store_id, report_start, report_end, source_task_id,
                       COUNT(*) AS rows_cnt, ROUND(SUM(alloc_amount),2) AS amt
                  FROM fact_inbound_freight_alloc GROUP BY store_id, report_start, report_end, source_task_id) f
            ON f.store_id=b.store_id AND f.report_start=b.report_start AND f.report_end=b.report_end
           AND f.source_task_id=b.task_id
    WHERE b.store_id='$CN2501' AND b.row_no=0
    ORDER BY b.report_start, b.created_at;"

echo ""
echo "--- 2.2 同一账期被导过几次（>1=重导覆盖，正常；关注是否只有最后一次算数）---"
q "SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS 期起, DATE_FORMAT(report_end,'%Y-%m-%d') AS 期止,
          COUNT(*) AS 导入次数, GROUP_CONCAT(task_id ORDER BY created_at) AS 批次链
     FROM raw_walmart_inbound_csv WHERE store_id='$CN2501' AND row_no=0
    GROUP BY report_start, report_end HAVING COUNT(*)>1 ORDER BY report_start;"

echo ""
echo "--- 2.3 事实表实际留存（去批次维度，看最终算数的金额）---"
q "SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS 期起, DATE_FORMAT(report_end,'%Y-%m-%d') AS 期止,
          COUNT(DISTINCT cargo_code) AS 货件数, COUNT(*) AS 分摊行, ROUND(SUM(alloc_amount),2) AS 运费,
          COUNT(DISTINCT source_task_id) AS 涉及批次数
     FROM fact_inbound_freight_alloc WHERE store_id='$CN2501'
    GROUP BY report_start, report_end ORDER BY report_start;"

echo ""
echo "--- 2.4 账期序列体检：是否有断档/重叠（14天一期，断档天数应=0）---"
q "SELECT 上期止, 下期起, DATEDIFF(下期起,上期止)-1 AS 缺口天数,
          CASE WHEN DATEDIFF(下期起,上期止)-1>0 THEN '❗断档(该期未导)'
               WHEN DATEDIFF(下期起,上期止)-1<0 THEN '❗重叠' ELSE '✅连续' END AS 判定 FROM (
     SELECT DATE_FORMAT(report_end,'%Y-%m-%d') AS 上期止,
            DATE_FORMAT(LEAD(report_start) OVER (ORDER BY report_start),'%Y-%m-%d') AS 下期起,
            report_end AS re, LEAD(report_start) OVER (ORDER BY report_start) AS nx
       FROM (SELECT DISTINCT report_start, report_end FROM raw_walmart_inbound_csv
              WHERE store_id='$CN2501' AND row_no=0) s) t
   WHERE nx IS NOT NULL AND DATEDIFF(nx,re)<>1;"

echo ""
echo "=============== 【三】CN2501 对账：按天摊平（权威口径，不按账期硬join）==============="
q "WITH RECURSIVE dates AS (
     SELECT DATE('2026-01-01') AS d UNION ALL SELECT d+INTERVAL 1 DAY FROM dates WHERE d < '2026-08-31'),
   pipe_day AS (
     SELECT dt.d, i.alloc_amount/(DATEDIFF(i.report_end,i.report_start)+1) AS amt
       FROM fact_inbound_freight_alloc i JOIN dates dt ON dt.d BETWEEN i.report_start AND i.report_end
      WHERE i.store_id='$CN2501'),
   bill AS (
     SELECT MIN(period_start) AS lo, MAX(period_end) AS hi,
            SUM(CASE WHEN fee_category='inbound_transport' THEN -amount ELSE 0 END) AS bill_amt
       FROM fact_reconciliation_item WHERE store_id='$CN2501')
   SELECT b.lo AS 账单起, b.hi AS 账单止, ROUND(b.bill_amt,2) AS 账单入库运费,
          ROUND(SUM(p.amt),2) AS 管道摊入同区间, ROUND(SUM(p.amt)-b.bill_amt,2) AS 差额,
          CASE WHEN ABS(SUM(p.amt)-b.bill_amt) <= GREATEST(30,ABS(b.bill_amt)*0.05) THEN '✅一致'
               WHEN SUM(p.amt) > b.bill_amt THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
     FROM bill b JOIN pipe_day p ON p.d BETWEEN b.lo AND b.hi;"

echo ""
echo "--- 3.2 CN2501 账单里逐账期的入库运费（供人工与本地文件逐个核对）---"
q "SELECT DATE_FORMAT(period_start,'%Y-%m-%d') AS 账单期起, DATE_FORMAT(period_end,'%Y-%m-%d') AS 账单期止,
          ROUND(-SUM(amount),2) AS 账单入库运费, COUNT(*) AS 行数
     FROM fact_reconciliation_item
    WHERE store_id='$CN2501' AND fee_category='inbound_transport'
    GROUP BY period_start, period_end ORDER BY period_start;"

echo ""
echo "=============== 【四】全库「0记录」批次：真空 vs 可疑（交叉账单）==============="
echo "--- 4.1 所有 RAW 明细行=0 的入库批次，并列出同期账单是否有入库运费 ---"
q "SELECT d.store_name AS 店铺, DATE_FORMAT(b.report_start,'%Y-%m-%d') AS 期起,
          DATE_FORMAT(b.report_end,'%Y-%m-%d') AS 期止, b.task_id AS 批次, b.created_at AS 导入时间,
          ROUND(COALESCE((SELECT -SUM(r.amount) FROM fact_reconciliation_item r
                           WHERE r.store_id=b.store_id AND r.fee_category='inbound_transport'
                             AND r.period_start<=b.report_end AND b.report_start<=r.period_end),0),2) AS 同期账单相交金额,
          CASE WHEN COALESCE((SELECT -SUM(r.amount) FROM fact_reconciliation_item r
                               WHERE r.store_id=b.store_id AND r.fee_category='inbound_transport'
                                 AND r.period_start<=b.report_end AND b.report_start<=r.period_end),0) > 0.5
               THEN '⚠️账单相交期有费用(需人工看是否落在本期)' ELSE '✅真空(账单亦无)' END AS 判定
     FROM raw_walmart_inbound_csv b LEFT JOIN dim_store d ON d.store_id=b.store_id
    WHERE b.row_no=0
      AND NOT EXISTS (SELECT 1 FROM raw_walmart_inbound_csv x WHERE x.task_id=b.task_id AND x.row_no>0)
    ORDER BY d.store_name, b.report_start;"

echo ""
echo "--- 4.2 各店入库账期覆盖：最早期起 / 最晚期止 / 期数 / 空期数 ---"
q "SELECT d.store_name AS 店铺, MIN(b.report_start) AS 最早期起, MAX(b.report_end) AS 最晚期止,
          COUNT(DISTINCT CONCAT(b.report_start,'~',b.report_end)) AS 账期数,
          SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM raw_walmart_inbound_csv x
                                     WHERE x.task_id=b.task_id AND x.row_no>0) THEN 1 ELSE 0 END) AS 空批次数
     FROM raw_walmart_inbound_csv b LEFT JOIN dim_store d ON d.store_id=b.store_id
    WHERE b.row_no=0 GROUP BY d.store_name ORDER BY d.store_name;"

echo ""
echo "=============== 【五】批13口径校验：SKU前缀 YC00200+ = 新品（需求方 2026-08-14 口径）==============="
echo "--- 5.1 按前缀分类的 item/SKU 家底 ---"
q "SELECT CASE WHEN p.sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(p.sku,'[0-9]+') AS UNSIGNED) >= 200
               THEN 'YC00200及之后(新品)'
               WHEN p.sku REGEXP '^YC[0-9]+' THEN 'YC00200之前(老品)'
               ELSE CONCAT('其它前缀(', LEFT(p.sku,2), ')') END AS 分类,
          COUNT(DISTINCT p.sku) AS SKU数, COUNT(DISTINCT CONCAT(p.store_id,'|',p.item_id)) AS 店item数
     FROM dim_product p
    WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
      AND COALESCE(p.sku,'') NOT IN ('XY2007','DC001','QH888','')
    GROUP BY 1 ORDER BY 2 DESC LIMIT 25;"

echo ""
echo "--- 5.2 前缀口径 × 期初池口径 交叉（两口径是否互相印证）---"
q "SELECT CASE WHEN p.sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(p.sku,'[0-9]+') AS UNSIGNED) >= 200
               THEN 'YC200+(新)' ELSE '非YC200+(老/其它)' END AS 前缀口径,
          CASE WHEN o.sku IS NULL THEN '不在期初池'
               WHEN COALESCE(o.snap_qty_0501,0)=0 THEN '期初数量=0'
               ELSE '有期初库存' END AS 期初口径,
          COUNT(DISTINCT p.sku) AS SKU数, COUNT(DISTINCT CONCAT(p.store_id,'|',p.item_id)) AS 店item数
     FROM dim_product p
     LEFT JOIN biz_finance_opening_cost o ON o.sku=p.sku AND o.cutoff_date='2026-05-01'
    WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
      AND COALESCE(p.sku,'') NOT IN ('XY2007','DC001','QH888','')
    GROUP BY 1,2 ORDER BY 1,2;"

echo ""
echo "=============== 【六】CN2501 仓储费同轮重导体检（需求方：仓储也全量重导了一遍，无报错）==============="
echo "--- 6.1 逐批次：报告期 / RAW明细行 / 事实行 / 金额 / 导入时间（同期多次=覆盖更新，属正常）---"
q "SELECT b.task_id AS 批次, DATE_FORMAT(b.report_start,'%Y-%m-%d') AS 期起,
          DATE_FORMAT(b.report_end,'%Y-%m-%d') AS 期止,
          (SELECT COUNT(*) FROM raw_walmart_storage_csv x WHERE x.task_id=b.task_id AND x.row_no>0) AS RAW明细行,
          b.operator AS 导入人, b.created_at AS 导入时间
     FROM raw_walmart_storage_csv b
    WHERE b.store_id='$CN2501' AND b.row_no=0
    ORDER BY b.report_start, b.created_at;"

echo ""
echo "--- 6.2 事实表最终留存（去批次维度；同账期只应有一份，不得累加）---"
q "SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS 期起, DATE_FORMAT(report_end,'%Y-%m-%d') AS 期止,
          DATEDIFF(report_end,report_start)+1 AS 天数, COUNT(*) AS 行数,
          ROUND(SUM(final_storage_fee),2) AS 仓储费, COUNT(DISTINCT source_task_id) AS 涉及批次数
     FROM fact_wfs_storage_fee WHERE store_id='$CN2501'
    GROUP BY report_start, report_end ORDER BY report_start;"

echo ""
echo "--- 6.3 【关键】重导是否造成累加：同账期行数是否翻倍（按 msku 看重复度，应=1）---"
q "SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS 期起, COUNT(*) AS 总行数,
          COUNT(DISTINCT msku) AS 去重msku数, ROUND(COUNT(*)/NULLIF(COUNT(DISTINCT msku),0),2) AS 每msku行数,
          CASE WHEN COUNT(*)=COUNT(DISTINCT msku) THEN '✅无重复' ELSE '❗同期同msku多行(疑累加)' END AS 判定
     FROM fact_wfs_storage_fee WHERE store_id='$CN2501'
    GROUP BY report_start ORDER BY report_start;"

echo ""
echo "--- 6.4 账期断档/重叠自检（14天一期）---"
q "SELECT 上期止, 下期起, DATEDIFF(下期起,上期止)-1 AS 缺口天数,
          CASE WHEN DATEDIFF(下期起,上期止)-1>0 THEN '❗断档' WHEN DATEDIFF(下期起,上期止)-1<0 THEN '❗重叠' ELSE '✅连续' END AS 判定 FROM (
     SELECT DATE_FORMAT(report_end,'%Y-%m-%d') AS 上期止,
            DATE_FORMAT(LEAD(report_start) OVER (ORDER BY report_start),'%Y-%m-%d') AS 下期起,
            report_end AS re, LEAD(report_start) OVER (ORDER BY report_start) AS nx
       FROM (SELECT DISTINCT report_start, report_end FROM fact_wfs_storage_fee WHERE store_id='$CN2501') s) t
   WHERE nx IS NOT NULL AND DATEDIFF(nx,re)<>1;"

echo ""
echo "--- 6.5 仓储费按天摊平 vs 账单（权威口径）---"
q "WITH RECURSIVE dates AS (
     SELECT DATE('2026-01-01') AS d UNION ALL SELECT d+INTERVAL 1 DAY FROM dates WHERE d < '2026-08-31'),
   pipe_day AS (
     SELECT dt.d, s.final_storage_fee/(DATEDIFF(s.report_end,s.report_start)+1) AS amt
       FROM fact_wfs_storage_fee s JOIN dates dt ON dt.d BETWEEN s.report_start AND s.report_end
      WHERE s.store_id='$CN2501'),
   bill AS (
     SELECT MIN(period_start) AS lo, MAX(period_end) AS hi,
            SUM(CASE WHEN fee_category='storage' THEN -amount ELSE 0 END) AS bill_amt
       FROM fact_reconciliation_item WHERE store_id='$CN2501')
   SELECT b.lo AS 账单起, b.hi AS 账单止, ROUND(b.bill_amt,2) AS 账单仓储费,
          ROUND(SUM(p.amt),2) AS 管道摊入同区间, ROUND(SUM(p.amt)-b.bill_amt,2) AS 差额,
          CASE WHEN ABS(SUM(p.amt)-b.bill_amt) <= GREATEST(30,ABS(b.bill_amt)*0.05) THEN '✅一致'
               WHEN SUM(p.amt) > b.bill_amt THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
     FROM bill b JOIN pipe_day p ON p.d BETWEEN b.lo AND b.hi;"

echo ""
echo "--- 6.6 全库重叠账期对数（应=0，验证防重上线后无新增重叠）---"
q "SELECT '仓储' AS 表, COUNT(*) AS 重叠对数 FROM (
     SELECT a.store_id FROM (SELECT DISTINCT store_id,report_start,report_end FROM fact_wfs_storage_fee) a
       JOIN (SELECT DISTINCT store_id,report_start,report_end FROM fact_wfs_storage_fee) b
         ON a.store_id=b.store_id
        AND (a.report_start<b.report_start OR (a.report_start=b.report_start AND a.report_end<b.report_end))
        AND a.report_start<=b.report_end AND b.report_start<=a.report_end) x
   UNION ALL
   SELECT '入库', COUNT(*) FROM (
     SELECT a.store_id FROM (SELECT DISTINCT store_id,report_start,report_end FROM fact_inbound_freight_alloc) a
       JOIN (SELECT DISTINCT store_id,report_start,report_end FROM fact_inbound_freight_alloc) b
         ON a.store_id=b.store_id
        AND (a.report_start<b.report_start OR (a.report_start=b.report_start AND a.report_end<b.report_end))
        AND a.report_start<=b.report_end AND b.report_start<=a.report_end) y;"

echo "---- done ----"
