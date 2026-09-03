#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手工版运营周报生成器 v0.2（AI经营分析报告系统原型，2026-07-13）

口径（需求方定稿）：
  - 分析窗口：上周三 ~ 本周二（本次手工版：2026-07-01 ~ 2026-07-07）
  - 对比窗口：再往前7天（2026-06-24 ~ 2026-06-30，注：早于方案B回溯自愈范围，如实标注）
  - 毛利统一来源：raw_feishu_table sheet_id='<REDACTED_FEISHU_SHEET_ID>'（快照内毛利由成本配置计算）
  - 广告销售额/ACOS：fact_ads_product_daily（store_id+item_id 聚合）
  - 库存：fact_inventory_daily 窗口末快照日
  - 问题信号：biz_product_rule_signal_daily（注意：信号自2026-07-06起才有，本窗口仅覆盖06/07两日，如实标注）
  - 运营日志：biz_product_operation_log（log_date 在窗口内；updated_by=admin_ui 视为人工记录）
  - 闭环v0规则：窗口内曾有信号且窗口末日无该信号 → 已恢复；窗口末日仍有 → 未闭环
  - 无运营日志只标"—"，不推断运营没有做事
  - "动作是否有效"留二期（需跨周对比）

v0.2 变更（需求方 2026-07-13 反馈）：
  - 统计范围过滤：仅统计窗口内有销售记录（销量>0 或 销售额≠0）或窗口内任一日
    库存(WFS+可用+在途)>0 的产品；完全无库存且无任何销售记录的产品不进入报告，
    剔除数在完整性校验中如实回传（excluded_no_sales_no_stock）
  - 页面结构：经营总结 + 产品明细单表；问题信号（未闭环含触发原因/已恢复）与
    人工运营记录并入明细表两列；原三/四/五独立段删除
  - HTML 定位：中间产物（供再加工），非最终开会材料

v0.3 变更（需求方 2026-07-13 反馈：运营直接截图贴PPT）：
  - 产品明细改为每个ItemID一张独立卡片（自带表头），本周(07-01~07-07)/上周
    (06-24~06-30)/环比 三行对比；广告分析、页面优化等内容由运营在PPT自行补充
  - 利润等级单独列出：权威来源 dim_product_business_state.profit_level
    （取<=窗口末日的最近快照日，直接读取不重算；多MSKU并集展示；
    CS测品无等级如实标注）——部署AI只读核验结论 2026-07-13
  - 上周无数据：显示"—"，环比行标"新增"

v0.5 变更（需求方 2026-07-13 反馈）：
  - 经营总结改为与产品卡片一致的三行表（本周/上周/环比），上周数值直观可见；
    上周无数据时上周行"—"、环比"新增"

v0.4 变更（需求方 2026-07-13 反馈：经营总结扩展）：
  - 经营总结新增"本月累计"：MTD_START~MTD_END（最新可用数据日=D-2）的
    销售额/毛利/毛利率，负责人页每人自己的，index 加公司级合计
  - 月度/季度目标完成率：目标表（biz_business_target，林翔密码授权录入）
    尚未建，本版显示"目标待录入"占位；正式系统接入后自动计算
  - 周环比沿用本周vs上周卡片（v0已有）

安全：只读数据库（全部 SELECT）；只写 OUT_DIR 下的 HTML 文件；不写任何数据表。
用法：python3 generate_weekly_report_manual.py
"""

import json
import os
import re
import sys
import html as html_mod
from collections import defaultdict
from datetime import datetime

try:
    import pymysql
except ImportError:
    sys.stderr.write("需要 pymysql：pip3 install pymysql --break-system-packages 或使用系统已有环境\n")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────
WIN_START, WIN_END = "2026-07-01", "2026-07-07"     # 分析窗口（上周三~本周二）
PREV_START, PREV_END = "2026-06-24", "2026-06-30"   # 对比窗口
MTD_START, MTD_END = "2026-07-01", "2026-07-11"     # 本月累计（末日=最新可用数据日D-2）
SIGNAL_MIN_DATE = "2026-07-06"                      # 信号表最早日期（如实标注覆盖不全）
PERIOD_KEY = "2026-W28"                             # 窗口末日所在ISO周
SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>"
OUT_DIR = "/opt/lingxing-auto/reports/ai-business/manual-%s" % PERIOD_KEY
ENV_PATH = "/opt/lingxing-auto/.env"

RULE_LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}


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
        host=env.get("DB_HOST", "127.0.0.1"),
        port=int(env.get("DB_PORT", "3306")),
        user=env.get("DB_USER", ""),
        password=env.get("DB_PASSWORD", ""),
        database=env.get("DB_NAME", "walmart_ai_data"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def num(v):
    """快照字段转数值：容忍 '1,234.56'、'12.3%'、空串"""
    if v is None:
        return 0.0
    s = str(v).replace(",", "").replace("%", "").strip()
    if s == "" or s.lower() in ("null", "none", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def esc(s):
    return html_mod.escape(str(s if s is not None else ""))


# ── 数据抓取 ──────────────────────────────────────────────────────────
def fetch_profit_rows(db, start, end):
    """order_profit_daily 快照行 → 解析 JSON"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT data_date, row_json FROM raw_feishu_table "
            "WHERE spreadsheet_token=%s AND sheet_id='<REDACTED_FEISHU_SHEET_ID>' "
            "AND data_date BETWEEN %s AND %s",
            (SPREADSHEET_TOKEN, start, end),
        )
        out = []
        for r in cur.fetchall():
            try:
                j = json.loads(r["row_json"])
            except Exception:
                continue
            j["_date"] = str(r["data_date"])[:10]
            out.append(j)
        return out


def fetch_ad_sales(db, start, end):
    """fact_ads_product_daily：store_id+item_id → {spend, sales}"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, ROUND(SUM(ad_spend),2) AS spend, "
            "ROUND(SUM(total_sales),2) AS ad_sales "
            "FROM fact_ads_product_daily WHERE platform='walmart' "
            "AND stat_date BETWEEN %s AND %s GROUP BY store_id, item_id",
            (start, end),
        )
        out = {}
        for r in cur.fetchall():
            out[(str(r["store_id"]), str(r["item_id"]))] = {
                "spend": fnum(r.get("spend")), "ad_sales": fnum(r.get("ad_sales")),
            }
        return out


def fetch_inventory(db, snap_date):
    """窗口末库存：store_id+item_id 聚合"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id, SUM(COALESCE(wfs_available_stock,0)) AS wfs, "
            "SUM(COALESCE(available_stock,0)) AS avail, SUM(COALESCE(inbound_stock,0)) AS inbound "
            "FROM fact_inventory_daily WHERE platform='walmart' AND snapshot_date=%s "
            "GROUP BY store_id, item_id",
            (snap_date,),
        )
        out = {}
        for r in cur.fetchall():
            out[(str(r["store_id"]), str(r["item_id"]))] = {
                "wfs": fnum(r.get("wfs")), "avail": fnum(r.get("avail")), "inbound": fnum(r.get("inbound")),
            }
        return out


def fetch_inventory_active(db, start, end):
    """窗口内任一日库存(WFS+可用+在途)>0 的 (store_id,item_id) 集合。
    用途：v0.2 统计过滤——无销售记录且窗口内始终无库存的产品不进入报告。
    库存字段非负，SUM>0 等价于"窗口内任一日任一仓 >0"。"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT store_id, item_id FROM fact_inventory_daily "
            "WHERE platform='walmart' AND snapshot_date BETWEEN %s AND %s "
            "GROUP BY store_id, item_id "
            "HAVING SUM(COALESCE(wfs_available_stock,0)+COALESCE(available_stock,0)"
            "+COALESCE(inbound_stock,0)) > 0",
            (start, end),
        )
        return {(str(r["store_id"]), str(r["item_id"])) for r in cur.fetchall()}


def fetch_signals(db, start, end):
    """窗口内规则信号：store_id+item_id → [signal...]"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT signal_date, store_id, item_id, msku, rule_code, rule_name, "
            "rule_level, trigger_reason, suggested_action "
            "FROM biz_product_rule_signal_daily "
            "WHERE platform='walmart' AND should_notify=1 AND signal_date BETWEEN %s AND %s",
            (start, end),
        )
        m = defaultdict(list)
        for r in cur.fetchall():
            r["signal_date"] = str(r["signal_date"])[:10]
            m[(str(r["store_id"]), str(r["item_id"]))].append(r)
        return m


def fetch_ops_logs(db, start, end):
    """窗口内运营日志：item_id → [log...]（owner维度在渲染时对齐）"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT log_date, owner, item_id, msku, data_issue, solution, log_content, "
            "updated_by, source FROM biz_product_operation_log "
            "WHERE log_date BETWEEN %s AND %s",
            (start, end),
        )
        m = defaultdict(list)
        for r in cur.fetchall():
            r["log_date"] = str(r["log_date"])[:10]
            m[str(r["item_id"])].append(r)
        return m


def fetch_profit_levels(db, upto_date):
    """利润等级权威来源：dim_product_business_state.profit_level。
    取 <= upto_date 的最近 stat_date 快照；表唯一粒度含 msku，报告Item单元为
    (store_id,item_id)，多MSKU等级/类型以并集展示。直接读取，不重算等级。"""
    with db.cursor() as cur:
        cur.execute(
            "SELECT MAX(stat_date) AS d FROM dim_product_business_state "
            "WHERE platform='walmart' AND stat_date<=%s", (upto_date,))
        row = cur.fetchone()
        stat_date = str(row["d"])[:10] if row and row.get("d") else None
        if not stat_date:
            return {}, None
        cur.execute(
            "SELECT store_id, item_id, profit_level, product_type "
            "FROM dim_product_business_state WHERE platform='walmart' AND stat_date=%s",
            (stat_date,))
        m = defaultdict(lambda: {"levels": set(), "types": set()})
        for r in cur.fetchall():
            k = (str(r["store_id"]), str(r["item_id"]))
            if r.get("profit_level"):
                m[k]["levels"].add(str(r["profit_level"]))
            if r.get("product_type"):
                m[k]["types"].add(str(r["product_type"]))
        return dict(m), stat_date


def fetch_roster(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT name FROM dim_feishu_member WHERE employment_status='active' "
            "AND COALESCE(NULLIF(name,''),'') <> '' ORDER BY name",
        )
        return [r["name"] for r in cur.fetchall()]


# ── 聚合 ──────────────────────────────────────────────────────────────
def aggregate(rows):
    """
    快照行 → (owner → item_key → 指标) 与 owner级汇总。
    item_key = (store_id, item_id)；MSKU 多行合并（分摊后的毛利/广告直接求和）。
    """
    items = defaultdict(lambda: defaultdict(lambda: {
        "sales": 0.0, "qty": 0.0, "profit": 0.0, "ad": 0.0,
        "mskus": set(), "store_name": "", "product_name": "", "dates": set(),
    }))
    for j in rows:
        owner = str(j.get("负责人") or "").strip() or "(未分配)"
        store_id = str(j.get("店铺ID") or "").strip()
        item_id = str(j.get("商品ID") or "").strip()
        if not item_id:
            continue
        key = (store_id, item_id)
        it = items[owner][key]
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
        it["dates"].add(j["_date"])
    return items


def owner_summary(item_map):
    s = {"sales": 0.0, "qty": 0.0, "profit": 0.0, "ad": 0.0, "items": len(item_map)}
    for it in item_map.values():
        for k in ("sales", "qty", "profit", "ad"):
            s[k] += it[k]
    return s


def fnum(v):
    """任意数值类型（含 decimal.Decimal/None/str）安全转 float"""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def pct(a, b):
    a, b = fnum(a), fnum(b)
    return (a / b * 100.0) if b else 0.0


def wow(cur_v, prev_v):
    cur_v, prev_v = fnum(cur_v), fnum(prev_v)
    if prev_v == 0:
        return "新增" if cur_v > 0 else "—"
    d = (cur_v - prev_v) / abs(prev_v) * 100.0
    arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
    return "%s%.1f%%" % (arrow, abs(d))


# ── HTML 渲染 ─────────────────────────────────────────────────────────
CSS = """
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:0;background:#f5f6f8;color:#222}
.wrap{max-width:1280px;margin:0 auto;padding:24px}
h1{font-size:22px}h2{font-size:17px;margin:28px 0 10px;border-left:4px solid #4a6cf7;padding-left:8px}
.meta{background:#fff;border-radius:8px;padding:14px 18px;font-size:13px;line-height:1.9;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.card{background:#fff;border-radius:8px;padding:12px 18px;min-width:130px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card .v{font-size:20px;font-weight:600}.card .k{font-size:12px;color:#888}.card .w{font-size:12px;color:#555}
table{border-collapse:collapse;width:100%;background:#fff;font-size:12.5px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
th,td{border:1px solid #e8e8e8;padding:6px 8px;text-align:right;white-space:nowrap}
th{background:#f0f2f7;cursor:pointer;position:sticky;top:0}
td.l,th.l{text-align:left;white-space:normal}
tr.bad{background:#fff4f2}tr.warn{background:#fffbe8}
.tag{display:inline-block;border-radius:3px;padding:1px 6px;font-size:11px;margin:1px}
.tag.c{background:#ffe3e0;color:#b02a1f}.tag.w{background:#fff1c2;color:#8a6d00}
.tag.ok{background:#dff5e3;color:#1e7a36}.tag.info{background:#e8edff;color:#3450c0}
.note{font-size:12px;color:#777;margin:6px 0}
.log{font-size:12px;background:#fafafa;border-left:3px solid #cfd6e4;margin:4px 0;padding:4px 8px}
.icard{background:#fff;border-radius:8px;padding:12px 16px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.06);border-left:4px solid #d8dde8;max-width:980px}
.icard.bad{border-left-color:#d9463c}.icard.warn{border-left-color:#e0a800}
.ihead{font-size:13.5px;margin-bottom:8px;line-height:1.6}
.itab{width:auto;min-width:760px}
.itab th{position:static;cursor:default;background:#eef1f7}
.itab td{text-align:right;white-space:nowrap}
.itab td:first-child{text-align:left}
.itab tr.hb td{background:#f6f8ff;font-weight:600}
.iline{font-size:12.5px;color:#333;margin:5px 0;line-height:1.6;max-width:960px}
input.flt{padding:6px 10px;width:280px;margin:8px 0;border:1px solid #ccc;border-radius:5px}
a{color:#3450c0;text-decoration:none}
.complete{background:#eef7ef;border:1px solid #bfe3c5;border-radius:8px;padding:10px 16px;font-size:13px;margin:14px 0}
"""

SORT_JS = """
function sortT(tid,ci){var t=document.getElementById(tid),b=t.tBodies[0],
r=Array.from(b.rows),asc=t.getAttribute('data-s')!=(''+ci);
r.sort(function(x,y){var a=x.cells[ci].getAttribute('data-v')||x.cells[ci].innerText,
c=y.cells[ci].getAttribute('data-v')||y.cells[ci].innerText,
na=parseFloat(a),nc=parseFloat(c);
if(!isNaN(na)&&!isNaN(nc))return asc?nc-na:na-nc;
return asc?(''+c).localeCompare(a,'zh'):(''+a).localeCompare(c,'zh');});
r.forEach(function(x){b.appendChild(x)});t.setAttribute('data-s',asc?(''+ci):'');}
function fltT(tid,q){q=q.toLowerCase();Array.from(document.getElementById(tid).tBodies[0].rows)
.forEach(function(r){r.style.display=r.innerText.toLowerCase().indexOf(q)>=0?'':'none';});}
function fltC(q){q=q.toLowerCase();Array.from(document.querySelectorAll('.icard'))
.forEach(function(c){c.style.display=c.innerText.toLowerCase().indexOf(q)>=0?'':'none';});}
"""


def render_owner_page(owner, cur_items, prev_items, ad_map, ad_prev, inv_map, sig_map, log_map, level_map, level_date, mtd_sum, gen_time):
    cs = owner_summary(cur_items)
    ps = owner_summary(prev_items)
    ad_total = sum(fnum(ad_map.get(k, {}).get("ad_sales", 0)) for k in cur_items)
    ad_total_prev = sum(fnum(ad_prev.get(k, {}).get("ad_sales", 0)) for k in prev_items)
    cs_margin = pct(cs["profit"], cs["sales"])
    acos_sum_c = pct(cs["ad"], ad_total) if ad_total else None

    # 经营总结三行表（v0.5：与产品卡片同构，上周数值直观可见）
    wl0 = "%s-%s" % (WIN_START[5:].replace("-", "."), WIN_END[5:].replace("-", "."))
    pl0 = "%s-%s" % (PREV_START[5:].replace("-", "."), PREV_END[5:].replace("-", "."))
    sum_cur = ('<tr><td>本周 %s</td><td>%.2f</td><td>%d</td><td>%.2f</td><td>%.1f%%</td>'
               '<td>%.2f</td><td>%.2f</td><td>%s</td><td>%d</td></tr>') % (
        wl0, cs["sales"], int(cs["qty"]), cs["profit"], cs_margin,
        cs["ad"], ad_total, ("%.1f%%" % acos_sum_c) if acos_sum_c is not None else "-",
        cs["items"])
    if prev_items:
        ps_margin = pct(ps["profit"], ps["sales"])
        acos_sum_p = pct(ps["ad"], ad_total_prev) if ad_total_prev else None
        sum_prev = ('<tr><td>上周 %s</td><td>%.2f</td><td>%d</td><td>%.2f</td><td>%.1f%%</td>'
                    '<td>%.2f</td><td>%.2f</td><td>%s</td><td>%d</td></tr>') % (
            pl0, ps["sales"], int(ps["qty"]), ps["profit"], ps_margin,
            ps["ad"], ad_total_prev, ("%.1f%%" % acos_sum_p) if acos_sum_p is not None else "-",
            ps["items"])
        acos_sum_wow = ("%+.1fpp" % (acos_sum_c - acos_sum_p)) \
            if (acos_sum_c is not None and acos_sum_p is not None) else "—"
        sum_wow = ('<tr class="hb"><td>环比</td><td>%s</td><td>%s</td><td>%s</td><td>%+.1fpp</td>'
                   '<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (
            esc(wow(cs["sales"], ps["sales"])), esc(wow(cs["qty"], ps["qty"])),
            esc(wow(cs["profit"], ps["profit"])), cs_margin - ps_margin,
            esc(wow(cs["ad"], ps["ad"])), esc(wow(ad_total, ad_total_prev)), acos_sum_wow,
            esc(wow(cs["items"], ps["items"])))
    else:
        sum_prev = "<tr><td>上周 %s</td>%s</tr>" % (pl0, "<td>—</td>" * 8)
        sum_wow = '<tr class="hb"><td>环比</td><td>新增</td>%s</tr>' % ("<td>—</td>" * 7)
    sum_table = ('<table class="itab"><thead><tr><th>周期</th><th>销售额$</th><th>销量</th>'
                 '<th>毛利$</th><th>毛利率</th><th>广告费$</th><th>广告销售额$</th><th>ACOS</th>'
                 '<th>Item数</th></tr></thead><tbody>%s%s%s</tbody></table>'
                 % (sum_cur, sum_prev, sum_wow))

    # 本月累计卡（v0.4）：MTD 销售/毛利/毛利率 + 目标完成率占位
    ms = mtd_sum or {"sales": 0.0, "profit": 0.0}
    mtd_cards = [
        ("本月销售额($)", "%.2f" % ms["sales"], "%s~%s" % (MTD_START[5:], MTD_END[5:])),
        ("本月毛利润($)", "%.2f" % ms["profit"], ""),
        ("本月毛利率", "%.2f%%" % pct(ms["profit"], ms["sales"]), ""),
        ("月度目标完成率", "目标待录入", "销售额/毛利目标由林翔在Tab设定后自动计算"),
        ("季度目标完成率", "目标待录入", ""),
    ]
    mtd_html = "".join(
        '<div class="card"><div class="v">%s</div><div class="k">%s</div><div class="w">%s</div></div>'
        % (esc(v), esc(k), esc(w)) for k, v, w in mtd_cards
    )

    # 明细卡片（v0.3：每个ItemID一张独立卡片+自带表头，运营直接截图贴PPT）
    wl = "%s-%s" % (WIN_START[5:].replace("-", "."), WIN_END[5:].replace("-", "."))
    pl_lbl = "%s-%s" % (PREV_START[5:].replace("-", "."), PREV_END[5:].replace("-", "."))
    item_cards = []
    open_n = 0
    for key, it in sorted(cur_items.items(), key=lambda kv: -kv[1]["sales"]):
        store_id, item_id = key
        prev = prev_items.get(key)
        ad = ad_map.get(key, {})
        adp = ad_prev.get(key, {})
        inv = inv_map.get(key, {})
        sigs = sig_map.get(key, [])
        logs = log_map.get(item_id, [])
        lv = level_map.get(key, {})

        margin = pct(it["profit"], it["sales"])
        cur_adsales = fnum(ad.get("ad_sales"))
        acos_c = pct(it["ad"], cur_adsales) if cur_adsales else None

        # 利润等级（权威：dim_product_business_state.profit_level，直接读取不重算）
        levels = sorted(lv.get("levels", set()))
        types = lv.get("types", set())
        if levels:
            level_txt = "/".join(levels)
        elif any(("CS" in t or "测品" in t) for t in types):
            level_txt = "CS测品·无等级"
        else:
            level_txt = "—"

        # 问题信号行
        end_sigs = [s for s in sigs if s["signal_date"] == WIN_END]
        early_sigs = [s for s in sigs if s["signal_date"] != WIN_END]
        if end_sigs:
            open_n += 1
            crit = any(s["rule_level"] == "critical" for s in end_sigs)
            sig_line = "<b>未闭环</b> " + "；".join(
                "[%s] %s：%s" % (esc(s["rule_level"]), esc(s["rule_name"]),
                                 esc(s.get("trigger_reason") or "-"))
                for s in sorted(end_sigs,
                                key=lambda x: RULE_LEVEL_ORDER.get(str(x["rule_level"]), 9))[:4])
            card_cls = "bad" if crit else "warn"
        elif early_sigs:
            sig_line = "已恢复（曾触发：%s）" % esc(
                "、".join(sorted({str(s["rule_name"]) for s in early_sigs})))
            card_cls = ""
        else:
            sig_line = "—"
            card_cls = ""

        # 运营记录行（人工 updated_by=admin_ui）
        admin_logs = sorted([l for l in logs if l.get("updated_by") == "admin_ui"],
                            key=lambda l: l["log_date"])
        ops_line = "；".join(
            "%s 问题：%s ｜ 措施：%s%s" % (
                esc(l["log_date"][5:]), esc(l.get("data_issue") or "-"),
                esc(l.get("solution") or "-"),
                ("（" + esc((l.get("log_content") or "")[:80]) + "）") if l.get("log_content") else "")
            for l in admin_logs) or "—"

        # 本周行
        cur_tr = ('<tr><td>本周 %s</td><td>%.2f</td><td>%d</td><td>%.2f</td><td>%.1f%%</td>'
                  '<td>%.2f</td><td>%.2f</td><td>%s</td></tr>') % (
            wl, it["sales"], int(it["qty"]), it["profit"], margin,
            it["ad"], cur_adsales, ("%.1f%%" % acos_c) if acos_c is not None else "-")

        # 上周行 + 环比行（上周无数据："—"/新增）
        if prev:
            pmargin = pct(prev["profit"], prev["sales"])
            prev_adsales = fnum(adp.get("ad_sales"))
            acos_p = pct(prev["ad"], prev_adsales) if prev_adsales else None
            prev_tr = ('<tr><td>上周 %s</td><td>%.2f</td><td>%d</td><td>%.2f</td><td>%.1f%%</td>'
                       '<td>%.2f</td><td>%.2f</td><td>%s</td></tr>') % (
                pl_lbl, prev["sales"], int(prev["qty"]), prev["profit"], pmargin,
                prev["ad"], prev_adsales, ("%.1f%%" % acos_p) if acos_p is not None else "-")
            acos_wow = ("%+.1fpp" % (acos_c - acos_p)) \
                if (acos_c is not None and acos_p is not None) else "—"
            wow_tr = ('<tr class="hb"><td>环比</td><td>%s</td><td>%s</td><td>%s</td>'
                      '<td>%+.1fpp</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (
                esc(wow(it["sales"], prev["sales"])), esc(wow(it["qty"], prev["qty"])),
                esc(wow(it["profit"], prev["profit"])), margin - pmargin,
                esc(wow(it["ad"], prev["ad"])), esc(wow(cur_adsales, prev_adsales)), acos_wow)
        else:
            prev_tr = "<tr><td>上周 %s</td>%s</tr>" % (pl_lbl, "<td>—</td>" * 7)
            wow_tr = '<tr class="hb"><td>环比</td><td>新增</td>%s</tr>' % ("<td>—</td>" * 6)

        item_cards.append(
            '<div class="icard %s">'
            '<div class="ihead"><b>%s</b> ｜ MSKU: %s ｜ %s ｜ %s ｜ <b>利润等级：%s</b> ｜ 负责人：%s</div>'
            '<table class="itab"><thead><tr><th>周期</th><th>销售额$</th><th>销量</th><th>毛利$</th>'
            '<th>毛利率</th><th>广告费$</th><th>广告销售额$</th><th>ACOS</th></tr></thead>'
            "<tbody>%s%s%s</tbody></table>"
            '<div class="iline">库存（%s）：WFS %d ｜ 可用 %d ｜ 在途 %d</div>'
            '<div class="iline">问题信号：%s</div>'
            '<div class="iline">本周运营记录：%s</div>'
            "</div>"
            % (card_cls, esc(item_id), esc("/".join(sorted(it["mskus"])) or "-"),
               esc(it["store_name"]), esc(it["product_name"]), esc(level_txt), esc(owner),
               cur_tr, prev_tr, wow_tr,
               WIN_END[5:], int(num(inv.get("wfs"))), int(num(inv.get("avail"))),
               int(num(inv.get("inbound"))),
               sig_line, ops_line)
        )

    return """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>周报 %(period)s - %(owner)s</title><style>%(css)s</style><script>%(js)s</script></head>
<body><div class="wrap">
<h1>运营周报 ｜ %(owner)s</h1>
<div class="meta">报告类型：周报（手工版v0.3·数据卡片，运营截图贴PPT后自行补充广告分析/页面优化等） ｜ 周期：%(period)s（%(ws)s ~ %(we)s） ｜ 对比周期：%(ps)s ~ %(pe)s ｜ 生成时间：%(gen)s<br>
口径说明：毛利=order_profit_daily快照（成本配置计算）；利润等级=dim_product_business_state.profit_level（快照日%(lvd)s，直接读取不重算）；对比窗口早于回溯自愈范围（未自愈口径）；规则信号自%(sigmin)s起才有数据，本窗口仅覆盖07-06/07-07两日。<br>
统计范围：仅含窗口内有销售记录（销量>0或销售额≠0）或窗口内任一日库存>0的产品；运营记录"—"仅代表未录入系统，不代表运营未做事。</div>
<h2>一、经营总结</h2>
%(sumtab)s
<p class="note">本月累计（%(ms)s ~ %(me)s，数据到D-2）与目标完成</p><div class="cards">%(mtd)s</div>
<h2>二、产品明细卡片（共 %(n)d 个Item，其中未闭环 %(open_n)d 个；按本周销售额降序）</h2>
<input class="flt" placeholder="搜索 ItemID / MSKU / 店铺 / 品名 / 等级..." onkeyup="fltC(this.value)">
%(item_cards)s
<p class="note"><a href="index.html">← 返回负责人列表</a></p>
</div></body></html>""" % {
        "period": PERIOD_KEY, "owner": esc(owner), "css": CSS, "js": SORT_JS,
        "ws": WIN_START, "we": WIN_END, "ps": PREV_START, "pe": PREV_END,
        "gen": gen_time, "sigmin": SIGNAL_MIN_DATE,
        "lvd": esc(level_date or "无快照"),
        "ms": MTD_START, "me": MTD_END,
        "sumtab": sum_table, "mtd": mtd_html, "n": len(cur_items), "open_n": open_n,
        "item_cards": "\n".join(item_cards),
    }


def safe_name(owner):
    return re.sub(r"[^\w一-鿿-]", "_", owner)


def main():
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    try:
        cur_rows = fetch_profit_rows(db, WIN_START, WIN_END)
        prev_rows = fetch_profit_rows(db, PREV_START, PREV_END)
        mtd_rows = fetch_profit_rows(db, MTD_START, MTD_END)
        ad_map = fetch_ad_sales(db, WIN_START, WIN_END)
        ad_prev = fetch_ad_sales(db, PREV_START, PREV_END)
        inv_map = fetch_inventory(db, WIN_END)
        inv_active = fetch_inventory_active(db, WIN_START, WIN_END)
        inv_active_prev = fetch_inventory_active(db, PREV_START, PREV_END)
        sig_map = fetch_signals(db, max(WIN_START, SIGNAL_MIN_DATE), WIN_END)
        log_map = fetch_ops_logs(db, WIN_START, WIN_END)
        level_map, level_date = fetch_profit_levels(db, WIN_END)
        roster = fetch_roster(db)
    finally:
        db.close()

    cur_agg = aggregate(cur_rows)
    prev_agg = aggregate(prev_rows)
    mtd_agg = aggregate(mtd_rows)   # MTD 不做过滤：累计金额不受零销售行影响

    # v0.2 统计范围过滤：窗口内有销售记录 或 窗口内任一日库存>0 才统计
    excluded = 0
    filtered_agg = {}
    for owner, imap in cur_agg.items():
        keep = {}
        for key, it in imap.items():
            if it["qty"] > 0 or it["sales"] != 0 or key in inv_active:
                keep[key] = it
            else:
                excluded += 1
        if keep:
            filtered_agg[owner] = keep
    cur_agg = filtered_agg

    # v0.5 上周窗口同口径过滤（Item数环比口径一致；被剔除行金额本为0，汇总金额不受影响）
    prev_filtered = {}
    for owner, imap in prev_agg.items():
        keep = {k: it for k, it in imap.items()
                if it["qty"] > 0 or it["sales"] != 0 or k in inv_active_prev}
        if keep:
            prev_filtered[owner] = keep
    prev_agg = prev_filtered

    os.makedirs(OUT_DIR, exist_ok=True)

    # 完整性校验：过滤后的全部 (owner,item) 必须全部进入报告；剔除数单独回传
    expected_items = sum(len(v) for v in cur_agg.values())
    written_items = 0

    index_rows = []
    owners_sorted = sorted(cur_agg.keys(), key=lambda o: -owner_summary(cur_agg[o])["sales"])
    for owner in owners_sorted:
        cur_items = cur_agg[owner]
        prev_items = prev_agg.get(owner, {})
        page = render_owner_page(owner, cur_items, prev_items, ad_map, ad_prev,
                                 inv_map, sig_map, log_map, level_map, level_date,
                                 owner_summary(mtd_agg.get(owner, {})), gen_time)
        fname = "owner-%s.html" % safe_name(owner)
        with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(page)
        written_items += len(cur_items)
        s = owner_summary(cur_items)
        in_roster = "在册" if owner in roster else ("—" if owner == "(未分配)" else "不在册")
        index_rows.append(
            '<tr><td class="l"><a href="%s">%s</a></td><td class="l">%s</td>'
            '<td data-v="%d">%d</td><td data-v="%.2f">%.2f</td>'
            '<td data-v="%.2f">%.2f</td><td data-v="%.2f">%.2f%%</td>'
            '<td data-v="%.2f">%.2f</td></tr>'
            % (fname, esc(owner), in_roster, s["items"], s["items"], s["sales"], s["sales"],
               s["profit"], s["profit"], pct(s["profit"], s["sales"]), pct(s["profit"], s["sales"]),
               s["ad"], s["ad"])
        )

    completeness = {
        "expected_items": expected_items,
        "written_items": written_items,
        "missing": expected_items - written_items,
        "excluded_no_sales_no_stock": excluded,
        "owners": len(owners_sorted),
        "status": "已完成" if expected_items == written_items else "不完整",
    }

    mtd_total = {"sales": 0.0, "profit": 0.0}
    for imap in mtd_agg.values():
        for it in imap.values():
            mtd_total["sales"] += it["sales"]
            mtd_total["profit"] += it["profit"]

    index_html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>AI经营分析报告 %(period)s</title><style>%(css)s</style><script>%(js)s</script></head>
<body><div class="wrap">
<h1>AI经营分析报告（周报·手工版v0.5，数据卡片供运营截图贴PPT）</h1>
<div class="meta">周期：%(period)s（%(ws)s ~ %(we)s） ｜ 生成时间：%(gen)s ｜ 毛利口径：order_profit_daily快照<br>
公司本月累计（%(ms)s ~ %(me)s，数据到D-2）：销售额 $%(mtd_sales).2f ｜ 毛利 $%(mtd_profit).2f ｜ 毛利率 %(mtd_margin).2f%% ｜ 目标完成率：目标待录入<br>
统计范围：仅含窗口内有销售记录或有库存的产品（完全无销售且无库存的 %(excl)d 个已剔除）</div>
<div class="complete">完整性校验 ｜ 应覆盖Item：%(exp)d ｜ 已写入Item：%(wr)d ｜ 遗漏：%(miss)d ｜ 剔除（无销售无库存）：%(excl)d ｜ 负责人：%(own)d ｜ 状态：%(st)s</div>
<h2>负责人列表（按销售额排序，点击进入个人周报）</h2>
<table id="t0"><thead><tr>
<th class="l" onclick="sortT('t0',0)">负责人</th><th class="l">花名册</th>
<th onclick="sortT('t0',2)">Item数</th><th onclick="sortT('t0',3)">销售额$</th>
<th onclick="sortT('t0',4)">毛利$</th><th onclick="sortT('t0',5)">毛利率</th>
<th onclick="sortT('t0',6)">广告$</th>
</tr></thead><tbody>%(rows)s</tbody></table>
</div></body></html>""" % {
        "period": PERIOD_KEY, "css": CSS, "js": SORT_JS,
        "ws": WIN_START, "we": WIN_END, "gen": gen_time,
        "exp": completeness["expected_items"], "wr": completeness["written_items"],
        "miss": completeness["missing"], "excl": excluded, "own": completeness["owners"],
        "ms": MTD_START, "me": MTD_END,
        "mtd_sales": mtd_total["sales"], "mtd_profit": mtd_total["profit"],
        "mtd_margin": pct(mtd_total["profit"], mtd_total["sales"]),
        "st": completeness["status"], "rows": "\n".join(index_rows),
    }
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print("REPORT_DONE")
    print("OUT_DIR=%s" % OUT_DIR)
    print("LEVEL_SNAPSHOT_DATE=%s" % (level_date or "NONE"))
    print("MTD_TOTAL=%s" % json.dumps(
        {"window": "%s~%s" % (MTD_START, MTD_END),
         "sales": round(mtd_total["sales"], 2), "profit": round(mtd_total["profit"], 2)},
        ensure_ascii=False))
    print("COMPLETENESS=%s" % json.dumps(completeness, ensure_ascii=False))
    print("OWNERS=%s" % json.dumps(
        [{"owner": o, **{k: round(v, 2) for k, v in owner_summary(cur_agg[o]).items()}}
         for o in owners_sorted], ensure_ascii=False))


if __name__ == "__main__":
    main()
