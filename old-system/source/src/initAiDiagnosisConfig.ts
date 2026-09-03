import currentReport from "../config/currentReportFieldMapping.json";
import { FeishuSheetWriter, SheetRow } from "./feishuSheetWriter";

const SHEET_NAME = "AI诊断配置";
const TASK_NAME = "初始化AI诊断配置";

function normalizeText(value: unknown): string {
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["value", "text", "formattedValue", "string", "number", "result"]) {
      if (record[key] !== undefined && record[key] !== null) {
        return normalizeText(record[key]);
      }
    }
    return "";
  }
  return String(value).trim();
}

function hasExistingConfig(rows: SheetRow[]): boolean {
  return rows.slice(1).some((row) => normalizeText(row[0]) && normalizeText(row[1]));
}

function buildDefaultRows(): SheetRow[] {
  return [
    ["配置项", "配置值", "说明", "是否启用"],
    ["AI_AD_ANALYSIS_DAYS", 7, "广告关键词分析近N天；例如7代表分析数据日期往前6天到数据日期", true],
    ["B_LEVEL_INTERVAL_DAYS", 7, "B级产品AI诊断频次：7天一次", true],
    ["C_LEVEL_INTERVAL_DAYS", 5, "C级产品AI诊断频次：5天一次", true],
    ["D_LEVEL_INTERVAL_DAYS", 3, "D级产品AI诊断频次：3天一次", true],
    [
      "AI_SYSTEM_PROMPT",
      "你是沃尔玛广告运营诊断助手。你只基于给定的利润、库存、近5天表现和关键词广告数据做诊断，不编造数据。",
      "AI系统提示词",
      true,
    ],
    [
      "AI_OUTPUT_FORMAT",
      "只返回严格JSON：{\"productDataIssue\":\"产品数据问题\",\"solution\":\"解决意见\"}。不要Markdown，不要额外解释。",
      "AI输出格式",
      true,
    ],
    [
      "KEYWORD_ANALYSIS_RULES",
      "必须分析到具体关键词。重点检查：高花费低转化、低曝光、长期无消耗、无订单、高ACOS、关键词与产品不相关、品牌词或泛词误投放。解决意见必须点名关键词和具体动作。",
      "关键词广告分析规则",
      true,
    ],
    [
      "FORBIDDEN_ACTIONS",
      "不要建议发货、退款、改库存；不要覆盖运营日志；不要编造不存在的关键词、订单或花费。",
      "禁止事项",
      true,
    ],
  ];
}

function main(): void {
  const confirmWrite = process.argv.includes("--confirm-write");
  const dryRun = !confirmWrite;
  const force = process.argv.includes("--force");
  const writer = new FeishuSheetWriter();
  const sheetId = currentReport.sheets[SHEET_NAME];

  if (!sheetId) {
    throw new Error(`config/currentReportFieldMapping.json 缺少 ${SHEET_NAME} Sheet ID`);
  }

  console.log(TASK_NAME);
  console.log(`目标 Sheet: ${SHEET_NAME} (${sheetId})`);
  console.log(`写入模式: ${confirmWrite ? "confirm-write" : "dry-run"}`);
  console.log(`强制覆盖: ${force ? "是" : "否"}`);

  const existingRows = writer.readValues({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    range: "A1:D200",
  });

  if (hasExistingConfig(existingRows) && !force) {
    console.log("AI诊断配置已存在，本次不覆盖。需要覆盖时追加 --force --confirm-write。");
    return;
  }

  const rows = buildDefaultRows();
  writer.writeCells({
    spreadsheetToken: currentReport.spreadsheetToken,
    sheetId,
    sheetName: SHEET_NAME,
    range: `A1:D${rows.length}`,
    rows,
    dryRun,
    confirmWrite,
    allowOverwrite: true,
  });

  console.log(`AI诊断配置初始化${dryRun ? "预览" : "写入"}完成，行数=${rows.length}`);
}

main();
