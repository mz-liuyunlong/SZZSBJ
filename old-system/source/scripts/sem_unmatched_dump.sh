#!/bin/bash
exec > /tmp/sem_unmatched_dump.log 2>&1
cd /opt/lingxing-auto
set -a; . ./.env; set +a
Q="SELECT a.store_name AS 店铺, a.campaign_id AS campaign_id, a.campaign_name AS campaign名称, \
COALESCE(s.latest_item,'') AS 当前itemid, \
CASE WHEN COALESCE(s.latest_item,'')='' THEN '空-名里无ItemID' ELSE '错误-dim_product查无' END AS 状态, \
ROUND(COALESCE(s.spend,0),2) AS 累计花费usd, \
DATE_FORMAT(a.first_seen_date,'%Y-%m-%d') AS 首次发现 \
FROM event_sem_naming_alert a \
LEFT JOIN (SELECT store_id, campaign_id, \
  SUBSTRING_INDEX(GROUP_CONCAT(COALESCE(item_id,'') ORDER BY stat_date DESC),',',1) AS latest_item, \
  SUM(ad_spend) AS spend \
  FROM fact_ads_product_daily WHERE platform='walmart' AND campaign_type='sem' GROUP BY store_id, campaign_id) s \
  ON s.store_id=a.store_id AND s.campaign_id=a.campaign_id \
WHERE a.status='open' ORDER BY a.store_name, 累计花费usd DESC;"
echo "== 汇总 =="
MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "SELECT status, COUNT(*) c FROM event_sem_naming_alert GROUP BY status;"
echo; echo "== TSV(34条明细,制表符分隔,供转表格)=="
MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -e "$Q"
