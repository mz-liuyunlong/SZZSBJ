#!/usr/bin/env bash
# icp_full_audit_probe.sh —— 全量存疑问题一次探清（只读，零写入）
# 【一】全店重叠账期扫描（仓储+入库，不只CN2601）——清理范围与防重方案的依据
# 【二】区间聚合法重算真实缺口（修正按账期join的误报）
# 【三】RAW原始账单行：赔付类是否带ItemId / Sale行佣金字段是否可用
# 【四】批13剩余未知：settlement回填率 / 采购拆分覆盖率 / 期初池拆分 / 虚拟SKU
exec > /tmp/icp_full_audit_probe.log 2>&1
echo "icp_full_audit_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "=============== 【一】全店重叠账期扫描（清理范围）==============="
echo "--- 1.1 仓储费：所有互相重叠的账期对（全部店铺）---"
q "SELECT d.store_name AS 店铺,
          CONCAT(a.report_start,'~',a.report_end) AS 账期A, a.days_a AS A天数, ROUND(a.amt,2) AS A金额,
          CONCAT(b.report_start,'~',b.report_end) AS 账期B, b.days_b AS B天数, ROUND(b.amt,2) AS B金额,
          GREATEST(0, DATEDIFF(LEAST(a.report_end,b.report_end), GREATEST(a.report_start,b.report_start))+1) AS 重叠天数
     FROM (SELECT store_id, report_start, report_end, DATEDIFF(report_end,report_start)+1 AS days_a, SUM(final_storage_fee) AS amt
             FROM fact_wfs_storage_fee GROUP BY store_id, report_start, report_end) a
     JOIN (SELECT store_id, report_start, report_end, DATEDIFF(report_end,report_start)+1 AS days_b, SUM(final_storage_fee) AS amt
             FROM fact_wfs_storage_fee GROUP BY store_id, report_start, report_end) b
       ON a.store_id=b.store_id
      AND (a.report_start < b.report_start OR (a.report_start=b.report_start AND a.report_end < b.report_end))
      AND a.report_start <= b.report_end AND b.report_start <= a.report_end
     LEFT JOIN dim_store d ON d.store_id=a.store_id
    ORDER BY d.store_name, a.report_start;"

echo ""
echo "--- 1.2 入库运输：所有互相重叠的账期对 ---"
q "SELECT d.store_name AS 店铺,
          CONCAT(a.report_start,'~',a.report_end) AS 账期A, ROUND(a.amt,2) AS A金额,
          CONCAT(b.report_start,'~',b.report_end) AS 账期B, ROUND(b.amt,2) AS B金额,
          GREATEST(0, DATEDIFF(LEAST(a.report_end,b.report_end), GREATEST(a.report_start,b.report_start))+1) AS 重叠天数
     FROM (SELECT store_id, report_start, report_end, SUM(alloc_amount) AS amt
             FROM fact_inbound_freight_alloc GROUP BY store_id, report_start, report_end) a
     JOIN (SELECT store_id, report_start, report_end, SUM(alloc_amount) AS amt
             FROM fact_inbound_freight_alloc GROUP BY store_id, report_start, report_end) b
       ON a.store_id=b.store_id
      AND (a.report_start < b.report_start OR (a.report_start=b.report_start AND a.report_end < b.report_end))
      AND a.report_start <= b.report_end AND b.report_start <= a.report_end
     LEFT JOIN dim_store d ON d.store_id=a.store_id
    ORDER BY d.store_name, a.report_start;"

echo ""
echo "--- 1.3 非标准账期清单（天数<>14，即自定义区间导入）---"
q "SELECT '仓储费' AS 表, d.store_name AS 店铺, s.report_start AS 期起, s.report_end AS 期止,
          DATEDIFF(s.report_end,s.report_start)+1 AS 天数, COUNT(*) AS 行数, ROUND(SUM(s.final_storage_fee),2) AS 金额,
          MIN(s.created_at) AS 导入时间, MIN(s.source_task_id) AS 批次
     FROM fact_wfs_storage_fee s LEFT JOIN dim_store d ON d.store_id=s.store_id
    WHERE DATEDIFF(s.report_end,s.report_start)+1 <> 14
    GROUP BY d.store_name, s.report_start, s.report_end ORDER BY d.store_name, s.report_start;"
q "SELECT '入库运输' AS 表, d.store_name AS 店铺, i.report_start AS 期起, i.report_end AS 期止,
          DATEDIFF(i.report_end,i.report_start)+1 AS 天数, COUNT(*) AS 行数, ROUND(SUM(i.alloc_amount),2) AS 金额
     FROM fact_inbound_freight_alloc i LEFT JOIN dim_store d ON d.store_id=i.store_id
    WHERE DATEDIFF(i.report_end,i.report_start)+1 <> 14
    GROUP BY d.store_name, i.report_start, i.report_end ORDER BY d.store_name, i.report_start;"

echo ""
echo "=============== 【二】区间聚合法：真实缺口重算（修正误报）==============="
echo "--- 2.1 仓储费：同截止日(账单最新账期止)下 Σ账单 vs Σ管道 ---"
q "SELECT d.store_name AS 店铺,
          MAX(b.cut) AS 对比截止日,
          ROUND(MAX(b.bill),2) AS 账单累计,
          ROUND(MAX(p.pipe),2) AS 管道累计,
          ROUND(MAX(p.pipe)-MAX(b.bill),2) AS 差额,
          CASE WHEN MAX(p.pipe)-MAX(b.bill) > GREATEST(50,ABS(MAX(b.bill))*0.05) THEN '⚠️管道虚高(疑重复导入)'
               WHEN MAX(b.bill)-MAX(p.pipe) > GREATEST(50,ABS(MAX(b.bill))*0.05) THEN '❗管道偏少(疑漏导)'
               ELSE '✅基本一致' END AS 判定
     FROM (SELECT r.store_id, MAX(r.period_end) AS cut,
                  SUM(CASE WHEN r.fee_category='storage' THEN -r.amount ELSE 0 END) AS bill
             FROM fact_reconciliation_item r GROUP BY r.store_id) b
     JOIN (SELECT s.store_id, SUM(s.final_storage_fee) AS pipe FROM fact_wfs_storage_fee s
            WHERE s.report_end <= (SELECT MAX(period_end) FROM fact_reconciliation_item r2 WHERE r2.store_id=s.store_id)
            GROUP BY s.store_id) p ON p.store_id=b.store_id
     LEFT JOIN dim_store d ON d.store_id=b.store_id
    GROUP BY d.store_name, b.store_id ORDER BY d.store_name;"

echo ""
echo "--- 2.2 入库运输：同口径对比 ---"
q "SELECT d.store_name AS 店铺,
          ROUND(MAX(b.bill),2) AS 账单累计, ROUND(MAX(p.pipe),2) AS 管道累计,
          ROUND(MAX(p.pipe)-MAX(b.bill),2) AS 差额,
          CASE WHEN MAX(p.pipe)-MAX(b.bill) > GREATEST(50,ABS(MAX(b.bill))*0.05) THEN '⚠️管道虚高'
               WHEN MAX(b.bill)-MAX(p.pipe) > GREATEST(50,ABS(MAX(b.bill))*0.05) THEN '❗管道偏少(疑漏导)'
               ELSE '✅基本一致' END AS 判定
     FROM (SELECT r.store_id, SUM(CASE WHEN r.fee_category='inbound_transport' THEN -r.amount ELSE 0 END) AS bill
             FROM fact_reconciliation_item r GROUP BY r.store_id) b
     JOIN (SELECT i.store_id, SUM(i.alloc_amount) AS pipe FROM fact_inbound_freight_alloc i
            WHERE i.report_end <= (SELECT MAX(period_end) FROM fact_reconciliation_item r2 WHERE r2.store_id=i.store_id)
            GROUP BY i.store_id) p ON p.store_id=b.store_id
     LEFT JOIN dim_store d ON d.store_id=b.store_id
    GROUP BY d.store_name, b.store_id ORDER BY d.store_name;"

echo ""
echo "--- 2.3 剔除重叠账期后，仓储费是否与账单对上（验证清理方案有效性）---"
q "SELECT d.store_name AS 店铺,
          ROUND(MAX(b.bill),2) AS 账单累计,
          ROUND(MAX(p.pipe14),2) AS 管道仅14天账期,
          ROUND(MAX(p.pipe14)-MAX(b.bill),2) AS 差额
     FROM (SELECT r.store_id, SUM(CASE WHEN r.fee_category='storage' THEN -r.amount ELSE 0 END) AS bill
             FROM fact_reconciliation_item r GROUP BY r.store_id) b
     JOIN (SELECT s.store_id, SUM(s.final_storage_fee) AS pipe14 FROM fact_wfs_storage_fee s
            WHERE DATEDIFF(s.report_end,s.report_start)+1=14
              AND s.report_end <= (SELECT MAX(period_end) FROM fact_reconciliation_item r2 WHERE r2.store_id=s.store_id)
            GROUP BY s.store_id) p ON p.store_id=b.store_id
     LEFT JOIN dim_store d ON d.store_id=b.store_id
    GROUP BY d.store_name, b.store_id ORDER BY d.store_name;"

echo ""
echo "=============== 【三】RAW原始账单行：赔付ItemId / 佣金字段 ==============="
echo "--- 3.1 statement RAW 样本的字段结构（看有哪些key）---"
q "SELECT api_path, COUNT(*) AS 行数 FROM raw_lingxing_api
    WHERE api_path LIKE '%statement%' OR api_path LIKE '%payout%' GROUP BY api_path;"
q "SELECT JSON_KEYS(JSON_EXTRACT(response_json,'\$.data[0]')) AS 首行字段清单
     FROM raw_lingxing_api WHERE api_path LIKE '%statement%'
       AND JSON_LENGTH(JSON_EXTRACT(response_json,'\$.data'))>0 ORDER BY id DESC LIMIT 1;"

echo ""
echo "--- 3.2 赔付/返还类交易行 是否带 itemId（决定能否按item直落）---"
q "SELECT JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.transactionType')) AS 交易类型,
          COUNT(*) AS 行数,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.itemId')),'') NOT IN ('','null')) AS 带itemId行,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.partnerItemId')),'') NOT IN ('','null')) AS 带partnerItemId行
     FROM raw_lingxing_api r
     JOIN JSON_TABLE(r.response_json,'\$.data[*]' COLUMNS(v JSON PATH '\$')) j
    WHERE r.api_path LIKE '%statement%'
    GROUP BY 交易类型 ORDER BY 行数 DESC LIMIT 25;"

echo ""
echo "--- 3.3 Sale行佣金字段可用性（originalCommission等，决定佣金能否展示）---"
q "SELECT COUNT(*) AS Sale行数,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.originalCommission')),'') NOT IN ('','null')) AS 带originalCommission,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.commissionRate')),'') NOT IN ('','null')) AS 带commissionRate,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.commissionSaving')),'') NOT IN ('','null')) AS 带commissionSaving,
          ROUND(SUM(CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.originalCommission')),'null'),'0') AS DECIMAL(18,4))),2) AS Σ原始佣金
     FROM raw_lingxing_api r
     JOIN JSON_TABLE(r.response_json,'\$.data[*]' COLUMNS(v JSON PATH '\$')) j
    WHERE r.api_path LIKE '%statement%'
      AND JSON_UNQUOTE(JSON_EXTRACT(j.v,'\$.transactionType')) LIKE '%ale%';"

echo ""
echo "=============== 【四】批13剩余未知 ==============="
echo "--- 4.1 settlement销量 item_id 回填可行性（按(店,msku)唯一命中）---"
q "SELECT COUNT(*) AS 总行数,
          SUM(CASE WHEN d.n=1 THEN 1 ELSE 0 END) AS 可唯一回填行,
          SUM(CASE WHEN d.n IS NULL THEN 1 ELSE 0 END) AS 维表查无行,
          SUM(CASE WHEN d.n>1 THEN 1 ELSE 0 END) AS 一对多行,
          SUM(CASE WHEN d.n=1 THEN s.sales_num ELSE 0 END) AS 可回填销量,
          SUM(CASE WHEN d.n IS NULL THEN s.sales_num ELSE 0 END) AS 无法回填销量
     FROM fact_settlement_msku_monthly s
     LEFT JOIN (SELECT store_id, msku, COUNT(DISTINCT item_id) AS n FROM dim_product
                 WHERE platform='walmart' AND COALESCE(item_id,'')<>'' GROUP BY store_id, msku) d
       ON d.store_id=s.store_id AND d.msku=s.msku
    WHERE s.settlement_month>='2026-05';"

echo ""
echo "--- 4.2 采购：按(店,sku)能否直落item / 需按发货单拆的比例 ---"
q "SELECT CASE WHEN d.n=1 THEN '1-唯一item可直落' WHEN d.n IS NULL THEN '0-维表查无' ELSE '2-多item需按发货单拆' END AS 情况,
          COUNT(*) AS 行数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i
     JOIN fact_purchase_cash c ON c.order_sn=i.order_sn
     LEFT JOIN (SELECT store_id, sku, COUNT(DISTINCT item_id) AS n FROM dim_product
                 WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(sku,'')<>''
                 GROUP BY store_id, sku) d ON d.store_id=i.sid AND d.sku=i.sku
    WHERE c.order_time>='2026-05-01' AND c.status_text<>'已作废'
    GROUP BY 1 ORDER BY 1;"

echo ""
echo "--- 4.3 期初池：sku 能否拆到 item（池表只有sku）---"
q "SELECT CASE WHEN d.n=1 THEN '1-唯一item' WHEN d.n IS NULL THEN '0-维表查无' ELSE CONCAT('2-多item(',d.n,')') END AS 情况,
          COUNT(*) AS sku数, SUM(o.snap_qty_0501) AS 期初数量,
          ROUND(SUM(o.snap_qty_0501*o.opening_unit_cost),2) AS 期初金额CNY
     FROM biz_finance_opening_cost o
     LEFT JOIN (SELECT sku, COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS n FROM dim_product
                 WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(sku,'')<>''
                 GROUP BY sku) d ON d.sku=o.sku
    GROUP BY 1 ORDER BY 1;"

echo ""
echo "--- 4.4 虚拟SKU确认（XY2007/DC001/QH888 涉及多少item与金额）---"
q "SELECT sku, COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS item数, COUNT(DISTINCT store_id) AS 店铺数
     FROM dim_product WHERE platform='walmart' AND sku IN ('XY2007','DC001','QH888') GROUP BY sku;"
echo "---- done ----"
