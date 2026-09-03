/**
 * autoAdImportCheck.ts - 自动广告搜索词导入检查（纯函数模块）
 *
 * 业务口径（2026-07-13 定稿）：
 *   targetDate = Asia/Shanghai 当前日期 - lagDays（默认 3 天）
 *   - 表内最新有效日期 >= targetDate → 正常，不通报（覆盖"存在 targetDate"与"最新日期大于 targetDate"）
 *   - 表内最新有效日期 <  targetDate → 发送数据缺失告警
 *   - 日期列无法解析（空列 / 全部非法值）→ 配置异常，不发缺失告警
 *
 * 本模块不依赖服务器系统时区（统一 Intl Asia/Shanghai），
 * 不引用飞书/领星/MySQL —— 外部 IO 全部通过 deps 注入，便于 Mock 测试。
 * 新旧两个版本的 checkAutoAdSearchTermImport.ts（本地旧版 / 生产 feishuNotify 版）均可接入。
 */

const CST_TIMEZONE = "Asia/Shanghai";

/** 标准日期格式校验 */
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** 从任意文本中提取首个日期（支持 2026-07-10 / 2026/7/10 / 2026.07.10 / 2026年7月10日 / 含时间串） */
const DATE_EXTRACT_RE = /(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})/;

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** 取某时刻在 Asia/Shanghai 时区的日期（YYYY-MM-DD），与服务器系统时区无关 */
export function formatDateCST(date: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: CST_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

/** 取某时刻在 Asia/Shanghai 时区的"YYYY-MM-DD HH:mm" */
export function formatDateTimeCST(date: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: CST_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string): string => parts.find((p) => p.type === type)?.value ?? "";
  // Intl 在 hour12:false 下可能返回 "24"，归一为 "00"
  const hour = get("hour") === "24" ? "00" : get("hour");
  return `${get("year")}-${get("month")}-${get("day")} ${hour}:${get("minute")}`;
}

/**
 * 计算应导入数据日期：Asia/Shanghai 当前日期 - lagDays。
 * 例：baseDate=2026-07-13（上海）, lagDays=3 → "2026-07-10"
 */
export function getTargetDateCST(baseDate: Date = new Date(), lagDays = 3): string {
  const todayCst = formatDateCST(baseDate); // YYYY-MM-DD
  const [y, m, d] = todayCst.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() - lagDays);
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`;
}

/**
 * 解析单元格中的日期为标准 YYYY-MM-DD。
 * 支持含时间（"2026-07-10 08:30"）、区间取首个日期；非法/不存在的日历日期返回 null。
 */
export function parseDateCell(value: unknown): string | null {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const m = DATE_EXTRACT_RE.exec(text);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) {
    return null; // 例如 2026-13-40
  }
  return `${y}-${pad2(mo)}-${pad2(d)}`;
}

/**
 * 日期列定位：优先表头候选词命中（header 模式），否则回退 positional 模式。
 * 生产 1HeaCn 实测为 positional，列索引 2（0-based，即 C 列）。
 */
export function findDateColumnIndex(
  headers: unknown[],
  candidates: string[],
  positionalIndex = 2,
): { index: number; mode: "header" | "positional" } {
  const normalized = headers.map((h) => String(h ?? "").trim().toLowerCase());
  for (const c of candidates) {
    const idx = normalized.indexOf(c.toLowerCase());
    if (idx >= 0) return { index: idx, mode: "header" };
  }
  return { index: positionalIndex, mode: "positional" };
}

export type ImportCheckStatus = "ok" | "missing" | "config_error";

export interface ImportCheckResult {
  status: ImportCheckStatus;
  targetDate: string;
  /** 表内最新成功数据日期（标准 YYYY-MM-DD）；无有效日期时为 null */
  latestDate: string | null;
  nonEmptyCount: number;
  parsedCount: number;
  invalidCount: number;
  /** config_error 时的原因说明 */
  configErrorReason?: string;
}

/**
 * 核心判定。最终业务判断只使用标准 YYYY-MM-DD 字符串比较，禁止模糊包含。
 */
export function evaluateImportStatus(cells: unknown[], targetDate: string): ImportCheckResult {
  if (!ISO_DATE_RE.test(targetDate)) {
    return {
      status: "config_error",
      targetDate,
      latestDate: null,
      nonEmptyCount: 0,
      parsedCount: 0,
      invalidCount: 0,
      configErrorReason: `targetDate 非标准 YYYY-MM-DD: ${targetDate}`,
    };
  }

  let latestDate: string | null = null;
  let nonEmptyCount = 0;
  let parsedCount = 0;
  let invalidCount = 0;

  for (const cell of cells) {
    const text = String(cell ?? "").trim();
    if (!text) continue;
    nonEmptyCount += 1;
    const parsed = parseDateCell(text);
    if (!parsed) {
      invalidCount += 1;
      continue;
    }
    parsedCount += 1;
    if (!latestDate || parsed > latestDate) latestDate = parsed;
  }

  if (parsedCount === 0) {
    return {
      status: "config_error",
      targetDate,
      latestDate: null,
      nonEmptyCount,
      parsedCount,
      invalidCount,
      configErrorReason:
        nonEmptyCount === 0
          ? "日期列为空，未读到任何非空单元格"
          : `日期列共 ${nonEmptyCount} 个非空值但全部无法解析为日期`,
    };
  }

  return {
    status: (latestDate as string) >= targetDate ? "ok" : "missing",
    targetDate,
    latestDate,
    nonEmptyCount,
    parsedCount,
    invalidCount,
  };
}

/** 缺失告警文案（固定四行；禁止使用旧错误文案，禁止把检查日当作应导入日） */
export function buildMissingAlertText(args: {
  targetDate: string;
  checkTime: string; // YYYY-MM-DD HH:mm
  latestDate: string | null;
}): string {
  return [
    "悦斯自动广告搜索词聚合分析数据缺失",
    `应导入数据日期：${args.targetDate}`,
    `任务检查时间：${args.checkTime}`,
    `表内最新成功数据日期：${args.latestDate ?? "无"}`,
  ].join("\n");
}

export interface AutoAdCheckDeps {
  /** 读取日期列全部单元格值（由脚本注入：飞书表格分批读取；测试注入 Mock 数组） */
  readDateCells: () => Promise<unknown[]>;
  /** 发送告警（由脚本注入：webhook/feishuNotify；测试注入 Mock） */
  sendAlert: (text: string) => Promise<void>;
  now?: Date;
  lagDays?: number;
  /** 追加在四行文案之后的 @ 提醒行（保留现有 @江梓博 行为），可为空 */
  mentionLine?: string;
}

export interface AutoAdCheckOutcome extends ImportCheckResult {
  checkTime: string;
  /** 实际生成的告警文案；未告警时为 null */
  alertText: string | null;
  checkedCells: number;
}

/**
 * 编排函数：脚本与测试共用。仅在 status === "missing" 时调用 sendAlert；
 * config_error 时不发缺失告警（由调用方按"配置异常"处理）。
 */
export async function runAutoAdImportCheck(deps: AutoAdCheckDeps): Promise<AutoAdCheckOutcome> {
  const now = deps.now ?? new Date();
  const targetDate = getTargetDateCST(now, deps.lagDays ?? 3);
  const checkTime = formatDateTimeCST(now);
  const cells = await deps.readDateCells();
  const result = evaluateImportStatus(cells, targetDate);

  let alertText: string | null = null;
  if (result.status === "missing") {
    alertText = buildMissingAlertText({
      targetDate: result.targetDate,
      checkTime,
      latestDate: result.latestDate,
    });
    if (deps.mentionLine) alertText += `\n${deps.mentionLine}`;
    await deps.sendAlert(alertText);
  }

  return { ...result, checkTime, alertText, checkedCells: cells.length };
}
