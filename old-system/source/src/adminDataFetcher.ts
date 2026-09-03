/**
 * adminDataFetcher.ts
 *
 * 根据问题关键词，智能拉取飞书各 sheet 的数据，
 * 转成 Markdown 表格作为 AI 上下文。
 *
 * 支持的数据源：
 *   - 当日数据 (<REDACTED_FEISHU_SHEET_ID>)
 *   - 每日运营跟进日志 (<REDACTED_FEISHU_SHEET_ID>)
 *   - 近期利润与广告 (<REDACTED_FEISHU_SHEET_ID>)
 *   - 悦斯测品汇总 (<REDACTED_FEISHU_SHEET_ID>)
 *   - 悦斯测品运营日志 (<REDACTED_FEISHU_SHEET_ID>)
 *   - 自动广告搜索词聚合分析 (1HeaCn)
 */

import "dotenv/config";
import { FeishuSheetWriter, CellValue } from "./feishuSheetWriter";
import currentReport from "../config/currentReportFieldMapping.json";

const TOKEN = currentReport.spreadsheetToken;
const EXT_TOKEN = currentReport.externalSheets.autoAdSearchTermAnalysis.spreadsheetToken;
const SHEETS = currentReport.sheets as Record<string, string>;
const EXT_SHEETS = currentReport.externalSheets;

// ── 类型定义 ────────────────────────────────────────────────────────────────

export interface FetchedContext {
  /** 已拉取的数据源名称列表 */
  sources: string[];
  /** 所有数据拼成的 Markdown 字符串（直接传给 AI） */
  markdown: string;
}

// ── 关键词 → 数据源检测 ────────────────────────────────────────────────────

function detectSources(question: string): Set<string> {
  const q = question.toLowerCase();
  const src = new Set<string>();

  // 始终拉取当日数据（体量小，几乎总是相关）
  src.add("daily");

  // 广告类问题
  if (/广告|acos|cpc|ctr|cvr|关键词|搜索词|投放|sp广告|自动广告|手动广告/.test(q)) {
    src.add("operationLog");
    src.add("autoAdSearch");
  }

  // 利润 / 销售类
  if (/利润|毛利|成本|销售额|营业额|收入|profit|revenue|roi/.test(q)) {
    src.add("recentProfit");
  }

  // 悦斯测品
  if (/悦斯|测品/.test(q)) {
    src.add("yuesiSummary");
    src.add("yuesiLog");
  }

  // 运营日志 / 问题 / 诊断
  if (/运营|负责人|产品问题|解决意见|诊断|日志|调整/.test(q)) {
    src.add("operationLog");
  }

  // 库存
  if (/库存|inventory|wfs|补货/.test(q)) {
    src.add("daily");
    src.add("recentProfit");
  }

  // 如果没有触发任何特殊规则，默认也拉运营日志
  if (src.size === 1) {
    src.add("operationLog");
  }

  return src;
}

// ── 工具函数 ────────────────────────────────────────────────────────────────

const writer = new FeishuSheetWriter();

function safeRead(
  spreadsheetToken: string,
  sheetId: string,
  range: string,
): CellValue[][] {
  try {
    return writer.readValues({ spreadsheetToken, sheetId, range });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.warn(`[DataFetcher] 读取 sheet=${sheetId} 失败: ${msg}`);
    return [];
  }
}

/** 把二维数组转成 Markdown 表格（限最多 rowLimit 行） */
function toMarkdownTable(headers: string[], rows: CellValue[][], rowLimit = 200): string {
  if (rows.length === 0) return "（无数据）";
  const limited = rows.slice(0, rowLimit);
  const header = `| ${headers.join(" | ")} |`;
  const sep = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = limited
    .map((row) => `| ${headers.map((_, i) => String(row[i] ?? "").replace(/\|/g, "｜")).join(" | ")} |`)
    .join("\n");
  const extra = rows.length > rowLimit ? `\n（共 ${rows.length} 行，已截取前 ${rowLimit} 行）` : "";
  return [header, sep, body].join("\n") + extra;
}

/** 过滤掉全空行 */
function dropEmptyRows(rows: CellValue[][]): CellValue[][] {
  return rows.filter((r) => r.some((c) => c !== null && c !== ""));
}

/** 从每行的日期列，过滤出最近 N 天的行 */
function filterRecentDays(rows: CellValue[][], dateColIdx: number, days: number): CellValue[][] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  cutoff.setHours(0, 0, 0, 0);

  return rows.filter((row) => {
    const raw = String(row[dateColIdx] ?? "");
    const m = /(\d{4}-\d{2}-\d{2})/.exec(raw);
    if (!m) return false;
    return new Date(m[1]) >= cutoff;
  });
}

/** 找列名中包含关键词的第一个列索引（-1 表示没找到） */
function findColIdx(headers: string[], keywords: string[]): number {
  for (const kw of keywords) {
    const idx = headers.findIndex((h) => h.includes(kw));
    if (idx >= 0) return idx;
  }
  return -1;
}

// ── 主函数 ──────────────────────────────────────────────────────────────────

/**
 * 根据管理员问题智能拉取飞书数据，返回 Markdown 格式上下文。
 *
 * @param question 管理员提问内容
 * @param days     运营日志等按日期过滤的天数范围，默认 7 天
 */
export async function fetchDataForQuestion(
  question: string,
  days = 7,
): Promise<FetchedContext> {
  const sources = detectSources(question);
  const parts: string[] = [];
  const sourceNames: string[] = [];

  console.log(`[DataFetcher] 检测到数据源: ${Array.from(sources).join(", ")}`);

  // ── 1. 当日数据 ──────────────────────────────────────────────────────────
  // 只取关键列：日期/店铺/商品ID/负责人/今日销量/销售额/广告费/广告占比/毛利润/毛利率/WFS库存
  if (sources.has("daily")) {
    const sheetId = SHEETS["当日数据"];
    if (sheetId) {
      const rows = safeRead(TOKEN, sheetId, "A1:V300");
      if (rows.length > 1) {
        const allHeaders = rows[0].map(String);
        // 只保留关键列，减少 token 用量
        const keepCols = ["日期","店铺","商品ID","MSKU","负责人","今日销量","今日销售额","广告花费","广告占比","毛利润","毛利率","WFS可售库存","备注"];
        const colIdxs = keepCols.map(k => allHeaders.findIndex(h => h.includes(k))).filter(i => i >= 0);
        const headers = colIdxs.map(i => allHeaders[i]);
        const data = dropEmptyRows(rows.slice(1)).map(r => colIdxs.map(i => r[i] ?? null));
        parts.push(`## 当日数据（sheet=<REDACTED_FEISHU_SHEET_ID>）\n${toMarkdownTable(headers, data, 150)}`);
        sourceNames.push("当日数据");
      }
    }
  }

  // ── 2. 每日运营跟进日志 ───────────────────────────────────────────────────
  // 只取最近 days 天，最多 80 行发给 AI
  if (sources.has("operationLog")) {
    const sheetId = SHEETS["每日运营跟进日志"];
    if (sheetId) {
      const rows = safeRead(TOKEN, sheetId, "A1:P2000");
      if (rows.length > 1) {
        const headers = rows[0].map(String);
        const dateCol = findColIdx(headers, ["日期", "date"]);
        let data = dropEmptyRows(rows.slice(1));
        if (dateCol >= 0) {
          data = filterRecentDays(data, dateCol, days);
        } else {
          data = data.slice(-80);
        }
        parts.push(
          `## 每日运营跟进日志（sheet=<REDACTED_FEISHU_SHEET_ID>，最近 ${days} 天，共 ${data.length} 行）\n` +
          toMarkdownTable(headers, data, 80),
        );
        sourceNames.push("每日运营跟进日志");
      }
    }
  }

  // ── 3. 近期利润与广告 ─────────────────────────────────────────────────────
  if (sources.has("recentProfit")) {
    const sheetId = SHEETS["近期利润与广告"];
    if (sheetId) {
      const rows = safeRead(TOKEN, sheetId, "A1:R200");
      if (rows.length > 1) {
        const headers = rows[0].map(String);
        const data = dropEmptyRows(rows.slice(1));
        parts.push(`## 近期利润与广告（sheet=<REDACTED_FEISHU_SHEET_ID>）\n${toMarkdownTable(headers, data, 80)}`);
        sourceNames.push("近期利润与广告");
      }
    }
  }

  // ── 4. 悦斯测品汇总 ───────────────────────────────────────────────────────
  if (sources.has("yuesiSummary")) {
    const sheetId = SHEETS["悦斯测品汇总"];
    if (sheetId) {
      const rows = safeRead(TOKEN, sheetId, "A1:O200");
      if (rows.length > 1) {
        const headers = rows[0].map(String);
        const data = dropEmptyRows(rows.slice(1));
        parts.push(`## 悦斯测品汇总（sheet=<REDACTED_FEISHU_SHEET_ID>）\n${toMarkdownTable(headers, data, 80)}`);
        sourceNames.push("悦斯测品汇总");
      }
    }
  }

  // ── 5. 悦斯测品运营日志 ───────────────────────────────────────────────────
  if (sources.has("yuesiLog")) {
    const sheetId = SHEETS["悦斯测品运营日志"];
    if (sheetId) {
      const rows = safeRead(TOKEN, sheetId, "A1:N1000");
      if (rows.length > 1) {
        const headers = rows[0].map(String);
        const dateCol = findColIdx(headers, ["分析日期", "日期", "date"]);
        let data = dropEmptyRows(rows.slice(1));
        if (dateCol >= 0) {
          data = filterRecentDays(data, dateCol, days);
        } else {
          data = data.slice(-80);
        }
        parts.push(
          `## 悦斯测品运营日志（sheet=<REDACTED_FEISHU_SHEET_ID>，最近 ${days} 天）\n` +
          toMarkdownTable(headers, data, 80),
        );
        sourceNames.push("悦斯测品运营日志");
      }
    }
  }

  // ── 6. 自动广告搜索词聚合分析 ─────────────────────────────────────────────
  if (sources.has("autoAdSearch")) {
    const extSheet = EXT_SHEETS.autoAdSearchTermAnalysis;
    if (extSheet) {
      const rows = safeRead(extSheet.spreadsheetToken, extSheet.sheetId, "A1:P200");
      if (rows.length > 1) {
        const headers = rows[0].map(String);
        const data = dropEmptyRows(rows.slice(1));
        parts.push(`## 自动广告搜索词聚合分析（sheet=1HeaCn）\n${toMarkdownTable(headers, data, 80)}`);
        sourceNames.push("自动广告搜索词");
      }
    }
  }

  // TODO: 领星 API 实时数据（当 question 包含"今天实时"/"当前库存"等词时触发）
  // const lingxing = new LingxingClient(loadConfig());
  // const result = await lingxing.get('/basicOpen/multiplatform/walmart/list', { ...params });

  return {
    sources: sourceNames,
    markdown: parts.join("\n\n---\n\n"),
  };
}
