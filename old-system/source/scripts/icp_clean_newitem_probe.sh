#!/usr/bin/env bash
# icp_clean_newitem_probe.sh —— 批13第一步：「干净新品」家底盘点（只读，零写入）
# 干净新品定义（需求方2026-08-14拍板：先做没有历史遗留的新品）：
#   该 item 对应的本地SKU **不在期初池** 或 **期初数量为0** → 无一刀切争议、无需按发货单拆期初，
#   采购/头程全在切点后可全额追溯 → 现金利润能算准、可逐个核到账单。
# 虚拟SKU(XY2007/DC001/QH888)整行豁免，不计入。
exec > /tmp/icp_clean_newitem_probe.log 2>&1
echo "icp_clean_newitem_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "===== 1. 干净新品 vs 老品：item 数量对比 ====="
q "SELECT CASE WHEN o.sku IS NULL THEN '干净新品(SKU不在期初池)'
               WHEN COALESCE(o.snap_qty_0501,0)=0 THEN '干净新品(期初数量为0)'
               ELSE '老品(有期初池)' END AS 分类,
          COUNT(DISTINCT CONCAT(p.store_id,'|',p.item_id)) AS 店item数,
          COUNT(DISTINCT p.sku) AS SKU数
     FROM dim_product p
     LEFT JOIN biz_finance_opening_cost o ON o.sku=p.sku AND o.cutoff_date='2026-05-01'
    WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
      AND COALESCE(p.sku,'') NOT IN ('XY2007','DC001','QH888','')
    GROUP BY 1 ORDER BY 2 DESC;"

echo ""
echo "===== 2. 【关键】收入占比：干净新品 vs 老品（recon sale，2026-05起）====="
q "SELECT CASE WHEN c.item_id IS NOT NULL THEN '干净新品' ELSE '老品/其它' END AS 分类,
          COUNT(DISTINCT CONCAT(r.store_id,'|',r.item_id)) AS 店item数,
          ROUND(SUM(r.amount),2) AS 销售额USD
     FROM fact_reconciliation_item r
     LEFT JOIN (SELECT DISTINCT p.store_id, p.item_id FROM dim_product p
                  LEFT JOIN biz_finance_opening_cost o ON o.sku=p.sku AND o.cutoff_date='2026-05-01'
                 WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
                   AND COALESCE(p.sku,'') NOT IN ('XY2007','DC001','QH888','')
                   AND (o.sku IS NULL OR COALESCE(o.snap_qty_0501,0)=0)) c
            ON c.store_id=r.store_id AND c.item_id=r.item_id
    WHERE r.fee_category='sale' AND r.period_end>='2026-05-01' AND COALESCE(r.item_id,'')<>''
    GROUP BY 1 ORDER BY 3 DESC;"

echo ""
echo "===== 3. 干净新品的各成本路径覆盖（能否算全）====="
q "WITH clean AS (
     SELECT DISTINCT p.store_id, p.item_id, p.sku FROM dim_product p
       LEFT JOIN biz_finance_opening_cost o ON o.sku=p.sku AND o.cutoff_date='2026-05-01'
      WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
        AND COALESCE(p.sku,'') NOT IN ('XY2007','DC001','QH888','')
        AND (o.sku IS NULL OR COALESCE(o.snap_qty_0501,0)=0))
   SELECT '收入(recon sale)' AS 路径, COUNT(DISTINCT CONCAT(r.store_id,'|',r.item_id)) AS 覆盖店item数,
          ROUND(SUM(r.amount),2) AS 金额
     FROM fact_reconciliation_item r JOIN clean c ON c.store_id=r.store_id AND c.item_id=r.item_id
    WHERE r.fee_category='sale' AND r.period_end>='2026-05-01'
   UNION ALL
   SELECT '广告(fact_ads_product_daily)', COUNT(DISTINCT CONCAT(a.store_id,'|',a.item_id)), ROUND(SUM(a.ad_spend),2)
     FROM fact_ads_product_daily a JOIN clean c ON c.store_id=a.store_id AND c.item_id=a.item_id
    WHERE a.platform='walmart' AND a.stat_date>='2026-05-01'
   UNION ALL
   SELECT '仓储费', COUNT(DISTINCT CONCAT(s.store_id,'|',s.item_id)), ROUND(SUM(s.final_storage_fee),2)
     FROM fact_wfs_storage_fee s JOIN clean c ON c.store_id=s.store_id AND c.item_id=s.item_id
    WHERE s.report_start>='2026-05-01'
   UNION ALL
   SELECT '入库运输', COUNT(DISTINCT CONCAT(i.store_id,'|',i.item_id)), ROUND(SUM(i.alloc_amount),2)
     FROM fact_inbound_freight_alloc i JOIN clean c ON c.store_id=i.store_id AND c.item_id=i.item_id
    WHERE i.report_start>='2026-05-01'
   UNION ALL
   SELECT '头程(发货单)', COUNT(DISTINCT CONCAT(f.store_id,'|',f.item_id)),
          ROUND(SUM(f.per_first_let_cost*f.delivery_num),2)
     FROM fact_shipping_first_let f JOIN clean c ON c.store_id=f.store_id AND c.item_id=f.item_id
    WHERE f.match_status='matched' AND f.cash_date>='2026-05-01' AND f.value_source<>'预估费用'
   UNION ALL
   SELECT 'SEM(账单表)', COUNT(DISTINCT CONCAT(b.store_id,'|',b.item_id)),
          ROUND(SUM(CASE WHEN b.charge_type='DEBIT' THEN b.line_amount ELSE -b.line_amount END),2)
     FROM fact_sem_billing_daily b JOIN clean c ON c.store_id=b.store_id AND c.item_id=b.item_id;"

echo ""
echo "===== 4. 干净新品的采购能否归属（按SKU查采购单）====="
q "WITH clean AS (
     SELECT DISTINCT p.sku FROM dim_product p
       LEFT JOIN biz_finance_opening_cost o ON o.sku=p.sku AND o.cutoff_date='2026-05-01'
      WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
        AND COALESCE(p.sku,'') NOT IN ('XY2007','DC001','QH888','')
        AND (o.sku IS NULL OR COALESCE(o.snap_qty_0501,0)=0))
   SELECT CASE WHEN COALESCE(i.sid,'') NOT IN ('','0') THEN '1-采购单自带店铺(可直落)'
               WHEN f.sku IS NOT NULL THEN '2-经发货单可定店定item'
               ELSE '3-发货单查无(新品未发货/待人工)' END AS 情况,
          COUNT(*) AS 采购行数, COUNT(DISTINCT i.sku) AS SKU数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i
     JOIN fact_purchase_cash pc ON pc.order_sn=i.order_sn
     JOIN clean c ON c.sku=i.sku
     LEFT JOIN (SELECT DISTINCT sku FROM fact_shipping_first_let
                 WHERE match_status='matched' AND COALESCE(item_id,'')<>'') f ON f.sku=i.sku
    WHERE pc.order_time>='2026-05-01' AND pc.status_text<>'已作废'
    GROUP BY 1 ORDER BY 1;"

echo ""
echo "===== 5. 抽样：收入TOP15 干净新品（供人工逐个核账单）====="
q "WITH clean AS (
     SELECT DISTINCT p.store_id, p.item_id, MAX(p.sku) AS sku, MAX(p.msku) AS msku, MAX(p.owner) AS owner
       FROM dim_product p
       LEFT JOIN biz_finance_opening_cost o ON o.sku=p.sku AND o.cutoff_date='2026-05-01'
      WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
        AND COALESCE(p.sku,'') NOT IN ('XY2007','DC001','QH888','')
        AND (o.sku IS NULL OR COALESCE(o.snap_qty_0501,0)=0)
      GROUP BY p.store_id, p.item_id)
   SELECT d.store_name AS 店铺, c.item_id, c.sku, c.msku, c.owner AS 负责人,
          ROUND(SUM(r.amount),2) AS 销售额USD
     FROM clean c
     JOIN fact_reconciliation_item r ON r.store_id=c.store_id AND r.item_id=c.item_id
      AND r.fee_category='sale' AND r.period_end>='2026-05-01'
     LEFT JOIN dim_store d ON d.store_id=c.store_id
    GROUP BY d.store_name, c.item_id, c.sku, c.msku, c.owner
    ORDER BY 销售额USD DESC LIMIT 15;"
echo "---- done ----"
