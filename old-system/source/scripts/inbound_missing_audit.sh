#!/usr/bin/env bash
# inbound_missing_audit.sh —— 入库运输「缺期是否=漏导」判定（只读，零写入）
# 判据：入库运输只有发生到货货件才有费用行。用货件表(fact_wfs_shipment)交叉验证：
#   该期有到货货件 而 入库分摊表无行 → ❗真漏导，需补导；
#   该期本就无货件 → ✅正常，非漏导。
exec > /tmp/inbound_missing_audit.log 2>&1
echo "inbound_missing_audit $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "===== 0. 货件表结构（确认可用的到货时间列）====="
q "SHOW CREATE TABLE fact_wfs_shipment\G"

echo ""
echo "===== 1. 修正上轮SQL错误：账单窗口外(report_start>=07-25)的仓储管道金额 ====="
q "SELECT '账单窗口外(>=07-25)仓储管道合计' AS chk, ROUND(SUM(final_storage_fee),2) AS 金额, COUNT(*) AS 行数
     FROM fact_wfs_storage_fee WHERE report_start >= '2026-07-25';"
q "SELECT d.store_name AS 店铺, s.report_start AS 期起, s.report_end AS 期止,
          ROUND(SUM(s.final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee s LEFT JOIN dim_store d ON d.store_id=s.store_id
    WHERE s.report_start >= '2026-07-25'
    GROUP BY d.store_name, s.report_start, s.report_end ORDER BY d.store_name;"

echo ""
echo "===== 2. 仓储 vs 入库：逐账期覆盖对照（找出入库缺哪些期）====="
q "SELECT d.store_name AS 店铺, p.report_start AS 期起, p.report_end AS 期止,
          ROUND(p.stor,2) AS 仓储费,
          IFNULL(ROUND(i.inb,2),'—') AS 入库运费,
          CASE WHEN i.inb IS NULL THEN '❓入库无此期(待验证是否有货件)' ELSE '✅两者都有' END AS 判定
     FROM (SELECT store_id, report_start, report_end, SUM(final_storage_fee) AS stor
             FROM fact_wfs_storage_fee GROUP BY store_id, report_start, report_end) p
     LEFT JOIN (SELECT store_id, report_start, report_end, SUM(alloc_amount) AS inb
                  FROM fact_inbound_freight_alloc GROUP BY store_id, report_start, report_end) i
            ON i.store_id=p.store_id AND i.report_start=p.report_start AND i.report_end=p.report_end
     LEFT JOIN dim_store d ON d.store_id=p.store_id
    WHERE p.report_start >= '2026-06-01'
    ORDER BY d.store_name, p.report_start;"

echo ""
echo "===== 3. 【关键】缺期是否有到货货件（有货件却无运费=真漏导）====="
q "SELECT d.store_name AS 店铺, p.report_start AS 期起, p.report_end AS 期止,
          COUNT(DISTINCT w.cargo_code) AS 该期到货货件数,
          CASE WHEN COUNT(DISTINCT w.cargo_code)=0 THEN '✅本就无货件(非漏导)'
               ELSE '❗有货件却无运费=疑漏导' END AS 判定
     FROM (SELECT store_id, report_start, report_end
             FROM fact_wfs_storage_fee GROUP BY store_id, report_start, report_end) p
     LEFT JOIN (SELECT store_id, report_start, report_end
                  FROM fact_inbound_freight_alloc GROUP BY store_id, report_start, report_end) i
            ON i.store_id=p.store_id AND i.report_start=p.report_start AND i.report_end=p.report_end
     LEFT JOIN fact_wfs_shipment w
            ON w.store_id=p.store_id
           AND DATE(w.to_receive_time) BETWEEN p.report_start AND p.report_end
     LEFT JOIN dim_store d ON d.store_id=p.store_id
    WHERE i.store_id IS NULL AND p.report_start >= '2026-06-01'
    GROUP BY d.store_name, p.store_id, p.report_start, p.report_end
    ORDER BY 该期到货货件数 DESC, d.store_name, p.report_start;"

echo ""
echo "===== 4. HK2613 为何两表皆空（有无货件与销售）====="
q "SELECT '货件数' AS chk, COUNT(*) AS c FROM fact_wfs_shipment WHERE store_id=(SELECT store_id FROM dim_store WHERE store_name LIKE 'HK2613%' LIMIT 1);"
q "SELECT '回款账期数' AS chk, COUNT(*) AS c, MIN(period_start) AS 最早, MAX(period_end) AS 最晚
     FROM fact_reconciliation_period WHERE store_id=(SELECT store_id FROM dim_store WHERE store_name LIKE 'HK2613%' LIMIT 1);"
q "SELECT '账单仓储费' AS chk, ROUND(-SUM(amount),2) AS 金额 FROM fact_reconciliation_item
    WHERE fee_category='storage' AND store_id=(SELECT store_id FROM dim_store WHERE store_name LIKE 'HK2613%' LIMIT 1);"
q "SELECT '账单入库运输费' AS chk, ROUND(-SUM(amount),2) AS 金额 FROM fact_reconciliation_item
    WHERE fee_category='inbound_transport' AND store_id=(SELECT store_id FROM dim_store WHERE store_name LIKE 'HK2613%' LIMIT 1);"

echo ""
echo "===== 5. CN2502 入库停在06-12（滞后43天）：期间有无货件 ====="
q "SELECT DATE_FORMAT(w.to_receive_time,'%Y-%m') AS 到货月, COUNT(DISTINCT w.cargo_code) AS 货件数
     FROM fact_wfs_shipment w WHERE w.store_id='110687428693128704'
      AND w.to_receive_time >= '2026-06-01'
    GROUP BY 到货月 ORDER BY 到货月;"

echo ""
echo "===== 6. HK2612 入库缺 06-27~07-10：该期有无货件 ====="
q "SELECT COUNT(DISTINCT cargo_code) AS 该期货件数, MIN(to_receive_time) AS 最早到货, MAX(to_receive_time) AS 最晚到货
     FROM fact_wfs_shipment WHERE store_id='110704872940532224'
      AND DATE(to_receive_time) BETWEEN '2026-06-27' AND '2026-07-10';"
echo "---- done ----"
