#!/usr/bin/env bash
# ambiguous_resolve_probe.sh —— ambiguous 行能否补回店铺/ITEMID（只读，零写入）
#
# 已查明成因（src/syncShippingOrders.ts L268-277）：
#   按 `msku||delivery_num` 反查货件时，若命中**多个货件**(cargos.length>1) → mstatus='ambiguous'，
#   且 store/cargo 留空、itemId 因 itemIdMap 以 `store||msku` 取键而必然为空（sku 走 fl.sku 兜底故有值）。
#   后果：这些行"货真发了、头程费也算了"，但 store_id/item_id 为空 → 所有按 (store,item) 关联的统计全部落空，
#   被误判为"该 SKU 无发货量"。实测全库 8 行 / 752 件 / ¥2,809.04（占 0.62%），单据状态全部为「已发货」。
#
# 本探针只回答一个问题：**这 8 行所在发货单的其他行是否指向唯一店铺**——
#   若唯一，则店铺可确定，修法=在 ambiguous 分支里对 hits 的 store 去重，唯一时照常赋值（歧义只在货件号，不在店铺）；
#   若不唯一，则不可自动补，须人工指定。
# 全程只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL，禁止改任何同步脚本与定时任务。
exec > /tmp/ambiguous_resolve_probe.log 2>&1
echo "ambiguous_resolve_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "=============== 【一】8 行 ambiguous 的原始面貌（确认 store/cargo/item_id 是否真为空）==============="
q "SELECT shipping_code AS 发货单, COALESCE(NULLIF(cargo_code,''),'(空)') AS 货件号,
          COALESCE(NULLIF(store_id,''),'(空)') AS 店铺id, sku, msku,
          COALESCE(NULLIF(item_id,''),'(空)') AS ITEMID, COALESCE(NULLIF(gtin,''),'(空)') AS GTIN,
          delivery_num AS 发货量, ROUND(per_first_let_cost,4) AS 单件头程,
          ROUND(per_first_let_cost*delivery_num,2) AS 头程金额CNY, value_source AS 值来源, cash_date AS 现金日
     FROM fact_shipping_first_let WHERE match_status='ambiguous'
    ORDER BY shipping_code, sku;"

echo ""
echo "=============== 【二】【关键】这些发货单里，matched 行指向的店铺是否唯一 ==============="
q "SELECT f.shipping_code AS 发货单,
          COUNT(DISTINCT CASE WHEN f.match_status='matched' THEN f.store_id END) AS matched店铺数,
          GROUP_CONCAT(DISTINCT CASE WHEN f.match_status='matched' THEN d.store_name END) AS 指向店铺,
          SUM(f.match_status='ambiguous') AS 歧义行数,
          SUM(f.match_status='matched') AS 正常行数,
          o.shipping_status AS 单据状态,
          CASE WHEN COUNT(DISTINCT CASE WHEN f.match_status='matched' THEN f.store_id END)=1
               THEN '✅整单唯一店铺 → 歧义行店铺可确定'
               WHEN COUNT(DISTINCT CASE WHEN f.match_status='matched' THEN f.store_id END)=0
               THEN '❗该单无任何 matched 行 → 无法从本单推断'
               ELSE '⚠️该单跨多店 → 不可自动补，须人工指定' END AS 判定
     FROM fact_shipping_first_let f
     LEFT JOIN fact_shipping_order o ON o.shipping_code=f.shipping_code
     LEFT JOIN dim_store d ON d.store_id=f.store_id
    WHERE f.shipping_code IN (SELECT DISTINCT shipping_code FROM fact_shipping_first_let WHERE match_status='ambiguous')
    GROUP BY f.shipping_code, o.shipping_status ORDER BY f.shipping_code;"

echo ""
echo "=============== 【三】逐单展开：歧义行与同单 matched 行并排看 ==============="
q "SELECT f.shipping_code AS 发货单, f.match_status AS 状态, COALESCE(NULLIF(f.cargo_code,''),'(空)') AS 货件号,
          COALESCE(d.store_name,'(空)') AS 店铺, f.sku, f.msku, COALESCE(NULLIF(f.item_id,''),'(空)') AS ITEMID,
          f.delivery_num AS 发货量, ROUND(f.per_first_let_cost*f.delivery_num,2) AS 头程CNY
     FROM fact_shipping_first_let f LEFT JOIN dim_store d ON d.store_id=f.store_id
    WHERE f.shipping_code IN (SELECT DISTINCT shipping_code FROM fact_shipping_first_let WHERE match_status='ambiguous')
    ORDER BY f.shipping_code, f.match_status DESC, f.sku;"

echo ""
echo "=============== 【四】若店铺可定，ITEMID 能否随之定（该 msku 在该店是否唯一 item）==============="
q "WITH amb AS (SELECT DISTINCT shipping_code, msku, sku FROM fact_shipping_first_let WHERE match_status='ambiguous'),
        one AS (SELECT f.shipping_code, MIN(f.store_id) AS store_id
                  FROM fact_shipping_first_let f
                 WHERE f.match_status='matched' AND f.shipping_code IN (SELECT shipping_code FROM amb)
                 GROUP BY f.shipping_code
                HAVING COUNT(DISTINCT f.store_id)=1)
   SELECT a.shipping_code AS 发货单, a.sku, a.msku, d.store_name AS 推断店铺,
          COUNT(DISTINCT p.item_id) AS 该店该msku对应item数,
          GROUP_CONCAT(DISTINCT p.item_id) AS ITEMID候选,
          CASE WHEN COUNT(DISTINCT p.item_id)=1 THEN '✅ITEMID可确定'
               WHEN COUNT(DISTINCT p.item_id)=0 THEN '❗dim_product 查无该(店,msku)'
               ELSE '⚠️多个item，需再拆' END AS 判定
     FROM amb a JOIN one ON one.shipping_code=a.shipping_code
     LEFT JOIN dim_store d ON d.store_id=one.store_id
     LEFT JOIN dim_product p ON p.platform='walmart' AND p.store_id=one.store_id AND p.msku=a.msku
    GROUP BY a.shipping_code, a.sku, a.msku, d.store_name ORDER BY a.shipping_code, a.sku;"

echo ""
echo "=============== 【五】影响面：ambiguous 目前完全没进成本的金额 ==============="
q "SELECT '全库 ambiguous 行' AS 项, COUNT(*) AS 行数, SUM(delivery_num) AS 发货量,
          ROUND(SUM(per_first_let_cost*delivery_num),2) AS 头程金额CNY,
          MIN(cash_date) AS 最早现金日, MAX(cash_date) AS 最晚现金日
     FROM fact_shipping_first_let WHERE match_status='ambiguous'
   UNION ALL
   SELECT '其中 cash_date>=切点2026-05-01（会进ICP的部分）', COUNT(*), SUM(delivery_num),
          ROUND(SUM(per_first_let_cost*delivery_num),2), MIN(cash_date), MAX(cash_date)
     FROM fact_shipping_first_let WHERE match_status='ambiguous' AND cash_date>='2026-05-01';"
echo ""
echo "--- 5.2 现网 ICP 头程口径复核：store_id 为空的行本就被排除（确认影响链路）---"
q "SELECT CASE WHEN COALESCE(store_id,'')='' THEN 'store_id为空(被ICP排除)' ELSE 'store_id有值' END AS 分组,
          match_status AS 匹配状态, COUNT(*) AS 行数,
          ROUND(SUM(per_first_let_cost*delivery_num),2) AS 头程金额CNY
     FROM fact_shipping_first_let GROUP BY 1,2 ORDER BY 1,2;"
echo "---- done ----"
