#!/usr/bin/env bash
# sem_svc_probe.sh —— 只读：dump SEM导入后端写映射表 + 回填fact.item_id 的源码，判定重导是否覆盖manual / 清空fact.item_id
# 纯只读：只 cat / grep 源码(非.env、无密钥)。零写入。
exec > /tmp/sem_svc_probe.log 2>&1
echo "sem_svc_probe $(date '+%F %T')"
F=/opt/asin-kw-mvp/backend/walmart_sem/service.py

echo "===== service.py 基本信息 ====="
wc -l "$F" 2>/dev/null
ls -la /opt/asin-kw-mvp/backend/walmart_sem/ 2>/dev/null

echo ""
echo "===== A. 写 dim_sem_campaign_item 的完整语句(±35行，看 INSERT IGNORE / ON DUPLICATE / source 判定) ====="
grep -n -B5 -A35 "dim_sem_campaign_item" "$F" 2>/dev/null

echo ""
echo "===== B. 回填/写 fact_ads_product_daily 的地方(±25行，看 item_id 从哪来：映射表JOIN 还是 名字解析) ====="
grep -n -B5 -A25 "fact_ads_product_daily" "$F" 2>/dev/null

echo ""
echo "===== C. campaign 名 → ItemID 解析逻辑(正则/11位/split) ====="
grep -n -B2 -A8 -E "item_id|campaign_name|re\.(search|findall|match|compile)|[0-9]\{11\}|split\(|parse" "$F" 2>/dev/null | head -80

echo ""
echo "===== D. 迁移脚本 048_sem_campaign_item_map.sql 全文(看初始回填口径 + IGNORE语义) ====="
cat /opt/asin-kw-mvp/backend/048_sem_campaign_item_map.sql 2>/dev/null

echo "---- done ----"
