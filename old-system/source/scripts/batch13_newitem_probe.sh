#!/usr/bin/env bash
# batch13_newitem_probe.sh —— 批13第一步「干净新品」家底 + 采购店铺归属切点 + 上一轮探针3处SQL纠错（只读，零写入）
#
# 本轮修正我方上一轮 inbound_reimport_audit.sh 的三处错误：
#   ① 【三】/【6.5】按天摊平对账：聚合列未 GROUP BY，撞 only_full_group_by → 本轮补 GROUP BY。
#   ② 【6.3】用了不存在的列 msku：fact_wfs_storage_fee 实际列名为 sku（DATABASE_MAP 已注明"sku(实为MSKU)"）→ 本轮改 sku。
#   ③ 【4.1】账单相交判据用了闭区间，账单端点与报告端点相接（如账单07-11~07-25 与报告07-25~08-07 共享07-25）
#      被误判为"⚠️账单相交期有费用"，实为端点相接、金额已归属前一期 → 本轮改为严格不等式（真正有重叠天数才算）。
#
# 需求方口径（2026-08-14 口述）：
#   - 本地SKU YC00200 之后基本都是新品；YC 之外前缀（JJ/BG/YM/HK）都是老品。
#   - **8月份开始采购订单才有开始归属到店铺**（此前 fact_purchase_cash_item.sid=0，需经发货单回退定店）。
# 全程只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL。
exec > /tmp/batch13_newitem_probe.log 2>&1
echo "batch13_newitem_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "=============== 【零】上一轮 500 报错的最终取证（补 11:40~11:55 窗口，上轮窗口起点写晚了）==============="
journalctl -u lingxing-admin --since "2026-08-14 11:40" --until "2026-08-14 11:55" --no-pager 2>&1 | tail -60
echo "(若此段为空，则以 nginx 500 + RAW 汇总行已写入/明细行=0 的组合为准定性)"

echo ""
echo "=============== 【一】纠错重跑：CN2501 按天摊平对账（补 GROUP BY）==============="
CN2501=$(MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -N -B \
        -e "SELECT store_id FROM dim_store WHERE platform='walmart' AND store_name LIKE 'CN2501%' LIMIT 1")
echo "CN2501 store_id = [$CN2501]"
for CAT in inbound_transport storage; do
  case "$CAT" in
    inbound_transport) TBL=fact_inbound_freight_alloc; AMT=alloc_amount; NAME="入库运输";;
    storage)           TBL=fact_wfs_storage_fee;      AMT=final_storage_fee; NAME="仓储费";;
  esac
  echo "--- 1.x $NAME（按天摊平，账单窗口内）---"
  q "WITH RECURSIVE dates AS (
       SELECT DATE('2026-01-01') AS d UNION ALL SELECT d+INTERVAL 1 DAY FROM dates WHERE d < '2026-08-31'),
     pipe_day AS (
       SELECT dt.d, t.$AMT/(DATEDIFF(t.report_end,t.report_start)+1) AS amt
         FROM $TBL t JOIN dates dt ON dt.d BETWEEN t.report_start AND t.report_end
        WHERE t.store_id='$CN2501'),
     bill AS (
       SELECT MIN(period_start) AS lo, MAX(period_end) AS hi,
              SUM(CASE WHEN fee_category='$CAT' THEN -amount ELSE 0 END) AS bill_amt
         FROM fact_reconciliation_item WHERE store_id='$CN2501')
     SELECT b.lo AS 账单起, b.hi AS 账单止, ROUND(b.bill_amt,2) AS 账单金额,
            ROUND(SUM(p.amt),2) AS 管道摊入同区间, ROUND(SUM(p.amt)-b.bill_amt,2) AS 差额,
            CASE WHEN ABS(SUM(p.amt)-b.bill_amt) <= GREATEST(30,ABS(b.bill_amt)*0.05) THEN '✅一致'
                 WHEN SUM(p.amt) > b.bill_amt THEN '⚠️管道虚高' ELSE '❗管道偏少(疑漏导)' END AS 判定
       FROM bill b JOIN pipe_day p ON p.d BETWEEN b.lo AND b.hi
      GROUP BY b.lo, b.hi, b.bill_amt;"
  echo "  （窗口外部分另计）"
  q "SELECT '账单窗口外的管道金额' AS chk, ROUND(SUM(t.$AMT),2) AS 金额
       FROM $TBL t WHERE t.store_id='$CN2501'
        AND (t.report_end < (SELECT MIN(period_start) FROM fact_reconciliation_item WHERE store_id='$CN2501')
          OR t.report_start > (SELECT MAX(period_end) FROM fact_reconciliation_item WHERE store_id='$CN2501'));"
done

echo ""
echo "--- 1.3 纠错重跑：CN2501 仓储费同账期是否累加（列名 sku，不是 msku）---"
q "SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS 期起, COUNT(*) AS 总行数, COUNT(DISTINCT sku) AS 去重sku数,
          CASE WHEN COUNT(*)=COUNT(DISTINCT sku) THEN '✅无重复' ELSE '❗同期同sku多行(疑累加)' END AS 判定
     FROM fact_wfs_storage_fee WHERE store_id='$CN2501' GROUP BY report_start ORDER BY report_start;"

echo ""
echo "--- 1.4 纠错重跑：全库空批次「真空 vs 可疑」（改严格重叠，排除端点相接）---"
q "SELECT d.store_name AS 店铺, DATE_FORMAT(b.report_start,'%Y-%m-%d') AS 期起,
          DATE_FORMAT(b.report_end,'%Y-%m-%d') AS 期止, COUNT(*) AS 该期空批次数,
          ROUND(COALESCE((SELECT -SUM(r.amount) FROM fact_reconciliation_item r
                           WHERE r.store_id=b.store_id AND r.fee_category='inbound_transport'
                             AND r.period_start < b.report_end AND b.report_start < r.period_end),0),2) AS 真重叠账单额,
          CASE WHEN COALESCE((SELECT -SUM(r.amount) FROM fact_reconciliation_item r
                               WHERE r.store_id=b.store_id AND r.fee_category='inbound_transport'
                                 AND r.period_start < b.report_end AND b.report_start < r.period_end),0) > 0.5
               THEN '❗账单该期确有费用(疑漏导)' ELSE '✅真空(账单亦无)' END AS 判定
     FROM raw_walmart_inbound_csv b LEFT JOIN dim_store d ON d.store_id=b.store_id
    WHERE b.row_no=0
      AND NOT EXISTS (SELECT 1 FROM raw_walmart_inbound_csv x WHERE x.task_id=b.task_id AND x.row_no>0)
    GROUP BY d.store_name, b.store_id, b.report_start, b.report_end
    ORDER BY d.store_name, b.report_start;"

echo ""
echo "=============== 【二】批13 干净新品名单：YC00200+ （前缀口径∩期初口径，上轮实证 211SKU/252店item 全部不在期初池）==============="
echo "--- 2.1 按店铺分布 ---"
q "SELECT d.store_name AS 店铺, COUNT(DISTINCT p.sku) AS SKU数, COUNT(DISTINCT p.item_id) AS item数
     FROM dim_product p LEFT JOIN dim_store d ON d.store_id=p.store_id
    WHERE p.platform='walmart' AND COALESCE(p.item_id,'')<>''
      AND p.sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(p.sku,'[0-9]+') AS UNSIGNED) >= 200
    GROUP BY d.store_name ORDER BY item数 DESC;"

echo ""
echo "--- 2.2 收入占比：干净新品 vs 全量（recon sale，2026-05起）---"
q "SELECT CASE WHEN c.item_id IS NOT NULL THEN 'YC200+干净新品' ELSE '其它' END AS 分类,
          COUNT(DISTINCT CONCAT(r.store_id,'|',r.item_id)) AS 店item数, ROUND(SUM(r.amount),2) AS 销售额USD
     FROM fact_reconciliation_item r
     LEFT JOIN (SELECT DISTINCT store_id, item_id FROM dim_product
                 WHERE platform='walmart' AND COALESCE(item_id,'')<>''
                   AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200) c
            ON c.store_id=r.store_id AND c.item_id=r.item_id
    WHERE r.fee_category='sale' AND r.period_end>='2026-05-01' AND COALESCE(r.item_id,'')<>''
    GROUP BY 1 ORDER BY 3 DESC;"

echo ""
echo "--- 2.3 各成本路径覆盖（能否把现金利润算全）---"
q "WITH clean AS (
     SELECT DISTINCT store_id, item_id, sku FROM dim_product
      WHERE platform='walmart' AND COALESCE(item_id,'')<>''
        AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200)
   SELECT '收入(recon sale)' AS 路径, COUNT(DISTINCT CONCAT(r.store_id,'|',r.item_id)) AS 覆盖店item数, ROUND(SUM(r.amount),2) AS 金额
     FROM fact_reconciliation_item r JOIN clean c ON c.store_id=r.store_id AND c.item_id=r.item_id
    WHERE r.fee_category='sale' AND r.period_end>='2026-05-01'
   UNION ALL SELECT '广告', COUNT(DISTINCT CONCAT(a.store_id,'|',a.item_id)), ROUND(SUM(a.ad_spend),2)
     FROM fact_ads_product_daily a JOIN clean c ON c.store_id=a.store_id AND c.item_id=a.item_id
    WHERE a.platform='walmart' AND a.stat_date>='2026-05-01'
   UNION ALL SELECT '仓储费', COUNT(DISTINCT CONCAT(s.store_id,'|',s.item_id)), ROUND(SUM(s.final_storage_fee),2)
     FROM fact_wfs_storage_fee s JOIN clean c ON c.store_id=s.store_id AND c.item_id=s.item_id
    WHERE s.report_start>='2026-05-01'
   UNION ALL SELECT '入库运输', COUNT(DISTINCT CONCAT(i.store_id,'|',i.item_id)), ROUND(SUM(i.alloc_amount),2)
     FROM fact_inbound_freight_alloc i JOIN clean c ON c.store_id=i.store_id AND c.item_id=i.item_id
    WHERE i.report_start>='2026-05-01'
   UNION ALL SELECT '头程(CNY)', COUNT(DISTINCT CONCAT(f.store_id,'|',f.item_id)), ROUND(SUM(f.per_first_let_cost*f.delivery_num),2)
     FROM fact_shipping_first_let f JOIN clean c ON c.store_id=f.store_id AND c.item_id=f.item_id;"

echo ""
echo "=============== 【三】采购店铺归属切点验证（需求方：8月起采购单才归属到店铺）==============="
echo "--- 3.1 采购单品 按月 × 是否带店铺(sid) ---"
q "SELECT DATE_FORMAT(COALESCE(h.order_time,h.create_time),'%Y-%m') AS 月份,
          SUM(CASE WHEN COALESCE(i.sid,0)=0 THEN 1 ELSE 0 END) AS 无店铺行数,
          SUM(CASE WHEN COALESCE(i.sid,0)<>0 THEN 1 ELSE 0 END) AS 有店铺行数,
          ROUND(SUM(CASE WHEN COALESCE(i.sid,0)<>0 THEN i.amount ELSE 0 END),2) AS 有店铺金额CNY,
          ROUND(SUM(CASE WHEN COALESCE(i.sid,0)=0 THEN i.amount ELSE 0 END),2) AS 无店铺金额CNY
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
    WHERE COALESCE(h.status_text,'') NOT LIKE '%作废%'
    GROUP BY 月份 ORDER BY 月份;"

echo ""
echo "--- 3.2 干净新品(YC200+)的采购：能否定店（sid直落 / 发货单回退 / 两者皆无）---"
q "WITH clean AS (SELECT DISTINCT sku FROM dim_product
                  WHERE platform='walmart' AND COALESCE(item_id,'')<>''
                    AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200)
   SELECT CASE WHEN COALESCE(i.sid,0)<>0 THEN 'A.采购单自带店铺(8月起)'
               WHEN EXISTS (SELECT 1 FROM fact_shipping_first_let f WHERE f.sku=i.sku) THEN 'B.可经发货单回退定店'
               ELSE 'C.无店铺且无发货单(多为新品尚未发货)' END AS 归属路径,
          COUNT(*) AS 采购行数, COUNT(DISTINCT i.sku) AS SKU数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i JOIN clean c ON c.sku=i.sku
     JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
    WHERE COALESCE(h.status_text,'') NOT LIKE '%作废%'
    GROUP BY 1 ORDER BY 2 DESC;"

echo ""
echo "--- 3.3 干净新品(YC200+)的头程：匹配状态与现金可追溯性 ---"
q "WITH clean AS (SELECT DISTINCT sku FROM dim_product
                  WHERE platform='walmart' AND COALESCE(item_id,'')<>''
                    AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200)
   SELECT COALESCE(f.match_status,'(空)') AS 匹配状态, COALESCE(f.value_source,'(空)') AS 值来源,
          COUNT(*) AS 行数, COUNT(DISTINCT f.item_id) AS item数,
          ROUND(SUM(f.per_first_let_cost*f.delivery_num),2) AS 头程金额CNY,
          MIN(f.cash_date) AS 最早现金日, MAX(f.cash_date) AS 最晚现金日
     FROM fact_shipping_first_let f JOIN clean c ON c.sku=f.sku
    GROUP BY 1,2 ORDER BY 3 DESC;"

echo ""
echo "--- 3.4 一个本地SKU 对多少个 item_id（1:1 可直归，1:多需按发货量拆）---"
q "WITH clean AS (SELECT DISTINCT sku, store_id, item_id FROM dim_product
                  WHERE platform='walmart' AND COALESCE(item_id,'')<>''
                    AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200)
   SELECT CASE WHEN n=1 THEN '1:1（可直归item）' WHEN n<=3 THEN '1:2~3（需拆）' ELSE '1:4+（需拆）' END AS 关系,
          COUNT(*) AS SKU数, SUM(n) AS 店item数
     FROM (SELECT sku, COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS n FROM clean GROUP BY sku) t
    GROUP BY 1 ORDER BY 2 DESC;"

echo ""
echo "--- 3.5 TOP15 干净新品样本（按销售额，供人工逐个核账单）---"
q "WITH clean AS (SELECT DISTINCT store_id, item_id, sku FROM dim_product
                  WHERE platform='walmart' AND COALESCE(item_id,'')<>''
                    AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200)
   SELECT d.store_name AS 店铺, c.sku AS 本地SKU, c.item_id AS ITEMID,
          ROUND(SUM(CASE WHEN r.fee_category='sale' THEN r.amount ELSE 0 END),2) AS 销售额USD,
          ROUND(SUM(CASE WHEN r.fee_category='refund' THEN -r.amount ELSE 0 END),2) AS 退款USD
     FROM clean c JOIN fact_reconciliation_item r ON r.store_id=c.store_id AND r.item_id=c.item_id
     LEFT JOIN dim_store d ON d.store_id=c.store_id
    WHERE r.period_end>='2026-05-01'
    GROUP BY d.store_name, c.sku, c.item_id ORDER BY 销售额USD DESC LIMIT 15;"
echo "---- done ----"
