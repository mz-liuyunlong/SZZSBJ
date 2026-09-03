#!/usr/bin/env bash
# sem_manual_attr.sh —— SEM 34条人工归属：写映射表(source=manual) + 告警预结算resolved(0分不扣)
# 用法：  bash sem_manual_attr.sh            # DRY-RUN：只解析+预览，零写入
#         bash sem_manual_attr.sh --commit   # 提交写入（dim_sem_campaign_item + event_sem_naming_alert）
# 零触碰：fact_sem_billing_daily / fact_ads_product_daily / 任何金额列。仅DIM映射 + EVENT状态机。
exec > /tmp/sem_manual_attr.log 2>&1
MODE="dry"; [ "$1" = "--commit" ] && MODE="commit"
echo "sem_manual_attr $(date '+%F_%T') MODE=$MODE"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB="${DB_NAME:-walmart_ai_data}"

cat > /tmp/sem_manual_attr.sql <<'SQL'
-- ===== 人工回填的34条映射（campaign_id -> 归属item_id）=====
CREATE TEMPORARY TABLE tmp_map (campaign_id VARCHAR(64) PRIMARY KEY, item_id VARCHAR(64));
INSERT INTO tmp_map VALUES
 ('1015672334','18431417012'),('1435055881','19995950748'),('1360056333','19986500361'),
 ('1353648891','20009206041'),('844620126','20086168853'),('780360403','20138100180'),
 ('794247073','20212169853'),('1073424285','19977660005'),('1256442588','19982708514'),
 ('1373226309','19989513564'),('1300679607','19988263071'),('22895042','19992364838'),
 ('1451052217','19992467121'),('632155125','20019460356'),('971548812','19984561835'),
 ('1556697358','20016118918'),('942278829','19995063402'),('1392850842','19986600162'),
 ('75231293','19971758344'),('354748327','19983613590'),('1926574460','20050021834'),
 ('747163124','20077964576'),('1715314787','20081300429'),('1946128685','20075253310'),
 ('586323571','20090252341'),('1178077650','20069817788'),('93904984','20024922791'),
 ('438967849','20067513622'),('338121782','20084107706'),('1972157908','20296163745'),
 ('1567219397','20390204120'),('1086989246','20250072767'),('1949104236','20022956170'),
 ('1597835400','20410011595');

-- ===== 解析 store_id / campaign_name(取自alert) / owner(dim_product唯一命中才认) =====
CREATE TEMPORARY TABLE tmp_attr AS
SELECT m.campaign_id, m.item_id, a.store_id, a.store_name, a.campaign_name,
       (SELECT p.owner FROM dim_product p
          WHERE p.platform='walmart' AND p.store_id=a.store_id AND p.item_id=m.item_id
            AND COALESCE(p.owner,'')<>'' GROUP BY p.owner LIMIT 1) AS owner_guess,
       (SELECT COUNT(DISTINCT p.owner) FROM dim_product p
          WHERE p.platform='walmart' AND p.store_id=a.store_id AND p.item_id=m.item_id
            AND COALESCE(p.owner,'')<>'') AS owner_cnt
  FROM tmp_map m
  JOIN (SELECT campaign_id, MAX(store_id) AS store_id, MAX(store_name) AS store_name,
               MAX(campaign_name) AS campaign_name
          FROM event_sem_naming_alert GROUP BY campaign_id) a
    ON a.campaign_id = m.campaign_id;

-- ===== 预览（写前必看）=====
SELECT '解析到的映射条数(应=34)' AS chk, COUNT(*) AS c FROM tmp_attr;
SELECT store_id, campaign_id, LEFT(campaign_name,30) AS campaign_name, item_id,
       CASE WHEN owner_cnt=1 THEN owner_guess WHEN owner_cnt=0 THEN '(空-未维护)'
            ELSE CONCAT('(多命中',owner_cnt,'-不回填)') END AS owner_final
  FROM tmp_attr ORDER BY store_id, campaign_id;
SELECT '当前仍open的告警条数' AS chk, COUNT(*) AS c
  FROM event_sem_naming_alert a JOIN tmp_map m ON m.campaign_id=a.campaign_id
 WHERE a.status='open';
SQL

if [ "$MODE" = "commit" ]; then
cat >> /tmp/sem_manual_attr.sql <<'SQL'
-- ① DIM层：写 campaign→item 映射（source=manual，幂等 upsert；系统永不覆盖 manual 行）
INSERT INTO dim_sem_campaign_item (platform, store_id, campaign_id, item_id, campaign_name, source, remark)
SELECT 'walmart', t.store_id, t.campaign_id, t.item_id, LEFT(t.campaign_name,250), 'manual', '人工归属兜底 2026-08-13'
  FROM tmp_attr t
ON DUPLICATE KEY UPDATE item_id=VALUES(item_id), source='manual',
                        campaign_name=VALUES(campaign_name), updated_at=NOW();

-- ② EVENT层：仅当前open的告警 → resolved + 预结算0分(penalty_at落定→扣分脚本永不结算) + owner唯一命中回填
UPDATE event_sem_naming_alert a
  JOIN tmp_attr t ON t.campaign_id=a.campaign_id AND a.platform='walmart' AND a.store_id=t.store_id
   SET a.status='resolved',
       a.resolved_at=COALESCE(a.resolved_at, NOW()),
       a.owner_name=CASE WHEN t.owner_cnt=1 THEN t.owner_guess ELSE a.owner_name END,
       a.penalty_points=0,
       a.penalty_at=COALESCE(a.penalty_at, NOW()),
       a.remark=CONCAT(COALESCE(a.remark,''), IF(COALESCE(a.remark,'')='','','; '),
                       '人工归属兜底不扣分 2026-08-13')
 WHERE a.status='open';

-- ③ 回读确认
SELECT '写后manual映射条数' AS chk, COUNT(*) AS c
  FROM dim_sem_campaign_item d JOIN tmp_map m ON m.campaign_id=d.campaign_id
 WHERE d.source='manual';
SELECT '写后已resolved且预结算0分' AS chk, COUNT(*) AS c
  FROM event_sem_naming_alert a JOIN tmp_map m ON m.campaign_id=a.campaign_id
 WHERE a.status='resolved' AND a.penalty_at IS NOT NULL AND a.penalty_points=0;
SELECT '这34条是否残留待扣分(应=0)' AS chk, COUNT(*) AS c
  FROM event_sem_naming_alert a JOIN tmp_map m ON m.campaign_id=a.campaign_id
 WHERE a.status='resolved' AND a.penalty_at IS NULL;
SQL
fi

MYSQL_PWD="$DB_PASSWORD" mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB" -t < /tmp/sem_manual_attr.sql
echo "---- done ($MODE) ----"
