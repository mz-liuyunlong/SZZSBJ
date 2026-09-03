/**
 * logger.ts - 统一日志工具
 *
 * 所有异常/运行信息写入 logs/ai-pmc.log（北京时间戳），并同时打印到控制台。
 * 写日志失败不抛出（不中断主流程）。
 */

import * as fs from "fs";
import * as path from "path";
import { formatBJ } from "./dateUtil";

const LOG_DIR = path.resolve(process.cwd(), "logs");
const LOG_FILE = path.join(LOG_DIR, "ai-pmc.log");

type Level = "INFO" | "WARN" | "ERROR";

function write(level: Level, msg: string): void {
  const line = `[${formatBJ(new Date(), true)}] [${level}] ${msg}`;
  if (level === "ERROR") console.error(line);
  else console.log(line);
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
    fs.appendFileSync(LOG_FILE, line + "\n", "utf8");
  } catch {
    // 写日志失败不影响主流程
  }
}

export const logger = {
  info: (msg: string) => write("INFO", msg),
  warn: (msg: string) => write("WARN", msg),
  error: (msg: string, err?: unknown) =>
    write("ERROR", err ? `${msg} | ${err instanceof Error ? err.stack ?? err.message : String(err)}` : msg),
};

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
