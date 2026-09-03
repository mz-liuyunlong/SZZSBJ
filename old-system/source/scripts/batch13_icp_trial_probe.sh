#!/usr/bin/env bash
# batch13_icp_trial_probe.sh —— 批13「干净新品 252 item」现金利润离线试算（只读，零写入）
#
# 需求方 2026-08-14 拍板：
#   ① 采购归属**不设日期切点**：逐行判断——sid≠0 直接归店；sid=0 经发货单(fact_shipping_first_let)
#      按 sku→店铺 发货量份额回填；两者皆无=新品采购尚未发货，单列不计入成本（不判缺陷）。
#   ② 批13 第一批范围=**YC00200+ 全部 252 个店item**（含尚未起量的新品），不只做有销售的 49 个。
# 口径对齐现网 /item-cash-profit：切点月 ICP_CUTOFF_M='2026-05'；虚拟SKU(XY2007/DC001/QH888)整行豁免；
#   汇率取归属月**上一月** my_rate，退 rate_org（fact_lingxing_fx_rate, currency_code='USD'）；
#   店铺级类目(sem/review/赔付/其他)不摊到品，本试算不含。
# 本试算按 store_id||item_id 出数（现网页面仍按 store||本地SKU，故两者不可直接对拍，仅供口径验证）。
# 全程只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL。
exec > /tmp/batch13_icp_trial.log 2>&1
echo "batch13_icp_trial $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

CLEAN="SELECT DISTINCT store_id, item_id, sku FROM dim_product
        WHERE platform='walmart' AND COALESCE(item_id,'')<>''
          AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200
          AND sku NOT IN ('XY2007','DC001','QH888')"

echo "=============== 【一】汇率可用性（缺月会导致 CNY↔USD 折算失败）==============="
q "SELECT rate_month AS 汇率月, ROUND(my_rate,4) AS my_rate, ROUND(rate_org,4) AS rate_org,
          CASE WHEN COALESCE(my_rate,0)>0 THEN 'my_rate' WHEN COALESCE(rate_org,0)>0 THEN 'rate_org(退路)' ELSE '❗无可用汇率' END AS 实际取用
     FROM fact_lingxing_fx_rate WHERE currency_code='USD' AND rate_month BETWEEN '2026-03' AND '2026-08'
    ORDER BY rate_month;"
echo "（归属月 2026-05~2026-08 分别取 2026-04~2026-07 的汇率；上表须无 ❗）"

echo ""
echo "=============== 【二】252 item 逐项成本可算性：各路径原币汇总（2026-05 起）==============="
q "WITH clean AS ($CLEAN)
   SELECT '① 销售额(recon sale, USD)' AS 路径, COUNT(DISTINCT CONCAT(c.store_id,'|',c.item_id)) AS 覆盖item, ROUND(SUM(r.amount),2) AS 金额
     FROM clean c JOIN fact_reconciliation_item r ON r.store_id=c.store_id AND r.item_id=c.item_id
    WHERE r.fee_category='sale' AND DATE_FORMAT(r.period_end,'%Y-%m')>='2026-05'
   UNION ALL SELECT '② 退款(refund, USD)', COUNT(DISTINCT CONCAT(c.store_id,'|',c.item_id)), ROUND(SUM(r.amount),2)
     FROM clean c JOIN fact_reconciliation_item r ON r.store_id=c.store_id AND r.item_id=c.item_id
    WHERE r.fee_category='refund' AND DATE_FORMAT(r.period_end,'%Y-%m')>='2026-05'
   UNION ALL SELECT '③ 其他按品类目(USD)', COUNT(DISTINCT CONCAT(c.store_id,'|',c.item_id)), ROUND(SUM(r.amount),2)
     FROM clean c JOIN fact_reconciliation_item r ON r.store_id=c.store_id AND r.item_id=c.item_id
    WHERE r.fee_category NOT IN ('sale','refund','storage','inbound_transport','ad_platform','sem','review_accelerator')
      AND DATE_FORMAT(r.period_end,'%Y-%m')>='2026-05'
   UNION ALL SELECT '④ 广告花费(USD)', COUNT(DISTINCT CONCAT(c.store_id,'|',c.item_id)), ROUND(SUM(a.ad_spend),2)
     FROM clean c JOIN fact_ads_product_daily a ON a.store_id=c.store_id AND a.item_id=c.item_id
    WHERE a.platform='walmart' AND DATE_FORMAT(a.stat_date,'%Y-%m')>='2026-05'
   UNION ALL SELECT '⑤ 仓储费(USD)', COUNT(DISTINCT CONCAT(c.store_id,'|',c.item_id)), ROUND(SUM(s.final_storage_fee),2)
     FROM clean c JOIN fact_wfs_storage_fee s ON s.store_id=c.store_id AND s.item_id=c.item_id
    WHERE DATE_FORMAT(s.report_start,'%Y-%m')>='2026-05'
   UNION ALL SELECT '⑥ 入库运输(USD)', COUNT(DISTINCT CONCAT(c.store_id,'|',c.item_id)), ROUND(SUM(i.alloc_amount),2)
     FROM clean c JOIN fact_inbound_freight_alloc i ON i.store_id=c.store_id AND i.item_id=c.item_id
    WHERE DATE_FORMAT(i.report_start,'%Y-%m')>='2026-05'
   UNION ALL SELECT '⑦ 头程现金(CNY, matched·非预估·切点后)', COUNT(DISTINCT CONCAT(c.store_id,'|',c.item_id)),
          ROUND(SUM(f.per_first_let_cost*f.delivery_num),2)
     FROM clean c JOIN fact_shipping_first_let f ON f.store_id=c.store_id AND f.item_id=c.item_id
    WHERE f.match_status='matched' AND COALESCE(f.value_source,'')<>'预估费用'
      AND f.cash_date>='2026-05-01';"

echo ""
echo "=============== 【三】采购归属试算（拍板口径：不设切点，逐行判断）==============="
echo "--- 3.1 全量采购单品的三条归属路径（切点后 order_time>='2026-05-01'，非作废）---"
q "SELECT CASE WHEN COALESCE(i.sid,0)<>0 THEN 'A. sid直归店铺'
               WHEN EXISTS (SELECT 1 FROM fact_shipping_first_let f
                             WHERE f.sku=i.sku AND f.match_status='matched' AND COALESCE(f.store_id,'')<>'')
                    THEN 'B. 经发货单回退定店'
               ELSE 'C. 无法定店(新品未发货，单列不计成本)' END AS 归属路径,
          COUNT(*) AS 采购行数, COUNT(DISTINCT i.sku) AS SKU数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
    WHERE COALESCE(h.status_text,'') NOT LIKE '%作废%'
      AND COALESCE(h.order_time,h.create_time) >= '2026-05-01'
    GROUP BY 1 ORDER BY 4 DESC;"

echo ""
echo "--- 3.2 A/B 两路归属后，落到 252 个干净新品 item 的采购成本（CNY）---"
echo "     口径：A 类按 sid 定店；B 类按发货单 sku→店铺 发货量份额拆店；店内再按该 sku 各 item 发货量份额拆到 item。"
q "WITH clean AS ($CLEAN),
   pur AS (SELECT i.sku, COALESCE(i.sid,0) AS sid, i.amount,
                  DATE_FORMAT(COALESCE(h.order_time,h.create_time),'%Y-%m') AS m
             FROM fact_purchase_cash_item i JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
            WHERE COALESCE(h.status_text,'') NOT LIKE '%作废%'
              AND COALESCE(h.order_time,h.create_time) >= '2026-05-01'),
   ship AS (SELECT store_id, sku, item_id, SUM(delivery_num) AS qty
              FROM fact_shipping_first_let
             WHERE match_status='matched' AND COALESCE(store_id,'')<>'' AND COALESCE(item_id,'')<>''
             GROUP BY store_id, sku, item_id),
   ship_sku AS (SELECT sku, SUM(qty) AS tot FROM ship GROUP BY sku),
   alloc AS (
     -- A：sid 直归店铺，再按该店该 sku 各 item 的发货量份额拆到 item
     SELECT s.store_id, s.item_id, p.m,
            p.amount * s.qty / NULLIF((SELECT SUM(s2.qty) FROM ship s2 WHERE s2.sku=p.sku AND s2.store_id=s.store_id),0) AS amt
       FROM pur p JOIN ship s ON s.sku=p.sku AND s.store_id=CAST(p.sid AS CHAR)
      WHERE p.sid<>0
     UNION ALL
     -- B：sid=0，按发货单全局 sku→(店,item) 发货量份额拆
     SELECT s.store_id, s.item_id, p.m, p.amount * s.qty / NULLIF(k.tot,0) AS amt
       FROM pur p JOIN ship s ON s.sku=p.sku JOIN ship_sku k ON k.sku=p.sku
      WHERE p.sid=0)
   SELECT d.store_name AS 店铺, COUNT(DISTINCT CONCAT(a.store_id,'|',a.item_id)) AS 命中item数,
          ROUND(SUM(a.amt),2) AS 采购成本CNY
     FROM alloc a JOIN clean c ON c.store_id=a.store_id AND c.item_id=a.item_id
     LEFT JOIN dim_store d ON d.store_id=a.store_id
    GROUP BY d.store_name ORDER BY 采购成本CNY DESC;"

echo ""
echo "--- 3.3 A 类 sid 是否真能对上 dim_store（sid 与 store_id 同源性抽查）---"
q "SELECT COALESCE(i.sid,0) AS sid, d.store_name AS 对上的店铺, COUNT(*) AS 行数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
     LEFT JOIN dim_store d ON d.store_id=CAST(i.sid AS CHAR)
    WHERE COALESCE(h.status_text,'') NOT LIKE '%作废%' AND COALESCE(i.sid,0)<>0
    GROUP BY i.sid, d.store_name ORDER BY 金额CNY DESC LIMIT 20;"
echo "（若「对上的店铺」为 NULL，说明 sid 与 dim_store.store_id 不同源，A 路径不可用，须改走 dim_store_config）"

echo ""
echo "=============== 【四】252 item 逐品试算表（原币，按销售额降序，全部输出）==============="
q "WITH clean AS ($CLEAN)
   SELECT d.store_name AS 店铺, c.sku AS SKU, c.item_id AS ITEMID,
          ROUND(COALESCE((SELECT SUM(r.amount) FROM fact_reconciliation_item r
                           WHERE r.store_id=c.store_id AND r.item_id=c.item_id AND r.fee_category='sale'
                             AND DATE_FORMAT(r.period_end,'%Y-%m')>='2026-05'),0),2) AS 销售USD,
          ROUND(COALESCE((SELECT SUM(r.amount) FROM fact_reconciliation_item r
                           WHERE r.store_id=c.store_id AND r.item_id=c.item_id AND r.fee_category='refund'
                             AND DATE_FORMAT(r.period_end,'%Y-%m')>='2026-05'),0),2) AS 退款USD,
          ROUND(COALESCE((SELECT SUM(a.ad_spend) FROM fact_ads_product_daily a
                           WHERE a.store_id=c.store_id AND a.item_id=c.item_id AND a.platform='walmart'
                             AND DATE_FORMAT(a.stat_date,'%Y-%m')>='2026-05'),0),2) AS 广告USD,
          ROUND(COALESCE((SELECT SUM(s.final_storage_fee) FROM fact_wfs_storage_fee s
                           WHERE s.store_id=c.store_id AND s.item_id=c.item_id
                             AND DATE_FORMAT(s.report_start,'%Y-%m')>='2026-05'),0),2) AS 仓储USD,
          ROUND(COALESCE((SELECT SUM(i.alloc_amount) FROM fact_inbound_freight_alloc i
                           WHERE i.store_id=c.store_id AND i.item_id=c.item_id
                             AND DATE_FORMAT(i.report_start,'%Y-%m')>='2026-05'),0),2) AS 入库USD,
          ROUND(COALESCE((SELECT SUM(f.per_first_let_cost*f.delivery_num) FROM fact_shipping_first_let f
                           WHERE f.store_id=c.store_id AND f.item_id=c.item_id AND f.match_status='matched'
                             AND COALESCE(f.value_source,'')<>'预估费用' AND f.cash_date>='2026-05-01'),0),2) AS 头程CNY
     FROM clean c LEFT JOIN dim_store d ON d.store_id=c.store_id
    ORDER BY 销售USD DESC, 头程CNY DESC;"

echo ""
echo "=============== 【五】坑位清单（做页面前必须知道的）==============="
echo "--- 5.1 252 item 中「零成本零收入」的空壳数（只有listing、无任何流水）---"
q "WITH clean AS ($CLEAN)
   SELECT COUNT(*) AS 空壳item数 FROM clean c
    WHERE NOT EXISTS (SELECT 1 FROM fact_reconciliation_item r WHERE r.store_id=c.store_id AND r.item_id=c.item_id)
      AND NOT EXISTS (SELECT 1 FROM fact_ads_product_daily a WHERE a.store_id=c.store_id AND a.item_id=c.item_id)
      AND NOT EXISTS (SELECT 1 FROM fact_shipping_first_let f WHERE f.store_id=c.store_id AND f.item_id=c.item_id);"
echo ""
echo "--- 5.2 同一 SKU 跨多店铺（采购拆分会跨店，需确认是否符合业务）---"
q "WITH clean AS ($CLEAN)
   SELECT sku AS SKU, COUNT(DISTINCT store_id) AS 涉及店铺数, GROUP_CONCAT(DISTINCT store_id) AS 店铺
     FROM clean GROUP BY sku HAVING COUNT(DISTINCT store_id)>1 ORDER BY 2 DESC LIMIT 20;"
echo ""
echo "--- 5.3 recon sale 中 item_id 为空的比例（决定按item出数会不会漏收入）---"
q "SELECT DATE_FORMAT(period_end,'%Y-%m') AS 月份,
          SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END) AS 无item行数,
          COUNT(*) AS 总行数,
          ROUND(100*SUM(CASE WHEN COALESCE(item_id,'')='' THEN 1 ELSE 0 END)/COUNT(*),2) AS 无item占比,
          ROUND(SUM(CASE WHEN COALESCE(item_id,'')='' THEN amount ELSE 0 END),2) AS 无item金额USD
     FROM fact_reconciliation_item WHERE fee_category='sale' AND DATE_FORMAT(period_end,'%Y-%m')>='2026-05'
    GROUP BY 月份 ORDER BY 月份;"
echo "---- done ----"
