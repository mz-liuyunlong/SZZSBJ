/**
 * MonthlyPlanPanel.tsx — 目标管理·月度规划 独立页（运营中心，key=monthly-plan）
 *   2026-07-15 初版挂运营日志Tab顶部 → 2026-07-31 抽出为独立页并 UI 重做（LxToolbar/KPI瓦片/本月目标列/右侧抽屉）
 *
 * 形态=需求方确认的 v2 设计稿：进度横幅 → 待填清单 → 结构化表单
 * 指标最多2个（清货/提高毛利率/提升销售额/新增变体/调整广告），或勾选"正常运营"表态。
 * 数据：GET /api/ai-business/monthly-plan/todo ｜ POST /api/ai-business/monthly-plan
 * 日常运营日志录入不受影响（本面板独立于下方日志表格）。
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { ItemIdLink } from "./ItemIdLink";
import { IconRefresh, IconHelp, IconDownload, IconColumns } from "./LxToolbar";

// ── 2026-07-24 月度规划批量导入（清货中心同款CSV模式；一次仅一个负责人）────────
const MP_IMPORT_MAX_ROWS = 1000;
const MP_IMPORT_HEADERS = [
  "店铺ID(勿改)", "店铺名称(参考)", "ItemID(勿改)", "MSKU(勿改)",
  "月报问题(参考)", "新品(参考)",
  "正常运营(是/空)", "指标1类型", "指标1目标(数字)",
  "指标2类型(选填)", "指标2目标(选填)",
  "月销售额目标$(非新品必填)", "月利润目标$(非新品必填)", "补充说明(选填)",
];

function mpParseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let cur = "", row: string[] = [], inQ = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQ) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cur += '"'; i++; }
        else inQ = false;
      } else cur += ch;
    } else if (ch === '"') inQ = true;
    else if (ch === ",") { row.push(cur); cur = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cur); cur = "";
      if (row.some((c) => c.trim() !== "")) rows.push(row);
      row = [];
    } else cur += ch;
  }
  row.push(cur);
  if (row.some((c) => c.trim() !== "")) rows.push(row);
  return rows;
}

function mpDownloadCsv(filename: string, lines: string[][]): void {
  const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const csv = "﻿" + lines.map((l) => l.map(esc).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// 国内 Excel 另存 CSV 常为 GBK：先按 UTF-8 解码，出现替换符则回退 GBK（清货中心同款）
async function mpReadCsvFile(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const utf8 = new TextDecoder("utf-8").decode(buf);
  if (!utf8.includes("�")) return utf8.replace(/^﻿/, "");
  try { return new TextDecoder("gbk").decode(buf); } catch { return utf8.replace(/^﻿/, ""); }
}


interface TodoRow {
  owner: string; store_id: string; store_name: string; item_id: string; msku: string;
  issue_reasons: unknown; suggested_action: string | null; metrics_json: unknown;
  is_exempt: number; wfs_stock: string | number | null; non_wfs_stock: string | number | null;
  profit_level: string | null; lifecycle: string | null; total_inventory: string | number | null;
  last_month_sales: number | null; last_month_qty: number | null;
  last_month_profit: number | null; last_month_ad: number | null;
  is_new_product: number; launch_date: string | null;
  target_sales_amount: string | number | null; target_gross_profit: string | number | null;
  plan_id: number | null; indicator1_type: string | null; indicator1_target: string | number | null;
  indicator2_type: string | null; indicator2_target: string | number | null;
  deadline: string | null; normal_operation: number | null; note: string | null;
  plan_updated_by: string | null; plan_updated_at: string | null;
}

const IND_TYPES = ["清货", "提高毛利率", "提升销售额", "新增变体", "调整广告"] as const;
const QLABEL: Record<string, string> = {
  "清货": "清货 ≥（件）", "提高毛利率": "月度综合毛利率 ≥（%）",
  "提升销售额": "月销售额 ≥（$）", "新增变体": "新增变体 ≥（个，人工汇报）",
  "调整广告": "月度广告占比 ≤（%）",
};

function reasonsText(v: unknown): string {
  try {
    const arr = typeof v === "string" ? JSON.parse(v) : v;
    return Array.isArray(arr) ? (arr as string[]).join("；") : String(v ?? "");
  } catch { return String(v ?? ""); }
}

/** plan_month 的上一个自然月（与后端 prevMonth 口径一致） */
function prevMonthLabel(planMonth: string): string {
  const [y, m] = planMonth.split("-").map(Number);
  if (!y || !m) return "-";
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
}

function monthEnd(planMonth: string): string {
  const [y, m] = planMonth.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return `${planMonth}-${String(last).padStart(2, "0")}`;
}

const pgBtn = (active: boolean, disabled: boolean) => ({ padding: "4px 11px", borderRadius: 5, border: "1px solid #e0e0e0", cursor: disabled ? "not-allowed" : "pointer", background: active ? "#1a73e8" : "#fff", color: active ? "#fff" : "#3c4043", fontWeight: active ? 700 : 400, fontSize: 12, opacity: disabled ? 0.5 : 1 } as React.CSSProperties);

export default function MonthlyPlanPanel({ onNavigate }: { onNavigate?: (p: string) => void } = {}) {
  const now = new Date();
  const defMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const [planMonth, setPlanMonth] = useState("");  // 空=等 /months 定妥再加载(默认最新有数据的月份,防当前空月竞态覆盖)
  const [owner, setOwner] = useState("");
  const [fillState, setFillState] = useState(""); // 填写情况：""全部 / "unfilled" / "filled" / "normal"
  const [rows, setRows] = useState<TodoRow[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TodoRow | null>(null);
  const [i1t, setI1t] = useState("调整广告");
  const [i1v, setI1v] = useState("");
  const [i2on, setI2on] = useState(false);
  const [i2t, setI2t] = useState("提高毛利率");
  const [i2v, setI2v] = useState("");
  const [deadline, setDeadline] = useState("");
  const [normalOp, setNormalOp] = useState(false);
  const [note, setNote] = useState("");
  const [tSales, setTSales] = useState(""); // 单品月销售额目标$（非新品必填）
  const [tProfit, setTProfit] = useState(""); // 单品月利润目标$（非新品必填，清货可为负）
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [colW, setColW] = useState<Record<string, number>>({});
  const [colHidden, setColHidden] = useState<Record<string, boolean>>({});
  const [colMenu, setColMenu] = useState(false);
  const [kw, setKw] = useState("");
  const [showKpi, setShowKpi] = useState(true);          // §6 KPI可隐藏
  const [pageSize, setPageSize] = useState(50);           // §8 每页
  const [page, setPage] = useState(1);                    // §8 翻页
  const loadSeq = useRef(0);                              // 竞态守卫

  // ── 2026-07-24 批量导入状态与逻辑（导入=逐行调用 POST /monthly-plan，与单条录入同规则同底座）──
  const [mpImpOpen, setMpImpOpen] = useState(false);
  const [mpImpOwner, setMpImpOwner] = useState("");
  const [mpImporting, setMpImporting] = useState(false);
  const [mpImpResult, setMpImpResult] = useState<string[]>([]);
  const [mpImpRejects, setMpImpRejects] = useState<string[][]>([]);
  const mpImpFileRef = useRef<HTMLInputElement | null>(null);

  // 2026-07-24 月份筛选改下拉：选项=已有数据的月份（后端 /monthly-plan/months）
  const [mpMonths, setMpMonths] = useState<string[]>([]);
  useEffect(() => {
    let alive = true;
    void fetch("/api/ai-business/monthly-plan/months")
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        const ms = Array.isArray(d.months) ? (d.months as string[]).filter((m) => /^\d{4}-\d{2}$/.test(m)) : [];
        setMpMonths(ms);
        // 默认选"最新有数据的月份"：当前月已有数据用当前月，否则回退最新有数据月(防当前空月)
        setPlanMonth(ms.includes(defMonth) ? defMonth : (ms[0] ?? defMonth));
      })
      .catch(() => { setPlanMonth(defMonth); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const mpRec = (r: unknown): Record<string, unknown> => r as unknown as Record<string, unknown>;
  const mpImpKey = (s: unknown, i: unknown, m: unknown): string => `${String(s ?? "")}|${String(i ?? "")}|${String(m ?? "")}`;
  const mpImpBase = rows.filter((r) => r.owner === mpImpOwner);
  const mpImpNeed = mpImpBase.filter((r) => Number(mpRec(r).is_exempt ?? 0) !== 1);

  function mpCell(v: unknown): string {
    if (v === null || v === undefined) return "";
    return String(v);
  }

  // v3：模板改 xlsx（含下拉数据验证），由后端渲染；清单行仍由前端 todo 单一来源生成
  async function mpDownloadOwnerTemplate(): Promise<void> {
    if (!mpImpOwner || mpImpNeed.length === 0 || mpImporting) return;
    try {
      const payload = {
        plan_month: planMonth,
        owner: mpImpOwner,
        rows: mpImpNeed.map((r0) => {
          const r = mpRec(r0);
          return [
            mpCell(r.store_id), mpCell(r.store_name), mpCell(r.item_id), mpCell(r.msku),
            mpCell(r.issue_text) || (reasonsText as (v: unknown) => string)(r.issue_reasons),
            Number(r.is_new_product ?? 0) === 1 ? "是" : "",
            Number(r.normal_operation ?? 0) === 1 ? "是" : "",
            mpCell(r.indicator1_type), mpCell(r.indicator1_target),
            mpCell(r.indicator2_type), mpCell(r.indicator2_target),
            mpCell(r.target_sales_amount), mpCell(r.target_gross_profit),
            mpCell(r.note),
          ];
        }),
      };
      const resp = await fetch("/api/ai-business/monthly-plan/template-xlsx", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        setMpImpResult([`❌ 模板生成失败：${String(d.error || `HTTP ${resp.status}`)}`]);
        return;
      }
      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `月度规划导入模板_${mpImpOwner}_${planMonth}.xlsx`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      setMpImpResult([`❌ 模板生成失败：${String(err)}`]);
    }
  }


  async function mpHandleImportFile(file: File): Promise<void> {
    if (!mpImpOwner || mpImporting) return;
    setMpImporting(true); setMpImpResult([]); setMpImpRejects([]);
    try {
      let grid: string[][];
      if (/\.xlsx$/i.test(file.name)) {
        const buf = await file.arrayBuffer();
        const resp0 = await fetch("/api/ai-business/monthly-plan/parse-xlsx", {
          method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: buf,
        });
        const d0 = await resp0.json().catch(() => ({}));
        if (!resp0.ok || d0.error || !Array.isArray(d0.grid)) {
          setMpImpResult([`❌ Excel 解析失败：${String(d0.error || `HTTP ${resp0.status}`)}`]); return;
        }
        grid = (d0.grid as unknown[][]).map((r) => r.map((c) => String(c ?? "")));
      } else {
        const text = await mpReadCsvFile(file);
        grid = mpParseCsv(text);
      }
      if (grid.length < 2) { setMpImpResult(["❌ 文件为空或只有表头"]); return; }
      // M7（2026-08）H⑤：按表头名匹配列（不再按固定列位，防增删/重排列错位）+ 校验必需表头
      const hdr = (grid[0] ?? []).map((h) => String(h ?? "").trim());
      const findCol = (...keys: string[]) => hdr.findIndex((h) => keys.some((k) => h.includes(k)));
      const ixStore = findCol("店铺ID"), ixItem = findCol("ItemID"), ixMsku = findCol("MSKU");
      const ixNormal = findCol("正常运营"), ixI1t = findCol("指标1类型"), ixI1v = findCol("指标1目标");
      const ixI2t = findCol("指标2类型"), ixI2v = findCol("指标2目标");
      const ixSales = findCol("月销售额目标", "销售额目标"), ixProfit = findCol("月利润目标", "利润目标"), ixNote = findCol("补充说明", "说明");
      const missingCols: string[] = [];
      if (ixStore < 0) missingCols.push("店铺ID"); if (ixItem < 0) missingCols.push("ItemID"); if (ixMsku < 0) missingCols.push("MSKU");
      if (ixNormal < 0) missingCols.push("正常运营"); if (ixI1t < 0) missingCols.push("指标1类型"); if (ixI1v < 0) missingCols.push("指标1目标");
      if (ixSales < 0) missingCols.push("月销售额目标"); if (ixProfit < 0) missingCols.push("月利润目标");
      if (missingCols.length) { setMpImpResult([`❌ 表头缺少必需列：${missingCols.join("、")}，请下载本面板最新模板填写`]); return; }
      const dataRows = grid.slice(1);
      if (dataRows.length > MP_IMPORT_MAX_ROWS) { setMpImpResult([`❌ 单次最多 ${MP_IMPORT_MAX_ROWS} 行`]); return; }
      const needMap = new Map(mpImpNeed.map((r) => [mpImpKey(mpRec(r).store_id, mpRec(r).item_id, mpRec(r).msku), r]));
      const allMap = new Map(rows.map((r) => [mpImpKey(mpRec(r).store_id, mpRec(r).item_id, mpRec(r).msku), r]));
      const [mpY, mpM] = planMonth.split("-").map(Number);
      const mpAutoDeadline = `${planMonth}-${String(new Date(mpY, mpM, 0).getDate()).padStart(2, "0")}`;
      let added = 0, updated = 0, skipped = 0;
      const rejects: string[][] = [];
      for (let i = 0; i < dataRows.length; i++) {
        const line = i + 2;
        const c = dataRows[i];
        const cAt = (ix: number) => ix >= 0 ? String(c[ix] ?? "").trim() : "";
        const sid = cAt(ixStore), iid = cAt(ixItem), mskuV = cAt(ixMsku);
        if (!sid && !iid) { skipped++; continue; }
        const key = mpImpKey(sid, iid, mskuV);
        const target = needMap.get(key);
        if (!target) {
          const other = allMap.get(key);
          if (other && String(other.owner) !== mpImpOwner) {
            rejects.push([String(line), iid, mskuV, `该产品负责人为 ${String(other.owner)}，与导入负责人不符`]);
          } else if (other && Number(mpRec(other).is_exempt ?? 0) === 1) {
            rejects.push([String(line), iid, mskuV, "不在本期需填清单（已豁免）"]);
          } else {
            rejects.push([String(line), iid, mskuV, "产品标识与清单不匹配（标识列被修改或不在本期清单）"]);
          }
          continue;
        }
        const normalOp = cAt(ixNormal) === "是";
        const i1tV = cAt(ixI1t), i1vV = cAt(ixI1v);
        const i2tV = cAt(ixI2t), i2vV = cAt(ixI2v);
        const tsV = cAt(ixSales), tpV = cAt(ixProfit);
        const noteV = cAt(ixNote);
        if (!normalOp && !i1tV && !i1vV && !i2tV && !i2vV && !tsV && !tpV && !noteV) { skipped++; continue; }
        const tr = mpRec(target);
        const body: Record<string, unknown> = {
          plan_month: planMonth, store_id: sid, item_id: iid, msku: mskuV,
          owner: mpImpOwner, filled_by: `bulk:${mpImpOwner}`.slice(0, 64),
          normal_operation: normalOp,
          issue_text: mpCell(tr.issue_text) || (reasonsText as (v: unknown) => string)(tr.issue_reasons) || undefined,
          note: noteV || undefined,
        };
        // 指标1 总是提交（后端：非清货+正常运营会自动丢弃、清货会强制采用『清货』），修清货+正常运营导入不送指标的边界
        if (i1tV) { body.indicator1_type = i1tV; body.indicator1_target = Number(i1vV); }
        if (!normalOp) {
          if (i2tV) { body.indicator2_type = i2tV; body.indicator2_target = Number(i2vV); }
          body.deadline = mpAutoDeadline; // v3：完成期限列取消，自动=当月最后一天
        }
        if (tsV !== "") body.target_sales_amount = Number(tsV);
        if (tpV !== "") body.target_gross_profit = Number(tpV);
        try {
          const resp = await fetch("/api/ai-business/monthly-plan", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
          });
          const data = await resp.json().catch(() => ({}));
          if (!resp.ok || data.error) {
            rejects.push([String(line), iid, mskuV, String(data.error || `HTTP ${resp.status}`)]);
            continue;
          }
          if (tr.plan_id === null || tr.plan_id === undefined) added++; else updated++;
        } catch (err) {
          rejects.push([String(line), iid, mskuV, String(err)]);
        }
      }
      setMpImpRejects(rejects);
      const out = [`✅ 成功 ${added + updated} 行（新增 ${added} / 覆盖 ${updated}）｜ 跳过空行 ${skipped} ｜ 拒绝 ${rejects.length} 行`];
      for (const rj of rejects.slice(0, 50)) out.push(`· 第${rj[0]}行(${rj[1]}): ${rj[3]}`);
      if (rejects.length > 50) out.push(`· …其余 ${rejects.length - 50} 条请点「下载拒绝行明细」查看`);
      setMpImpResult(out);
      await load();
    } catch (err) {
      setMpImpResult([`❌ 导入失败：${String(err)}`]);
    } finally {
      setMpImporting(false);
      if (mpImpFileRef.current) mpImpFileRef.current.value = "";
    }
  }

  function mpDownloadRejects(): void {
    if (!mpImpRejects.length) return;
    mpDownloadCsv(`月度规划导入拒绝行_${mpImpOwner}_${planMonth}.csv`,
      [["行号", "ItemID", "MSKU", "拒绝原因"], ...mpImpRejects]);
  }


  // 一次拉全量、前端本地按负责人过滤——下拉选项始终齐全（修复：选人后无法换人的bug）
  const load = useCallback(async () => {
    if (!planMonth) return;                          // 月份未定前不加载(等 /months)，防空月竞态
    const seq = ++loadSeq.current;
    try {
      const r = await fetch(`/api/ai-business/monthly-plan/todo?plan_month=${encodeURIComponent(planMonth)}`);
      const d = (await r.json()) as { rows?: TodoRow[] };
      if (seq !== loadSeq.current) return;           // 竞态守卫：只认最新一次请求，晚到的旧月响应丢弃
      setRows(d.rows ?? []);
    } catch { if (seq === loadSeq.current) setRows([]); }
  }, [planMonth]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [owner, fillState, kw, planMonth, pageSize]);

  // 2026-07-21 下载导出（密码授权+审计，导出当前筛选后的清单）
  const handleDownload = useCallback(async (list: TodoRow[]) => {
    // M7（2026-08）：导出去密码——SSO 登录即身份，去掉 export-verify 密码门禁
    try {
      if (list.length === 0) { alert("当前筛选无数据可导出"); return; }
      const stateOf = (r: TodoRow) => r.plan_id === null ? "未填" : (r.normal_operation ? "正常运营" : "已填");
      const cols = ["负责人","ItemID","MSKU","店铺","月报问题","建议方向","状态","指标1","指标1目标",
        "指标2","指标2目标","截止日期","备注","单品月销售额目标$","单品月利润目标$",
        "上月销售额","上月销量","上月毛利","上月广告费","是否新品","上架时间","更新人","更新时间"];
      const esc = (v: unknown) => {
        const sv = v === null || v === undefined ? "" : String(v);
        return /[",\n]/.test(sv) ? `"${sv.replace(/"/g, '""')}"` : sv;
      };
      const lines = list.map((r) => [
        r.owner, r.item_id, r.msku, r.store_name, reasonsText(r.issue_reasons), r.suggested_action ?? "",
        stateOf(r), r.indicator1_type ?? "", r.indicator1_target ?? "", r.indicator2_type ?? "",
        r.indicator2_target ?? "", r.deadline ? String(r.deadline).slice(0, 10) : "", r.note ?? "",
        r.target_sales_amount ?? "", r.target_gross_profit ?? "",
        r.last_month_sales ?? "", r.last_month_qty ?? "", r.last_month_profit ?? "", r.last_month_ad ?? "",
        r.is_new_product ? "是" : "否", r.launch_date ? String(r.launch_date).slice(0, 10) : "",
        r.plan_updated_by ?? "", r.plan_updated_at ? String(r.plan_updated_at) : "",
      ].map(esc).join(","));
      const csv = "\uFEFF" + [cols.join(","), ...lines].join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `月度规划_${planMonth}_${list.length}行.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("导出失败: " + String(e));
    }
  }, [planMonth, owner, fillState]);

  const owners = [...new Set(rows.map((r) => r.owner))].sort((a, b) => a.localeCompare(b, "zh"));
  const ownerAll = owner ? rows.filter((r) => r.owner === owner) : rows;
  // 2026-07-21 读法B：豁免=WFS库存=0 且 上月销量=0（未填才豁免、已填保留、新品除外；后端判定）
  const exemptRows = ownerAll.filter((r) => r.is_exempt === 1);
  const ownerView = ownerAll.filter((r) => r.is_exempt !== 1);
  // 问题产品=非新品且issue_reasons非空（2026-08-04 拍板剔除新品：月报给待到货/本月上架品打的"月销0单"等标签不计入，
  // 新品行内仍展示问题标签不丢信息）；考核口径=全量在营·非新品·非豁免未填（与每日扣分cron一致）
  const issueRows = ownerView.filter((r) => !r.is_new_product && r.issue_reasons !== null && r.issue_reasons !== undefined);
  // 会被扣分的未填=非新品 且 (无计划行 或 未定销售额目标)；豁免/CS 已在 ownerView/后端剔除
  const dueUnfilled = ownerView.filter((r) => !r.is_new_product && (r.plan_id === null || r.target_sales_amount === null || r.target_sales_amount === undefined));
  const clearanceRows = ownerView.filter((r) => r.lifecycle === "清货期");   // 2026-08-01 清货期不豁免,单列展示
  const newRows = ownerView.filter((r) => !!r.is_new_product);          // 新品=上架月==规划月:公司公式定目标,运营不填不扣
  const needFillRows = ownerView.filter((r) => !r.is_new_product);      // 在营需填报=非豁免且剔除新品(运营实际要填)
  const view = fillState === "exempt" ? exemptRows : ownerView.filter((r) => {
    if (fillState === "unfilled") return !r.is_new_product && (r.plan_id === null || r.target_sales_amount === null || r.target_sales_amount === undefined);
    if (fillState === "filled") return r.plan_id !== null && !r.normal_operation;
    if (fillState === "normal") return r.plan_id !== null && !!r.normal_operation;
    if (fillState === "new") return !!r.is_new_product;
    return true;
  });
  const unfilled = view.filter((r) => r.plan_id === null);
  void unfilled;
  const kwl = kw.trim().toLowerCase();
  const viewRows = kwl ? view.filter((r) => (String(r.item_id) + " " + String(r.msku) + " " + String(r.store_name || "") + " " + String(r.store_id || "")).toLowerCase().includes(kwl)) : view;
  const totalPages = Math.max(1, Math.ceil(viewRows.length / pageSize));
  const pagedRows = viewRows.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [totalPages, page]);

  function startEdit(r: TodoRow) {
    setEditing(r);
    setI1t(r.lifecycle === "清货期" ? "清货" : (r.indicator1_type ?? "调整广告"));
    setI1v(r.indicator1_target !== null && r.indicator1_target !== undefined ? String(Number(r.indicator1_target)) : "");
    setI2on(!!r.indicator2_type);
    setI2t(r.indicator2_type ?? "提高毛利率");
    setI2v(r.indicator2_target !== null && r.indicator2_target !== undefined ? String(Number(r.indicator2_target)) : "");
    setDeadline(r.deadline ? String(r.deadline).slice(0, 10) : monthEnd(planMonth));
    setNormalOp(!!r.normal_operation);
    setNote(r.note ?? "");
    setTSales(r.target_sales_amount !== null && r.target_sales_amount !== undefined ? String(Number(r.target_sales_amount)) : "");
    setTProfit(r.target_gross_profit !== null && r.target_gross_profit !== undefined ? String(Number(r.target_gross_profit)) : "");
    setMsg("");
  }

  async function submit() {
    if (!editing) return;
    setMsg("");
    const isClr = editing.lifecycle === "清货期";
    if (!editing.is_new_product) {
      if (tSales.trim() === "" || !Number.isFinite(Number(tSales)) || Number(tSales) < 0) {
        setMsg("请填写单品月销售额目标（$，非负数字，正常运营也必填）"); return;
      }
      if (!isClr && (tProfit.trim() === "" || !Number.isFinite(Number(tProfit)))) {
        setMsg("请填写单品月利润目标（$，数字，清货可为负）"); return;
      }
    }
    if (isClr) {
      if (i1v.trim() === "" || !Number.isFinite(Number(i1v)) || Number(i1v) <= 0) { setMsg("清货产品必须填清货数量（件，>0）"); return; }
    } else {
      if (!normalOp && (!i1t || i1v.trim() === "")) { setMsg("请填写指标1及量化目标，或勾选正常运营"); return; }
      if (!normalOp && i2on && (i1t === i2t)) { setMsg("两个指标类型不能相同"); return; }
      if (!normalOp && i2on && i2v.trim() === "") { setMsg("指标2需填量化目标（或移除指标2）"); return; }
    }
    setBusy(true);
    try {
      const body = {
        plan_month: planMonth, store_id: editing.store_id, item_id: editing.item_id,
        msku: editing.msku, owner: editing.owner,
        issue_text: reasonsText(editing.issue_reasons),
        indicator1_type: isClr ? "清货" : (normalOp ? "" : i1t),
        indicator1_target: isClr ? Number(i1v) : (normalOp ? undefined : Number(i1v)),
        indicator2_type: isClr ? "" : (normalOp || !i2on ? "" : i2t),
        indicator2_target: isClr ? undefined : (normalOp || !i2on ? undefined : Number(i2v)),
        deadline: isClr ? deadline : (normalOp ? "" : deadline),
        normal_operation: normalOp, note,
        target_sales_amount: editing.is_new_product ? undefined : Number(tSales),
        target_gross_profit: editing.is_new_product ? undefined : (isClr ? Math.round(Number(tSales) * -0.10 * 100) / 100 : Number(tProfit)),
      };
      const r = await fetch("/api/ai-business/monthly-plan", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const d = (await r.json()) as { ok?: boolean; error?: string };
      if (!r.ok || !d.ok) { setMsg(`保存失败：${d.error ?? r.statusText}`); return; }
      setMsg("✅ 已保存");
      setEditing(null);
      await load();
    } catch (e) {
      setMsg(`网络错误：${e instanceof Error ? e.message : String(e)}`);
    } finally { setBusy(false); }
  }

  // 最近更新时间（人工录入数据，取 max(plan_updated_at) 作"同步"口径，避免 §1 禁止的"同步 -"）
  const latestSync = rows.reduce((mx, r) => { const t = r.plan_updated_at ? String(r.plan_updated_at) : ""; return t > mx ? t : mx; }, "");
  const syncLabel = latestSync ? latestSync.replace("T", " ").slice(0, 16) : "—";

  // 列（驱动列宽拖拽 §5 + 列配置）
  const COLS: { key: string; label: string; w: number; lock?: boolean }[] = [
    { key: "owner", label: "负责人", w: 88 },
    { key: "idmsku", label: "ItemID / MSKU", w: 168, lock: true },
    { key: "store", label: "店铺", w: 150 },
    { key: "issue", label: "月报问题", w: 288 },
    { key: "goal", label: "本月目标", w: 252 },
    { key: "status", label: "状态", w: 108 },
    { key: "op", label: "操作", w: 92, lock: true },
  ];
  const visCols = COLS.filter((c) => !colHidden[c.key]);
  const cw = (k: string, def: number) => colW[k] ?? def;
  function startResize(k: string, def: number, e: React.MouseEvent) {
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX; const startW = colW[k] ?? def;
    const move = (ev: MouseEvent) => setColW((pv) => ({ ...pv, [k]: Math.max(60, startW + (ev.clientX - startX)) }));
    const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  }
  function openHelp() { if (onNavigate) onNavigate("help"); window.location.hash = "#/help?page=monthly_plan"; }

  const UNIT: Record<string, (t: string) => string> = {
    "清货": (t) => "清货 ≥" + t + "件",
    "提高毛利率": (t) => "毛利率 ≥" + t + "%",
    "提升销售额": (t) => "销售额 ≥$" + t,
    "新增变体": (t) => "新增变体 ≥" + t + "个",
    "调整广告": (t) => "广告占比 ≤" + t + "%",
  };
  const indText = (type: string | null, target: unknown): string => {
    if (!type) return "";
    const t = target === null || target === undefined ? "" : String(Number(target));
    return UNIT[type] ? UNIT[type](t) : type + " " + t;
  };
  const money = (v: unknown) => v === null || v === undefined || v === "" ? "-" : "$" + Number(v).toLocaleString();

  const G = {
    blue: "#1a73e8", blueDk: "#174ea6", blueBg: "#e8f0fe", green: "#1e8e3e", greenBg: "#e6f4ea",
    red: "#d93025", redDk: "#c5221f", redBg: "#fce8e6", amber: "#b06000", amberBg: "#fef7e0",
    ink: "#202124", sub: "#5f6368", mut: "#80868b", line: "#dadce0", line2: "#e8eaed",
  };
  const T = {
    page: { padding: 4 } as React.CSSProperties,
    card: { background: "#fff", border: "1px solid " + G.line2, borderRadius: 12, boxShadow: "0 1px 2px rgba(60,64,67,.08)", overflow: "hidden" } as React.CSSProperties,
    hd: { display: "flex", alignItems: "flex-start", justifyContent: "space-between", padding: "16px 20px 14px", borderBottom: "1px solid " + G.line2, gap: 12, flexWrap: "wrap" } as React.CSSProperties,
    title: { fontSize: 18, fontWeight: 600, color: G.ink, display: "flex", alignItems: "center", gap: 9 } as React.CSSProperties,
    titleIco: { width: 26, height: 26, borderRadius: 7, background: G.blueBg, color: G.blue, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 15 } as React.CSSProperties,
    sub: { fontSize: 12, color: G.mut, marginTop: 4 } as React.CSSProperties,
    hdR: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" } as React.CSSProperties,
    sel: { height: 34, border: "1px solid " + G.line, borderRadius: 8, background: "#fff", color: G.ink, fontSize: 13, padding: "0 12px", cursor: "pointer", outline: "none" } as React.CSSProperties,
    btnPri: { height: 34, padding: "0 14px", borderRadius: 8, background: G.blue, color: "#fff", border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer" } as React.CSSProperties,
    btnGho: { height: 34, padding: "0 14px", borderRadius: 8, background: "#fff", color: G.blue, border: "1px solid " + G.line, fontSize: 13, fontWeight: 600, cursor: "pointer" } as React.CSSProperties,
    kpis: { display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, padding: "16px 20px" } as React.CSSProperties,
    tile: { border: "1px solid " + G.line2, borderRadius: 10, padding: "12px 14px", background: "#fff" } as React.CSSProperties,
    tileLab: { fontSize: 12, color: G.sub, display: "flex", alignItems: "center", gap: 6 } as React.CSSProperties,
    tileNum: { fontSize: 26, fontWeight: 600, marginTop: 4, letterSpacing: "-.5px", fontVariantNumeric: "tabular-nums" } as React.CSSProperties,
    tileHint: { fontSize: 11, color: G.mut, marginTop: 3, lineHeight: 1.4 } as React.CSSProperties,
    tbar: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 12px", position: "relative" } as React.CSSProperties,
    meta: { fontSize: 12, color: G.mut } as React.CSSProperties,
    icons: { display: "flex", gap: 2 } as React.CSSProperties,
    ib: { background: "none", border: "none", cursor: "pointer", padding: 6, borderRadius: 6, color: G.sub, display: "inline-flex", alignItems: "center" } as React.CSSProperties,
    filters: { display: "flex", alignItems: "center", gap: 10, padding: "0 20px 14px", flexWrap: "wrap" } as React.CSSProperties,
    search: { height: 34, border: "1px solid " + G.line, borderRadius: 8, padding: "0 12px", fontSize: 13, width: 220, outline: "none" } as React.CSSProperties,
    reset: { height: 34, padding: "0 12px", border: "1px solid " + G.line, borderRadius: 8, background: "#fff", color: G.sub, fontSize: 13, cursor: "pointer" } as React.CSSProperties,
    idlink: { color: G.blue, fontWeight: 600, fontVariantNumeric: "tabular-nums" } as React.CSSProperties,
    msku: { color: G.mut, fontSize: 12 } as React.CSSProperties,
    edit: { color: G.blue, fontWeight: 600, cursor: "pointer", background: "none", border: "none", fontSize: 13, padding: "4px 8px", borderRadius: 6 } as React.CSSProperties,
    pager: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 20px", color: G.mut, fontSize: 12 } as React.CSSProperties,
    // 抽屉
    backdrop: { position: "fixed", inset: 0, background: "rgba(32,33,36,.32)", zIndex: 900 } as React.CSSProperties,
    drawer: { position: "fixed", top: 0, right: 0, height: "100%", width: 420, maxWidth: "94vw", background: "#fff", zIndex: 901, boxShadow: "-8px 0 30px rgba(0,0,0,.16)", display: "flex", flexDirection: "column" } as React.CSSProperties,
    dwHd: { padding: "14px 18px", borderBottom: "1px solid " + G.line2, display: "flex", alignItems: "center", justifyContent: "space-between" } as React.CSSProperties,
    dwBd: { padding: "16px 18px", overflowY: "auto", flex: 1 } as React.CSSProperties,
    dwFt: { padding: "12px 18px", borderTop: "1px solid " + G.line2, display: "flex", justifyContent: "flex-end", gap: 8 } as React.CSSProperties,
    dwInp: { width: "100%", height: 34, border: "1px solid " + G.line, borderRadius: 8, padding: "0 10px", fontSize: 13, outline: "none", background: "#fff", boxSizing: "border-box" } as React.CSSProperties,
    lab: { fontSize: 12, color: G.sub, marginBottom: 5, fontWeight: 600 } as React.CSSProperties,
  };

  function pill(r: TodoRow) {
    if (r.is_exempt === 1) return <span style={{ fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 999, color: G.sub, background: "#f1f3f4" }}>豁免</span>;
    if (r.plan_id === null) return <span style={{ fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 999, color: G.redDk, background: G.redBg }}>! 未填</span>;
    if (r.normal_operation) return <span style={{ fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 999, color: G.blueDk, background: G.blueBg }}>● 正常运营</span>;
    return <span style={{ fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 999, color: G.green, background: G.greenBg }}>✓ 已填</span>;
  }
  function goalCell(r: TodoRow) {
    const biz = !r.is_new_product && (r.target_sales_amount != null || r.target_gross_profit != null)
      ? <div style={{ color: G.sub, fontSize: 12, marginTop: 3, fontVariantNumeric: "tabular-nums" }}>月销 {money(r.target_sales_amount)} · 利润 {money(r.target_gross_profit)}</div> : null;
    if (r.plan_id === null) return <span style={{ color: G.mut, fontSize: 12.5 }}>— 待填 —</span>;
    if (r.normal_operation) return <div><span style={{ color: G.sub, fontSize: 12.5 }}>正常运营（维持）</span>{biz}</div>;
    const chip = (txt: string) => <span key={txt} style={{ display: "inline-flex", alignItems: "center", background: G.blueBg, color: G.blueDk, borderRadius: 6, padding: "2px 8px", fontSize: 12, fontWeight: 600, margin: "1px 4px 1px 0" }}>{txt}</span>;
    const chips: React.ReactNode[] = [];
    if (r.indicator1_type) chips.push(chip(indText(r.indicator1_type, r.indicator1_target)));
    if (r.indicator2_type) chips.push(chip(indText(r.indicator2_type, r.indicator2_target)));
    return <div><div>{chips.length ? chips : <span style={{ color: G.mut, fontSize: 12.5 }}>—</span>}</div>{biz}</div>;
  }
  function cellContent(r: TodoRow, key: string) {
    if (key === "owner") return <span style={{ fontWeight: 600 }}>{r.owner}</span>;
    if (key === "idmsku") return <div><ItemIdLink itemId={r.item_id} /><div style={T.msku}>{r.msku || "-"}</div></div>;
    if (key === "store") return <span style={{ color: G.sub }}>{r.store_name || r.store_id || "-"}</span>;
    if (key === "issue") return <span style={{ color: G.redDk, fontWeight: 500, fontSize: 12.5 }}>{reasonsText(r.issue_reasons) || <span style={{ color: G.mut, fontWeight: 400 }}>无</span>}</span>;
    if (key === "goal") return goalCell(r);
    if (key === "status") return pill(r);
    if (key === "op") return r.is_exempt === 1
      ? <span style={{ color: G.mut, fontSize: 12 }}>无需填报</span>
      : <button type="button" onClick={() => startEdit(r)} style={T.edit}>{r.plan_id === null ? "去填写" : "修改"}</button>;
    return null;
  }

  return (
    <div style={T.page}>
      <style>{`
        .mp-th{position:sticky;top:0;z-index:3;text-align:left;font-size:12px;font-weight:600;color:${G.sub};background:#f8f9fa;padding:11px 14px;border-top:1px solid ${G.line2};border-bottom:1px solid ${G.line};white-space:nowrap;box-shadow:inset 0 -1px 0 ${G.line};}
        .mp-grip{position:absolute;right:0;top:22%;height:56%;width:2px;background:${G.line};border-radius:2px;cursor:col-resize;}
        .mp-th:hover .mp-grip{background:${G.blue};width:3px;top:0;height:100%;}
        .mp-td{padding:12px 14px;border-bottom:1px solid ${G.line2};vertical-align:middle;font-size:13px;color:${G.ink};}
        .mp-row:hover{background:#fafbfc;}
        .mp-ib:hover{background:#f1f3f4;color:${G.blue};}
        .mp-idlink,.mp-idlink *{color:${G.blue}!important;}
      `}</style>

      <div style={T.card}>
        {/* 页头 */}
        <div style={T.hd}>
          <div>
            <div style={T.title}><span style={T.titleIco}>◎</span>目标管理</div>
            <div style={T.sub}>月度规划 · 运营中心 ｜ 每月 7 号前填报并定目标（全量在营产品均需填），8 号起未填按天计绩效</div>
          </div>
          <div style={T.hdR}>
            <select value={planMonth} onChange={(e) => setPlanMonth(e.target.value)} style={T.sel}>
              {[...new Set([...mpMonths, planMonth])].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <button type="button" onClick={() => { setMpImpOpen(true); setMpImpOwner(owner && owner !== "(未分配)" ? owner : ""); setMpImpResult([]); setMpImpRejects([]); }} style={T.btnPri}>⇪ 批量导入</button>
          </div>
        </div>

        {/* KPI 瓦片 §6可隐藏 */}
        {showKpi && (
        <div style={T.kpis}>
          <div style={{ ...T.tile, cursor: "pointer" }} onClick={() => setFillState("")}>
            <div style={T.tileLab}><span style={{ width: 8, height: 8, borderRadius: 4, background: G.mut }} />在营需填报</div>
            <div style={{ ...T.tileNum, color: G.ink }}>{needFillRows.length}</div><div style={T.tileHint}>在营·剔除新品·运营需填</div>
          </div>
          <div style={T.tile}>
            <div style={T.tileLab}><span style={{ width: 8, height: 8, borderRadius: 4, background: G.blue }} />问题产品</div>
            <div style={{ ...T.tileNum, color: G.blue }}>{issueRows.length}</div><div style={T.tileHint}>月报有问题·需重点关注</div>
          </div>
          <div style={T.tile}>
            <div style={T.tileLab}><span style={{ width: 8, height: 8, borderRadius: 4, background: G.green }} />清货产品</div>
            <div style={{ ...T.tileNum, color: G.green }}>{clearanceRows.length}</div><div style={T.tileHint}>清货期·需填清货目标</div>
          </div>
          <div style={{ ...T.tile, cursor: "pointer" }} onClick={() => setFillState("unfilled")}>
            <div style={T.tileLab}><span style={{ width: 8, height: 8, borderRadius: 4, background: dueUnfilled.length ? G.red : G.mut }} />未填</div>
            <div style={{ ...T.tileNum, color: dueUnfilled.length ? G.red : G.ink }}>{dueUnfilled.length}</div><div style={T.tileHint}>8 号起未填按天计绩效</div>
          </div>
          <div style={{ ...T.tile, cursor: "pointer" }} onClick={() => setFillState("new")}>
            <div style={T.tileLab}><span style={{ width: 8, height: 8, borderRadius: 4, background: G.amber }} />新品</div>
            <div style={{ ...T.tileNum, color: G.amber }}>{newRows.length}</div><div style={T.tileHint}>上架本月/待到货·公司公式定</div>
          </div>
          <div style={{ ...T.tile, cursor: "pointer" }} onClick={() => setFillState("exempt")}>
            <div style={T.tileLab}><span style={{ width: 8, height: 8, borderRadius: 4, background: G.mut }} />豁免</div>
            <div style={{ ...T.tileNum, color: G.ink }}>{exemptRows.length}</div><div style={T.tileHint}>WFS=0 且上月0销量</div>
          </div>
        </div>
        )}

        {/* 工具条元信息 §1 */}
        <div style={T.tbar}>
          <div style={T.meta}>共 <b style={{ color: G.sub }}>{viewRows.length}</b> 行 · 同步 <b style={{ color: G.sub }}>{syncLabel}</b> · 第 <b style={{ color: G.sub }}>{page}/{totalPages}</b> 页</div>
          <div style={T.icons}>
            <button className="mp-ib" style={T.ib} title="隐藏 / 显示 顶部KPI" onClick={() => setShowKpi((v) => !v)}><span style={{ fontSize: 15, lineHeight: 1 }}>▤</span></button>
            <button className="mp-ib" style={T.ib} title="刷新" onClick={load}><IconRefresh /></button>
            <button className="mp-ib" style={T.ib} title="帮助（壳内直达本页帮助）" onClick={openHelp}><IconHelp /></button>
            <button className="mp-ib" style={T.ib} title="下载当前筛选（需密码）" onClick={() => handleDownload(view)}><IconDownload /></button>
            <button className="mp-ib" style={T.ib} title="列配置" onClick={() => setColMenu(!colMenu)}><IconColumns /></button>
          </div>
          {colMenu && (
            <div style={{ position: "absolute", right: 20, top: 34, background: "#fff", border: "1px solid " + G.line, borderRadius: 10, boxShadow: "0 6px 24px rgba(0,0,0,.14)", padding: "8px 6px", zIndex: 20, minWidth: 150 }}>
              <div style={{ fontSize: 11, color: G.mut, padding: "2px 10px 6px", fontWeight: 600 }}>显示列</div>
              {COLS.map((c) => (
                <label key={c.key} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 10px", fontSize: 13, color: c.lock ? G.mut : G.ink, cursor: c.lock ? "not-allowed" : "pointer" }}>
                  <input type="checkbox" checked={!colHidden[c.key]} disabled={c.lock} onChange={(e) => setColHidden((pv) => ({ ...pv, [c.key]: !e.target.checked }))} style={{ accentColor: G.blue }} />
                  {c.label}{c.lock ? "（锁定）" : ""}
                </label>
              ))}
              <div style={{ borderTop: "1px solid " + G.line2, marginTop: 6, paddingTop: 6, textAlign: "right" }}>
                <button type="button" onClick={() => setColW({})} style={{ ...T.reset, height: 28, fontSize: 12 }}>列宽重置</button>
              </div>
            </div>
          )}
        </div>

        {/* 筛选栏 */}
        <div style={T.filters}>
          <select value={owner} onChange={(e) => setOwner(e.target.value)} style={T.sel}>
            <option value="">全部负责人</option>
            {owners.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <select value={fillState} onChange={(e) => setFillState(e.target.value)} style={T.sel}>
            <option value="">填写情况：全部</option>
            <option value="unfilled">未填</option>
            <option value="filled">已填</option>
            <option value="normal">正常运营</option>
            <option value="new">新品</option>
            <option value="exempt">已豁免</option>
          </select>
          <input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="搜 ItemID / MSKU / 店铺" style={T.search} />
          {(owner || fillState || kw) && <button type="button" onClick={() => { setOwner(""); setFillState(""); setKw(""); }} style={T.reset}>重置</button>}
        </div>

        {/* 表格 §8.0表头吸顶 */}
        <div style={{ overflow: "auto", maxHeight: "62vh" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <thead><tr>
              {visCols.map((c) => (
                <th key={c.key} className="mp-th" style={{ width: cw(c.key, c.w), textAlign: c.key === "op" ? "right" : "left" }}>
                  {c.label}{c.key !== "op" && <span className="mp-grip" onMouseDown={(e) => startResize(c.key, c.w, e)} />}
                </th>
              ))}
            </tr></thead>
            <tbody>
              {viewRows.length === 0 && (
                <tr><td className="mp-td" colSpan={visCols.length} style={{ textAlign: "center", color: G.mut, padding: "28px 0" }}>无数据</td></tr>
              )}
              {pagedRows.map((r) => (
                <tr className="mp-row" key={`${r.store_id}|${r.item_id}|${r.msku}`}>
                  {visCols.map((c) => (
                    <td key={c.key} className="mp-td" style={{ width: cw(c.key, c.w), textAlign: c.key === "op" ? "right" : "left", whiteSpace: c.key === "issue" || c.key === "goal" || c.key === "store" ? "normal" : "nowrap", overflow: "hidden" }}>
                      {cellContent(r, c.key)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={T.pager}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <span>每页</span>
            {[50, 100, 200].map((ps) => (
              <button key={ps} type="button" onClick={() => { setPageSize(ps); setPage(1); }} style={pgBtn(pageSize === ps, false)}>{ps}</button>
            ))}
            <span style={{ width: 8 }} />
            <button type="button" disabled={page <= 1} onClick={() => setPage(1)} style={pgBtn(false, page <= 1)}>首页</button>
            <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} style={pgBtn(false, page <= 1)}>上一页</button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4));
              const pg = start + i;
              return pg <= totalPages ? <button key={pg} type="button" onClick={() => setPage(pg)} style={pgBtn(pg === page, false)}>{pg}</button> : null;
            })}
            <button type="button" disabled={page >= totalPages} onClick={() => setPage(page + 1)} style={pgBtn(false, page >= totalPages)}>下一页</button>
            <button type="button" disabled={page >= totalPages} onClick={() => setPage(totalPages)} style={pgBtn(false, page >= totalPages)}>末页</button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span>共 {viewRows.length} 条 · 第 {page}/{totalPages} 页</span>
            <span>跳至</span>
            <input type="number" min={1} max={totalPages} defaultValue={page} key={page}
              onKeyDown={(e) => { if (e.key === "Enter") { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= totalPages) setPage(v); } }}
              style={{ width: 54, height: 28, border: "1px solid " + G.line, borderRadius: 6, padding: "0 8px", fontSize: 12, outline: "none" }} />
            <span>页</span>
          </div>
        </div>
      </div>

      {/* 修改抽屉 */}
      {editing && (
        <>
          <div style={T.backdrop} onClick={() => setEditing(null)} />
          <div style={T.drawer}>
            <div style={T.dwHd}>
              <div style={{ fontSize: 15, fontWeight: 600, color: G.ink }}>✏️ {editing.plan_id === null ? "填写" : "修改"}月度目标</div>
              <span style={{ cursor: "pointer", color: G.mut, fontSize: 20 }} onClick={() => setEditing(null)}>×</span>
            </div>
            <div style={T.dwBd}>
              <div style={{ marginBottom: 12 }}>
                <div style={T.lab}>产品</div>
                <div style={{ fontSize: 13, color: G.ink }}><ItemIdLink itemId={editing.item_id} /> · {editing.msku || "-"}</div>
                <div style={{ fontSize: 12, color: G.mut, marginTop: 2 }}>{editing.owner} ｜ {editing.store_name || editing.store_id || "-"} ｜ 库存 {editing.total_inventory != null ? Math.round(Number(editing.total_inventory)) : "-"} ｜ 生命周期 {editing.lifecycle || "-"}</div>
                <div style={{ fontSize: 12, color: G.mut, marginTop: 2 }}>
                  上月（{prevMonthLabel(planMonth)}）：销量 {editing.last_month_qty != null ? editing.last_month_qty : "-"} ｜ 销售额 ${editing.last_month_sales != null ? Number(editing.last_month_sales).toFixed(2) : "-"} ｜ 毛利 ${editing.last_month_profit != null ? Number(editing.last_month_profit).toFixed(2) : "-"}
                  {editing.last_month_sales != null && Number(editing.last_month_sales) !== 0 && editing.last_month_profit != null ? " ｜ 毛利率 " + (Number(editing.last_month_profit) / Number(editing.last_month_sales) * 100).toFixed(1) + "%" : ""}
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <div style={T.lab}>月报问题（系统判定）</div>
                <div style={{ fontSize: 12.5, color: G.redDk, background: G.amberBg, border: "1px solid #fde293", borderRadius: 8, padding: "7px 10px" }}>{reasonsText(editing.issue_reasons) || "（无预填问题）"}</div>
              </div>

              {editing.is_new_product ? (
                <div style={{ fontSize: 12.5, color: G.blueDk, background: G.blueBg, borderRadius: 8, padding: "8px 11px", marginBottom: 12 }}>
                  🆕 新品（{editing.launch_date} 上架）：业绩目标由公司统一核算，无需填写
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  <div><div style={T.lab}>月销售额目标 $ <span style={{ color: G.red }}>*</span></div><input value={tSales} onChange={(e) => setTSales(e.target.value)} placeholder="如 1200" style={T.dwInp} /></div>
                  <div><div style={T.lab}>月利润目标 $ {editing.lifecycle === "清货期" ? <span style={{ color: G.mut, fontWeight: 400 }}>（清货自动 = 销售额×−10%）</span> : <span style={{ color: G.red }}>*</span>}</div>
                    {editing.lifecycle === "清货期"
                      ? <input value={tSales.trim() === "" ? "" : String(Math.round(Number(tSales) * -0.10 * 100) / 100)} readOnly style={{ ...T.dwInp, background: "#f1f3f5", color: G.mut }} />
                      : <input value={tProfit} onChange={(e) => setTProfit(e.target.value)} placeholder="如 180" style={T.dwInp} />}
                  </div>
                </div>
              )}

              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: G.ink, background: "#f8f9fa", border: "1px solid " + G.line2, borderRadius: 8, padding: "9px 11px", marginBottom: 12, cursor: "pointer" }}>
                <input type="checkbox" checked={normalOp} onChange={(e) => setNormalOp(e.target.checked)} style={{ width: 16, height: 16, accentColor: G.blue }} />
                本月<b style={{ margin: "0 2px" }}>正常运营</b>（维持，不设专项指标，也算已表态）
              </label>

              {editing.lifecycle === "清货期" ? (
                <div style={{ border: "1px solid " + G.line2, borderRadius: 9, padding: "10px 11px", marginBottom: 10, background: "#fafbfc" }}>
                  <div style={{ fontSize: 11, color: G.mut, fontWeight: 600, marginBottom: 6 }}>清货指标（锁定）<span style={{ color: G.red }}>*</span></div>
                  <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr auto", gap: 8, alignItems: "center" }}>
                    <select value="清货" disabled style={{ ...T.dwInp, background: "#f1f3f5" }}><option value="清货">清货</option></select>
                    <input value={i1v} onChange={(e) => setI1v(e.target.value)} placeholder="清货数量（件）" style={T.dwInp} />
                    <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} style={{ ...T.dwInp, width: "auto" }} />
                  </div>
                  <div style={{ fontSize: 11, color: G.mut, marginTop: 6 }}>清货产品仅填清货数量+销售额，利润自动=销售额×−10%（勾"正常运营"也需填清货数量与销售额）</div>
                </div>
              ) : !normalOp && (
                <>
                  <div style={{ border: "1px solid " + G.line2, borderRadius: 9, padding: "10px 11px", marginBottom: 10, background: "#fafbfc" }}>
                    <div style={{ fontSize: 11, color: G.mut, fontWeight: 600, marginBottom: 6 }}>指标 1 <span style={{ color: G.red }}>*</span></div>
                    <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr auto", gap: 8, alignItems: "center" }}>
                      <select value={i1t} onChange={(e) => setI1t(e.target.value)} style={T.dwInp}>{IND_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select>
                      <input value={i1v} onChange={(e) => setI1v(e.target.value)} placeholder={QLABEL[i1t]} style={T.dwInp} />
                      <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} style={{ ...T.dwInp, width: "auto" }} />
                    </div>
                  </div>
                  {i2on ? (
                    <div style={{ border: "1px solid " + G.line2, borderRadius: 9, padding: "10px 11px", marginBottom: 10, background: "#fafbfc" }}>
                      <div style={{ fontSize: 11, color: G.mut, fontWeight: 600, marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
                        <span>指标 2（类型不可与指标1相同）</span>
                        <span style={{ color: G.redDk, cursor: "pointer" }} onClick={() => { setI2on(false); setI2v(""); }}>✕ 移除</span>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 8 }}>
                        <select value={i2t} onChange={(e) => setI2t(e.target.value)} style={T.dwInp}>{IND_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select>
                        <input value={i2v} onChange={(e) => setI2v(e.target.value)} placeholder={QLABEL[i2t]} style={T.dwInp} />
                      </div>
                    </div>
                  ) : (
                    <button type="button" onClick={() => setI2on(true)} style={{ ...T.btnGho, height: 30, marginBottom: 10 }}>+ 新增指标 2</button>
                  )}
                </>
              )}

              <div style={{ marginBottom: 8 }}>
                <div style={T.lab}>补充说明（选填）</div>
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="如：降竞价止损后观察2周…" style={T.dwInp} />
              </div>
              <div style={{ fontSize: 11.5, color: G.mut, marginBottom: 4 }}>完成期限自动 = 当月最后一天；非新品必填两项业绩目标；清货利润可为负。</div>
              {msg && <div style={{ marginTop: 8, fontSize: 12.5, color: msg.startsWith("✅") ? G.green : G.redDk }}>{msg}</div>}
            </div>
            <div style={T.dwFt}>
              <button type="button" onClick={() => setEditing(null)} style={T.btnGho}>取消</button>
              <button type="button" disabled={busy} onClick={submit} style={{ ...T.btnPri, opacity: busy ? 0.6 : 1 }}>{busy ? "保存中…" : "保存"}</button>
            </div>
          </div>
        </>
      )}

      {/* 批量导入弹层 */}
      {mpImpOpen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(32,33,36,.32)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => !mpImporting && setMpImpOpen(false)}>
          <div style={{ width: 640, maxWidth: "94%", background: "#fff", borderRadius: 12, boxShadow: "0 18px 50px rgba(32,33,36,.18)", border: "1px solid " + G.line2 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: "1px solid " + G.line2 }}>
              <span style={{ fontSize: 15, fontWeight: 600, color: G.ink }}>月度规划批量导入</span>
              <button onClick={() => !mpImporting && setMpImpOpen(false)} style={{ background: "none", border: "none", fontSize: 20, color: G.mut, cursor: "pointer" }}>×</button>
            </div>
            <div style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: G.sub, marginBottom: 10 }}>一次只能导入一个负责人的月度规划；模板即该负责人本期需填产品清单（预填已填内容）。</div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: G.ink }}>导入负责人 <span style={{ color: G.red }}>*</span>：</span>
                <select value={mpImpOwner} onChange={(e) => { setMpImpOwner(e.target.value); setMpImpResult([]); setMpImpRejects([]); }} style={T.sel} disabled={mpImporting}>
                  <option value="">请选择负责人（必选，单人）</option>
                  {owners.filter((o) => o !== "(未分配)").map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
                {mpImpOwner
                  ? <span style={{ fontSize: 12, color: G.green }}>✓ 本期需填 {mpImpNeed.length} 个产品（豁免 {mpImpBase.length - mpImpNeed.length} 个不在模板内）</span>
                  : <span style={{ fontSize: 12, color: G.amber, background: G.amberBg, border: "1px solid #fde293", borderRadius: 6, padding: "3px 8px" }}>⚠️ 未选择负责人，无法下载模板或导入</span>}
              </div>
              <div style={{ display: "flex", gap: 10, marginBottom: 12, alignItems: "center" }}>
                <button type="button" disabled={!mpImpOwner || mpImporting} onClick={() => mpImpFileRef.current?.click()} style={{ ...T.btnPri, opacity: !mpImpOwner || mpImporting ? 0.4 : 1 }}>{mpImporting ? "导入中…" : "导入文件"}</button>
                <button type="button" disabled={!mpImpOwner || mpImporting} onClick={mpDownloadOwnerTemplate} style={{ ...T.btnGho, opacity: !mpImpOwner || mpImporting ? 0.4 : 1 }}>下载导入模板{mpImpOwner ? "（" + mpImpOwner + " · " + planMonth + " · " + mpImpNeed.length + " 行）" : ""}</button>
                <input ref={mpImpFileRef} type="file" accept=".xlsx,.csv" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) void mpHandleImportFile(f); }} />
              </div>
              <ul style={{ margin: "0 0 12px 18px", padding: 0, fontSize: 12, color: G.sub, lineHeight: 1.8 }}>
                <li>模板为 Excel(.xlsx)：正常运营/指标类型为单元格下拉；填写后直接导入 .xlsx（也兼容 CSV）；单次最多 1000 行</li>
                <li>表头与标识列（店铺ID / ItemID / MSKU）不可修改；<b style={{ color: G.redDk }}>仅允许导入所选负责人本期需填清单内的产品</b>，他人/豁免/清单外逐行拒绝</li>
                <li>已有计划则覆盖、没有则新增；整行填写列全空 = 跳过不更新</li>
                <li>校验与页面一致：正常运营选「是」可不填指标；否则至少 1 个指标+目标；非新品必填两项业绩目标</li>
              </ul>
              {mpImpResult.length > 0 && (
                <div style={{ maxHeight: 240, overflow: "auto", background: "#f8f9fa", border: "1px solid " + G.line2, borderRadius: 8, padding: "10px 12px", fontSize: 12.5, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                  {mpImpResult.map((l, i) => <div key={i} style={{ color: l.startsWith("✅") ? G.green : l.startsWith("❌") ? G.redDk : G.sub }}>{l}</div>)}
                </div>
              )}
              {mpImpRejects.length > 0 && <div style={{ marginTop: 10, textAlign: "right" }}><button type="button" onClick={mpDownloadRejects} style={T.btnGho}>下载拒绝行明细</button></div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
