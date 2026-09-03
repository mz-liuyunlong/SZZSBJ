#!/usr/bin/env bash
# ship_purchase_gap_probe.sh —— 「无发货量」到底是真没有，还是被我们过滤/漏同步了（只读，零写入）
#
# 触发（需求方 2026-08-14 截图实证）：我方判为「无发货量」的 SKU，在领星侧**采购与发货数据都存在**。
#   例：YC00312 → 采购单 PO260622009（供应商永峰/惠州仓库/单价¥38/采购量100/货值¥3800/到货100，**店铺列为空**）；
#       WFS货件 9550251WFA、9550176WFA（店铺 HK2615，发货单 SP202607150010005，MSKU YC00312-1B，已发货 4 与 96）；
#       另有货件 9436958WFA 的 YC00312-1A **状态=未配对**。
# 三条待验假设（不预设结论，用数据说话）：
#   H1 我方统计一律加了 match_status='matched'，未配对行被丢弃 → 发货量算成 0。
#      ⚠️需求方 2026-08-14 澄清：**未配对的是已取消的货件**，理应排除 → H1 基本排除，但仍实测坐实
#      「未配对 ≡ 已取消/已作废」，把这条口径钉死（见【四】4.2）。
#   H2 本地SKU 对应多个 MSKU（YC00312-1A / -1B，GTIN 不同），若关联列存的是 MSKU 而非本地SKU，join 落空。
#   H3 领星侧数据根本没同步进我方库（RAW/事实表都查无此行）。
# 全程只允许 SELECT，禁止 INSERT/UPDATE/DELETE/DDL。
exec > /tmp/ship_purchase_gap_probe.log 2>&1
echo "ship_purchase_gap_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

# 被判「全部子项无发货量」的 15 个 + 需求方截图涉及的 5 个
SKUS="'YC00206','YC00364','YC00377','YC00378','YC00379','YC00380','YC00584','YC00585','YC00592','YC00593','YC00594','YC00595','YC00596','YC00597','YC00598','YC00312','YC00335','YC00372','YC00261','YC00410'"

echo "=============== 【一】H1 验证：这批 SKU 在 fact_shipping_first_let 的全貌（不加任何过滤）==============="
echo "--- 1.1 按 match_status × value_source 分组（若 matched 之外还有量，即证实被过滤掉）---"
q "SELECT COALESCE(match_status,'(空)') AS 匹配状态, COALESCE(value_source,'(空)') AS 值来源,
          COUNT(*) AS 行数, COUNT(DISTINCT sku) AS SKU数, SUM(delivery_num) AS 发货量合计,
          ROUND(SUM(per_first_let_cost*delivery_num),2) AS 头程金额CNY
     FROM fact_shipping_first_let WHERE sku IN ($SKUS)
    GROUP BY 1,2 ORDER BY 3 DESC;"

echo ""
echo "--- 1.2 逐 SKU：matched 发货量 vs 全部发货量（差值>0 即被过滤掉的部分）---"
q "SELECT sku AS SKU,
          SUM(CASE WHEN match_status='matched' THEN delivery_num ELSE 0 END) AS matched发货量,
          SUM(delivery_num) AS 全部发货量,
          SUM(delivery_num) - SUM(CASE WHEN match_status='matched' THEN delivery_num ELSE 0 END) AS 被过滤掉的量,
          COUNT(DISTINCT store_id) AS 涉及店铺数, COUNT(DISTINCT item_id) AS 涉及item数,
          GROUP_CONCAT(DISTINCT COALESCE(match_status,'(空)')) AS 状态集合
     FROM fact_shipping_first_let WHERE sku IN ($SKUS)
    GROUP BY sku ORDER BY 被过滤掉的量 DESC, sku;"

echo ""
echo "--- 1.3 这 20 个 SKU 在该表里一行都没有的（H3 嫌疑：根本没同步）---"
q "SELECT s.sku AS 查无此SKU FROM (SELECT DISTINCT sku FROM dim_product WHERE sku IN ($SKUS)) s
    WHERE NOT EXISTS (SELECT 1 FROM fact_shipping_first_let f WHERE f.sku=s.sku) ORDER BY s.sku;"

echo ""
echo "--- 1.4 需求方点名的货件/发货单是否在库（9550251WFA / 9550176WFA / 9436958WFA / SP202607150010005）---"
q "SELECT shipping_code AS 发货单, cargo_code AS 货件号, store_id, sku, msku, item_id, gtin,
          delivery_num AS 发货量, match_status AS 匹配状态, value_source AS 值来源, cash_date AS 现金日
     FROM fact_shipping_first_let
    WHERE cargo_code IN ('9550251WFA','9550176WFA','9436958WFA')
       OR shipping_code='SP202607150010005'
    ORDER BY shipping_code, cargo_code, sku;"
q "SELECT shipping_code AS 发货单, shipping_status AS 单据状态, cash_date AS 现金日,
          freight_cny, freight_usd, first_let_rows AS 分摊行数, unmatched_rows AS 未匹配行数
     FROM fact_shipping_order WHERE shipping_code='SP202607150010005';"

echo ""
echo "=============== 【二】H2 验证：本地SKU ↔ MSKU 的一对多结构（YC00312-1A/-1B）==============="
echo "--- 2.1 这批 SKU 在 dim_product 的 msku / item_id 清单 ---"
q "SELECT p.sku AS 本地SKU, d.store_name AS 店铺, p.msku AS MSKU, p.item_id AS ITEMID
     FROM dim_product p LEFT JOIN dim_store d ON d.store_id=p.store_id
    WHERE p.platform='walmart' AND p.sku IN ($SKUS)
    ORDER BY p.sku, d.store_name, p.msku;"

echo ""
echo "--- 2.2 fact_shipping_first_let 里 sku 列与 msku 列的实际形态（抽样，判断关联键是否错位）---"
q "SELECT sku AS sku列, msku AS msku列, COUNT(*) AS 行数,
          CASE WHEN sku=msku THEN 'sku=msku(同值)'
               WHEN msku LIKE CONCAT(sku,'-%') THEN 'msku=sku+后缀(正常)'
               ELSE '❗两者无前缀关系(需查)' END AS 形态
     FROM fact_shipping_first_let WHERE sku IN ($SKUS)
    GROUP BY sku, msku ORDER BY sku, msku;"

echo ""
echo "=============== 【三】采购侧：这批 SKU 到底有没有采购单要摊 ==============="
echo "--- 3.1 逐 SKU 的采购行（含 sid=0 者；不设日期过滤，先看全貌）---"
q "SELECT i.sku AS SKU, i.order_sn AS 采购单号, COALESCE(i.sid,0) AS sid,
          COALESCE(d.store_name,'（无店铺归属）') AS 店铺, i.quantity AS 采购量,
          ROUND(i.amount,2) AS 金额CNY, COALESCE(h.order_time,h.create_time) AS 下单日, h.status_text AS 单据状态
     FROM fact_purchase_cash_item i JOIN fact_purchase_cash h ON h.order_sn=i.order_sn
     LEFT JOIN dim_store d ON CAST(d.store_id AS UNSIGNED)=i.sid
    WHERE i.sku IN ($SKUS) ORDER BY i.sku, 下单日;"

echo ""
echo "--- 3.2 需求方点名的采购单 PO260622009 是否在库 ---"
q "SELECT h.order_sn AS 采购单, h.order_time AS 下单时间, h.create_time AS 创建时间, h.status_text AS 状态,
          ROUND(h.amount_total,2) AS 单头总额, i.sku, i.quantity AS 采购量, ROUND(i.unit_price,2) AS 单价,
          ROUND(i.amount,2) AS 金额, COALESCE(i.sid,0) AS sid
     FROM fact_purchase_cash h LEFT JOIN fact_purchase_cash_item i ON i.order_sn=h.order_sn
    WHERE h.order_sn='PO260622009';"
echo "（若查无，说明采购同步有缺口——需求方截图显示该单确实存在：¥3800.00 / 100件 / 惠州仓库 / 供应商永峰）"

echo ""
echo "=============== 【四】口径坐实：未配对是否都对应已取消/已作废单据（需求方口径）==============="
q "SELECT COALESCE(match_status,'(空)') AS 匹配状态, COUNT(*) AS 行数, COUNT(DISTINCT sku) AS SKU数,
          SUM(delivery_num) AS 发货量合计, ROUND(SUM(per_first_let_cost*delivery_num),2) AS 头程金额CNY,
          ROUND(100*COUNT(*)/(SELECT COUNT(*) FROM fact_shipping_first_let),2) AS 行数占比
     FROM fact_shipping_first_let GROUP BY 1 ORDER BY 2 DESC;"
echo ""
echo "--- 4.2 【关键】未配对(非matched)行的单据状态分布：若集中在已取消/已作废，则现行过滤正确、不需改口径 ---"
q "SELECT f.match_status AS 匹配状态, COALESCE(o.shipping_status,'(无单头)') AS 单据状态,
          COUNT(*) AS 行数, SUM(f.delivery_num) AS 发货量
     FROM fact_shipping_first_let f
     LEFT JOIN fact_shipping_order o ON o.shipping_code=f.shipping_code
    WHERE COALESCE(f.match_status,'')<>'matched'
    GROUP BY 1,2 ORDER BY 3 DESC LIMIT 20;"

echo ""
echo "=============== 【五】同步时效：发货单/采购 最近同步到哪一天 ==============="
q "SELECT '发货单(fact_shipping_order)' AS 表, COUNT(*) AS 行数, MAX(gmt_create) AS 最新创建时间, MAX(cash_date) AS 最新现金日 FROM fact_shipping_order
   UNION ALL
   SELECT '头程分摊(fact_shipping_first_let)', COUNT(*), NULL, MAX(cash_date) FROM fact_shipping_first_let
   UNION ALL
   SELECT '采购单头(fact_purchase_cash)', COUNT(*), MAX(create_time), MAX(order_time) FROM fact_purchase_cash
   UNION ALL
   SELECT '采购单品(fact_purchase_cash_item)', COUNT(*), NULL, NULL FROM fact_purchase_cash_item;"
echo "---- done ----"
