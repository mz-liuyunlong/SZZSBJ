#!/bin/bash
exec > /tmp/itemid_probe.log 2>&1
cd /opt/lingxing-auto
set -a; . ./.env; set +a
q(){ echo; echo "== $1 =="; MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$2"; }
echo "itemid_probe $(date +%F_%T)"

q "I1 recon 切点后各类目 item_id 填充率(重点 sale)" "SELECT fee_category, COUNT(*) rows_cnt, SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) empty_item, ROUND(SUM(amount),2) amt, ROUND(SUM(CASE WHEN COALESCE(item_id,'')='' THEN amount ELSE 0 END),2) empty_item_amt FROM fact_reconciliation_item WHERE period_end>='2026-05-01' GROUP BY fee_category ORDER BY amt;"

q "I2 每(store,sku)挂几个 item_id 分布" "SELECT sku_cnt_bucket, COUNT(*) AS store_sku_pairs FROM (SELECT r.store_id, k.sku, CASE WHEN COUNT(DISTINCT r.item_id)=1 THEN '1' WHEN COUNT(DISTINCT r.item_id)=2 THEN '2' WHEN COUNT(DISTINCT r.item_id)<=4 THEN '3-4' ELSE '5+' END AS sku_cnt_bucket FROM fact_reconciliation_item r LEFT JOIN (SELECT msku, MAX(sku) sku FROM fact_inventory_daily WHERE COALESCE(sku,'')<>'' AND msku<>'' GROUP BY msku HAVING COUNT(DISTINCT sku)=1) k ON k.msku COLLATE utf8mb4_unicode_ci=r.msku COLLATE utf8mb4_unicode_ci WHERE r.period_end>='2026-05-01' AND COALESCE(r.item_id,'')<>'' AND k.sku IS NOT NULL GROUP BY r.store_id, k.sku) t GROUP BY sku_cnt_bucket ORDER BY sku_cnt_bucket;"

q "I3 item_id→sku 是否干净(一个 item_id 只对一个 sku)" "SELECT COUNT(*) total_item, SUM(CASE WHEN sku_cnt>1 THEN 1 ELSE 0 END) ambiguous_item FROM (SELECT r.item_id, COUNT(DISTINCT k.sku) sku_cnt FROM fact_reconciliation_item r LEFT JOIN (SELECT msku, MAX(sku) sku FROM fact_inventory_daily WHERE COALESCE(sku,'')<>'' AND msku<>'' GROUP BY msku HAVING COUNT(DISTINCT sku)=1) k ON k.msku COLLATE utf8mb4_unicode_ci=r.msku COLLATE utf8mb4_unicode_ci WHERE COALESCE(r.item_id,'')<>'' AND k.sku IS NOT NULL GROUP BY r.item_id) t;"

q "I5 发货单头程 列结构(查有无 item_id/msku/gtin)" "SHOW COLUMNS FROM fact_shipping_first_let;"
q "I6 结算月度 列结构(查有无 item_id/gtin)" "SHOW COLUMNS FROM fact_settlement_msku_monthly;"

q "I7 结算 msku→item_id 覆盖(经 dim_product 店内唯一)" "SELECT COUNT(*) rows_cnt, SUM(CASE WHEN d.item_id IS NOT NULL THEN 1 ELSE 0 END) msku_to_item_hit FROM (SELECT DISTINCT store_id, msku FROM fact_settlement_msku_monthly WHERE COALESCE(msku,'')<>'') f LEFT JOIN (SELECT store_id, msku, MAX(item_id) item_id FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>'' GROUP BY store_id, msku HAVING COUNT(DISTINCT item_id)=1) d ON d.store_id=f.store_id AND d.msku COLLATE utf8mb4_unicode_ci=f.msku COLLATE utf8mb4_unicode_ci;"

q "I8 采购/头程 msku 填充(可否退 item_id)" "SELECT 'purchase' src, COUNT(*) rows_cnt, SUM(CASE WHEN COALESCE(msku,'')<>'' THEN 1 ELSE 0 END) has_msku FROM fact_purchase_cash_item;"

q "I9 storage/inbound item_id 填充率" "SELECT 'storage' src, COUNT(*) c, SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) empty_item FROM fact_wfs_storage_fee UNION ALL SELECT 'inbound', COUNT(*), SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) FROM fact_inbound_freight_alloc;"

q "W1 WFS货件头 列结构" "SHOW COLUMNS FROM fact_wfs_shipment;"
q "W2 WFS货件明细 列结构(重点 gtin/item_id/msku)" "SHOW COLUMNS FROM fact_wfs_shipment_item;"

q "W3 GTIN↔item_id 是否 1:1(recon 内 gtin+item_id 都有的行)" "SELECT COUNT(*) total_gtin, SUM(CASE WHEN item_cnt>1 THEN 1 ELSE 0 END) gtin_multi_item FROM (SELECT gtin, COUNT(DISTINCT item_id) item_cnt FROM fact_reconciliation_item WHERE COALESCE(gtin,'')<>'' AND COALESCE(item_id,'')<>'' GROUP BY gtin) t;"

q "W4 (store,msku)→item_id 干净度[dim_product]" "SELECT n_bucket, COUNT(*) store_msku_pairs FROM (SELECT store_id, msku, CASE WHEN COUNT(DISTINCT item_id)=1 THEN '1(干净)' ELSE '>1(多义)' END n_bucket FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(msku,'')<>'' GROUP BY store_id, msku) t GROUP BY n_bucket;"

q "W5 (store,msku)→item_id 干净度[recon 实证]" "SELECT n_bucket, COUNT(*) store_msku_pairs FROM (SELECT store_id, msku, CASE WHEN COUNT(DISTINCT item_id)=1 THEN '1(干净)' ELSE '>1(多义)' END n_bucket FROM fact_reconciliation_item WHERE COALESCE(msku,'')<>'' AND COALESCE(item_id,'')<>'' GROUP BY store_id, msku) t GROUP BY n_bucket;"

q "W6 WFS货件明细样本(看实际 msku/gtin/item_id 值)" "SELECT * FROM fact_wfs_shipment_item LIMIT 3;"
