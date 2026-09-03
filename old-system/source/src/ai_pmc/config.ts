/**
 * config.ts - 读取飞书配置表，返回 PMC 运行配置（P1-7 单一权威源）
 *
 * 数据源：
 *  - 规则配置表 (2HamUU)：超时天数 / 提醒间隔 / 升级天数
 *  - 负责人配置表 (3waBiS)：固定角色 open_id 的【唯一权威源】，禁止硬编码
 * 读取失败时回退到文档既定默认值并记日志（不中断主流程）。
 */

import "dotenv/config";
import { FeishuSheetWriter, CellValue } from "../feishuSheetWriter";
import { logger } from "./logger";

// ── 常量：表 token / sheetId（已确认） ─────────────────────────────
export const PMC_SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";
export const SHEET = {
  taskLedger: "0HadpM", // PMC任务台账
  execConfig: "1QDvLl", // 执行配置
  ruleConfig: "2HamUU", // PMC规则配置
  ownerConfig: "3waBiS", // PMC负责人配置
  notifyLog: "4BfsYD", // PMC通知日志
} as const;
export const SHEET_NAME = {
  taskLedger: "PMC任务台账",
  notifyLog: "PMC通知日志",
} as const;

// ItemID 负责人表（已有，只读）
export const ITEM_OWNER_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";
export const ITEM_OWNER_SHEET_ID = "<REDACTED_FEISHU_SHEET_ID>";

// ── 类型 ───────────────────────────────────────────────────────────
export interface RuleSpec {
  timeoutDays: number;
  intervalDays: number;
  escalateDays: number | null;
}
export interface OwnerSpec {
  name: string;
  openId: string;
}
export interface PmcConfig {
  rules: { R001: RuleSpec; R002: RuleSpec; R003: RuleSpec; R004: RuleSpec };
  owners: { purchase: OwnerSpec; warehouse: OwnerSpec; pmc: OwnerSpec };
  pmcWebhookUrl: string;
  logLookbackDays: number;
}

// ── 文档既定默认值（读取失败时兜底） ───────────────────────────────
const DEFAULT_RULES: PmcConfig["rules"] = {
  R001: { timeoutDays: 7, intervalDays: 7, escalateDays: 14 },
  R002: { timeoutDays: 7, intervalDays: 7, escalateDays: 21 },
  R003: { timeoutDays: 0, intervalDays: 1, escalateDays: null },
  R004: { timeoutDays: 5, intervalDays: 3, escalateDays: 10 },
};
const DEFAULT_OWNERS: PmcConfig["owners"] = {
  purchase: { name: "巫新健", openId: "<REDACTED_FEISHU_OPEN_ID>" },
  warehouse: { name: "刘晶晶", openId: "<REDACTED_FEISHU_OPEN_ID>" },
  pmc: { name: "江梓博", openId: "<REDACTED_FEISHU_OPEN_ID>" },
};

// ── 工具 ───────────────────────────────────────────────────────────
function s(v: CellValue): string {
  return String(v ?? "").trim();
}
function normHeader(v: CellValue): string {
  return s(v).replace(/\s+/g, "").toLowerCase();
}
function toNumOr(v: CellValue, fallback: number | null): number | null {
  const t = s(v);
  if (t === "" || t === "-") return fallback;
  const n = Number(t);
  return Number.isFinite(n) ? n : fallback;
}

// ── 读取规则配置表 (2HamUU) ────────────────────────────────────────
function readRules(writer: FeishuSheetWriter): PmcConfig["rules"] {
  try {
    const rows = writer.readValues({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: SHEET.ruleConfig,
      range: "A1:F50",
    });
    if (rows.length < 2) throw new Error("规则配置表为空");
    const head = rows[0];
    const idIdx = head.findIndex((h) => normHeader(h) === "rule_id");
    const toIdx = head.findIndex((h) => ["超时天数", "timeout"].includes(normHeader(h)));
    const ivIdx = head.findIndex((h) => ["提醒间隔天数", "提醒间隔", "interval"].includes(normHeader(h)));
    const esIdx = head.findIndex((h) => ["升级天数", "escalate"].includes(normHeader(h)));
    if (idIdx < 0) throw new Error("规则配置表缺少 rule_id 列");

    const rules = JSON.parse(JSON.stringify(DEFAULT_RULES)) as PmcConfig["rules"];
    for (const row of rows.slice(1)) {
      const id = s(row[idIdx]).toUpperCase() as keyof PmcConfig["rules"];
      if (!(id in rules)) continue;
      const def = DEFAULT_RULES[id];
      rules[id] = {
        timeoutDays: toNumOr(row[toIdx], def.timeoutDays) ?? def.timeoutDays,
        intervalDays: toNumOr(row[ivIdx], def.intervalDays) ?? def.intervalDays,
        escalateDays: esIdx >= 0 ? toNumOr(row[esIdx], def.escalateDays) : def.escalateDays,
      };
    }
    logger.info("规则配置：已从飞书 2HamUU 读取");
    return rules;
  } catch (e) {
    logger.warn(`规则配置读取失败，使用默认值：${e instanceof Error ? e.message : String(e)}`);
    return JSON.parse(JSON.stringify(DEFAULT_RULES));
  }
}

// ── 读取负责人配置表 (3waBiS) ──────────────────────────────────────
function readOwnersConfig(writer: FeishuSheetWriter): PmcConfig["owners"] {
  try {
    const rows = writer.readValues({
      spreadsheetToken: PMC_SPREADSHEET_TOKEN,
      sheetId: SHEET.ownerConfig,
      range: "A1:F50",
    });
    if (rows.length < 2) throw new Error("负责人配置表为空");
    const head = rows[0];
    const roleIdx = head.findIndex((h) => normHeader(h) === "角色");
    const nameIdx = head.findIndex((h) => normHeader(h) === "姓名");
    const oidIdx = head.findIndex((h) => ["open_id", "飞书open_id", "openid"].includes(normHeader(h)));
    if (roleIdx < 0 || oidIdx < 0) throw new Error("负责人配置表缺少 角色/open_id 列");

    const owners = JSON.parse(JSON.stringify(DEFAULT_OWNERS)) as PmcConfig["owners"];
    for (const row of rows.slice(1)) {
      const role = s(row[roleIdx]);
      const name = nameIdx >= 0 ? s(row[nameIdx]) : "";
      const oid = s(row[oidIdx]);
      if (!oid || !oid.startsWith("ou_")) continue;
      if (role.includes("采购")) owners.purchase = { name: name || owners.purchase.name, openId: oid };
      else if (role.includes("仓库")) owners.warehouse = { name: name || owners.warehouse.name, openId: oid };
      else if (role.includes("PMC") || role.includes("总")) owners.pmc = { name: name || owners.pmc.name, openId: oid };
    }
    logger.info("负责人配置：已从飞书 3waBiS 读取（唯一权威源）");
    return owners;
  } catch (e) {
    logger.warn(`负责人配置读取失败，使用默认值：${e instanceof Error ? e.message : String(e)}`);
    return JSON.parse(JSON.stringify(DEFAULT_OWNERS));
  }
}

/** 加载 PMC 配置。offline=true 时跳过飞书读取，直接用默认值（供离线自测）。 */
export function loadPmcConfig(writer?: FeishuSheetWriter, offline = false): PmcConfig {
  const pmcWebhookUrl = process.env.FEISHU_PMC_WEBHOOK_URL?.trim() ?? "";
  const logLookbackDays = Number(process.env.PMC_LOG_LOOKBACK_DAYS?.trim() || "30") || 30;

  if (offline || !writer) {
    return {
      rules: JSON.parse(JSON.stringify(DEFAULT_RULES)),
      owners: JSON.parse(JSON.stringify(DEFAULT_OWNERS)),
      pmcWebhookUrl,
      logLookbackDays,
    };
  }

  return {
    rules: readRules(writer),
    owners: readOwnersConfig(writer),
    pmcWebhookUrl,
    logLookbackDays,
  };
}
