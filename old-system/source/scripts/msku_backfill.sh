#!/usr/bin/env bash
# msku_backfill.sh —— fact_sales_daily.msku 空串定点回填（只填空/不覆盖/不动金额）
# 规则：msku='' 且 item_id 在该店 dim_product 唯一命中一个非空 msku 时才回填；多msku歧义或维表无msku一律跳过。
# 用法：  bash msku_backfill.sh            # DRY-RUN：列出待回填行，零写入
#         bash msku_backfill.sh --commit   # 提交回填
exec > /tmp/msku_backfill.log 2>&1
MODE="dry"; [ "$1" = "--commit" ] && MODE="commit"
echo "msku_backfill $(date '+%F_%T') MODE=$MODE"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB="${DB_NAME:-walmart_ai_data}"

cat > /tmp/msku_backfill.sql <<'SQL'
-- 候选：fact_sales_daily 有item_id但msku空串的 (店,item)，看dim_product能否唯一给出msku
CREATE TEMPORARY TABLE tmp_fill AS
SELECT f.store_id, f.item_id, COUNT(*) AS blank_rows,
       (SELECT p.msku FROM dim_product p
          WHERE p.platform='walmart' AND p.store_id=f.store_id AND p.item_id=f.item_id
            AND COALESCE(p.msku,'')<>'' GROUP BY p.msku LIMIT 1) AS msku_fill,
       (SELECT COUNT(DISTINCT p.msku) FROM dim_product p
          WHERE p.platform='walmart' AND p.store_id=f.store_id AND p.item_id=f.item_id
            AND COALESCE(p.msku,'')<>'') AS msku_cnt
  FROM fact_sales_daily f
 WHERE f.platform='walmart' AND COALESCE(f.msku,'')='' AND COALESCE(f.item_id,'')<>''
 GROUP BY f.store_id, f.item_id;

-- 预览
SELECT store_id, item_id, blank_rows, msku_cnt, msku_fill,
       CASE WHEN msku_cnt=1 THEN '可回填' WHEN msku_cnt=0 THEN '跳过-维表无msku'
            ELSE '跳过-多msku歧义' END AS action
  FROM tmp_fill ORDER BY (msku_cnt=1) DESC, store_id, item_id;
SELECT SUM(CASE WHEN msku_cnt=1 THEN blank_rows ELSE 0 END) AS rows_to_fill,
       SUM(msku_cnt=1) AS items_fillable, SUM(msku_cnt=0) AS items_no_msku,
       SUM(msku_cnt>1) AS items_ambiguous
  FROM tmp_fill;
SQL

if [ "$MODE" = "commit" ]; then
cat >> /tmp/msku_backfill.sql <<'SQL'
-- 只回填唯一命中；只填空、不覆盖、不动 sales_qty/sales_amount 等任何金额列
UPDATE fact_sales_daily f
  JOIN tmp_fill t ON t.store_id=f.store_id AND t.item_id=f.item_id AND t.msku_cnt=1
   SET f.msku = t.msku_fill
 WHERE f.platform='walmart' AND COALESCE(f.msku,'')='' AND COALESCE(f.item_id,'')<>'';
SELECT '回填后仍空msku的行(有item_id)' AS chk, COUNT(*) AS c
  FROM fact_sales_daily
 WHERE platform='walmart' AND COALESCE(msku,'')='' AND COALESCE(item_id,'')<>'';
SQL
fi

MYSQL_PWD="$DB_PASSWORD" mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB" -t < /tmp/msku_backfill.sql
echo "---- done ($MODE) ----"
