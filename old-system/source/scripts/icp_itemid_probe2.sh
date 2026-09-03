#!/usr/bin/env bash
# icp_itemid_probe2.sh —— 批13探针二 + 仓储/入库账期连续性体检（只读，零写入）
# ①各事实表 item_id 列的真实填充率（有列≠有值，决定能否直接按item取数）
# ②B段8个(店,msku)→2个itemid 具体是什么（换绑历史 or 真并存）
# ③E段454个itemid的SKU是不是虚拟SKU
# ④仓储费/入库运输：各店账期覆盖与缺口（需求方要求体检）+ 账期规律（给导入提醒定时任务定口径）
exec > /tmp/icp_itemid_probe2.log 2>&1
echo "icp_itemid_probe2 $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }
echo "MySQL版本:"; q "SELECT VERSION() AS v;"

echo ""
echo "===== ① item_id 填充率（2026-05起；有列≠有值，这是能否直接按item取数的关键）====="
q "SELECT 'recon回款' AS 表, COUNT(*) AS 行数, SUM(COALESCE(item_id,'')<>'') AS 带item行,
          ROUND(100*SUM(COALESCE(item_id,'')<>'')/COUNT(*),1) AS 填充率百分比,
          ROUND(SUM(CASE WHEN COALESCE(item_id,'')='' THEN ABS(amount) ELSE 0 END),2) AS 无item金额
     FROM fact_reconciliation_item WHERE period_end>='2026-05-01';"
q "SELECT '仓储费' AS 表, COUNT(*) AS 行数, SUM(COALESCE(item_id,'')<>'') AS 带item行,
          ROUND(100*SUM(COALESCE(item_id,'')<>'')/COUNT(*),1) AS 填充率百分比,
          ROUND(SUM(CASE WHEN COALESCE(item_id,'')='' THEN ABS(final_storage_fee) ELSE 0 END),2) AS 无item金额
     FROM fact_wfs_storage_fee WHERE report_start>='2026-05-01';"
q "SELECT '入库运输' AS 表, COUNT(*) AS 行数, SUM(COALESCE(item_id,'')<>'') AS 带item行,
          ROUND(100*SUM(COALESCE(item_id,'')<>'')/COUNT(*),1) AS 填充率百分比,
          ROUND(SUM(CASE WHEN COALESCE(item_id,'')='' THEN ABS(alloc_amount) ELSE 0 END),2) AS 无item金额
     FROM fact_inbound_freight_alloc WHERE report_start>='2026-05-01';"
q "SELECT '结算销量' AS 表, COUNT(*) AS 行数, SUM(COALESCE(item_id,'')<>'') AS 带item行,
          ROUND(100*SUM(COALESCE(item_id,'')<>'')/COUNT(*),1) AS 填充率百分比,
          SUM(CASE WHEN COALESCE(item_id,'')='' THEN sales_num ELSE 0 END) AS 无item销量
     FROM fact_settlement_msku_monthly WHERE settlement_month>='2026-05';"
q "SELECT '发货单头程' AS 表, COUNT(*) AS 行数, SUM(COALESCE(item_id,'')<>'') AS 带item行,
          ROUND(100*SUM(COALESCE(item_id,'')<>'')/COUNT(*),1) AS 填充率百分比
     FROM fact_shipping_first_let WHERE match_status='matched';"
q "SELECT '采购明细(看msku填充)' AS 表, COUNT(*) AS 行数, SUM(COALESCE(msku,'')<>'') AS 带msku行,
          ROUND(100*SUM(COALESCE(msku,'')<>'')/COUNT(*),1) AS msku填充率
     FROM fact_purchase_cash_item;"

echo ""
echo "===== ② B段那8个(店,msku)→2个ItemID 具体是什么（含状态/上架日，判换绑还是并存）====="
q "SELECT p.store_id, p.msku, p.item_id, p.sku, p.status, p.walmart_publish_status AS 发布状态,
          p.launch_date AS 上架日, p.product_management_status AS 管理状态
     FROM dim_product p
     JOIN (SELECT store_id, msku FROM dim_product
            WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(msku,'')<>''
            GROUP BY store_id, msku HAVING COUNT(DISTINCT item_id)=2) d
       ON d.store_id=p.store_id AND d.msku=p.msku
    WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
    ORDER BY p.store_id, p.msku, p.item_id;"

echo ""
echo "===== ③ E段那个对应454个ItemID的SKU是谁（确认是虚拟SKU）====="
q "SELECT store_id, sku, COUNT(DISTINCT item_id) AS item数, COUNT(DISTINCT msku) AS msku数
     FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(sku,'')<>''
    GROUP BY store_id, sku HAVING item数>=3 ORDER BY item数 DESC LIMIT 10;"

echo ""
echo "===== ④-1 仓储费：各店账期清单（看是否连续无间断）====="
q "SELECT s.store_id, d.store_name, DATE_FORMAT(s.report_start,'%Y-%m-%d') AS 期起,
          DATE_FORMAT(s.report_end,'%Y-%m-%d') AS 期止,
          DATEDIFF(s.report_end,s.report_start)+1 AS 天数,
          COUNT(*) AS 行数, ROUND(SUM(s.final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee s LEFT JOIN dim_store d ON d.store_id=s.store_id
    GROUP BY s.store_id, d.store_name, s.report_start, s.report_end
    ORDER BY d.store_name, s.report_start;"

echo ""
echo "===== ④-2 仓储费：缺口检测（上期止日+1 <> 下期起日 即为断档）====="
q "SELECT store_name, 上期止, 下期起, DATEDIFF(下期起,上期止)-1 AS 缺口天数 FROM (
     SELECT d.store_name,
            DATE_FORMAT(s.report_end,'%Y-%m-%d') AS 上期止,
            DATE_FORMAT(LEAD(s.report_start) OVER (PARTITION BY s.store_id ORDER BY s.report_start),'%Y-%m-%d') AS 下期起,
            s.report_end AS re,
            LEAD(s.report_start) OVER (PARTITION BY s.store_id ORDER BY s.report_start) AS nx
       FROM (SELECT DISTINCT store_id, report_start, report_end FROM fact_wfs_storage_fee) s
       LEFT JOIN dim_store d ON d.store_id=s.store_id) t
    WHERE nx IS NOT NULL AND DATEDIFF(nx,re)<>1 ORDER BY store_name, 上期止;"

echo ""
echo "===== ④-3 入库运输：各店账期清单 ====="
q "SELECT i.store_id, d.store_name, DATE_FORMAT(i.report_start,'%Y-%m-%d') AS 期起,
          DATE_FORMAT(i.report_end,'%Y-%m-%d') AS 期止,
          COUNT(*) AS 行数, ROUND(SUM(i.alloc_amount),2) AS 金额
     FROM fact_inbound_freight_alloc i LEFT JOIN dim_store d ON d.store_id=i.store_id
    GROUP BY i.store_id, d.store_name, i.report_start, i.report_end
    ORDER BY d.store_name, i.report_start;"

echo ""
echo "===== ④-4 入库运输：缺口检测 ====="
q "SELECT store_name, 上期止, 下期起, DATEDIFF(下期起,上期止)-1 AS 缺口天数 FROM (
     SELECT d.store_name,
            DATE_FORMAT(i.report_end,'%Y-%m-%d') AS 上期止,
            DATE_FORMAT(LEAD(i.report_start) OVER (PARTITION BY i.store_id ORDER BY i.report_start),'%Y-%m-%d') AS 下期起,
            i.report_end AS re,
            LEAD(i.report_start) OVER (PARTITION BY i.store_id ORDER BY i.report_start) AS nx
       FROM (SELECT DISTINCT store_id, report_start, report_end FROM fact_inbound_freight_alloc) i
       LEFT JOIN dim_store d ON d.store_id=i.store_id) t
    WHERE nx IS NOT NULL AND DATEDIFF(nx,re)<>1 ORDER BY store_name, 上期止;"

echo ""
echo "===== ④-5 账期规律 + 最新已导账期（给「账单出来第二天提醒导入」定时任务定口径）====="
q "SELECT '仓储费' AS 报表, COUNT(DISTINCT CONCAT(report_start,'~',report_end)) AS 账期数,
          MIN(report_start) AS 最早起, MAX(report_end) AS 最新止,
          ROUND(AVG(DATEDIFF(report_end,report_start)+1),1) AS 平均账期天数,
          MAX(imported_at) AS 最近导入时间
     FROM fact_wfs_storage_fee;"
q "SELECT '入库运输' AS 报表, COUNT(DISTINCT CONCAT(report_start,'~',report_end)) AS 账期数,
          MIN(report_start) AS 最早起, MAX(report_end) AS 最新止,
          ROUND(AVG(DATEDIFF(report_end,report_start)+1),1) AS 平均账期天数,
          MAX(imported_at) AS 最近导入时间
     FROM fact_inbound_freight_alloc;"
q "SELECT '回款账期(参照:账单节奏)' AS 报表, COUNT(*) AS 账期数,
          MAX(period_end) AS 最新账期止
     FROM fact_reconciliation_period;"
echo "---- done ----"
