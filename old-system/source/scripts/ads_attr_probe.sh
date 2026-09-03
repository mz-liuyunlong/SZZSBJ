#!/usr/bin/env bash
# ads_attr_probe.sh —— 只读探针：定位广告系统(:3000)源码 + 查它回填 fact_ads_product_daily.item_id 是否读 dim_sem_campaign_item
# 纯只读：仅进程/端口/目录探查 + grep 源码 + information_schema 查询。零写入。
exec > /tmp/ads_attr_probe.log 2>&1
echo "ads_attr_probe $(date '+%F_%T')"

echo "===== 1. 定位 :3000 监听进程 ====="
ss -ltnp 2>/dev/null | grep ':3000' || netstat -ltnp 2>/dev/null | grep ':3000' || echo "(无 :3000 socket 信息，可能需 sudo)"
echo "--- pm2 进程 ---"
pm2 list 2>/dev/null || echo "(无 pm2)"
echo "--- docker 容器 ---"
docker ps --format '{{.Names}} | {{.Ports}} | {{.Image}}' 2>/dev/null | grep -iE '3000|ads|sem' || echo "(无 docker 或无匹配)"

echo "===== 2. 由 :3000 进程反查工作目录 ====="
PID=$(ss -ltnp 2>/dev/null | grep ':3000' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
[ -z "$PID" ] && PID=$(lsof -ti:3000 2>/dev/null | head -1)
echo "PID=$PID"
CWD=""
if [ -n "$PID" ]; then CWD=$(readlink -f /proc/$PID/cwd 2>/dev/null); echo "CWD=$CWD"; fi

echo "===== 3. 候选广告系统源码目录 ====="
CANDS="$CWD /opt/walmart-ads /opt/ads /opt/walmart-sem /opt/walmart-sem-data /opt/lingxing-ads /root/walmart-ads /var/www/walmart-ads"
for d in $CANDS; do
  [ -n "$d" ] && [ -d "$d" ] && { echo "FOUND: $d"; ls -la "$d" 2>/dev/null | head -15; echo; }
done

echo "===== 4. 归因逻辑 grep（只读；关键：回填 fact.item_id 是否读 dim_sem_campaign_item / manual）====="
for d in $CANDS; do
  [ -n "$d" ] && [ -d "$d" ] || continue
  echo "---- 在 $d ----"
  echo "  [a] 提到 dim_sem_campaign_item 的地方："
  grep -rnI "dim_sem_campaign_item" "$d" --include=*.ts --include=*.tsx --include=*.js 2>/dev/null | grep -v node_modules | head -15
  echo "  [b] 回填 / 写 fact_ads_product_daily.item_id 的地方："
  grep -rnI "fact_ads_product_daily" "$d" --include=*.ts --include=*.tsx --include=*.js 2>/dev/null | grep -v node_modules | grep -iE "item_id|UPDATE|INSERT|campaign_item|auto_name|归因|attribut" | head -15
  echo "  [c] .env 里的 DB 名："
  grep -rhI "DB_NAME\|DB_DATABASE\|DATABASE" "$d"/.env* 2>/dev/null | grep -v PASSWORD | head
  echo
done

echo "===== 5. 这两张表到底在哪个库（是否两库各一张）====="
cd /opt/lingxing-auto 2>/dev/null && set -a && . ./.env && set +a
MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" -t -e "
SELECT table_schema, table_name, table_rows
  FROM information_schema.tables
 WHERE table_name IN ('dim_sem_campaign_item','fact_ads_product_daily','event_sem_naming_alert')
 ORDER BY table_name, table_schema;" 2>/dev/null || echo "(mysql 查询失败)"

echo "===== 6. 佐证：auto_name 映射的 item_id 是否已同步进 fact（同库对照）====="
MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "
SELECT d.campaign_id, d.source, d.item_id AS map_item,
       (SELECT SUBSTRING_INDEX(GROUP_CONCAT(COALESCE(f.item_id,'') ORDER BY f.stat_date DESC),',',1)
          FROM fact_ads_product_daily f
         WHERE f.platform='walmart' AND f.campaign_type='sem' AND f.campaign_id=d.campaign_id) AS fact_latest_item
  FROM dim_sem_campaign_item d
 WHERE d.source='auto_name' LIMIT 8;" 2>/dev/null || echo "(mysql 查询失败)"
echo "---- done ----"
