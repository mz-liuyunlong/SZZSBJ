#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_auto_ads_fact.py — 自动广告 FACT 历史重建（2026-07-15）

背景：csv_processor 旧聚合键把同搜索词跨 Campaign 合并（campaign_id 逗号串、指标相加），
FACT 层丢失活动粒度（TASK_CHANGE_LOG 2026-07-15 广告数据排查）。聚合键补丁生效后，
本脚本从 raw_walmart_ads_csv 全量重建 source_type='walmart_auto_csv' 的 FACT 行。

口径零漂移：直接 import 生产（已打补丁的）csv_processor 的 is_auto_ad / aggregate /
compute_metrics，字段映射镜像 service._to_fact_row（英文键 1:1 对应）。

流程（--execute 时，单事务）：
  1. 备份：CREATE TABLE backup_fact_ads_auto_<ts> AS SELECT ...（事务外，先行）
  2. DELETE FROM fact_ads_keyword_daily WHERE source_type='walmart_auto_csv'
  3. 按 (task_id, store_name, operator) 分组重放 RAW 行 → 新粒度 upsert
用法：
  python3 rebuild_auto_ads_fact.py            # dry-run：统计+黄金样例预览，零写入
  python3 rebuild_auto_ads_fact.py --execute
前置：csv_processor 聚合键补丁已部署（脚本会自检聚合函数签名注释）。
"""

import json
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, "/opt/asin-kw-mvp/backend")
try:
    from walmart_ads.csv_processor import aggregate, compute_metrics, is_auto_ad  # noqa: E402
except Exception as e:
    sys.exit("无法导入生产 csv_processor（确认路径与补丁部署）: %s" % e)

try:
    import pymysql
except ImportError:
    sys.exit("需要 pymysql")

ENV_PATH = "/opt/lingxing-auto/.env"


def load_env(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_db():
    env = load_env(ENV_PATH)
    return pymysql.connect(
        host=env.get("DB_HOST", "127.0.0.1"), port=int(env.get("DB_PORT", "3306")),
        user=env.get("DB_USER", ""), password=env.get("DB_PASSWORD", ""),
        database=env.get("DB_NAME", "walmart_ai_data"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def json_val(v):
    """JSON 列类型自适应（对象直返/字符串解析），与重放器 v4 同教训"""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(str(v))
    except Exception:
        return None


# 聚合键补丁自检：未打补丁的 aggregate 会把跨 Campaign 合并，重建将复现旧病
_PROBE = [
    {"Date": "2026-01-01", "Item Id": "X", "Item Name": "n", "Searched Keyword": "kw",
     "Campaign Id": "1", "Ad Group Id": "1", "Campaign Name": "A", "Ad Group Name": "a",
     "Bidded Keyword": "b", "Match Type": "e",
     "Impressions": "1", "Clicks": "0", "Ad Spend": "0", "Orders": "0",
     "Total Attributed Sales": "0", "Advertised SKU Sales": "0", "Other SKU Sales": "0",
     "Units Sold": "0", "Total Add to Cart": "0", "Total Product Detail Page Views": "0"},
    {"Date": "2026-01-01", "Item Id": "X", "Item Name": "n", "Searched Keyword": "kw",
     "Campaign Id": "2", "Ad Group Id": "2", "Campaign Name": "B", "Ad Group Name": "b",
     "Bidded Keyword": "b", "Match Type": "e",
     "Impressions": "1", "Clicks": "0", "Ad Spend": "0", "Orders": "0",
     "Total Attributed Sales": "0", "Advertised SKU Sales": "0", "Other SKU Sales": "0",
     "Units Sold": "0", "Total Add to Cart": "0", "Total Product Detail Page Views": "0"},
]
if len(aggregate(list(_PROBE))) != 2:
    sys.exit("PATCH_CHECK_FAILED: 生产 csv_processor 聚合键补丁未生效（跨Campaign仍被合并），停止")

UPSERT_SQL = """
INSERT INTO fact_ads_keyword_daily
  (stat_date, platform, store_id, store_name, campaign_id, campaign_name,
   ad_group_id, ad_group_name, item_id, item_name, keyword, normalized_keyword,
   match_type, keyword_type, impressions, clicks, ctr, ad_spend, orders,
   conversion_rate, total_sales, acos, cpc, cvr, roas, total_add_to_cart,
   operator, source_type, source_system, source_task_id)
VALUES (%s,'walmart','',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'auto_search_term',
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'walmart_auto_csv','walmart_auto_tool',%s)
ON DUPLICATE KEY UPDATE
  store_name=VALUES(store_name), campaign_id=VALUES(campaign_id),
  campaign_name=VALUES(campaign_name), ad_group_id=VALUES(ad_group_id),
  ad_group_name=VALUES(ad_group_name), item_name=VALUES(item_name),
  impressions=VALUES(impressions), clicks=VALUES(clicks), ctr=VALUES(ctr),
  ad_spend=VALUES(ad_spend), orders=VALUES(orders),
  conversion_rate=VALUES(conversion_rate), total_sales=VALUES(total_sales),
  acos=VALUES(acos), cpc=VALUES(cpc), cvr=VALUES(cvr), roas=VALUES(roas),
  total_add_to_cart=VALUES(total_add_to_cart), source_task_id=VALUES(source_task_id)
"""


def agg_to_params(agg, store_name, operator, task_id):
    kw = str(agg.get("keyword") or "").strip()
    # 来源列聚合后为字符串（新键下应为单值）；Match Type 取聚合值
    return (
        agg.get("date") or "", store_name,
        str(agg.get("Campaign Id") or ""), str(agg.get("Campaign Name") or ""),
        str(agg.get("Ad Group Id") or ""), str(agg.get("Ad Group Name") or ""),
        str(agg.get("item_id") or ""), str(agg.get("item_name") or ""),
        kw, kw.lower()[:100],
        str(agg.get("Match Type") or ""),
        agg.get("impressions") or 0, agg.get("clicks") or 0, agg.get("ctr"),
        agg.get("ad_spend") or 0, agg.get("orders") or 0, agg.get("cvr"),
        agg.get("total_attributed_sales") or 0, agg.get("acos"), agg.get("cpc"),
        agg.get("cvr"), agg.get("roas"), agg.get("total_add_to_cart") or 0,
        operator or "", task_id or "",
    )


def main():
    execute = "--execute" in sys.argv
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT task_id, store_name, operator, row_json FROM raw_walmart_ads_csv ORDER BY id")
            groups = defaultdict(list)
            meta = {}
            for r in cur.fetchall():
                row = json_val(r["row_json"])
                if not isinstance(row, dict):
                    continue
                k = (str(r["task_id"] or ""), str(r["store_name"] or ""))
                groups[k].append(row)
                meta[k] = str(r["operator"] or "")
        print("RAW 分组数(task×store)=%d 总行=%d" % (len(groups), sum(len(v) for v in groups.values())))

        all_params = []
        for (task_id, store_name), rows in groups.items():
            auto_rows = [r for r in rows if is_auto_ad(r)]
            aggs = aggregate(auto_rows)
            for a in aggs:
                compute_metrics(a)
                all_params.append(agg_to_params(a, store_name, meta[(task_id, store_name)], task_id))
        print("重建FACT行数=%d" % len(all_params))

        # 黄金样例预览：2026-07-13 / 19973255164 / cooking oil spray 应为两行（两个Campaign）
        golden = [p for p in all_params if p[6] == "19973255164" and p[8] == "cooking oil spray"]
        print("GOLDEN_PREVIEW=%s" % json.dumps(
            [{"date": g[0], "campaign": g[3], "imp": g[11], "clicks": g[12],
              "spend": float(g[14]), "orders": g[15], "sales": float(g[17])} for g in golden],
            ensure_ascii=False))

        if not execute:
            print("DRY_RUN_DONE（零写入）")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = "backup_fact_ads_auto_%s" % ts
        with db.cursor() as cur:
            cur.execute("CREATE TABLE %s AS SELECT * FROM fact_ads_keyword_daily "
                        "WHERE source_type='walmart_auto_csv'" % backup)
            cur.execute("SELECT COUNT(*) n FROM %s" % backup)
            bn = cur.fetchone()["n"]
        db.commit()
        print("BACKUP_TABLE=%s rows=%d" % (backup, bn))

        with db.cursor() as cur:
            cur.execute("DELETE FROM fact_ads_keyword_daily WHERE source_type='walmart_auto_csv'")
            deleted = cur.rowcount
            affected = 0
            for i in range(0, len(all_params), 500):
                affected += cur.executemany(UPSERT_SQL, all_params[i:i + 500])
        db.commit()
        print("SUMMARY_JSON=%s" % json.dumps({
            "backupTable": backup, "backupRows": bn, "deleted": deleted,
            "rebuiltParams": len(all_params), "affectedRows": affected,
            "status": "success"}, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
