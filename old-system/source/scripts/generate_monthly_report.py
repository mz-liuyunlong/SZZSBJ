#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
月报生成器 v1.0（2026-07-15，口径=月报系统/月报与月度规划_开发方案.md 定稿）

产物：index.html（公司月报）+ owner-*.html（个人月报）+ summary.json
落库：ai_business_report 登记（monthly）+ ai_monthly_issue_item 问题清单（催办/待填/对账三用）

核心口径（定稿，勿改）：
  - 利润等级：dim_product_business_state.profit_level 直读（取<=月末最近快照日，如实标注）
  - 生命周期：dim_product.manual_lifecycle_stage 优先，否则 state.lifecycle_stage（实际六档）
  - 库存金额 = 库存数量×(采购成本+头程)÷6.6 折美元；缺成本按0计并分级披露
  - 问题产品 = 月毛利率<10%(含亏损) ∪ 月末信号命中 ∪ 月销量<30 ∪ 周转>90 ∪
               新品上架7天未出单 ∪ 缺成本(有WFS库存或0401后创建) ∪ 缺负责人；全量列出
  - 豁免(v5,2026-08 同 todo)：报告月整月WFS库存MAX=0 且 报告月WFS销量=0 且 WFS在途(PMC)=0 → 不进问题清单，单独披露数量
  - 广告占比 = 月度广告费÷月度销售额
  - 等级不做环比；销售/利润与上月环比
  - 目标：biz_business_target monthly/quarterly；公司=负责人合计
  - 对账：biz_monthly_plan(plan_month=报告月) 五态：✅达成/⚠️部分达成/❌未执行/🚫未填/—观察中

安全：只读业务数据；写入仅限 ai_business_report + ai_monthly_issue_item（AI层）+ OUT_DIR 文件。
用法：python3 generate_monthly_report.py [--month 2026-06] [--trigger cron|manual]
      [--out-base DIR] [--no-register]
"""

import argparse
import json
import os
import re
import sys
import html as html_mod
from collections import defaultdict
from datetime import datetime, date, timedelta

try:
    import pymysql
except ImportError:
    sys.stderr.write("需要 pymysql\n")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────
SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>"
ENV_PATH = "/opt/lingxing-auto/.env"
OUT_BASE_DEFAULT = "/opt/lingxing-auto/reports/ai-business"
DATA_READY_HOUR = 17
EXCHANGE_RATE = 6.6
LOW_MARGIN_PCT = 10.0
LOW_SALES_QTY = 30
TURNOVER_DAYS = 90
NEWPROD_NO_ORDER_DAYS = 7
HIST_CUTOFF = "2026-04-01"
SIGNAL_MIN_DATE = "2026-07-06"
LIFECYCLE_ORDER = ["新品期", "测品期", "测品结束", "上升期", "稳定期", "清货期"]
LEVEL_ORDER = ["A级【稳健款】", "B级【潜力稳健款】", "C级【优化整改款】", "D级【止损亏损款】", "未评级"]
# 成本表列名（启动自省校验，与生产不符则干净退出并回传实际列）
COST_TABLE = "dim_product_cost_config"
COST_PURCHASE_COL = "purchase_cost"
COST_FIRSTMILE_COL = "first_mile_shipping_cost"
# 负责人别名归一（RAW 历史快照按 B案不改原始数据，读取时统一；2026-07-14 需求方确认啊四=林翔）
OWNER_ALIASES = {"啊四": "林翔"}


def normalize_owner(name):
    n = str(name or "").strip()
    return OWNER_ALIASES.get(n, n)

MONTH_KEY = ""      # 报告月 2026-06
MONTH_START = MONTH_END = PREV_START = PREV_END = ""
PLAN_MONTH = ""     # 规划月=报告月+1
QUARTER_KEY = ""
OUT_DIR = ""
TRIGGER_SOURCE = "manual"
REGISTER = True


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


def num(v):
    if v is None:
        return 0.0
    s = str(v).replace(",", "").replace("%", "").strip()
    if s == "" or s.lower() in ("null", "none", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def fnum(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def pct(a, b):
    a, b = fnum(a), fnum(b)
    return (a / b * 100.0) if b else 0.0


def esc(s):
    return html_mod.escape(str(s if s is not None else ""))


def safe_name(owner):
    return re.sub(r"[^\w一-鿿-]", "_", owner)


def fmt_money(v):
    return "{:,.2f}".format(fnum(v))


def latest_complete_date():
    lag = 2 if datetime.now().hour >= DATA_READY_HOUR else 3
    return date.today() - timedelta(days=lag)


def month_range(key):
    y, m = int(key[:4]), int(key[5:7])
    last = (date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)).day
    return "%04d-%02d-01" % (y, m), "%04d-%02d-%02d" % (y, m, last)


def init_config(argv=None):
    global MONTH_KEY, MONTH_START, MONTH_END, PREV_START, PREV_END
    global PLAN_MONTH, QUARTER_KEY, OUT_DIR, TRIGGER_SOURCE, REGISTER
    ap = argparse.ArgumentParser(description="月报生成器 v1.0")
    ap.add_argument("--month", help="报告月 YYYY-MM（默认=上个自然月）")
    ap.add_argument("--trigger", choices=["cron", "manual"], default="manual")
    ap.add_argument("--out-base", default=OUT_BASE_DEFAULT)
    ap.add_argument("--no-register", action="store_true")
    a = ap.parse_args(argv)
    if a.month:
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", a.month):
            sys.exit("--month 格式应为 YYYY-MM")
        MONTH_KEY = a.month
    else:
        first = date.today().replace(day=1)
        MONTH_KEY = (first - timedelta(days=1)).strftime("%Y-%m")
    MONTH_START, MONTH_END = month_range(MONTH_KEY)
    if date.fromisoformat(MONTH_END) > latest_complete_date():
        sys.exit("报告月 %s 数据未收口（最新完整数据日 %s），拒绝生成"
                 % (MONTH_KEY, latest_complete_date()))
    prev_last = date.fromisoformat(MONTH_START) - timedelta(days=1)
    PREV_START, PREV_END = month_range(prev_last.strftime("%Y-%m"))
    y, m = int(MONTH_KEY[:4]), int(MONTH_KEY[5:7])
    PLAN_MONTH = "%04d-%02d" % (y + (m == 12), (m % 12) + 1)
    QUARTER_KEY = "%d-Q%d" % (y, (m - 1) // 3 + 1)
    TRIGGER_SOURCE = a.trigger
    REGISTER = not a.no_register
    OUT_DIR = os.path.join(a.out_base, "monthly-%s" % MONTH_KEY)
    if os.path.exists(OUT_DIR):
        OUT_DIR += "-%s" % datetime.now().strftime("%H%M%S")


# ── 取数 ──────────────────────────────────────────────────────────────
def verify_cost_columns(db):
    """启动自省：成本表列名与假设不符则干净退出（禁止臆测字段铁律）"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (COST_TABLE,))
        cols = {r["COLUMN_NAME"] for r in cur.fetchall()}
    need = {COST_PURCHASE_COL, COST_FIRSTMILE_COL, "msku"}
    missing = need - cols
    if missing:
        sys.exit("COST_COLUMNS_MISMATCH: %s 缺列 %s ；实际列=%s"
                 % (COST_TABLE, sorted(missing), sorted(cols)))


def fetch_profit_agg(db, start, end):
    """RAW order_profit_daily → owner→(store,item)→{sales,qty,profit,ad,mskus,names}"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT data_date, row_json FROM raw_feishu_table "
            "WHERE spreadsheet_token=%s AND sheet_id='<REDACTED_FEISHU_SHEET_ID>' "
            "AND data_date BETWEEN %s AND %s",
            (SPREADSHEET_TOKEN, start, end))
        agg = defaultdict(lambda: defaultdict(lambda: {
            "sales": 0.0, "qty": 0.0, "profit": 0.0, "ad": 0.0,
            "mskus": set(), "store_name": "", "product_name": ""}))
        for r in cur.fetchall():
            try:
                j = json.loads(r["row_json"])
            except Exception:
                continue
            item_id = str(j.get("商品ID") or "").strip()
            if not item_id:
                continue
            owner = normalize_owner(j.get("负责人")) or "(未分配)"
            key = (str(j.get("店铺ID") or "").strip(), item_id)
            it = agg[owner][key]
            it["sales"] += num(j.get("今日销售额（$）"))
            it["qty"] += num(j.get("今日销量"))
            it["profit"] += num(j.get("毛利润（$）"))
            it["ad"] += num(j.get("广告花费（$）"))
            msku = str(j.get("MSKU") or "").strip()
            if msku:
                it["mskus"].add(msku)
            if not it["store_name"]:
                it["store_name"] = str(j.get("店铺") or "")
            if not it["product_name"]:
                it["product_name"] = str(j.get("品名") or "")
        return agg


def fetch_state(db, upto):
    """business_state 最近快照（<=月末，无则最早可得）：(store,item)→level/lifecycle/turnover"""
    with db.cursor() as cur:
        cur.execute("SELECT MAX(stat_date) d FROM dim_product_business_state WHERE stat_date<=%s", (upto,))
        r = cur.fetchone()
        stat = str(r["d"])[:10] if r and r.get("d") else None
        approx = False
        if not stat:
            cur.execute("SELECT MIN(stat_date) d FROM dim_product_business_state")
            r = cur.fetchone()
            stat = str(r["d"])[:10] if r and r.get("d") else None
            approx = True
        if not stat:
            return {}, None, False
        cur.execute(
            "SELECT s.store_id, s.item_id, s.profit_level, s.lifecycle_stage, "
            "s.product_type, s.inventory_turnover_days, d.manual_lifecycle_stage "
            "FROM dim_product_business_state s "
            "LEFT JOIN dim_product d ON d.platform=s.platform AND d.store_id=s.store_id "
            "  AND d.item_id=s.item_id AND d.msku=s.msku "
            "WHERE s.platform='walmart' AND s.stat_date=%s", (stat,))
        m = {}
        for r in cur.fetchall():
            k = (str(r["store_id"]), str(r["item_id"]))
            cur_v = m.get(k, {"levels": set(), "lifecycles": set(), "types": set(), "turnover": None})
            if r.get("profit_level"):
                cur_v["levels"].add(str(r["profit_level"]))
            if r.get("product_type"):
                cur_v["types"].add(str(r["product_type"]))
            lc = str(r.get("manual_lifecycle_stage") or "").strip() or str(r.get("lifecycle_stage") or "").strip()
            if lc:
                cur_v["lifecycles"].add(lc)
            t = r.get("inventory_turnover_days")
            if t is not None:
                cur_v["turnover"] = max(fnum(t), fnum(cur_v["turnover"]))
            m[k] = cur_v
        return m, stat, approx


def fetch_inventory(db, upto):
    """<=月末最近快照：(store,item)→{wfs,avail,inbound,total_qty}"""
    with db.cursor() as cur:
        cur.execute("SELECT MAX(snapshot_date) d FROM fact_inventory_daily WHERE snapshot_date<=%s", (upto,))
        r = cur.fetchone()
        snap = str(r["d"])[:10] if r and r.get("d") else None
        if not snap:
            return {}, None
        cur.execute(
            "SELECT store_id, item_id, SUM(COALESCE(wfs_available_stock,0)) wfs, "
            "SUM(COALESCE(available_stock,0)) avail, SUM(COALESCE(inbound_stock,0)) inbound "
            "FROM fact_inventory_daily WHERE platform='walmart' AND snapshot_date=%s "
            "GROUP BY store_id, item_id", (snap,))
        m = {}
        for r in cur.fetchall():
            m[(str(r["store_id"]), str(r["item_id"]))] = {
                "wfs": fnum(r["wfs"]), "avail": fnum(r["avail"]), "inbound": fnum(r["inbound"]),
                "total_qty": fnum(r["wfs"]) + fnum(r["avail"]) + fnum(r["inbound"]),
            }
        return m, snap


def fetch_costs(db):
    """msku→单位成本$=(采购+头程)/汇率；cost_flags: full/no_purchase/no_firstmile/none"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT msku, %s AS pc, %s AS fm FROM %s"
            % (COST_PURCHASE_COL, COST_FIRSTMILE_COL, COST_TABLE))
        m = {}
        for r in cur.fetchall():
            msku = str(r["msku"] or "").strip()
            if not msku:
                continue
            pc, fm = r.get("pc"), r.get("fm")
            unit = (fnum(pc) + fnum(fm)) / EXCHANGE_RATE
            flag = "full"
            if pc is None and fm is None:
                flag = "none"
            elif pc is None:
                flag = "no_purchase"
            elif fm is None:
                flag = "no_firstmile"
            old = m.get(msku)
            if old is None or unit > old[0]:
                m[msku] = (unit, flag)
        return m


def fetch_signals_on(db, day):
    """月末日信号：(store,item)→{rules:[名], action}"""
    if day < SIGNAL_MIN_DATE:
        return {}
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, rule_name, suggested_action "
            "FROM biz_product_rule_signal_daily "
            "WHERE platform='walmart' AND should_notify=1 AND signal_date=%s", (day,))
        m = defaultdict(lambda: {"rules": [], "action": ""})
        for r in cur.fetchall():
            k = (str(r["store_id"]), str(r["item_id"]))
            m[k]["rules"].append(str(r["rule_name"]))
            if not m[k]["action"]:
                m[k]["action"] = str(r.get("suggested_action") or "")
        return dict(m)


def fetch_launch_dates(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, MIN(launch_date) d FROM dim_product "
            "WHERE platform='walmart' AND launch_date IS NOT NULL GROUP BY store_id, item_id")
        return {(str(r["store_id"]), str(r["item_id"])): str(r["d"])[:10]
                for r in cur.fetchall() if r.get("d")}


def fetch_since_qty(db, since):
    """since 以来累计销量（历史SKU判定）：(store,item)→qty，来源 fact_sales_daily"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, SUM(COALESCE(sales_qty,0)) q FROM fact_sales_daily "
            "WHERE platform='walmart' AND stat_date>=%s GROUP BY store_id, item_id", (since,))
        return {(str(r["store_id"]), str(r["item_id"])): fnum(r["q"]) for r in cur.fetchall()}


def fetch_targets(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT target_type, owner, metric, target_value FROM biz_business_target "
            "WHERE (target_type='monthly' AND period_key=%s) "
            "   OR (target_type='quarterly' AND period_key=%s)",
            (MONTH_KEY, QUARTER_KEY))
        t = defaultdict(lambda: {"m_sales": 0.0, "m_profit": 0.0, "q_sales": 0.0, "q_profit": 0.0})
        for r in cur.fetchall():
            key = ("m_" if r["target_type"] == "monthly" else "q_") + str(r["metric"])
            t[str(r["owner"])][key] = fnum(r["target_value"])
        return dict(t)


def fetch_ads_sales(db, start, end):
    """公司级 ACOS 用：月度广告销售额，按 (store,item) 返回，供按 universe 过滤（2026-07-24 #2-7）"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, ROUND(SUM(total_sales),2) s FROM fact_ads_product_daily "
            "WHERE platform='walmart' AND stat_date BETWEEN %s AND %s "
            "GROUP BY store_id, item_id", (start, end))
        return {(str(r["store_id"]), str(r["item_id"])): fnum(r["s"]) for r in cur.fetchall()}


def fetch_plans(db, plan_month):
    """对账用：plan_month 的月度规划，(store,item)→plan行"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, msku, owner, indicator1_type, indicator1_target, "
            "indicator2_type, indicator2_target, normal_operation, note, variant_actual "
            "FROM biz_monthly_plan WHERE plan_month=%s", (plan_month,))
        m = {}
        for r in cur.fetchall():
            m[(str(r["store_id"]), str(r["item_id"]))] = r
        return m


# ── 判定 ──────────────────────────────────────────────────────────────
def fetch_month_wfs_max(db, start, end):
    """v5豁免：报告月整月 WFS 库存 MAX：(store,item)→max_wfs"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, MAX(COALESCE(wfs_available_stock,0)) mx "
            "FROM fact_inventory_daily WHERE platform='walmart' AND snapshot_date BETWEEN %s AND %s "
            "GROUP BY store_id, item_id", (start, end))
        return {(str(r["store_id"]), str(r["item_id"])): fnum(r["mx"]) for r in cur.fetchall()}


def fetch_wfs_sales(db, start, end):
    """v5豁免：报告月 WFS 销量 SUM：(store,item)→wfs_qty，来源 fact_mp_sales_channel_daily"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, SUM(COALESCE(wfs_sales_qty,0)) q "
            "FROM fact_mp_sales_channel_daily WHERE platform='walmart' AND stat_date BETWEEN %s AND %s "
            "GROUP BY store_id, item_id", (start, end))
        return {(str(r["store_id"]), str(r["item_id"])): fnum(r["q"]) for r in cur.fetchall()}


def fetch_wfs_transit(db):
    """v5豁免：WFS 在途（PMC 口径）未完结货件 Σmax(declare-received)，经 dim_product 映射 (store,item)→transit"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT dp.store_id, dp.item_id, SUM(t.in_transit) transit FROM ("
            " SELECT s.store_id, si.msku, SUM(GREATEST(COALESCE(si.declare_num,0)-COALESCE(si.received_num,0),0)) in_transit"
            " FROM fact_wfs_shipment s JOIN fact_wfs_shipment_item si"
            "  ON si.platform=s.platform AND si.store_id=s.store_id AND si.shipment_id=s.shipment_id"
            " WHERE s.platform='walmart' AND s.to_closed_time IS NULL AND s.to_cancelled_time IS NULL"
            " GROUP BY s.store_id, si.msku) t"
            " JOIN dim_product dp ON dp.platform='walmart' AND dp.store_id=t.store_id AND dp.msku=t.msku"
            " GROUP BY dp.store_id, dp.item_id")
        return {(str(r["store_id"]), str(r["item_id"])): fnum(r["transit"]) for r in cur.fetchall()}


def build_issue(key, it, state, inv, sig, launch, wfs_max, wfs_sales, transit, cost_flag, owner):
    """返回 (是否豁免/历史SKU, reasons列表, action)。
    豁免口径 v5（2026-08，与 todo/M2 一致）：报告月整月WFS库存MAX=0 且 报告月WFS销量SUM=0 且 WFS在途(PMC)=0。"""
    is_hist = (fnum(wfs_max) <= 0 and fnum(wfs_sales) <= 0 and fnum(transit) <= 0)
    if is_hist:
        return True, [], ""
    reasons = []
    margin = pct(it["profit"], it["sales"])
    if it["sales"] > 0 and it["profit"] < 0:
        reasons.append("亏损（毛利%.2f）" % it["profit"])
    elif it["sales"] > 0 and margin < LOW_MARGIN_PCT:
        reasons.append("月毛利率%.1f%%<%.0f%%" % (margin, LOW_MARGIN_PCT))
    if sig and sig.get("rules"):
        reasons.append("信号：" + "、".join(sorted(set(sig["rules"]))[:3]))
    if it["qty"] < LOW_SALES_QTY:
        reasons.append("月销%d单<%d" % (int(it["qty"]), LOW_SALES_QTY))
    turnover = state.get("turnover") if state else None
    if turnover is not None and fnum(turnover) > TURNOVER_DAYS:
        reasons.append("周转%d天>%d" % (int(fnum(turnover)), TURNOVER_DAYS))
    lifecycles = state.get("lifecycles", set()) if state else set()
    if "新品期" in lifecycles and it["qty"] <= 0 and launch:
        try:
            days = (date.fromisoformat(MONTH_END) - date.fromisoformat(launch)).days
            if days >= NEWPROD_NO_ORDER_DAYS:
                reasons.append("新品上架%d天未出单" % days)
        except ValueError:
            pass
    if cost_flag != "full":
        flag_txt = {"none": "完全无成本配置", "no_purchase": "缺采购成本", "no_firstmile": "缺头程成本"}
        reasons.append(flag_txt.get(cost_flag, "成本异常"))
    if owner == "(未分配)":
        reasons.append("缺负责人")
    action = (sig or {}).get("action", "")
    return False, reasons, action


def reconcile_plan(plan, it, months_metrics):
    """五态对账：✅/⚠️/❌/🚫/—；months_metrics={'margin':..,'sales':..,'qty':..,'ad_ratio':..}"""
    if plan is None:
        return "🚫 未填计划", []
    if plan.get("normal_operation"):
        return "— 观察中（正常运营）", []
    results = []
    for i in ("1", "2"):
        t = plan.get("indicator%s_type" % i)
        v = fnum(plan.get("indicator%s_target" % i))
        if not t:
            continue
        if t == "提高毛利率":
            ok = months_metrics["margin"] >= v
            results.append(("毛利率≥%.1f%%" % v, "实际%.1f%%" % months_metrics["margin"], ok))
        elif t == "提升销售额":
            ok = months_metrics["sales"] >= v
            results.append(("销售额≥$%s" % fmt_money(v), "实际$%s" % fmt_money(months_metrics["sales"]), ok))
        elif t == "调整广告":
            ok = months_metrics["ad_ratio"] <= v
            results.append(("广告占比≤%.1f%%" % v, "实际%.1f%%" % months_metrics["ad_ratio"], ok))
        elif t == "清货":
            ok = months_metrics["qty"] >= v
            results.append(("清货≥%d件" % int(v), "实际%d件" % int(months_metrics["qty"]), ok))
        elif t == "新增变体":
            va = plan.get("variant_actual")
            ok = va is not None and fnum(va) >= v
            results.append(("新增变体≥%d" % int(v),
                            ("人工汇报%d" % int(fnum(va))) if va is not None else "待人工汇报", ok))
    if not results:
        return "🚫 未填计划", []
    oks = [r[2] for r in results]
    if all(oks):
        return "✅ 达成", results
    if any(oks):
        return "⚠️ 部分达成", results
    return "❌ 未达成", results


# ── 维度产品全集（总盘口径：product_management_status=active） ────────
def fetch_archived_set(db):
    """归档产品集合（2026-07-15 需求方：归档商品不参与任何报告分析）"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT store_id, item_id FROM dim_product "
            "WHERE platform='walmart' AND product_management_status='archived'")
        return {(str(r["store_id"]), str(r["item_id"])) for r in cur.fetchall()}


def fetch_dim_products(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, store_name, "
            "MAX(COALESCE(NULLIF(owner,''),'')) owner, "
            "MAX(COALESCE(NULLIF(product_name,''), NULLIF(item_name,''),'')) pname, "
            "GROUP_CONCAT(DISTINCT NULLIF(msku,'')) mskus, "
            "MIN(created_at) created_at "
            "FROM dim_product WHERE platform='walmart' "
            "AND COALESCE(NULLIF(product_management_status,''),'active')='active' "
            "GROUP BY store_id, item_id, store_name")
        m = {}
        for r in cur.fetchall():
            m[(str(r["store_id"]), str(r["item_id"]))] = {
                "owner": normalize_owner(r["owner"]) or "(未分配)",
                "store_name": str(r["store_name"] or ""),
                "pname": str(r["pname"] or ""),
                "mskus": [s for s in str(r["mskus"] or "").split(",") if s],
                "created_at": str(r["created_at"] or "")[:10],
            }
        return m


# ── 记录组装 ──────────────────────────────────────────────────────────
def assemble_records(db):
    verify_cost_columns(db)
    cur_agg = fetch_profit_agg(db, MONTH_START, MONTH_END)
    prev_agg = fetch_profit_agg(db, PREV_START, PREV_END)
    q_start = month_range("%s-%02d" % (QUARTER_KEY[:4], (int(QUARTER_KEY[6]) - 1) * 3 + 1))[0]
    qtr_agg = fetch_profit_agg(db, q_start, MONTH_END)
    state, state_date, state_approx = fetch_state(db, MONTH_END)
    inv, inv_date = fetch_inventory(db, MONTH_END)
    costs = fetch_costs(db)
    signals = fetch_signals_on(db, MONTH_END)
    launches = fetch_launch_dates(db)
    since_qty = fetch_since_qty(db, HIST_CUTOFF)
    wfs_max_m = fetch_month_wfs_max(db, MONTH_START, MONTH_END)   # v5豁免：报告月整月WFS库存MAX
    wfs_sales_m = fetch_wfs_sales(db, MONTH_START, MONTH_END)     # v5豁免：报告月WFS销量SUM
    wfs_transit_m = fetch_wfs_transit(db)                          # v5豁免：WFS在途(PMC)
    targets = fetch_targets(db)
    dimp = fetch_dim_products(db)
    plans = fetch_plans(db, MONTH_KEY)  # 对账：报告月的规划（首期为空）
    ads_sales_items = fetch_ads_sales(db, MONTH_START, MONTH_END)

    def flat(agg):
        out = defaultdict(lambda: {"sales": 0.0, "qty": 0.0, "profit": 0.0, "ad": 0.0,
                                   "mskus": set(), "store_name": "", "product_name": ""})
        owner_of = {}
        for owner, imap in agg.items():
            for key, it in imap.items():
                o = out[key]
                for k in ("sales", "qty", "profit", "ad"):
                    o[k] += it[k]
                o["mskus"] |= it["mskus"]
                o["store_name"] = o["store_name"] or it["store_name"]
                o["product_name"] = o["product_name"] or it["product_name"]
                owner_of.setdefault(key, owner)
        return out, owner_of

    cur_items, cur_owner_of = flat(cur_agg)
    prev_items, _ = flat(prev_agg)
    qtr_items, _ = flat(qtr_agg)

    archived = fetch_archived_set(db)
    universe = (set(dimp.keys()) | set(cur_items.keys()))
    archived_excluded = len(universe & archived)
    universe -= archived
    records, hist_count, cs_excluded = [], 0, 0
    for key in universe:
        dp = dimp.get(key, {})
        it = cur_items.get(key, {"sales": 0.0, "qty": 0.0, "profit": 0.0, "ad": 0.0,
                                 "mskus": set(), "store_name": "", "product_name": ""})
        owner = dp.get("owner") or cur_owner_of.get(key, "(未分配)")
        st = state.get(key, {})
        iv = inv.get(key)
        mskus = sorted(set(dp.get("mskus", [])) | it["mskus"])
        unit_cost, cost_flag = 0.0, "none"
        found = False
        for mk in mskus:
            if mk in costs:
                c, f = costs[mk]
                if (not found) or (c > unit_cost):
                    unit_cost = c
                    cost_flag = f
                found = True
        if not found:
            cost_flag = "none"
        inv_qty = fnum((iv or {}).get("wfs")) + fnum((iv or {}).get("avail")) + fnum((iv or {}).get("inbound"))
        inv_value = inv_qty * unit_cost
        is_hist, reasons, action = build_issue(
            key, it, st, iv, signals.get(key), launches.get(key),
            wfs_max_m.get(key, 0.0), wfs_sales_m.get(key, 0.0), wfs_transit_m.get(key, 0.0), cost_flag, owner)
        if is_hist:
            hist_count += 1
            continue
        # CS测品不参与月度规划与问题清单（2026-07-15 需求方定稿；仍留在总盘/等级/生命周期统计）
        is_cs = any("CS" in t or "测品" in t for t in st.get("types", set()))
        if is_cs and reasons:
            reasons, action = [], ""
            cs_excluded += 1
        margin = pct(it["profit"], it["sales"])
        ad_ratio = pct(it["ad"], it["sales"])
        levels = sorted(st.get("levels", set()),
                        key=lambda x: LEVEL_ORDER.index(x) if x in LEVEL_ORDER else 99)
        level = levels[0] if levels else "未评级"
        lifecycles = st.get("lifecycles", set())
        lifecycle = next((x for x in LIFECYCLE_ORDER if x in lifecycles), "") or (sorted(lifecycles)[0] if lifecycles else "-")
        prev_it = prev_items.get(key)
        status, details = reconcile_plan(
            plans.get(key), it,
            {"margin": margin, "sales": it["sales"], "qty": it["qty"], "ad_ratio": ad_ratio},
        ) if reasons else ("", [])
        records.append({
            "key": key, "owner": owner, "store_name": it["store_name"] or dp.get("store_name", ""),
            "pname": (it["product_name"] or dp.get("pname", ""))[:30],
            "mskus": mskus, "level": level, "lifecycle": lifecycle,
            "sales": it["sales"], "qty": it["qty"], "profit": it["profit"], "ad": it["ad"],
            "margin": margin, "ad_ratio": ad_ratio,
            "prev_sales": fnum(prev_it["sales"]) if prev_it else 0.0,
            "prev_profit": fnum(prev_it["profit"]) if prev_it else 0.0,
            "wfs": fnum((iv or {}).get("wfs")), "inbound": fnum((iv or {}).get("inbound")),
            "inv_qty": inv_qty, "inv_value": inv_value, "cost_flag": cost_flag,
            "turnover": fnum(st.get("turnover")) if st.get("turnover") is not None else None,
            "reasons": reasons, "action": action,
            "plan_status": status, "plan_details": details,
        })
    ctx = {
        "records": records, "hist_count": hist_count, "cs_excluded": cs_excluded,
        "archived_excluded": archived_excluded,
        "targets": targets, "qtr_items": qtr_items,
        "prev_items": prev_items, "cur_owner_of": cur_owner_of,
        "state_date": state_date, "state_approx": state_approx, "inv_date": inv_date,
        "ads_sales_items": ads_sales_items,
    }
    return ctx


# ── 渲染 ──────────────────────────────────────────────────────────────
CSS = """
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:0;background:#f5f6f8;color:#222}
.wrap{max-width:1360px;margin:0 auto;padding:24px}
h1{font-size:22px}h2{font-size:17px;margin:26px 0 10px;border-left:4px solid #4a6cf7;padding-left:8px}
.meta{background:#fff;border-radius:8px;padding:12px 16px;font-size:12.5px;line-height:1.9;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}
.card{background:#fff;border-radius:8px;padding:10px 16px;min-width:120px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card .v{font-size:19px;font-weight:600}.card .k{font-size:12px;color:#888}
table{border-collapse:collapse;width:100%;background:#fff;font-size:12.5px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin:8px 0}
th,td{border:1px solid #e8e8e8;padding:5px 8px;text-align:right;white-space:nowrap}
th{background:#f0f2f7;cursor:pointer}
td.l,th.l{text-align:left}td.wrapc{text-align:left;white-space:normal;max-width:320px}
tr.bad{background:#fff4f2}
input.flt{padding:6px 10px;width:300px;margin:6px 0;border:1px solid #ccc;border-radius:5px}
.note{font-size:12px;color:#777;margin:5px 0}
a{color:#3450c0;text-decoration:none}
"""
SORT_JS = """
function sortT(tid,ci){var t=document.getElementById(tid),b=t.tBodies[0],
r=Array.from(b.rows),asc=t.getAttribute('data-s')!=(''+ci);
r.sort(function(x,y){var a=x.cells[ci].innerText,c=y.cells[ci].innerText,
na=parseFloat(a.replace(/[,%$]/g,'')),nc=parseFloat(c.replace(/[,%$]/g,''));
if(!isNaN(na)&&!isNaN(nc))return asc?nc-na:na-nc;
return asc?(''+c).localeCompare(a,'zh'):(''+a).localeCompare(c,'zh');});
r.forEach(function(x){b.appendChild(x)});t.setAttribute('data-s',asc?(''+ci):'');}
function fltT(tid,q){q=q.toLowerCase();Array.from(document.getElementById(tid).tBodies[0].rows)
.forEach(function(r){r.style.display=r.innerText.toLowerCase().indexOf(q)>=0?'':'none';});}
"""


def group_table(recs, keyf, order, tid):
    groups = defaultdict(list)
    for r in recs:
        groups[keyf(r)].append(r)
    tot_sales = sum(r["sales"] for r in recs) or 1
    tot_profit = sum(r["profit"] for r in recs)
    rows = []
    for g in order + sorted(set(groups) - set(order)):
        rs = groups.get(g)
        if not rs:
            continue
        s = sum(r["sales"] for r in rs)
        p = sum(r["profit"] for r in rs)
        rows.append(
            "<tr><td class='l'>%s</td><td>%d</td><td>%.1f%%</td><td>%s</td><td>%.1f%%</td>"
            "<td>%s</td><td>%s</td><td>%.1f%%</td><td>%s</td><td>%s</td></tr>"
            % (esc(g), len(rs), len(rs) * 100.0 / max(len(recs), 1),
               fmt_money(s), s * 100.0 / tot_sales, fmt_money(p),
               ("%.1f%%" % (p * 100.0 / tot_profit)) if tot_profit else "-",
               pct(p, s), fmt_money(sum(r["ad"] for r in rs)),
               fmt_money(sum(r["inv_value"] for r in rs))))
    head = ("<table id='%s'><thead><tr><th class='l'>分组</th><th>产品数</th><th>数量占比</th>"
            "<th>销售额$</th><th>销售贡献</th><th>毛利$</th><th>利润贡献</th><th>毛利率</th>"
            "<th>广告$</th><th>库存金额$</th></tr></thead><tbody>" % tid)
    return head + "\n".join(rows) + "</tbody></table>"


def issue_table(recs, tid):
    rows = []
    for r in sorted([x for x in recs if x["reasons"]], key=lambda x: -x["sales"]):
        plan_txt = r["plan_status"] or "—"
        if r["plan_details"]:
            plan_txt += "：" + "；".join("%s→%s%s" % (t, a, "✅" if ok else "✗") for t, a, ok in r["plan_details"])
        rows.append(
            "<tr class='bad'><td class='l'>%s</td><td class='l'>%s</td><td class='l'>%s</td>"
            "<td class='l'>%s</td><td class='l'>%s</td>"
            "<td>%s</td><td>%s</td><td>%.1f%%</td><td>%s</td><td>%.1f%%</td>"
            "<td>%d</td><td>%s</td><td class='wrapc'>%s</td><td class='wrapc'>%s</td><td class='wrapc'>%s</td></tr>"
            % (esc(r["key"][1]), esc("/".join(r["mskus"])[:40] or "-"), esc(r["owner"]),
               esc(r["level"].split("【")[0]), esc(r["lifecycle"]),
               fmt_money(r["sales"]), fmt_money(r["profit"]), r["margin"],
               fmt_money(r["ad"]), r["ad_ratio"],
               int(r["inv_qty"]), fmt_money(r["inv_value"]),
               esc("；".join(r["reasons"])), esc(r["action"] or "-"), esc(plan_txt)))
    head = ("<input class='flt' placeholder='搜索...' onkeyup=\"fltT('%s',this.value)\">"
            "<table id='%s'><thead><tr>"
            "<th class='l' onclick=\"sortT('%s',0)\">ItemID</th><th class='l'>MSKU</th>"
            "<th class='l' onclick=\"sortT('%s',2)\">负责人</th><th class='l'>等级</th><th class='l'>生命周期</th>"
            "<th onclick=\"sortT('%s',5)\">销售额$</th><th onclick=\"sortT('%s',6)\">毛利$</th>"
            "<th onclick=\"sortT('%s',7)\">毛利率</th><th>广告$</th><th onclick=\"sortT('%s',9)\">广告占比</th>"
            "<th>库存</th><th onclick=\"sortT('%s',11)\">库存金额$</th>"
            "<th class='l'>问题原因</th><th class='l'>建议方向</th><th class='l'>上月计划对账</th>"
            "</tr></thead><tbody>" % ((tid,) * 9))
    return head + "\n".join(rows) + "</tbody></table>", len(rows)


def action_groups(recs):
    grow, adjust, clear = [], [], []
    for r in recs:
        lv = r["level"]
        if lv.startswith("A级") or (lv.startswith("B级") and r["sales"] > r["prev_sales"]) \
           or (r["lifecycle"] == "新品期" and r["profit"] > 0 and r["sales"] > 0):
            grow.append(r)
        if r["sales"] > 0 and r["margin"] < LOW_MARGIN_PCT and not lv.startswith("D级"):
            adjust.append(r)
        if r["ad_ratio"] > 15 and r["sales"] > 0 and r not in adjust:
            adjust.append(r)
        if lv.startswith("D级") or r["lifecycle"] == "清货期" \
           or (r["turnover"] is not None and r["turnover"] > TURNOVER_DAYS):
            clear.append(r)
    def block(title, rs):
        if not rs:
            return "<p class='note'>%s：无</p>" % title
        items = "、".join("%s(%s)" % (esc(r["key"][1]), esc(r["owner"])) for r in sorted(rs, key=lambda x: -x["sales"]))
        return "<p class='note'><b>%s（%d个）</b>：%s</p>" % (title, len(rs), items)
    return (block("放大（A级/上升B级/正毛利新品）", grow)
            + block("调整（毛利率<10%非D级/广告占比>15%）", adjust)
            + block("清货或退出（D级/清货期/周转>90天）", clear))


def render_page(owner, recs, ctx, gen_time):
    """owner=None → 公司月报"""
    is_company = owner is None
    scope = [r for r in recs if is_company or r["owner"] == owner]
    t = ctx["targets"]
    if is_company:
        m_sales_t = sum(v["m_sales"] for v in t.values())
        m_profit_t = sum(v["m_profit"] for v in t.values())
        q_sales_t = sum(v["q_sales"] for v in t.values())
        q_profit_t = sum(v["q_profit"] for v in t.values())
    else:
        tv = t.get(owner, {"m_sales": 0, "m_profit": 0, "q_sales": 0, "q_profit": 0})
        m_sales_t, m_profit_t = tv["m_sales"], tv["m_profit"]
        q_sales_t, q_profit_t = tv["q_sales"], tv["q_profit"]
    sales = sum(r["sales"] for r in scope)
    profit = sum(r["profit"] for r in scope)
    ad = sum(r["ad"] for r in scope)
    prev_sales = sum(r["prev_sales"] for r in scope)
    prev_profit = sum(r["prev_profit"] for r in scope)
    qtr = ctx["qtr_items"]
    keys = {r["key"] for r in scope}
    q_sales = sum(v["sales"] for k, v in qtr.items() if k in keys)
    q_profit = sum(v["profit"] for k, v in qtr.items() if k in keys)
    ads_sales_scope = sum(v for k, v in ctx["ads_sales_items"].items() if k in keys)

    def wow(a, b):
        if b == 0:
            return "新增" if a > 0 else "—"
        d = (a - b) / abs(b) * 100
        return "%s%.1f%%" % ("↑" if d > 0 else ("↓" if d < 0 else "→"), abs(d))

    perf = ("<table><thead><tr><th class='l'>指标</th><th>目标</th><th>实际</th><th>完成率</th>"
            "<th>上月</th><th>环比</th></tr></thead><tbody>"
            "<tr><td class='l'>月销售额$</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            "<tr><td class='l'>月毛利润$</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            "<tr><td class='l'>月毛利率</td><td>-</td><td>%.2f%%</td><td>-</td><td>%.2f%%</td><td>%+.1fpp</td></tr>"
            "<tr><td class='l'>广告费$ / 广告占比</td><td>-</td><td>%s / %.1f%%</td><td colspan='3'>%s</td></tr>"
            "<tr><td class='l'>季度累计销售$（%s）</td><td>%s</td><td>%s</td><td>%s</td><td colspan='2'>-</td></tr>"
            "<tr><td class='l'>季度累计毛利$</td><td>%s</td><td>%s</td><td>%s</td><td colspan='2'>-</td></tr>"
            "</tbody></table>") % (
        fmt_money(m_sales_t) if m_sales_t else "未设定", fmt_money(sales),
        ("%.1f%%" % pct(sales, m_sales_t)) if m_sales_t else "—",
        fmt_money(prev_sales), wow(sales, prev_sales),
        fmt_money(m_profit_t) if m_profit_t else "未设定", fmt_money(profit),
        ("%.1f%%" % pct(profit, m_profit_t)) if m_profit_t else "—",
        fmt_money(prev_profit), wow(profit, prev_profit),
        pct(profit, sales), pct(prev_profit, prev_sales), pct(profit, sales) - pct(prev_profit, prev_sales),
        fmt_money(ad), pct(ad, sales),
        ("公司ACOS %.1f%%" % pct(ad, ads_sales_scope)) if is_company and ads_sales_scope else "-",
        QUARTER_KEY,
        fmt_money(q_sales_t) if q_sales_t else "未设定", fmt_money(q_sales),
        ("%.1f%%" % pct(q_sales, q_sales_t)) if q_sales_t else "—",
        fmt_money(q_profit_t) if q_profit_t else "未设定", fmt_money(q_profit),
        ("%.1f%%" % pct(q_profit, q_profit_t)) if q_profit_t else "—")

    with_sales = [r for r in scope if r["qty"] > 0]
    newps = [r for r in scope if r["lifecycle"] == "新品期"]
    issues = [r for r in scope if r["reasons"]]
    inv_total_v = sum(r["inv_value"] for r in scope)
    overstock = [r for r in scope if r["turnover"] is not None and r["turnover"] > TURNOVER_DAYS]
    cost_missing = [r for r in scope if r["cost_flag"] != "full"]
    cards = [
        ("产品总数", "%d" % len(scope)), ("有销售", "%d" % len(with_sales)),
        ("无销售", "%d" % (len(scope) - len(with_sales))),
        ("有库存", "%d" % sum(1 for r in scope if r["inv_qty"] > 0)),
        ("新品", "%d" % len(newps)),
        ("清货", "%d" % sum(1 for r in scope if r["lifecycle"] == "清货期")),
        ("问题产品", "%d" % len(issues)),
        ("总库存件", "%d" % int(sum(r["inv_qty"] for r in scope))),
        ("库存金额$", fmt_money(inv_total_v)),
        ("积压金额$(周转>90)", fmt_money(sum(r["inv_value"] for r in overstock))),
        ("缺成本产品", "%d" % len(cost_missing)),
    ]
    cards_html = "".join("<div class='card'><div class='v'>%s</div><div class='k'>%s</div></div>"
                         % (esc(v), esc(k)) for k, v in cards)

    new_sold = [r for r in newps if r["qty"] > 0]
    new_block = ("<div class='cards'>" + "".join(
        "<div class='card'><div class='v'>%s</div><div class='k'>%s</div></div>" % (esc(v), esc(k))
        for k, v in [
            ("新品总数", "%d" % len(newps)), ("已出单", "%d" % len(new_sold)),
            ("未出单", "%d" % (len(newps) - len(new_sold))),
            ("正毛利", "%d" % sum(1 for r in newps if r["profit"] > 0)),
            ("毛利率<10%", "%d" % sum(1 for r in newps if r["sales"] > 0 and r["margin"] < LOW_MARGIN_PCT and r["profit"] >= 0)),
            ("亏损", "%d" % sum(1 for r in newps if r["profit"] < 0)),
            ("新品销售$", fmt_money(sum(r["sales"] for r in newps))),
            ("新品毛利$", fmt_money(sum(r["profit"] for r in newps))),
            ("新品广告$", fmt_money(sum(r["ad"] for r in newps))),
            ("新品库存$", fmt_money(sum(r["inv_value"] for r in newps))),
        ]) + "</div>")

    lv = lambda r: r["level"].split("【")[0]
    inv_block = ("<div class='cards'>" + "".join(
        "<div class='card'><div class='v'>%s</div><div class='k'>%s</div></div>" % (esc(v), esc(k))
        for k, v in [
            ("总库存件", "%d" % int(sum(r["inv_qty"] for r in scope))),
            ("总库存金额$", fmt_money(inv_total_v)),
            ("A/B级库存$", fmt_money(sum(r["inv_value"] for r in scope if lv(r) in ("A级", "B级")))),
            ("C/D级库存$", fmt_money(sum(r["inv_value"] for r in scope if lv(r) in ("C级", "D级")))),
            ("清货库存$", fmt_money(sum(r["inv_value"] for r in scope if r["lifecycle"] == "清货期"))),
            ("问题产品库存$", fmt_money(sum(r["inv_value"] for r in issues))),
            ("新品库存$", fmt_money(sum(r["inv_value"] for r in newps))),
            ("60天+库存$", fmt_money(sum(r["inv_value"] for r in scope if r["turnover"] is not None and r["turnover"] > 60))),
            ("90天+库存$", fmt_money(sum(r["inv_value"] for r in overstock))),
        ]) + "</div>")

    it_html, issue_n = issue_table(scope, "ti")
    title = "公司月报" if is_company else ("个人月报 ｜ " + owner)
    nav = "" if is_company else "<p class='note'><a href='index.html'>← 返回公司月报</a></p>"
    return """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>%(title)s %(mk)s</title><style>%(css)s</style><script>%(js)s</script></head>
<body><div class="wrap">
<h1>%(title)s ｜ %(mk)s（%(ms)s ~ %(me)s）</h1>
<div class="meta">生成：%(gen)s ｜ 等级/生命周期快照日：%(sd)s%(approx)s ｜ 库存快照：%(ivd)s ｜ 库存金额=(采购+头程)÷%(rate)s×库存件数，缺成本按0计 ｜ 豁免已剔除 %(hist)d 个（v5：报告月整月WFS库存MAX=0且WFS销量=0且在途=0）｜ CS测品 %(cs)d 个不参与问题清单与月度规划 ｜ 归档产品已全剔除 %(arch)d 个 ｜ 问题产品全量列出%(sig_note)s</div>
<h2>一、目标完成情况</h2>%(perf)s
<h2>二、产品总盘</h2><div class="cards">%(cards)s</div>
<h2>三、ABCD利润等级结构</h2>%(abcd)s
<h2>四、生命周期经营情况</h2>%(lc)s
<h2>五、新品经营情况</h2>%(newb)s
<h2>六、全部问题产品（%(issue_n)d 个）</h2>%(issues)s
<h2>七、库存与资金占用</h2>%(invb)s
<h2>八、下月行动</h2>%(actions)s
%(nav)s
</div></body></html>""" % {
        "title": esc(title), "mk": MONTH_KEY, "ms": MONTH_START, "me": MONTH_END,
        "css": CSS, "js": SORT_JS, "gen": gen_time,
        "sd": ctx["state_date"] or "无", "approx": "（近似月末，如实标注）" if ctx["state_approx"] else "",
        "ivd": ctx["inv_date"] or "无", "rate": EXCHANGE_RATE, "hist": ctx["hist_count"],
        "cs": ctx["cs_excluded"], "arch": ctx["archived_excluded"],
        "sig_note": "" if MONTH_END >= SIGNAL_MIN_DATE else " ｜ 本月无规则信号数据（信号自%s起）" % SIGNAL_MIN_DATE,
        "perf": perf, "cards": cards_html,
        "abcd": group_table(scope, lv, [x.split("【")[0] for x in LEVEL_ORDER], "tabcd"),
        "lc": group_table(scope, lambda r: r["lifecycle"], LIFECYCLE_ORDER, "tlc"),
        "newb": new_block, "issues": it_html, "issue_n": issue_n,
        "invb": inv_block, "actions": action_groups(scope), "nav": nav,
    }


# ── 登记与主流程 ──────────────────────────────────────────────────────
def register_all(ctx, owners_sorted, completeness):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO ai_business_report (report_type, period_key, win_start, win_end, "
                "filter_json, out_dir, completeness_json, status, trigger_source, generated_at) "
                "VALUES ('monthly', %s, %s, %s, %s, %s, %s, 'success', %s, NOW())",
                (MONTH_KEY, MONTH_START, MONTH_END,
                 json.dumps({"owners": "all", "report_type": "monthly"}, ensure_ascii=False),
                 OUT_DIR, json.dumps(completeness, ensure_ascii=False), TRIGGER_SOURCE))
            rid = cur.lastrowid
            n = 0
            for r in ctx["records"]:
                if not r["reasons"]:
                    continue
                # 2026-08-11 upsert 改造（配套 sql/041 唯一键 uq_issue(plan_month,platform,store_id,item_id)）：
                # 同月重跑=就地刷新为最新一次生成，杜绝重复行（2026-07 曾因裸INSERT重跑产生1434条重复）。
                cur.execute(
                    "INSERT INTO ai_monthly_issue_item (report_id, plan_month, owner, platform, "
                    "store_id, item_id, msku, issue_reasons, suggested_action, metrics_json) "
                    "VALUES (%s, %s, %s, 'walmart', %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE report_id=VALUES(report_id), owner=VALUES(owner), "
                    "msku=VALUES(msku), issue_reasons=VALUES(issue_reasons), "
                    "suggested_action=VALUES(suggested_action), metrics_json=VALUES(metrics_json)",
                    (rid, PLAN_MONTH, r["owner"], r["key"][0], r["key"][1],
                     "/".join(r["mskus"])[:120],
                     json.dumps(r["reasons"], ensure_ascii=False),
                     (r["action"] or None),
                     json.dumps({"margin": round(r["margin"], 2), "sales": round(r["sales"], 2),
                                 "qty": int(r["qty"]), "ad_ratio": round(r["ad_ratio"], 2),
                                 "inv_qty": int(r["inv_qty"]), "inv_value": round(r["inv_value"], 2),
                                 "turnover": r["turnover"]}, ensure_ascii=False)))
                n += 1
            # 收尾：清掉本月不属于本次生成的残留行（上次生成有、这次不再是问题产品的行）
            cur.execute(
                "DELETE FROM ai_monthly_issue_item WHERE plan_month=%s AND report_id<>%s",
                (PLAN_MONTH, rid))
            purged = cur.rowcount
        db.commit()
        return rid, n, purged
    finally:
        db.close()


def main():
    init_config()
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("WINDOWS=%s" % json.dumps({
        "month": MONTH_KEY, "win": [MONTH_START, MONTH_END], "prev": [PREV_START, PREV_END],
        "plan_month": PLAN_MONTH, "quarter": QUARTER_KEY, "out_dir": OUT_DIR,
        "trigger": TRIGGER_SOURCE}, ensure_ascii=False))
    db = get_db()
    try:
        ctx = assemble_records(db)
    finally:
        db.close()
    recs = ctx["records"]
    owners = sorted({r["owner"] for r in recs},
                    key=lambda o: -sum(r["sales"] for r in recs if r["owner"] == o))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_page(None, recs, ctx, gen_time))
    for o in owners:
        with open(os.path.join(OUT_DIR, "owner-%s.html" % safe_name(o)), "w", encoding="utf-8") as f:
            f.write(render_page(o, recs, ctx, gen_time))
    issues_total = sum(1 for r in recs if r["reasons"])
    completeness = {"universe_items": len(recs), "hist_excluded": ctx["hist_count"],
                    "cs_excluded_from_plan": ctx["cs_excluded"],
                    "archived_excluded": ctx["archived_excluded"],
                    "owners": len(owners), "issue_items": issues_total, "status": "已完成"}
    summary = {
        "report_kind": "monthly", "period_key": MONTH_KEY, "plan_month": PLAN_MONTH,
        "win_start": MONTH_START, "win_end": MONTH_END, "scope": "all",
        "mtd": {"start": MONTH_START, "end": MONTH_END,
                "sales": round(sum(r["sales"] for r in recs), 2),
                "profit": round(sum(r["profit"] for r in recs), 2)},
        "company_week": {"sales": round(sum(r["sales"] for r in recs), 2),
                         "profit": round(sum(r["profit"] for r in recs), 2)},
        "owners": [{"owner": o, "page": "owner-%s.html" % safe_name(o),
                    "open_issues": sum(1 for r in recs if r["owner"] == o and r["reasons"]),
                    "sales": round(sum(r["sales"] for r in recs if r["owner"] == o), 2),
                    "qty": int(sum(r["qty"] for r in recs if r["owner"] == o)),
                    "profit": round(sum(r["profit"] for r in recs if r["owner"] == o), 2),
                    "ad": round(sum(r["ad"] for r in recs if r["owner"] == o), 2),
                    "items": sum(1 for r in recs if r["owner"] == o)}
                   for o in owners],
        "generated_at": gen_time,
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("COMPLETENESS=%s" % json.dumps(completeness, ensure_ascii=False))
    if REGISTER:
        rid, n, purged = register_all(ctx, owners, completeness)
        print("REPORT_ID=%s" % rid)
        print("ISSUE_ROWS=%d" % n)
        print("PURGED_STALE=%d" % purged)
    else:
        print("REGISTER_SKIPPED")
    print("REPORT_DONE")
    print("OUT_DIR=%s" % OUT_DIR)
    print("RUN_OK")


if __name__ == "__main__":
    main()
