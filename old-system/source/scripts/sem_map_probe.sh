#!/usr/bin/env bash
# sem_map_probe.sh —— 只读探针：SEM人工归属写库前的结构核实 + 34条ItemID校验（零写入，仅临时表）
exec > /tmp/sem_map_probe.log 2>&1
echo "sem_map_probe $(date '+%F_%T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB="${DB_NAME:-walmart_ai_data}"

cat > /tmp/sem_map_probe.sql <<'SQL'
-- ===== 1. 表结构（主键/唯一键/source/备注列） =====
SHOW CREATE TABLE dim_sem_campaign_item\G
SHOW CREATE TABLE event_sem_naming_alert\G
SHOW CREATE TABLE dim_product\G

-- ===== 2. dim_sem_campaign_item 现状（来源分布 + 是否已有这34个campaign） =====
SELECT source, COUNT(*) AS c FROM dim_sem_campaign_item GROUP BY source;

-- ===== 3. 临时映射表：人工回填的34条（campaign_id -> 拟归属item_id）=====
CREATE TEMPORARY TABLE tmp_map (campaign_id VARCHAR(64), item_id VARCHAR(32));
INSERT INTO tmp_map VALUES
 ('1015672334','18431417012'),
 ('1435055881','19995950748'),
 ('1360056333','19986500361'),
 ('1353648891','20009206041'),
 ('844620126','20086168853'),
 ('780360403','20138100180'),
 ('794247073','20212169853'),
 ('1073424285','19977660005'),
 ('1256442588','19982708514'),
 ('1373226309','19989513564'),
 ('1300679607','19988263071'),
 ('22895042','19992364838'),
 ('1451052217','19992467121'),
 ('632155125','20019460356'),
 ('971548812','19984561835'),
 ('1556697358','20016118918'),
 ('942278829','19995063402'),
 ('1392850842','19986600162'),
 ('75231293','19971758344'),
 ('354748327','19983613590'),
 ('1926574460','20050021834'),
 ('747163124','20077964576'),
 ('1715314787','20081300429'),
 ('1946128685','20075253310'),
 ('586323571','20090252341'),
 ('1178077650','20069817788'),
 ('93904984','20024922791'),
 ('438967849','20067513622'),
 ('338121782','20084107706'),
 ('1972157908','20296163745'),
 ('1567219397','20390204120'),
 ('1086989246','20250072767'),
 ('1949104236','20022956170'),
 ('1597835400','20410011595');

-- ===== 4. 逐条校验：store(取自alert) + 该店该item是否在dim_product + owner =====
SELECT m.campaign_id, a.store_id, a.store_name, a.campaign_name, m.item_id,
       CASE WHEN p.item_id IS NULL THEN 'MISS-维表无' ELSE 'OK' END AS chk,
       p.owner AS owner
FROM tmp_map m
LEFT JOIN (SELECT campaign_id, MAX(store_id) AS store_id, MAX(store_name) AS store_name,
                  MAX(campaign_name) AS campaign_name
             FROM event_sem_naming_alert GROUP BY campaign_id) a
       ON a.campaign_id = m.campaign_id
LEFT JOIN (SELECT store_id, item_id, MAX(owner) AS owner
             FROM dim_product WHERE platform='walmart' GROUP BY store_id, item_id) p
       ON p.store_id = a.store_id AND p.item_id = m.item_id
ORDER BY (p.item_id IS NULL) DESC, m.campaign_id;

-- ===== 5. dim_sem_campaign_item 里这34个campaign现有映射（有无冲突/已存在）=====
SELECT d.* FROM dim_sem_campaign_item d
 JOIN tmp_map m ON m.campaign_id = d.campaign_id;

-- ===== 6. 归属是否已落到fact：这34个campaign的 billing / ads item_id 落库情况 =====
SELECT 'billing' AS src, b.campaign_id, COUNT(*) AS rows_cnt,
       SUM(COALESCE(b.item_id,'')<>'') AS has_item
  FROM fact_sem_billing_daily b JOIN tmp_map m ON m.campaign_id=b.campaign_id
 GROUP BY b.campaign_id;
SELECT 'ads' AS src, f.campaign_id, COUNT(*) AS rows_cnt,
       SUM(COALESCE(f.item_id,'')<>'') AS has_item
  FROM fact_ads_product_daily f JOIN tmp_map m ON m.campaign_id=f.campaign_id
 WHERE f.campaign_type='sem'
 GROUP BY f.campaign_id;
SQL

MYSQL_PWD="$DB_PASSWORD" mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB" -t < /tmp/sem_map_probe.sql
echo "---- done ----"
