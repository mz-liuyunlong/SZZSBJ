#!/usr/bin/env bash
# ads_attr_probe2.sh —— 只读：找出「写 dim_sem_campaign_item / 回填 fact_ads_product_daily.item_id」的后端代码
# 纯只读：仅 ls / find / grep 源码。零写入。
exec > /tmp/ads_attr_probe2.log 2>&1
echo "ads_attr_probe2 $(date '+%F %T')"

echo "===== 1. /opt 一览 ====="
ls -la /opt 2>/dev/null

echo "===== 2. asin-kw-mvp 目录结构(两层，排除 node_modules/.next/.git) ====="
find /opt/asin-kw-mvp -maxdepth 2 -type d 2>/dev/null | grep -vE "node_modules|/\.next|/\.git" | head -50

echo "===== 3. 全 /opt 搜：哪些文件提到 dim_sem_campaign_item（去重文件名）====="
grep -rlI "dim_sem_campaign_item" /opt --include=*.ts --include=*.tsx --include=*.js --include=*.py --include=*.sql 2>/dev/null \
  | grep -vE "node_modules|/\.next/|/\.git/" | head -30

echo "===== 4. 写映射表的语句（INSERT/UPDATE/REPLACE/ON DUPLICATE，排除中台仓库自身）====="
grep -rnI "dim_sem_campaign_item" /opt --include=*.ts --include=*.js --include=*.py --include=*.sql 2>/dev/null \
  | grep -vE "node_modules|/\.next/|/\.git/|/lingxing-auto/" \
  | grep -iE "insert|update|duplicate|replace|into|source" | head -40

echo "===== 5. 回填 fact_ads_product_daily.item_id 的地方（关键：是否 JOIN/读 映射表 或 只解析名字）====="
grep -rnI "fact_ads_product_daily" /opt --include=*.ts --include=*.js --include=*.py 2>/dev/null \
  | grep -vE "node_modules|/\.next/|/\.git/" \
  | grep -iE "item_id|campaign_item|auto_name|coalesce|update .*set|归因|attribut" | head -40

echo "===== 6. campaign 名解析成 ItemID 的逻辑（正则/11位数字/SUBSTRING）====="
grep -rnI -E "campaign.{0,20}item|item.{0,20}campaign|[^0-9](1[0-9]{10})[^0-9]|\\\\d\{11\}|source *= *['\"]auto" /opt/asin-kw-mvp --include=*.ts --include=*.js --include=*.py 2>/dev/null \
  | grep -vE "node_modules|/\.next/|/\.git/" | head -25

echo "===== 7. 后端服务/入口线索（package.json scripts / python 入口 / start脚本）====="
for f in /opt/asin-kw-mvp/*/package.json /opt/asin-kw-mvp/*/start*.sh /opt/asin-kw-mvp/*/main.py /opt/asin-kw-mvp/*/app.py; do
  [ -f "$f" ] && { echo "---- $f ----"; head -30 "$f"; echo; }
done
echo "---- done ----"
