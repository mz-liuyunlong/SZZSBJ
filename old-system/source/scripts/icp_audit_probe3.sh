#!/usr/bin/env bash
# icp_audit_probe3.sh —— 补充探针（只读，零写入）
# 【一】RAW真实JSON结构 → 解决「佣金能否取」「赔付带不带ItemId」（上轮路径猜错，本轮先dump结构）
# 【二】同起同止精确对账 → 修正上轮未卡起始日导致的虚高/偏少误判
# 【三】采购 sid=0 链路 → ¥172万采购怎么定店铺再定item
# 【四】期初池拆分基数 → 92%的SKU对多item，按什么拆
exec > /tmp/icp_audit_probe3.log 2>&1
echo "icp_audit_probe3 $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }
qr(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -N -B -e "$1"; }

echo "=============== 【一】RAW 真实 JSON 结构（先看结构再解析）==============="
echo "--- 1.1 statement 响应顶层结构 ---"
qr "SELECT JSON_KEYS(response_json) FROM raw_lingxing_api
     WHERE api_path LIKE '%statement%' ORDER BY id DESC LIMIT 1;"
echo ""
echo "--- 1.2 响应前2500字符原文（看数组挂在哪个key下）---"
qr "SELECT SUBSTRING(CAST(response_json AS CHAR), 1, 2500) FROM raw_lingxing_api
     WHERE api_path LIKE '%statement%' AND JSON_LENGTH(response_json) > 0
     ORDER BY id DESC LIMIT 1;"
echo ""
echo "--- 1.3 常见候选路径的数组长度（定位真实数据路径）---"
q "SELECT JSON_LENGTH(response_json,'\$.data') AS len_data,
          JSON_LENGTH(response_json,'\$.data.list') AS len_data_list,
          JSON_LENGTH(response_json,'\$.data.records') AS len_data_records,
          JSON_LENGTH(response_json,'\$.data.rows') AS len_data_rows,
          JSON_LENGTH(response_json,'\$.list') AS len_list,
          JSON_LENGTH(response_json,'\$.rows') AS len_rows
     FROM raw_lingxing_api WHERE api_path LIKE '%statement%' ORDER BY id DESC LIMIT 3;"
echo ""
echo "--- 1.4 单条交易行的完整字段清单（关键：找 itemId / commission 字段真名）---"
qr "SELECT JSON_PRETTY(JSON_EXTRACT(response_json,'\$.data.list[0]')) FROM raw_lingxing_api
     WHERE api_path LIKE '%statement%' AND JSON_LENGTH(response_json,'\$.data.list')>0
     ORDER BY id DESC LIMIT 1;"
echo ""
qr "SELECT JSON_PRETTY(JSON_EXTRACT(response_json,'\$.data[0]')) FROM raw_lingxing_api
     WHERE api_path LIKE '%statement%' AND JSON_LENGTH(response_json,'\$.data')>0
     ORDER BY id DESC LIMIT 1;"

echo ""
echo "=============== 【二】同起同止精确对账（修正上轮误判）==============="
echo "--- 2.1 各店 账单覆盖区间 vs 管道覆盖区间（先看边界差多少）---"
q "SELECT d.store_name AS 店铺,
          b.bill_min AS 账单最早, b.bill_max AS 账单最晚,
          s.pipe_min AS 仓储表最早, s.pipe_max AS 仓储表最晚,
          i.inb_min AS 入库表最早, i.inb_max AS 入库表最晚
     FROM (SELECT store_id, MIN(period_start) AS bill_min, MAX(period_end) AS bill_max
             FROM fact_reconciliation_item GROUP BY store_id) b
     LEFT JOIN (SELECT store_id, MIN(report_start) AS pipe_min, MAX(report_end) AS pipe_max
                  FROM fact_wfs_storage_fee GROUP BY store_id) s ON s.store_id=b.store_id
     LEFT JOIN (SELECT store_id, MIN(report_start) AS inb_min, MAX(report_end) AS inb_max
                  FROM fact_inbound_freight_alloc GROUP BY store_id) i ON i.store_id=b.store_id
     LEFT JOIN dim_store d ON d.store_id=b.store_id ORDER BY d.store_name;"

echo ""
echo "--- 2.2 仓储费：只比对「账单与管道共同覆盖」的区间（同起同止，剔重叠账期）---"
q "SELECT d.store_name AS 店铺, w.lo AS 共同起, w.hi AS 共同止,
          ROUND(bb.bill,2) AS 账单区间内, ROUND(pp.pipe,2) AS 管道区间内,
          ROUND(pp.pipe-bb.bill,2) AS 差额,
          CASE WHEN ABS(pp.pipe-bb.bill) <= GREATEST(30, ABS(bb.bill)*0.05) THEN '✅一致'
               WHEN pp.pipe > bb.bill THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
     FROM (SELECT b.store_id,
                  GREATEST(b.bill_min, COALESCE(s.pipe_min,b.bill_min)) AS lo,
                  LEAST(b.bill_max, COALESCE(s.pipe_max,b.bill_max)) AS hi
             FROM (SELECT store_id, MIN(period_start) AS bill_min, MAX(period_end) AS bill_max
                     FROM fact_reconciliation_item GROUP BY store_id) b
             LEFT JOIN (SELECT store_id, MIN(report_start) AS pipe_min, MAX(report_end) AS pipe_max
                          FROM fact_wfs_storage_fee GROUP BY store_id) s ON s.store_id=b.store_id) w
     JOIN (SELECT r.store_id, SUM(CASE WHEN r.fee_category='storage' THEN -r.amount ELSE 0 END) AS bill,
                  r.store_id AS sid2 FROM fact_reconciliation_item r GROUP BY r.store_id) bb ON bb.store_id=w.store_id
     JOIN (SELECT s.store_id, SUM(s.final_storage_fee) AS pipe FROM fact_wfs_storage_fee s
            WHERE NOT (s.store_id='110687423514268160'
                       AND ((s.report_start='2026-07-01' AND s.report_end='2026-07-31')
                         OR (s.report_start='2026-07-14' AND s.report_end='2026-08-12')))
            GROUP BY s.store_id) pp ON pp.store_id=w.store_id
     LEFT JOIN dim_store d ON d.store_id=w.store_id ORDER BY d.store_name;"

echo ""
echo "--- 2.3 CN2601 剔除两条重叠账期后，与账单逐账期核对 ---"
q "SELECT DATE_FORMAT(report_start,'%m-%d') AS 期起, DATE_FORMAT(report_end,'%m-%d') AS 期止,
          DATEDIFF(report_end,report_start)+1 AS 天数, ROUND(SUM(final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee WHERE store_id='110687423514268160'
       AND NOT ((report_start='2026-07-01' AND report_end='2026-07-31')
             OR (report_start='2026-07-14' AND report_end='2026-08-12'))
     GROUP BY report_start, report_end ORDER BY report_start;"
q "SELECT DATE_FORMAT(period_start,'%m-%d') AS 账单期起, DATE_FORMAT(period_end,'%m-%d') AS 账单期止,
          ROUND(-SUM(amount),2) AS 账单仓储费
     FROM fact_reconciliation_item WHERE store_id='110687423514268160' AND fee_category='storage'
     GROUP BY period_start, period_end ORDER BY period_start;"

echo ""
echo "=============== 【三】采购 sid=0 链路（¥172万怎么归店归item）==============="
echo "--- 3.1 采购单 sid 分布（多少是0/无效）---"
q "SELECT CASE WHEN COALESCE(i.sid,'') IN ('','0') THEN 'sid为空或0'
               WHEN ds.store_id IS NOT NULL THEN 'sid有效(dim_store命中)'
               ELSE 'sid无效(dim_store查无)' END AS 情况,
          COUNT(*) AS 行数, COUNT(DISTINCT i.sku) AS sku数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash c ON c.order_sn=i.order_sn
     LEFT JOIN dim_store ds ON ds.store_id=i.sid AND ds.platform='walmart'
    WHERE c.order_time>='2026-05-01' AND c.status_text<>'已作废'
    GROUP BY 1 ORDER BY 3 DESC;"

echo ""
echo "--- 3.2 sid=0 的采购SKU 能否经发货单找到店铺+item ---"
q "SELECT CASE WHEN f.sku IS NULL THEN '0-发货单查无此SKU'
               WHEN f.n_store=1 AND f.n_item=1 THEN '1-单店单item(可直落)'
               WHEN f.n_store=1 THEN CONCAT('2-单店多item(',f.n_item,')按发货量拆')
               ELSE CONCAT('3-多店(',f.n_store,')多item(',f.n_item,')按发货量拆') END AS 情况,
          COUNT(*) AS 采购行数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash c ON c.order_sn=i.order_sn
     LEFT JOIN (SELECT sku, COUNT(DISTINCT store_id) AS n_store,
                       COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS n_item
                  FROM fact_shipping_first_let WHERE match_status='matched' AND COALESCE(item_id,'')<>''
                 GROUP BY sku) f ON f.sku=i.sku
    WHERE c.order_time>='2026-05-01' AND c.status_text<>'已作废'
      AND COALESCE(i.sid,'') IN ('','0')
    GROUP BY 1 ORDER BY 1;"

echo ""
echo "=============== 【四】期初池拆分基数（92%的SKU对多item）==============="
echo "--- 4.1 候选基数A：按该SKU下各item的结算销量占比 可用性 ---"
q "SELECT CASE WHEN t.qty IS NULL OR t.qty=0 THEN '无销量(无法按销量拆)' ELSE '有销量(可按销量拆)' END AS 情况,
          COUNT(*) AS sku数, SUM(o.snap_qty_0501) AS 期初数量,
          ROUND(SUM(o.snap_qty_0501*o.opening_unit_cost),2) AS 期初金额CNY
     FROM biz_finance_opening_cost o
     LEFT JOIN (SELECT JSON_UNQUOTE(JSON_EXTRACT(extra_json,'\$.localSku')) AS sku, SUM(sales_num) AS qty
                  FROM fact_settlement_msku_monthly WHERE settlement_month>='2026-05'
                 GROUP BY 1) t ON t.sku=o.sku
    GROUP BY 1;"

echo ""
echo "--- 4.2 候选基数B：按该SKU下各item的期初库存(WFS快照)占比 可用性 ---"
q "SELECT table_name FROM information_schema.tables
    WHERE table_schema=DATABASE() AND (table_name LIKE '%inventory%' OR table_name LIKE '%wfs_snapshot%' OR table_name LIKE '%batch%');"
q "SELECT COUNT(*) AS 行数, COUNT(DISTINCT msku) AS msku数, COUNT(DISTINCT item_id) AS item数,
          MIN(snapshot_date) AS 最早快照, MAX(snapshot_date) AS 最新快照
     FROM fact_inventory_daily WHERE platform='walmart';" 2>/dev/null \
|| q "SHOW COLUMNS FROM fact_inventory_daily;"

echo ""
echo "--- 4.3 期初池表结构（确认只有sku、无msku/item）---"
q "SHOW CREATE TABLE biz_finance_opening_cost\G"
echo "---- done ----"
