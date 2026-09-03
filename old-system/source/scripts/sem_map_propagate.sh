#!/usr/bin/env bash
# sem_map_propagate.sh —— 把 dim_sem_campaign_item 映射(含manual)立即回填到 fact.item_id（只填空/不覆盖）
# 等价于 SEM导入后端 _backfill_by_map / 迁移048 的 step3+4+5，只是手动立即执行一次，让前端马上显示归属。
# 用法：  bash sem_map_propagate.sh            # DRY-RUN：只统计将回填多少行，零写入
#         bash sem_map_propagate.sh --commit   # 提交回填（UPDATE IGNORE，只填空）
exec > /tmp/sem_map_propagate.log 2>&1
MODE="dry"; [ "$1" = "--commit" ] && MODE="commit"
echo "sem_map_propagate $(date '+%F %T') MODE=$MODE"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB="${DB_NAME:-walmart_ai_data}"

cat > /tmp/sem_map_propagate.sql <<'SQL'
-- 预览：将被回填的空归属行数（daily / billing），以及我们34条manual campaign当前fact状态
SELECT 'daily待回填(空item且映射有值)' AS chk, COUNT(*) AS c
  FROM fact_ads_product_daily f
  JOIN dim_sem_campaign_item m ON m.platform='walmart' AND m.store_id=f.store_id AND m.campaign_id=f.campaign_id
 WHERE f.platform='walmart' AND f.campaign_type='sem' AND COALESCE(f.item_id,'')='';
SELECT 'billing待回填(空item且映射有值)' AS chk, COUNT(*) AS c
  FROM fact_sem_billing_daily b
  JOIN dim_sem_campaign_item m ON m.platform='walmart' AND m.store_id=b.store_id AND m.campaign_id=b.campaign_id
 WHERE COALESCE(b.item_id,'')='';
SELECT 'manual映射覆盖的daily行(将显示归属)' AS chk, COUNT(*) AS c
  FROM fact_ads_product_daily f
  JOIN dim_sem_campaign_item m ON m.platform='walmart' AND m.store_id=f.store_id AND m.campaign_id=f.campaign_id AND m.source='manual'
 WHERE f.platform='walmart' AND f.campaign_type='sem';
SQL

if [ "$MODE" = "commit" ]; then
cat >> /tmp/sem_map_propagate.sql <<'SQL'
-- step3 每日事实回填（只填空；UPDATE IGNORE 防唯一键极端冲突）
UPDATE IGNORE fact_ads_product_daily f
  JOIN dim_sem_campaign_item m ON m.platform='walmart' AND m.store_id=f.store_id AND m.campaign_id=f.campaign_id
   SET f.item_id=m.item_id
 WHERE f.platform='walmart' AND f.campaign_type='sem' AND COALESCE(f.item_id,'')='';
-- step4 账单事实回填（只填空）
UPDATE fact_sem_billing_daily b
  JOIN dim_sem_campaign_item m ON m.platform='walmart' AND m.store_id=b.store_id AND m.campaign_id=b.campaign_id
   SET b.item_id=m.item_id
 WHERE COALESCE(b.item_id,'')='';
-- step5 msku补齐（dim_product店内唯一命中才填；只填空）
UPDATE fact_ads_product_daily f
  JOIN (SELECT store_id, item_id, MAX(msku) AS msku FROM dim_product
         WHERE platform='walmart' AND COALESCE(msku,'')<>''
         GROUP BY store_id, item_id HAVING COUNT(DISTINCT msku)=1) p
    ON p.store_id=f.store_id AND p.item_id=f.item_id
   SET f.msku=p.msku
 WHERE f.platform='walmart' AND f.campaign_type='sem' AND COALESCE(f.msku,'')='' AND COALESCE(f.item_id,'')<>'';
-- 回读：34条manual campaign的daily/billing现在有多少已带item_id
SELECT '回填后-daily带item的manual行' AS chk, COUNT(*) AS c
  FROM fact_ads_product_daily f
  JOIN dim_sem_campaign_item m ON m.platform='walmart' AND m.store_id=f.store_id AND m.campaign_id=f.campaign_id AND m.source='manual'
 WHERE f.platform='walmart' AND f.campaign_type='sem' AND COALESCE(f.item_id,'')<>'';
SELECT '剩余未归属sem行(全店)' AS chk, COUNT(*) AS c
  FROM fact_ads_product_daily
 WHERE platform='walmart' AND campaign_type='sem' AND COALESCE(item_id,'')='';
SQL
fi

MYSQL_PWD="$DB_PASSWORD" mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB" -t < /tmp/sem_map_propagate.sql
echo "---- done ($MODE) ----"
