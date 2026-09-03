#!/usr/bin/env bash
# icp_audit_probe4.sh —— 收口探针（只读，零写入）。路径已确认为 $.list[*]
# 【一】账单全部 amountType 分布 + 各自带不带 partnerItemId/GTIN → 赔付能否落item、佣金量级
# 【二】发货单 delivery_num 作为拆分基数的完整性 → 期初池/采购按发货单拆的覆盖率
# 【三】按天摊平的精确对账 → 一次算准各店仓储/入库真实差额
exec > /tmp/icp_audit_probe4.log 2>&1
echo "icp_audit_probe4 $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "=============== 【一】账单 amountType 全景 + item标识可用性 ==============="
echo "--- 1.1 全部 amountType × transactionType 分布（含带item率）---"
q "SELECT JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.transactionType')) AS 交易类型,
          JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.amountType')) AS 金额类型,
          COUNT(*) AS 行数,
          ROUND(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.amount')),'null'),'0') AS DECIMAL(18,4))),2) AS 金额,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.partnerItemId')),'') NOT IN ('','null')) AS 带MSKU行,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.partnerGtin')),'') NOT IN ('','null')) AS 带GTIN行
     FROM raw_lingxing_api r
     JOIN JSON_TABLE(r.response_json,'\$.list[*]' COLUMNS(v JSON PATH '\$')) j
    WHERE r.api_path LIKE '%statement%'
    GROUP BY 1,2 ORDER BY ABS(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.amount')),'null'),'0') AS DECIMAL(18,4)))) DESC
    LIMIT 40;"

echo ""
echo "--- 1.2 佣金行专项：量级 + 折扣 + 是否可按item落 ---"
q "SELECT JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.storeName')) AS 店铺,
          COUNT(*) AS 佣金行数,
          ROUND(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.amount')),'null'),'0') AS DECIMAL(18,4))),2) AS 实收佣金,
          ROUND(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.originalCommission')),'null'),'0') AS DECIMAL(18,4))),2) AS 原始佣金,
          ROUND(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.commissionSaving')),'null'),'0') AS DECIMAL(18,4))),2) AS 佣金折扣,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.partnerItemId')),'') NOT IN ('','null')) AS 带MSKU行
     FROM raw_lingxing_api r
     JOIN JSON_TABLE(r.response_json,'\$.list[*]' COLUMNS(v JSON PATH '\$')) j
    WHERE r.api_path LIKE '%statement%'
      AND JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.amountType')) LIKE '%ommission%'
    GROUP BY 1 ORDER BY 3;"

echo ""
echo "--- 1.3 赔付/返还类（非Sale交易）是否带 item 标识 ---"
q "SELECT JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.transactionType')) AS 交易类型,
          COUNT(*) AS 行数,
          ROUND(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.amount')),'null'),'0') AS DECIMAL(18,4))),2) AS 金额,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.partnerItemId')),'') NOT IN ('','null')) AS 带MSKU行,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.partnerGtin')),'') NOT IN ('','null')) AS 带GTIN行,
          ROUND(100*SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.partnerItemId')),'') NOT IN ('','null'))/COUNT(*),1) AS 带MSKU率
     FROM raw_lingxing_api r
     JOIN JSON_TABLE(r.response_json,'\$.list[*]' COLUMNS(v JSON PATH '\$')) j
    WHERE r.api_path LIKE '%statement%'
      AND JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.transactionType')) <> 'Sale'
    GROUP BY 1 ORDER BY ABS(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.amount')),'null'),'0') AS DECIMAL(18,4)))) DESC;"

echo ""
echo "=============== 【二】发货单作为拆分基数的完整性（需求方：必须按发货单算）==============="
echo "--- 2.1 发货单 sku→item 的发货量分布（拆分权重来源）---"
q "SELECT COUNT(DISTINCT sku) AS sku数, COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS 店item数,
          SUM(delivery_num) AS 总发货量, COUNT(*) AS 明细行,
          MIN(cash_date) AS 最早, MAX(cash_date) AS 最晚
     FROM fact_shipping_first_let WHERE match_status='matched' AND COALESCE(item_id,'')<>'';"

echo ""
echo "--- 2.2 期初池205个SKU：能否在发货单里找到 item 及发货量（决定期初能否按发货单拆）---"
q "SELECT CASE WHEN f.sku IS NULL THEN '0-发货单查无(需人工)'
               WHEN f.n_item=1 THEN '1-单item直落'
               ELSE CONCAT('2-多item(',f.n_item,')按发货量拆') END AS 情况,
          COUNT(*) AS sku数, SUM(o.snap_qty_0501) AS 期初数量,
          ROUND(SUM(o.snap_qty_0501*o.opening_unit_cost),2) AS 期初金额CNY
     FROM biz_finance_opening_cost o
     LEFT JOIN (SELECT sku, COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS n_item, SUM(delivery_num) AS qty
                  FROM fact_shipping_first_let WHERE match_status='matched' AND COALESCE(item_id,'')<>''
                 GROUP BY sku) f ON f.sku=o.sku
    GROUP BY 1 ORDER BY 1;"

echo ""
echo "--- 2.3 期初池按发货单拆分示例（前10个SKU，看权重是否合理）---"
q "SELECT o.sku, o.snap_qty_0501 AS 期初数量, f.store_id, f.item_id,
          f.qty AS 该item发货量, t.tot AS SKU总发货量,
          ROUND(o.snap_qty_0501 * f.qty / t.tot, 2) AS 应分得期初数量
     FROM biz_finance_opening_cost o
     JOIN (SELECT sku, store_id, item_id, SUM(delivery_num) AS qty
             FROM fact_shipping_first_let WHERE match_status='matched' AND COALESCE(item_id,'')<>''
            GROUP BY sku, store_id, item_id) f ON f.sku=o.sku
     JOIN (SELECT sku, SUM(delivery_num) AS tot FROM fact_shipping_first_let
            WHERE match_status='matched' AND COALESCE(item_id,'')<>'' GROUP BY sku) t ON t.sku=o.sku
    WHERE o.snap_qty_0501>0
    ORDER BY o.snap_qty_0501*o.opening_unit_cost DESC LIMIT 20;"

echo ""
echo "--- 2.4 采购73行发货单查无的SKU 是什么（¥29.8万需人工）---"
q "SELECT i.sku, COUNT(*) AS 采购行数, ROUND(SUM(i.amount),2) AS 金额CNY,
          MAX(c.order_time) AS 最近采购日
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash c ON c.order_sn=i.order_sn
     LEFT JOIN (SELECT DISTINCT sku FROM fact_shipping_first_let
                 WHERE match_status='matched' AND COALESCE(item_id,'')<>'') f ON f.sku=i.sku
    WHERE c.order_time>='2026-05-01' AND c.status_text<>'已作废'
      AND COALESCE(i.sid,'') IN ('','0') AND f.sku IS NULL
    GROUP BY i.sku ORDER BY 3 DESC LIMIT 20;"

echo ""
echo "=============== 【三】按天摊平的精确对账（一次算准）==============="
echo "--- 3.1 仓储费：管道按天摊入账单区间后对比（剔CN2601两条重叠）---"
q "WITH RECURSIVE dates AS (
     SELECT DATE('2026-03-01') AS d UNION ALL SELECT d+INTERVAL 1 DAY FROM dates WHERE d < '2026-08-31'),
   pipe_day AS (
     SELECT s.store_id, dt.d, s.final_storage_fee/(DATEDIFF(s.report_end,s.report_start)+1) AS amt
       FROM fact_wfs_storage_fee s JOIN dates dt
         ON dt.d BETWEEN s.report_start AND s.report_end
      WHERE NOT (s.store_id='110687423514268160'
                 AND ((s.report_start='2026-07-01' AND s.report_end='2026-07-31')
                   OR (s.report_start='2026-07-14' AND s.report_end='2026-08-12')))),
   bill AS (
     SELECT store_id, MIN(period_start) AS lo, MAX(period_end) AS hi,
            SUM(CASE WHEN fee_category='storage' THEN -amount ELSE 0 END) AS bill_amt
       FROM fact_reconciliation_item GROUP BY store_id)
   SELECT ds.store_name AS 店铺, b.lo AS 账单起, b.hi AS 账单止,
          ROUND(b.bill_amt,2) AS 账单仓储费,
          ROUND(SUM(p.amt),2) AS 管道摊入同区间,
          ROUND(SUM(p.amt)-b.bill_amt,2) AS 差额,
          CASE WHEN ABS(SUM(p.amt)-b.bill_amt) <= GREATEST(30,ABS(b.bill_amt)*0.05) THEN '✅一致'
               WHEN SUM(p.amt) > b.bill_amt THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
     FROM bill b JOIN pipe_day p ON p.store_id=b.store_id AND p.d BETWEEN b.lo AND b.hi
     LEFT JOIN dim_store ds ON ds.store_id=b.store_id
    GROUP BY ds.store_name, b.store_id, b.lo, b.hi, b.bill_amt ORDER BY ds.store_name;"

echo ""
echo "--- 3.2 入库运输：同法对比 ---"
q "WITH RECURSIVE dates AS (
     SELECT DATE('2026-03-01') AS d UNION ALL SELECT d+INTERVAL 1 DAY FROM dates WHERE d < '2026-08-31'),
   pipe_day AS (
     SELECT i.store_id, dt.d, i.alloc_amount/(DATEDIFF(i.report_end,i.report_start)+1) AS amt
       FROM fact_inbound_freight_alloc i JOIN dates dt
         ON dt.d BETWEEN i.report_start AND i.report_end),
   bill AS (
     SELECT store_id, MIN(period_start) AS lo, MAX(period_end) AS hi,
            SUM(CASE WHEN fee_category='inbound_transport' THEN -amount ELSE 0 END) AS bill_amt
       FROM fact_reconciliation_item GROUP BY store_id)
   SELECT ds.store_name AS 店铺, ROUND(b.bill_amt,2) AS 账单入库费,
          ROUND(SUM(p.amt),2) AS 管道摊入同区间, ROUND(SUM(p.amt)-b.bill_amt,2) AS 差额,
          CASE WHEN ABS(SUM(p.amt)-b.bill_amt) <= GREATEST(30,ABS(b.bill_amt)*0.05) THEN '✅一致'
               WHEN SUM(p.amt) > b.bill_amt THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
     FROM bill b JOIN pipe_day p ON p.store_id=b.store_id AND p.d BETWEEN b.lo AND b.hi
     LEFT JOIN dim_store ds ON ds.store_id=b.store_id
    GROUP BY ds.store_name, b.store_id, b.bill_amt ORDER BY ds.store_name;"
echo "---- done ----"
