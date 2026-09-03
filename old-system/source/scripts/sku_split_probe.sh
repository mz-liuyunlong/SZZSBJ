#!/usr/bin/env bash
# sku_split_probe.sh —— 本地SKU ↔ 店铺/ITEMID 一对多分类清单（只读，零写入）
# 需求方 2026-08-14：「先把 SKU 对应多个店铺和多个 ITEMID 的分出来」——这批是唯一需要"分摊"的，
#   其余 1:1 的可直归 ITEMID、零争议，批13 可先落地。
# 顺带修复上一轮 3.2/3.3 的 collation 报错：CAST(sid AS CHAR) 与 store_id 排序规则不同
#   （utf8mb4_0900_ai_ci vs utf8mb4_unicode_ci）→ 改为数值比对 CAST(store_id AS UNSIGNED)=sid，彻底绕开。
# 全程只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL。
exec > /tmp/sku_split_probe.log 2>&1
echo "sku_split_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

BASE="SELECT DISTINCT store_id, item_id, sku FROM dim_product
       WHERE platform='walmart' AND COALESCE(item_id,'')<>'' AND COALESCE(sku,'')<>''
         AND sku NOT IN ('XY2007','DC001','QH888')"
NEW="AND sku REGEXP '^YC[0-9]+' AND CAST(REGEXP_SUBSTR(sku,'[0-9]+') AS UNSIGNED) >= 200"

echo "=============== 【一】全量 SKU 的四象限分类（决定要不要分摊）==============="
q "WITH b AS ($BASE),
     s AS (SELECT sku, COUNT(DISTINCT store_id) AS n_store,
                  COUNT(DISTINCT item_id) AS n_item,
                  COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS n_pair FROM b GROUP BY sku)
   SELECT CASE WHEN n_store=1 AND n_item=1 THEN '① 1店1item —— 可直归，零分摊'
               WHEN n_store=1 AND n_item>1 THEN '② 1店多item —— 店内按发货量拆'
               WHEN n_store>1 AND n_item=1 THEN '③ 多店同item —— 跨店拆（同一listing多店共用）'
               ELSE '④ 多店多item —— 先拆店再拆item' END AS 分类,
          COUNT(*) AS SKU数, SUM(n_pair) AS 店item对数
     FROM s GROUP BY 1 ORDER BY 1;"

echo ""
echo "--- 1.2 同一分类，只看 YC00200+ 干净新品（批13 第一批范围）---"
q "WITH b AS ($BASE $NEW),
     s AS (SELECT sku, COUNT(DISTINCT store_id) AS n_store, COUNT(DISTINCT item_id) AS n_item,
                  COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS n_pair FROM b GROUP BY sku)
   SELECT CASE WHEN n_store=1 AND n_item=1 THEN '① 1店1item —— 可直归，零分摊'
               WHEN n_store=1 AND n_item>1 THEN '② 1店多item —— 店内按发货量拆'
               WHEN n_store>1 AND n_item=1 THEN '③ 多店同item —— 跨店拆'
               ELSE '④ 多店多item —— 先拆店再拆item' END AS 分类,
          COUNT(*) AS SKU数, SUM(n_pair) AS 店item对数
     FROM s GROUP BY 1 ORDER BY 1;"

echo ""
echo "=============== 【二】需要分摊的 SKU 明细清单（YC00200+，逐 SKU 列出所有店铺×ITEMID）==============="
echo "--- 2.1 ② 1店多item ---"
q "WITH b AS ($BASE $NEW),
     s AS (SELECT sku FROM b GROUP BY sku
            HAVING COUNT(DISTINCT store_id)=1 AND COUNT(DISTINCT item_id)>1)
   SELECT b.sku AS SKU, d.store_name AS 店铺, b.item_id AS ITEMID,
          COALESCE(sh.qty,0) AS 发货量, CASE WHEN COALESCE(sh.qty,0)>0 THEN '✅可按发货量拆' ELSE '❗无发货量(需均摊或人工)' END AS 拆分依据
     FROM b JOIN s ON s.sku=b.sku
     LEFT JOIN dim_store d ON d.store_id=b.store_id
     LEFT JOIN (SELECT store_id, sku, item_id, SUM(delivery_num) AS qty FROM fact_shipping_first_let
                 WHERE match_status='matched' GROUP BY store_id, sku, item_id) sh
            ON sh.store_id=b.store_id AND sh.sku=b.sku AND sh.item_id=b.item_id
    ORDER BY b.sku, 发货量 DESC;"

echo ""
echo "--- 2.2 ③④ 跨店铺（一个SKU挂到多个店铺）---"
q "WITH b AS ($BASE $NEW),
     s AS (SELECT sku FROM b GROUP BY sku HAVING COUNT(DISTINCT store_id)>1)
   SELECT b.sku AS SKU, d.store_name AS 店铺, b.item_id AS ITEMID,
          COALESCE(sh.qty,0) AS 发货量, CASE WHEN COALESCE(sh.qty,0)>0 THEN '✅可按发货量拆' ELSE '❗无发货量(需均摊或人工)' END AS 拆分依据
     FROM b JOIN s ON s.sku=b.sku
     LEFT JOIN dim_store d ON d.store_id=b.store_id
     LEFT JOIN (SELECT store_id, sku, item_id, SUM(delivery_num) AS qty FROM fact_shipping_first_let
                 WHERE match_status='matched' GROUP BY store_id, sku, item_id) sh
            ON sh.store_id=b.store_id AND sh.sku=b.sku AND sh.item_id=b.item_id
    ORDER BY b.sku, 店铺;"

echo ""
echo "--- 2.3 【关键】同一 ITEMID 挂在多个店铺下（若存在，说明 item_id 不是店内唯一，口径要重定）---"
q "WITH b AS ($BASE)
   SELECT item_id AS ITEMID, COUNT(DISTINCT store_id) AS 店铺数,
          GROUP_CONCAT(DISTINCT sku) AS 涉及SKU
     FROM b GROUP BY item_id HAVING COUNT(DISTINCT store_id)>1 ORDER BY 店铺数 DESC LIMIT 30;"
echo "（上表若非空：同一 ITEMID 出现在多店，需确认是同一listing多店共用还是主数据脏）"

echo ""
echo "=============== 【三】拆分可行性：需分摊的 SKU 里有多少拿得到发货量 ==============="
q "WITH b AS ($BASE $NEW),
     s AS (SELECT sku FROM b GROUP BY sku
            HAVING COUNT(DISTINCT store_id)>1 OR COUNT(DISTINCT item_id)>1),
     j AS (SELECT b.sku, b.store_id, b.item_id,
                  COALESCE((SELECT SUM(f.delivery_num) FROM fact_shipping_first_let f
                             WHERE f.match_status='matched' AND f.sku=b.sku
                               AND f.store_id=b.store_id AND f.item_id=b.item_id),0) AS qty
             FROM b JOIN s ON s.sku=b.sku)
   SELECT CASE WHEN tot=0 THEN '❗该SKU全部子项均无发货量 → 只能均摊或人工指定'
               WHEN zero_cnt=0 THEN '✅所有子项都有发货量 → 可全额按量拆'
               ELSE '⚠️部分子项无发货量 → 有量的按量拆，无量的记0（会全额压到有量的item）' END AS 可行性,
          COUNT(*) AS SKU数
     FROM (SELECT sku, SUM(qty) AS tot, SUM(CASE WHEN qty=0 THEN 1 ELSE 0 END) AS zero_cnt
             FROM j GROUP BY sku) t
    GROUP BY 1 ORDER BY 2 DESC;"

echo ""
echo "=============== 【四】纠错重跑：采购归属试算（改数值比对，绕开 collation）==============="
echo "--- 4.1 A类 sid 能否对上 dim_store（A路径可用性前提）---"
q "SELECT i.sid AS sid, COALESCE(d.store_name,'❗对不上 dim_store') AS 对上的店铺,
          COUNT(*) AS 行数, ROUND(SUM(i.amount),2) AS 金额CNY
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
     LEFT JOIN dim_store d ON CAST(d.store_id AS UNSIGNED)=i.sid
    WHERE COALESCE(h.status_text,'') NOT LIKE '%作废%' AND COALESCE(i.sid,0)<>0
    GROUP BY i.sid, d.store_name ORDER BY 金额CNY DESC LIMIT 20;"

echo ""
echo "--- 4.2 A/B 两路归属后落到 YC00200+ 干净新品的采购成本（CNY）---"
q "WITH clean AS ($BASE $NEW),
   pur AS (SELECT i.sku, COALESCE(i.sid,0) AS sid, i.amount
             FROM fact_purchase_cash_item i JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
            WHERE COALESCE(h.status_text,'') NOT LIKE '%作废%'
              AND COALESCE(h.order_time,h.create_time) >= '2026-05-01'),
   ship AS (SELECT store_id, sku, item_id, SUM(delivery_num) AS qty
              FROM fact_shipping_first_let
             WHERE match_status='matched' AND COALESCE(store_id,'')<>'' AND COALESCE(item_id,'')<>''
             GROUP BY store_id, sku, item_id),
   ship_sku AS (SELECT sku, SUM(qty) AS tot FROM ship GROUP BY sku),
   ship_store AS (SELECT store_id, sku, SUM(qty) AS tot FROM ship GROUP BY store_id, sku),
   alloc AS (
     SELECT s.store_id, s.item_id, p.amount * s.qty / NULLIF(ss.tot,0) AS amt
       FROM pur p JOIN ship s ON s.sku=p.sku AND CAST(s.store_id AS UNSIGNED)=p.sid
       JOIN ship_store ss ON ss.store_id=s.store_id AND ss.sku=s.sku
      WHERE p.sid<>0
     UNION ALL
     SELECT s.store_id, s.item_id, p.amount * s.qty / NULLIF(k.tot,0) AS amt
       FROM pur p JOIN ship s ON s.sku=p.sku JOIN ship_sku k ON k.sku=p.sku
      WHERE p.sid=0)
   SELECT d.store_name AS 店铺, COUNT(DISTINCT CONCAT(a.store_id,'|',a.item_id)) AS 命中item数,
          ROUND(SUM(a.amt),2) AS 采购成本CNY
     FROM alloc a JOIN clean c ON c.store_id=a.store_id AND c.item_id=a.item_id
     LEFT JOIN dim_store d ON d.store_id=a.store_id
    GROUP BY d.store_name ORDER BY 采购成本CNY DESC;"
echo "---- done ----"
