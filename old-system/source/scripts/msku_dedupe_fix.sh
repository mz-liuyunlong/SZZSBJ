#!/usr/bin/env bash
# msku_dedupe_fix.sh —— fact_sales_daily msku空串脏行终治（2026-08-13 需求方批准：备份留档后删）
# ①双算行(空msku行与同日同店同品非空msku行 qty+金额完全相等) → 备份到留档表后删除（从严判据，差一分钱不动）
# ②4个领星已配对但walmart/list不返回的item → 按需求方截图定点填msku（防撞键守卫）
# ③其余情况一律不动。
# 用法：  bash msku_dedupe_fix.sh            # DRY-RUN：预览将删/将填，零写入
#         bash msku_dedupe_fix.sh --commit   # 备份+删除+定点填
exec > /tmp/msku_dedupe_fix.log 2>&1
MODE="dry"; [ "$1" = "--commit" ] && MODE="commit"
echo "msku_dedupe_fix $(date '+%F_%T') MODE=$MODE"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB="${DB_NAME:-walmart_ai_data}"

cat > /tmp/msku_dedupe_fix.sql <<'SQL'
-- ===== ① 双算行判定（从严：同日同店同品 且 qty与金额完全相等 的空msku行）=====
CREATE TEMPORARY TABLE tmp_dup AS
SELECT f.stat_date, f.store_id, f.item_id, f.sales_qty, f.sales_amount, g.msku AS twin_msku
  FROM fact_sales_daily f
  JOIN fact_sales_daily g
    ON g.platform='walmart' AND g.stat_date=f.stat_date AND g.store_id=f.store_id
   AND g.item_id=f.item_id AND COALESCE(g.msku,'')<>''
   AND g.sales_qty=f.sales_qty AND g.sales_amount=f.sales_amount
 WHERE f.platform='walmart' AND COALESCE(f.msku,'')='' AND COALESCE(f.item_id,'')<>'';

-- ===== ② 4个item定点填（需求方截图口径，仅CN2502店）=====
CREATE TEMPORARY TABLE tmp_manual (item_id VARCHAR(64) PRIMARY KEY, msku VARCHAR(128));
INSERT INTO tmp_manual VALUES
 ('20202469420','CS050-1A'),('20249053598','CS096-1A'),
 ('20320607367','CS165-1A'),('20412163849','CS231-1A');

-- ===== 预览 =====
SELECT '①将删双算行(应=247)' AS chk, COUNT(*) AS c,
       SUM(sales_qty) AS dup_qty, ROUND(SUM(sales_amount),2) AS dup_amt FROM tmp_dup;
SELECT '②将填定点行(应=20)' AS chk, COUNT(*) AS c
  FROM fact_sales_daily f
  JOIN tmp_manual m ON m.item_id=f.item_id
  LEFT JOIN (SELECT stat_date,store_id,item_id,msku FROM fact_sales_daily
              WHERE platform='walmart' AND COALESCE(msku,'')<>'') g
    ON g.stat_date=f.stat_date AND g.store_id=f.store_id AND g.item_id=f.item_id AND g.msku=m.msku
 WHERE f.platform='walmart' AND f.store_id='110687428693128704'
   AND COALESCE(f.msku,'')='' AND g.stat_date IS NULL;
SELECT '②定点撞键跳过(应=0)' AS chk, COUNT(*) AS c
  FROM fact_sales_daily f
  JOIN tmp_manual m ON m.item_id=f.item_id
  JOIN (SELECT stat_date,store_id,item_id,msku FROM fact_sales_daily
         WHERE platform='walmart' AND COALESCE(msku,'')<>'') g
    ON g.stat_date=f.stat_date AND g.store_id=f.store_id AND g.item_id=f.item_id AND g.msku=m.msku
 WHERE f.platform='walmart' AND f.store_id='110687428693128704' AND COALESCE(f.msku,'')='';
SQL

if [ "$MODE" = "commit" ]; then
cat >> /tmp/msku_dedupe_fix.sql <<'SQL'
-- ===== ① 备份留档（表结构同源；INSERT IGNORE按主键防重跑重复）=====
CREATE TABLE IF NOT EXISTS fact_sales_daily_dupblank_bak_20260813 LIKE fact_sales_daily;
INSERT IGNORE INTO fact_sales_daily_dupblank_bak_20260813
SELECT f.* FROM fact_sales_daily f
  JOIN tmp_dup d ON d.stat_date=f.stat_date AND d.store_id=f.store_id AND d.item_id=f.item_id
               AND d.sales_qty=f.sales_qty AND d.sales_amount=f.sales_amount
 WHERE f.platform='walmart' AND COALESCE(f.msku,'')='';
SELECT '备份表行数' AS chk, COUNT(*) AS c FROM fact_sales_daily_dupblank_bak_20260813;

-- ===== ① 删除双算行（判据与备份完全一致）=====
DELETE f FROM fact_sales_daily f
  JOIN tmp_dup d ON d.stat_date=f.stat_date AND d.store_id=f.store_id AND d.item_id=f.item_id
               AND d.sales_qty=f.sales_qty AND d.sales_amount=f.sales_amount
 WHERE f.platform='walmart' AND COALESCE(f.msku,'')='';

-- ===== ② 定点填（防撞键守卫）=====
UPDATE fact_sales_daily f
  JOIN tmp_manual m ON m.item_id=f.item_id
  LEFT JOIN (SELECT stat_date,store_id,item_id,msku FROM fact_sales_daily
              WHERE platform='walmart' AND COALESCE(msku,'')<>'') g
    ON g.stat_date=f.stat_date AND g.store_id=f.store_id AND g.item_id=f.item_id AND g.msku=m.msku
   SET f.msku=m.msku
 WHERE f.platform='walmart' AND f.store_id='110687428693128704'
   AND COALESCE(f.msku,'')='' AND g.stat_date IS NULL;

-- ===== 终检 =====
SELECT '终检:仍空msku的行(有item_id,应=0)' AS chk, COUNT(*) AS c
  FROM fact_sales_daily
 WHERE platform='walmart' AND COALESCE(msku,'')='' AND COALESCE(item_id,'')<>'';
SQL
fi

MYSQL_PWD="$DB_PASSWORD" mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB" -t < /tmp/msku_dedupe_fix.sql
echo "---- done ($MODE) ----"
