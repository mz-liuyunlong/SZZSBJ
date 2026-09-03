/**
 * lock.ts - 运行锁，防并发写台账（P2-4）
 *
 * 锁文件 logs/ai-pmc.lock：内含获取时间戳。
 * 若锁存在且未超过 LOCK_TTL_MS（默认 2 小时）→ 跳过本次运行；否则视为陈旧锁，接管。
 * 进程退出时自动释放。
 */

import * as fs from "fs";
import * as path from "path";
import { logger } from "./logger";

const LOCK_FILE = path.resolve(process.cwd(), "logs", "ai-pmc.lock");
const LOCK_TTL_MS = 2 * 60 * 60 * 1000;

export interface LockHandle {
  release: () => void;
}

/** 尝试获取运行锁；获取失败返回 null（调用方应跳过本次运行）。 */
export function acquireLock(label: string): LockHandle | null {
  try {
    const dir = path.dirname(LOCK_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    if (fs.existsSync(LOCK_FILE)) {
      const raw = fs.readFileSync(LOCK_FILE, "utf8").trim();
      const acquiredAt = Number(raw.split("|")[0]);
      const ageMs = Date.now() - (Number.isFinite(acquiredAt) ? acquiredAt : 0);
      if (Number.isFinite(acquiredAt) && ageMs < LOCK_TTL_MS) {
        logger.warn(`运行锁被占用（${Math.round(ageMs / 1000)}s 前由「${raw.split("|")[1] ?? "?"}」获取），跳过本次运行：${label}`);
        return null;
      }
      logger.warn(`检测到陈旧运行锁（${Math.round(ageMs / 1000)}s），接管。`);
    }

    fs.writeFileSync(LOCK_FILE, `${Date.now()}|${label}`, "utf8");
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      try {
        if (fs.existsSync(LOCK_FILE)) fs.unlinkSync(LOCK_FILE);
      } catch (e) {
        logger.warn(`释放运行锁失败: ${e instanceof Error ? e.message : String(e)}`);
      }
    };
    process.once("exit", release);
    return { release };
  } catch (e) {
    logger.error("获取运行锁异常，保守跳过本次运行", e);
    return null;
  }
}
