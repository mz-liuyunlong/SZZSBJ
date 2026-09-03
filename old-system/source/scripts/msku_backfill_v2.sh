#!/usr/bin/env bash
# msku_backfill_v2.sh —— fact_sales_daily.msku 空串定点回填 v2（防撞键版）
# v1问题：填空后与同日同店同品已有msku行撞 uq_fact_sales(stat_date,platform,store_id,item_id,msku)，整条UPDATE回滚零写入。
# v2改动：①冲突行(目标行已存在)自动跳过并单独列出(含两行qty/金额，留人工判是否重复) ②其余照填。只填空/不覆盖/不动金额。
# 用法：  bash msku_backfill_v2.sh            # DRY-RUN：预览可填+冲突清单，零写入
#         bash msku_backfill_v2.sh --commit   # 提交回填(仅非冲突行)
exec > /tmp/msku_backfill_v2.log 2>&1
MODE="dry"; [ "$1" = "--commit" ] && MODE="commit"
echo "msku_backfill_v2 $(date '+%F_%T') MODE=$MODE"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB="${DB_NAME:-walmart_ai_data}"

cat > /tmp/msku_backfill_v2.sql <<'SQL'
-- 候选：msku空串但item_id有值的(店,item)，dim_product唯一命中才可填
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

-- 冲突：该空行若填成 msku_fill，与同日同店同品已有行撞唯一键 → 跳过留人工
CREATE TEMPORARY TABLE tmp_conflict AS
SELECT f.stat_date, f.store_id, f.item_id, t.msku_fill,
       f.sales_qty AS blank_qty, f.sales_amount AS blank_amt,
       g.sales_qty AS exist_qty, g.sales_amount AS exist_amt
  FROM fact_sales_daily f
  JOIN tmp_fill t ON t.store_id=f.store_id AND t.item_id=f.item_id AND t.msku_cnt=1
  JOIN fact_sales_daily g ON g.platform='walmart' AND g.stat_date=f.stat_date
       AND g.store_id=f.store_id AND g.item_id=f.item_id AND g.msku=t.msku_fill
 WHERE f.platform='walmart' AND COALESCE(f.msku,'')='';

-- 预览
SELECT SUM(CASE WHEN msku_cnt=1 THEN blank_rows ELSE 0 END) AS rows_candidate,
       SUM(msku_cnt=1) AS items_fillable, SUM(msku_cnt=0) AS items_no_msku,
       SUM(msku_cnt>1) AS items_ambiguous
  FROM tmp_fill;
SELECT '冲突行(撞唯一键,跳过留人工)' AS chk, COUNT(*) AS c FROM tmp_conflict;
SELECT * FROM tmp_conflict ORDER BY store_id, item_id, stat_date;
SELECT store_id, item_id, blank_rows, msku_fill,
       CASE WHEN msku_cnt=1 THEN '可回填' WHEN msku_cnt=0 THEN '跳过-维表无msku' ELSE '跳过-多msku歧义' END AS action
  FROM tmp_fill WHERE msku_cnt<>1 ORDER BY store_id, item_id;
SQL

if [ "$MODE" = "commit" ]; then
cat >> /tmp/msku_backfill_v2.sql <<'SQL'
-- 回填：唯一命中 且 非冲突行；只填空、不动金额
UPDATE fact_sales_daily f
  JOIN tmp_fill t ON t.store_id=f.store_id AND t.item_id=f.item_id AND t.msku_cnt=1
  LEFT JOIN tmp_conflict c ON c.stat_date=f.stat_date AND c.store_id=f.store_id AND c.item_id=f.item_id
   SET f.msku=t.msku_fill
 WHERE f.platform='walmart' AND COALESCE(f.msku,'')='' AND c.stat_date IS NULL;
SELECT '回填后仍空msku的行(有item_id)' AS chk, COUNT(*) AS c
  FROM fact_sales_daily
 WHERE platform='walmart' AND COALESCE(msku,'')='' AND COALESCE(item_id,'')<>'';
SQL
fi

MYSQL_PWD="$DB_PASSWORD" mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB" -t < /tmp/msku_backfill_v2.sql
echo "---- done ($MODE) ----"
