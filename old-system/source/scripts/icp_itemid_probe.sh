#!/usr/bin/env bash
# icp_itemid_probe.sh —— 批13只读探针：单品现金利润改按 ITEM_ID 维度的可行性实测（零写入）
# 核心问的问题：各路钱的原生粒度能不能落到 item_id；(店,msku)→item_id 有多唯一；SKU级的钱怎么拆。
exec > /tmp/icp_itemid_probe.log 2>&1
echo "icp_itemid_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "===== A. 各事实表到底有没有 item_id / msku 列（不臆测）====="
q "SELECT table_name, GROUP_CONCAT(column_name ORDER BY ordinal_position) AS cols
     FROM information_schema.columns
    WHERE table_schema=DATABASE()
      AND table_name IN ('fact_reconciliation_item','fact_wfs_storage_fee','fact_inbound_freight_alloc',
                         'fact_purchase_cash_item','fact_shipping_first_let','fact_settlement_msku_monthly',
                         'biz_finance_opening_cost','fact_sem_billing_daily')
      AND column_name IN ('item_id','msku','sku','store_id','sid','local_sku','product_id')
    GROUP BY table_name;"

echo ""
echo "===== B. 关键：(店铺,msku) → item_id 唯一性分布（决定收入/仓储/入库能否落item）====="
q "SELECT n_items AS 一个msku对应几个itemid, COUNT(*) AS msku店铺组合数
     FROM (SELECT store_id, msku, COUNT(DISTINCT item_id) AS n_items
             FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(msku,'')<>''
            GROUP BY store_id, msku) t
    GROUP BY n_items ORDER BY n_items;"

echo ""
echo "===== C. 反向：(店铺,item_id) → msku 唯一性（决定广告item反查msku展示）====="
q "SELECT n_mskus AS 一个itemid对应几个msku, COUNT(*) AS item店铺组合数
     FROM (SELECT store_id, item_id, COUNT(DISTINCT msku) AS n_mskus
             FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(msku,'')<>''
            GROUP BY store_id, item_id) t
    GROUP BY n_mskus ORDER BY n_mskus;"

echo ""
echo "===== D. 收入侧实测：recon 金额中有多少能唯一落到 item_id（5月起，按金额占比）====="
q "SELECT CASE WHEN d.n IS NULL THEN '0-msku查无维表'
              WHEN d.n=1 THEN '1-唯一可落item'
              ELSE '2-一对多需分摊' END AS 归属可行性,
          COUNT(*) AS 行数, ROUND(SUM(ABS(r.amount)),2) AS 金额绝对值合计
     FROM fact_reconciliation_item r
     LEFT JOIN (SELECT store_id, msku, COUNT(DISTINCT item_id) AS n
                  FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>''
                 GROUP BY store_id, msku) d
       ON d.store_id=r.store_id AND d.msku=r.msku
    WHERE r.period_end >= '2026-05-01' AND COALESCE(r.msku,'')<>''
    GROUP BY 1 ORDER BY 1;"

echo ""
echo "===== E. 本地SKU侧：一个SKU在一个店下摊到几个 item_id（采购/头程/期初的拆分难度）====="
q "SELECT n_items AS 一个sku对应几个itemid, COUNT(*) AS sku店铺组合数
     FROM (SELECT p.store_id, p.sku, COUNT(DISTINCT p.item_id) AS n_items
             FROM dim_product p
            WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>'' AND COALESCE(p.sku,'')<>''
            GROUP BY p.store_id, p.sku) t
    GROUP BY n_items ORDER BY n_items;"

echo ""
echo "===== F. 发货单能否给出 item_id 拆分权重（用户口径：按发货单分摊）====="
q "SELECT COUNT(*) AS 发货明细行, SUM(COALESCE(item_id,'')<>'') AS 带itemid行,
          COUNT(DISTINCT sku) AS sku数, COUNT(DISTINCT store_id) AS 店铺数
     FROM fact_shipping_first_let WHERE match_status='matched';" 2>/dev/null \
  || q "SELECT COUNT(*) AS 发货明细行, COUNT(DISTINCT sku) AS sku数 FROM fact_shipping_first_let WHERE match_status='matched';"

echo ""
echo "===== G. 销量表粒度：settlement 有没有 msku/item 可直接用 ====="
q "SELECT COUNT(*) AS 行数, COUNT(DISTINCT msku) AS msku数,
          SUM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'\$.localSku')),'')<>'') AS 带localSku行
     FROM fact_settlement_msku_monthly WHERE settlement_month >= '2026-05';"

echo ""
echo "===== H. SEM按item_id现状（今晚已打通，确认可直接按item出钱）====="
q "SELECT COUNT(*) AS 账单行, SUM(COALESCE(item_id,'')<>'') AS 带item行,
          ROUND(SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE -line_amount END),2) AS 净额USD
     FROM fact_sem_billing_daily;"

echo ""
echo "===== I. 规模感：改造后大概多少行（店×item vs 现在店×sku）====="
q "SELECT COUNT(DISTINCT CONCAT(store_id,'||',sku)) AS 现在店铺sku行数,
          COUNT(DISTINCT CONCAT(store_id,'||',item_id)) AS 改后店铺item行数
     FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>'';"
echo "---- done ----"
