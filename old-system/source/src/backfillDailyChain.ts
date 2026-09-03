/**
 * backfillDailyChain.ts - 方案B：N=5 三层每日回溯编排（第14版·封板，2026-07-12）
 *
 * 背景：生产原每天只处理 T-2 单日，领星侧晚到/修订数据无法自愈。
 * 本脚本按"阶段串行"依次回溯（默认 T-6 → T-2 共5天）：
 *   第一阶段 FACT     ：syncLingxingDailyToDb  （--date=YYYY-MM-DD，upsert幂等）
 *   第二阶段 每日销售明细：syncLingxingToRawFeishu（位置参数日期，删日重写）
 *   第三阶段 订单利润   ：syncOrderProfitDaily   （--date=YYYY-MM-DD，删日重写）
 *
 * 核心安全设计（第9版定稿）：
 *   0. ★活动子进程标记（.lock.unsafe，前置式生命周期）：每个真实子任务 spawn 前
 *      原子创建（state=starting, unsafeChildPid=null）→ spawn 成功后临时文件+rename
 *      原子更新（state=running, 真实PID）→ 超时/信号终止开始时 state=terminating →
 *      仅在真实 exit 事件或 PID 明确 dead 后才删除。父进程在任意时刻被 SIGKILL，
 *      标记都已在盘上；后续任何 execute 一律 fail-closed 拒绝（含 state=starting/
 *      PID为null/损坏/dead 全部拒绝），人工核查后手删或 /tmp 重启自清。
 *      acquireLock 在入口、直接建锁后、cleanup临界区删旧锁前、cleanup建新锁后、
 *      返回true前多点复查（防TOCTOU）；复查命中只释放自己刚建的主锁，不删标记。
 *      标记写入失败严格分级：EEXIST=保留已有现场；EACCES/ENOSPC等=CRITICAL；
 *      spawn前创建失败=禁止spawn+全链中止；spawn后更新失败=立即终止该子进程
 *   1. 默认 dry-run；--execute 必须显式 --deadline=HH:mm（当天上海时刻，不跨午夜）
 *   2. 单任务超时闭环：SIGTERM → 10s → SIGKILL → 最多再等15s → 必须 resolve
 *      （禁止Promise悬挂）；exitConfirmed 严格三态核验（仅 exit 事件或 PID 明确
 *      dead 才算确认）；exitConfirmed=false → 记失败+dirty（重写阶段）→
 *      ★立即中止整条编排 → summary.childExitUnconfirmed=true + unsafeChildPid →
 *      main 按未确认存活子进程保守不释放锁
 *   3. PID探测三态：alive（kill 0 成功）/ dead（明确 ESRCH）/ unknown（EPERM等）。
 *      只有 dead 能证明进程不存在；alive/unknown 一律保守（不删锁、不确认退出）
 *   4. 陈旧主锁清理走独立 cleanup 互斥锁（.cleanup）：只有原子获得 cleanup 锁的
 *      进程允许清理；获得后重读重判主锁（仅 PID dead 或 alive+cmdline明确nomatch
 *      才删）；未获得者等待后重试主锁，绝不自行 unlink
 *   5. sleep 可中断：日期间等待按 250ms 分片轮询 shutdown 与 deadline
 *   6. 外部信号：处理器只置停止标志+终止活动子任务；runChain 收敛输出完整
 *      SUMMARY_JSON；锁由 main 统一 finally 核验后释放（fatalReleaseLock 兜底同判定）
 *   7. 子任务以 node + ts-node/dist/bin.js 直启（无 npm/npx 壳）；生产 cron 与
 *      首次试跑使用绝对路径 node 直启 + exec（见交接包）
 *   8. 日期一律 Asia/Shanghai；历史日重写用当前 dim_product 负责人（本期口径）
 *
 * 用法：
 *   npm run backfill:daily-chain                              # dry-run
 *   npm run backfill:daily-chain:execute -- --deadline=19:10  # 测试环境
 *   生产/试跑：node <ts-node-bin绝对路径> src/backfillDailyChain.ts --execute --deadline=...
 *
 * 安全纪律：日志不输出数据库密码/App Secret/token/群ID/webhook。
 */

import * as fs from "fs";
import * as path from "path";
import { spawn } from "child_process";

// ── 常量 ──────────────────────────────────────────────────────────────
const LOCK_FILE = "/tmp/lingxing-backfill-daily-chain.lock";
const LOCK_NEEDLE = "backfillDailyChain";
const LOCK_STALE_WARN_MS = 24 * 60 * 60 * 1000;
const SIGKILL_GRACE_MS = 10000;   // SIGTERM 后宽限
const POST_KILL_WAIT_MS = 15000;  // SIGKILL 后最多再等
const SLEEP_CHECK_MS = 250;       // sleep 分片轮询间隔
const UNSAFE_SUFFIX = ".unsafe";  // 危险子进程隔离标记文件后缀
const MAX_DAYS = 31;
const TZ = "Asia/Shanghai";

export type StageId = "fact" | "rawSales" | "orderProfit";

export interface StageDef {
  id: StageId;
  label: string;
  entry: string;               // 相对项目根的 ts 入口
  buildArgs: (date: string) => string[];
  rewriteStyle: boolean;       // true=删日重写（非成功退出产生脏数据日）
}

export const STAGES: StageDef[] = [
  { id: "fact",        label: "FACT(lingxing-daily)",    entry: "src/syncLingxingDailyToDb.ts",  buildArgs: (d) => [`--date=${d}`], rewriteStyle: false },
  { id: "rawSales",    label: "每日销售明细(RAW快照)",    entry: "src/syncLingxingToRawFeishu.ts", buildArgs: (d) => [d, "--only=detail"], rewriteStyle: true  },
  { id: "orderProfit", label: "订单利润(RAW快照)",        entry: "src/syncOrderProfitDaily.ts",    buildArgs: (d) => [`--date=${d}`], rewriteStyle: true  },
];

// ── 上海时区日期工具 ───────────────────────────────────────────────────
export function shanghaiDateStr(ms: number): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(ms));
}

export function addDaysStr(dateStr: string, delta: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + delta));
  return dt.toISOString().slice(0, 10);
}

function isValidDateStr(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, d] = s.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

/** 把 HH:mm（上海时区、执行当天）换算成毫秒时间戳；不跨午夜 */
export function deadlineToMs(hhmm: string, nowMs: number): number {
  const [hh, mm] = hhmm.split(":").map(Number);
  const todayStr = shanghaiDateStr(nowMs);
  const [y, mo, d] = todayStr.split("-").map(Number);
  return Date.UTC(y, mo - 1, d, hh - 8, mm, 0, 0); // 上海=UTC+8 无夏令时
}

// ── 参数解析 ──────────────────────────────────────────────────────────
export interface ParsedConfig {
  mode: "dry-run" | "execute";
  dates: string[];             // 旧→新
  deadlineHHmm: string | null; // execute 必填
  intervalSeconds: number;
  taskTimeoutMinutes: number;
}

export function parseConfig(argv: string[], nowMs: number): ParsedConfig {
  const get = (name: string): string | undefined => {
    const hit = argv.find((a) => a.startsWith(`--${name}=`));
    return hit ? hit.slice(name.length + 3) : undefined;
  };
  const mode: "dry-run" | "execute" = argv.includes("--execute") ? "execute" : "dry-run";

  // 未知参数直接拒绝（防拼写错误绕过校验，如 --dead-line）
  const KNOWN = ["execute"];
  const KNOWN_KV = ["start-date", "end-date", "days", "end-offset", "interval-seconds", "deadline", "task-timeout-minutes"];
  for (const a of argv) {
    if (!a.startsWith("--")) throw new Error(`参数校验失败: 未知参数 "${a}"`);
    const body = a.slice(2);
    const key = body.includes("=") ? body.slice(0, body.indexOf("=")) : body;
    if (!KNOWN.includes(key) && !(KNOWN_KV.includes(key) && body.includes("="))) {
      throw new Error(`参数校验失败: 未知或格式错误的参数 "${a}"`);
    }
  }

  const startArg = get("start-date");
  const endArg = get("end-date");
  const daysArg = get("days");
  const endOffsetArg = get("end-offset");
  const intervalArg = get("interval-seconds");
  const deadlineArg = get("deadline");
  const timeoutArg = get("task-timeout-minutes");

  const fail = (msg: string): never => { throw new Error(`参数校验失败: ${msg}`); };

  // 死线：execute 必须显式传（不允许默认无死线）
  let deadlineHHmm: string | null = null;
  if (deadlineArg !== undefined) {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(deadlineArg)) fail(`--deadline 格式必须为 HH:mm，收到 "${deadlineArg}"`);
    deadlineHHmm = deadlineArg;
    // 已知边界：死线只解释为"执行当天(上海)的 HH:mm"，不跨午夜；已过=立即中止（fail-closed）
    if (mode === "execute" && deadlineToMs(deadlineArg, nowMs) <= nowMs) {
      console.log(`[提示] --deadline=${deadlineArg} 为执行当天时刻且已过（死线不跨午夜），本次将立即中止；晚间补跑请传当天更晚时刻（如 23:30）`);
    }
  }
  if (mode === "execute" && !deadlineHHmm) {
    fail("--execute 必须显式指定 --deadline=HH:mm（生产 cron 用 19:10，晚间手动补跑请自行指定如 23:30）");
  }

  const days = daysArg !== undefined ? Number(daysArg) : 5;
  const endOffset = endOffsetArg !== undefined ? Number(endOffsetArg) : 2;
  if (!Number.isInteger(days) || days < 1 || days > MAX_DAYS) fail(`--days 必须是 1~${MAX_DAYS} 的整数`);
  if (!Number.isInteger(endOffset) || endOffset < 0) fail("--end-offset 必须是 >=0 的整数");

  const intervalSeconds = intervalArg !== undefined ? Number(intervalArg) : 3;
  if (!Number.isFinite(intervalSeconds) || intervalSeconds < 0 || intervalSeconds > 3600) {
    fail("--interval-seconds 必须是 0~3600 的数字（防误传超大值导致持锁滞留）");
  }

  const taskTimeoutMinutes = timeoutArg !== undefined ? Number(timeoutArg) : 15;
  if (!Number.isFinite(taskTimeoutMinutes) || taskTimeoutMinutes <= 0) fail("--task-timeout-minutes 必须是 >0 的数字");

  // 日期窗口：显式日期优先于 days/end-offset
  let startDate: string;
  let endDate: string;
  if (startArg !== undefined || endArg !== undefined) {
    if (startArg === undefined || endArg === undefined) fail("--start-date 与 --end-date 必须成对提供");
    if (!isValidDateStr(startArg!)) fail(`--start-date 非法: "${startArg}"`);
    if (!isValidDateStr(endArg!)) fail(`--end-date 非法: "${endArg}"`);
    startDate = startArg!;
    endDate = endArg!;
  } else {
    endDate = addDaysStr(shanghaiDateStr(nowMs), -endOffset);
    startDate = addDaysStr(endDate, -(days - 1));
  }
  if (startDate > endDate) fail(`start-date(${startDate}) 不得晚于 end-date(${endDate})`);

  const dates: string[] = [];
  for (let d = startDate; d <= endDate; d = addDaysStr(d, 1)) {
    dates.push(d);
    if (dates.length > MAX_DAYS) fail(`日期跨度超过上限 ${MAX_DAYS} 天`);
  }

  return { mode, dates, deadlineHHmm, intervalSeconds, taskTimeoutMinutes };
}

// ── PID 三态探测 ──────────────────────────────────────────────────────
/** alive=kill 0 成功；dead=明确 ESRCH；unknown=EPERM等（存在与否未证实，一律保守） */
export type PidState = "alive" | "dead" | "unknown";

let pidStateOverride: ((pid: number) => PidState | undefined) | null = null;
/** 仅测试注入（模拟 EPERM 等无法真实构造的场景） */
export function __setPidStateForTest(fn: ((pid: number) => PidState | undefined) | null): void {
  pidStateOverride = fn;
}

export function pidState(pid: number): PidState {
  if (pidStateOverride) {
    const o = pidStateOverride(pid);
    if (o !== undefined) return o;
  }
  try {
    process.kill(pid, 0);
    return "alive";
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code;
    return code === "ESRCH" ? "dead" : "unknown";
  }
}

type CmdlineCheck = "match" | "nomatch" | "unknown";
function pidCmdlineCheck(pid: number, needle: string): CmdlineCheck {
  try {
    const raw = fs.readFileSync(`/proc/${pid}/cmdline`);
    return raw.toString("utf-8").includes(needle) ? "match" : "nomatch";
  } catch { return "unknown"; }
}

// ── 单实例锁（含独立 cleanup 互斥锁） ─────────────────────────────────
interface LockContent { pid: number; taskRunId: string; startedAt: string; }

function readLockFile(file: string): LockContent | null {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, "utf-8")) as LockContent;
    return parsed && Number.isInteger(parsed.pid) ? parsed : null;
  } catch { return null; }
}

function writeLockAtomic(file: string, taskRunId: string): boolean {
  try {
    const fd = fs.openSync(file, "wx"); // 原子创建
    fs.writeFileSync(fd, JSON.stringify({ pid: process.pid, taskRunId, startedAt: new Date().toISOString() }));
    fs.closeSync(fd);
    return true;
  } catch { return false; }
}

// ── 活动子进程标记（前置式生命周期，跨父进程死亡防护） ────────────────
export type UnsafeMarkerState = "starting" | "running" | "terminating";

export interface UnsafeMarker {
  taskRunId: string;
  parentPid: number;
  unsafeChildPid: number | null;
  stage: string;
  date: string;
  state: UnsafeMarkerState;
  reason?: string;
  createdAt: string;
  updatedAt?: string;
}

export type MarkerWriteResult = { ok: true } | { ok: false; code: string };

/**
 * spawn 前原子创建标记（O_EXCL）。错误严格分级：
 * EEXIST=已有现场保留（返回失败码EEXIST，调用方按fail-closed处理）；
 * EACCES/ENOSPC/EROFS/其他=CRITICAL + unsafe_marker_write_failed。
 */
export function createUnsafeMarker(markerFile: string, marker: UnsafeMarker, log: (s: string) => void): MarkerWriteResult {
  try {
    fs.writeFileSync(markerFile, JSON.stringify(marker), { flag: "wx" });
    return { ok: true };
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code ?? "UNKNOWN";
    if (code === "EEXIST") {
      log(`[CRITICAL] unsafe标记已存在（保留已有现场，不覆盖）: ${markerFile}`);
      return { ok: false, code: "EEXIST" };
    }
    log(`[CRITICAL] unsafe_marker_write_failed：标记创建失败（code=${code}）${markerFile}`);
    return { ok: false, code };
  }
}

/** 临时文件+rename 原子更新标记（同目录保证同文件系统rename原子性） */
export function updateUnsafeMarker(markerFile: string, patch: Partial<UnsafeMarker>, log: (s: string) => void): MarkerWriteResult {
  const tmp = `${markerFile}.tmp.${process.pid}`; // 明确路径，catch 可访问；禁止通配符
  try {
    const cur = JSON.parse(fs.readFileSync(markerFile, "utf-8")) as UnsafeMarker;
    const next: UnsafeMarker = { ...cur, ...patch, updatedAt: new Date().toISOString() };
    fs.writeFileSync(tmp, JSON.stringify(next));
    fs.renameSync(tmp, markerFile);
    return { ok: true };
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code ?? "UNKNOWN";
    log(`[CRITICAL] unsafe_marker_write_failed：标记更新失败（code=${code}）${markerFile}`);
    // best-effort 清理本次创建的 tmp（只删这一个明确路径；失败仅告警，绝不动正式标记）
    try {
      if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
    } catch (e2) {
      log(`[告警] tmp清理失败（code=${(e2 as NodeJS.ErrnoException)?.code ?? "?"}），残留 ${tmp}`);
    }
    return { ok: false, code };
  }
}

export interface MarkerCleanupResult { removedOrAbsent: boolean; errorCode?: string; }

/**
 * 仅在子进程退出已确认（真实exit事件或PID明确dead）后删除；只删本进程创建的标记。
 * 返回明确结果：本来不存在/成功删除=true；归属他人/不可解析/unlink失败=false+错误码。
 * 调用方只有 removedOrAbsent=true 才允许宣称标记已清理。
 */
export function removeUnsafeMarkerOwned(markerFile: string, log: (s: string) => void): MarkerCleanupResult {
  if (!fs.existsSync(markerFile)) return { removedOrAbsent: true };
  let m: UnsafeMarker | null = null;
  try {
    m = JSON.parse(fs.readFileSync(markerFile, "utf-8")) as UnsafeMarker;
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code ?? "UNPARSEABLE";
    log(`[告警] unsafe标记不可解析（${code}），不删除 ${markerFile}`);
    return { removedOrAbsent: false, errorCode: "UNPARSEABLE" };
  }
  if (!m || m.parentPid !== process.pid) {
    log(`[告警] unsafe标记归属其他进程（parentPid=${m?.parentPid ?? "?"}），不删除`);
    return { removedOrAbsent: false, errorCode: "NOT_OWNER" };
  }
  try {
    fs.unlinkSync(markerFile);
    return { removedOrAbsent: true };
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code ?? "UNKNOWN";
    log(`[CRITICAL] unsafe标记删除失败（code=${code}）——标记仍在盘上，不得宣称已清理 ${markerFile}`);
    return { removedOrAbsent: false, errorCode: code };
  }
}

function unsafeManualSteps(markerFile: string, lockFile: string): string {
  return `人工处置步骤：1) cat ${markerFile} 核查 unsafeChildPid/stage/date/state；` +
    `2) ps 确认该进程（及其可能的子进程）确已不存在，仍存活则先人工 kill 并确认数据库无长事务残留；` +
    `3) 对照 SUMMARY_JSON dirtyDates 检查该 stage+date 是否需获批后手动单日重跑；` +
    `4) 确认后手动删除 ${markerFile} 与残留主锁 ${lockFile}（或等主机重启 /tmp 自清）；` +
    `5) 先确认主锁、cleanup锁与unsafe标记已按审批处理，再执行 dry-run 验证参数与任务计划` +
    `（dry-run 不获取锁；真正的锁获取只能在获批 --execute 时验证）`;
}

/**
 * unsafe 标记检查：存在即 fail-closed（优先级高于主锁判断）。
 * 不可解析/缺PID/alive/unknown/dead 全部拒绝——dead 也拒绝（防PID复用与错误自动恢复），
 * 且任何情况下不自动删除标记。
 */
function unsafeMarkerBlocks(lockFile: string, log: (s: string) => void, context = "入口"): boolean {
  const markerFile = `${lockFile}${UNSAFE_SUFFIX}`;
  if (!fs.existsSync(markerFile)) return false;
  let detail = "内容不可解析";
  try {
    const m = JSON.parse(fs.readFileSync(markerFile, "utf-8")) as UnsafeMarker;
    detail = Number.isInteger(m?.unsafeChildPid)
      ? `state=${m.state ?? "?"} unsafeChildPid=${m.unsafeChildPid} pid状态=${pidState(m.unsafeChildPid as number)} stage=${m.stage ?? "?"} date=${m.date ?? "?"} taskRunId=${m.taskRunId ?? "?"}`
      : `state=${(() => { try { return (JSON.parse(fs.readFileSync(markerFile, "utf-8")) as UnsafeMarker).state ?? "?"; } catch { return "?"; } })()} unsafeChildPid 缺失/为null（可能在starting阶段父进程崩溃）`;
  } catch { /* 保持"内容不可解析" */ }
  log(`[CRITICAL] 存在活动子进程标记（检查点=${context}，${detail}）——fail-closed 拒绝，不自动删除。${unsafeManualSteps(markerFile, lockFile)}`);
  return true;
}

export interface LockReleaseResult { releasedOrAbsent: boolean; errorCode?: string; }

/**
 * 主锁释放（结果必须真实）：不存在/归属本进程且删除成功=true；
 * 归属他人=NOT_OWNER、不可解析=UNPARSEABLE、unlink失败=真实错误码——均为 false，
 * 调用方不得在 false 时宣称"释放成功"。
 */
export function releaseLock(lockFile: string): LockReleaseResult {
  if (!fs.existsSync(lockFile)) return { releasedOrAbsent: true };
  let cur: LockContent | null = null;
  try {
    cur = JSON.parse(fs.readFileSync(lockFile, "utf-8")) as LockContent;
  } catch {
    console.log(`[告警] 主锁不可解析，不删除 ${lockFile}`);
    return { releasedOrAbsent: false, errorCode: "UNPARSEABLE" };
  }
  if (!cur || cur.pid !== process.pid) {
    return { releasedOrAbsent: false, errorCode: "NOT_OWNER" };
  }
  try {
    fs.unlinkSync(lockFile);
    return { releasedOrAbsent: true };
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code ?? "UNKNOWN";
    console.log(`[CRITICAL] 主锁删除失败（code=${code}）——主锁仍在盘上 ${lockFile}，不得宣称释放成功`);
    return { releasedOrAbsent: false, errorCode: code };
  }
}

const sleepMs = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

/**
 * 陈旧主锁的清理与接管：必须先原子获得独立 cleanup 互斥锁。
 * 获得后重读主锁并重新判定；仅 PID 明确 dead、或 alive 且 cmdline 明确 nomatch
 * 才允许删除。未获得 cleanup 锁的进程等待后重试主锁一次，绝不自行 unlink。
 */
async function cleanupAndTakeover(lockFile: string, taskRunId: string, log: (s: string) => void): Promise<boolean> {
  const cleanupFile = `${lockFile}.cleanup`;
  const tryMain = (): boolean => writeLockAtomic(lockFile, taskRunId);

  if (!writeLockAtomic(cleanupFile, taskRunId)) {
    // cleanup 锁已存在——★fail-closed：只要存在就绝不自动删除
    //（自动删除"持有者已死"的残留 cleanup 锁存在双进程互删竞态：两实例同时判死，
    //  后者会删掉前者刚创建的新 cleanup 锁。文件锁无原子所有权转移手段，故封死。）
    const c = readLockFile(cleanupFile);
    if (c && pidState(c.pid) === "alive") {
      // 他人正在清理 → 等待后只重试主锁，不得 unlink
      log("[信息] 另一实例正在处理陈旧锁——等待150ms后重试主锁");
      await sleepMs(150);
      if (tryMain()) {
        if (unsafeMarkerBlocks(lockFile, log, "重试建锁后复查")) { releaseLock(lockFile); return false; }
        return true;
      }
      log("[锁冲突] 主锁仍被占用——退出");
      return false;
    }
    // 持有者 dead/unknown/不可解析：一律保守拒绝并给出人工处置指引
    log(`[告警] 残留 cleanup 锁存在（${cleanupFile}，持有者${c ? `pid=${c.pid} 状态=${pidState(c.pid)}` : "内容不可解析"}）——` +
        "fail-closed 不自动删除。请人工核查：确认无 backfillDailyChain 进程存活后手动删除该文件" +
        "（或等待主机重启由 /tmp 自然清理）。本次按锁冲突退出");
    return false;
  }

  try {
    // ★持有 cleanup 锁：先复查活动子进程标记（删旧主锁前）
    if (unsafeMarkerBlocks(lockFile, log, "cleanup临界区删旧锁前")) return false;
    // 重读主锁并重新判定（判定与清理在同一互斥段内，杜绝互删）
    if (!fs.existsSync(lockFile)) {
      if (!tryMain()) return false;
      if (unsafeMarkerBlocks(lockFile, log, "cleanup建锁后复查")) { releaseLock(lockFile); return false; }
      return true;
    }
    const cur = readLockFile(lockFile);
    if (!cur) {
      log("[告警] cleanup互斥段内主锁不可解析——保守退出，不删除");
      return false;
    }
    const st = pidState(cur.pid);
    const evidence = st === "dead" || (st === "alive" && pidCmdlineCheck(cur.pid, LOCK_NEEDLE) === "nomatch");
    if (!evidence) {
      log(`[信息] cleanup复判：主锁持有者${st === "alive" ? "有效存活" : "状态不明"}——不清理，按锁冲突退出`);
      return false;
    }
    log(st === "dead"
      ? "[信息] cleanup复判确认：持有进程已不存在（明确dead），清理后接管"
      : "[告警] cleanup复判确认：PID存活但命令明确不匹配（PID复用），清理后接管");
    try { fs.unlinkSync(lockFile); } catch { /* 竞态：互斥段内不应发生 */ }
    if (!tryMain()) {
      log("[告警] 清理后原子重建失败——按锁冲突退出");
      return false;
    }
    // ★cleanup 建新锁后复查标记；命中只释放自己的新锁
    if (unsafeMarkerBlocks(lockFile, log, "cleanup建锁后复查")) {
      releaseLock(lockFile);
      return false;
    }
    return true;
  } finally {
    try {
      const cc = readLockFile(cleanupFile);
      if (cc && cc.pid === process.pid) fs.unlinkSync(cleanupFile);
    } catch { /* 尽量释放 */ }
  }
}

export async function acquireLock(
  lockFile: string,
  taskRunId: string,
  log: (s: string) => void,
  testHooks?: { afterEntryCheck?: () => void }, // 仅测试注入（TOCTOU场景构造）
): Promise<boolean> {
  // ★第一步：活动子进程标记检查（优先级高于主锁判断）
  if (unsafeMarkerBlocks(lockFile, log, "入口")) return false;
  testHooks?.afterEntryCheck?.();

  // 直接建锁成功后必须复查（防"入口检查后他进程写入标记"的TOCTOU）：
  // 命中只释放自己刚建的主锁，不删标记
  if (writeLockAtomic(lockFile, taskRunId)) {
    if (unsafeMarkerBlocks(lockFile, log, "建锁后复查")) {
      releaseLock(lockFile); // 只释放本进程自己刚创建的主锁
      return false;
    }
    return true;
  }

  // 主锁已存在：读取（解析失败=可能写入中，75ms后重读一次；仍失败保守拒绝不删除）
  let old = readLockFile(lockFile);
  if (!old) {
    await sleepMs(75);
    old = readLockFile(lockFile);
    if (!old) {
      if (!fs.existsSync(lockFile) && writeLockAtomic(lockFile, taskRunId)) {
        if (unsafeMarkerBlocks(lockFile, log, "重读建锁后复查")) { releaseLock(lockFile); return false; }
        return true;
      }
      log(`[告警] 锁文件存在但内容无法解析（可能正在写入中）——保守按锁冲突处理，不删除 ${lockFile}`);
      return false;
    }
  }

  const st = pidState(old.pid);
  if (st === "alive") {
    const c = pidCmdlineCheck(old.pid, LOCK_NEEDLE);
    if (c === "match" || c === "unknown") {
      if (c === "unknown") log(`[告警] 锁持有者 pid=${old.pid} 存活但 cmdline 读取失败——保守按有效锁处理，不删除锁`);
      const ageMs = Date.now() - Date.parse(old.startedAt || "");
      if (Number.isFinite(ageMs) && ageMs > LOCK_STALE_WARN_MS) {
        log(`[告警] 锁龄已超过24小时（持有者 pid=${old.pid} 仍存活）——仅告警，不删除存活的有效进程锁`);
      }
      log(`[锁冲突] 已有 backfillDailyChain 实例运行中（taskRunId=${old.taskRunId ?? "?"}），本次退出`);
      return false;
    }
    // alive + 明确 nomatch → PID复用，陈旧候选（经 cleanup 互斥清理）
  } else if (st === "unknown") {
    log(`[告警] 锁持有者 pid=${old.pid} 状态未知（EPERM等）——保守按有效锁处理，不删除锁`);
    return false;
  }
  // st === "dead" 或 alive+nomatch → 走 cleanup 互斥清理
  return cleanupAndTakeover(lockFile, taskRunId, log);
}

// ── 子任务执行 ────────────────────────────────────────────────────────
export interface TaskResult {
  exitCode: number | null;
  signal: string | null;
  timedOut: boolean;
  exitConfirmed: boolean;  // true=收到exit事件或PID明确dead；false=未确认（可能仍存活）
  pid?: number;
  startedAt: string;
  finishedAt: string;
  durationSeconds: number;
}

/** runner→编排层事件（标记生命周期驱动）：spawn成功报PID；开始终止流程时通知 */
export interface RunnerEvents {
  onSpawn?: (pid: number | undefined) => void;
  onTerminating?: () => void;
}

export type TaskRunner = (entry: string, args: string[], timeoutMs: number, events?: RunnerEvents) => Promise<TaskResult>;

// ── 活动子进程登记（外部信号终止用） ─────────────────────────────────
export interface KillableChild {
  pid?: number;
  kill(signal?: NodeJS.Signals): boolean;
  once(event: "exit", listener: (...args: unknown[]) => void): unknown;
}

let activeChild: KillableChild | null = null;
export function setActiveChildForTest(c: KillableChild | null): void { activeChild = c; }

// ── 全局停止标志 ──────────────────────────────────────────────────────
export interface ShutdownRef { requested: boolean; signal: string | null; }
const globalShutdown: ShutdownRef = { requested: false, signal: null };
export function getGlobalShutdownRef(): ShutdownRef { return globalShutdown; }

export interface TerminationOutcome {
  had: boolean;
  confirmedExited: boolean;
  pid?: number;
}

/**
 * kill 调用封装：try/catch + 返回值检查 + ESRCH/EPERM/未知区分。
 * 返回 "sent"=信号已送出；"confirmed_dead"=明确证实进程不存在；"unconfirmed"=未证实。
 */
function tryKill(child: KillableChild, sig: NodeJS.Signals, log: (s: string) => void): "sent" | "confirmed_dead" | "unconfirmed" {
  const pid = child.pid;
  try {
    const ok = child.kill(sig);
    if (ok) return "sent";
    // kill 返回 false：信号未送出——核验三态
    if (pid !== undefined && pidState(pid) === "dead") return "confirmed_dead";
    log(`[告警] ${sig} 发送失败（kill返回false）且无法证实 pid=${pid ?? "?"} 已消亡——按未证实处理`);
    return "unconfirmed";
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code;
    if (code === "ESRCH") return "confirmed_dead";
    if (pid !== undefined && pidState(pid) === "dead") return "confirmed_dead";
    log(`[CRITICAL] kill(${sig}) 异常（code=${code ?? "unknown"}）且无法证实子进程(pid=${pid ?? "?"})已退出——按未确认处理`);
    return "unconfirmed";
  }
}

/**
 * 终止当前活动子任务：SIGTERM → 宽限 → SIGKILL → 最多再等 hardWaitMs。
 * confirmedExited 仅在收到 exit 事件或 PID 明确 dead 时为 true。
 */
export function terminateActiveTask(
  graceMs: number = SIGKILL_GRACE_MS,
  log: (s: string) => void = console.log,
  hardWaitMs: number = POST_KILL_WAIT_MS,
): Promise<TerminationOutcome> {
  const child = activeChild;
  // ★第13版回归修复（恢复第8版设计）：不得在此立即清空 activeChild——
  //   仅在真实exit事件 / PID明确dead / spawn前失败 时清空；
  //   exitConfirmed=false 时必须保留句柄，后续 SIGTERM/SIGINT 仍能找到并再次终止
  if (!child) return Promise.resolve({ had: false, confirmedExited: true });
  const pid = child.pid;
  return new Promise<TerminationOutcome>((resolve) => {
    let done = false;
    let killTimer: NodeJS.Timeout | null = null;
    let hardTimer: NodeJS.Timeout | null = null;
    // 计时器不得 unref——事件循环只剩计时器时 unref 会让进程在 SIGKILL 前退出
    const finish = (confirmed: boolean) => {
      if (done) return;
      done = true;
      if (killTimer) clearTimeout(killTimer);
      if (hardTimer) clearTimeout(hardTimer);
      if (confirmed) {
        if (activeChild === child) activeChild = null; // ★仅确认退出后清空
      } else {
        log(`[CRITICAL] 子进程(pid=${pid ?? "?"})退出未获确认——按仍可能存活处理，activeChild 保留以供再次终止`);
      }
      resolve({ had: true, confirmedExited: confirmed, pid });
    };
    child.once("exit", () => finish(true));
    log(`[信号] 向活动子任务发送 SIGTERM（pid=${pid ?? "?"}）`);
    const r1 = tryKill(child, "SIGTERM", log);
    if (r1 === "confirmed_dead") { finish(true); return; }
    if (r1 === "unconfirmed") { finish(false); return; }
    killTimer = setTimeout(() => {
      log(`[信号] 宽限 ${Math.round(graceMs / 1000)}s 未退出，发送 SIGKILL（pid=${pid ?? "?"}）`);
      const r2 = tryKill(child, "SIGKILL", log);
      if (r2 === "confirmed_dead") { finish(true); return; }
      if (r2 === "unconfirmed") { finish(false); return; }
    }, graceMs);
    hardTimer = setTimeout(() => {
      const confirmed = pid !== undefined && pidState(pid) === "dead";
      finish(confirmed);
    }, graceMs + hardWaitMs);
  });
}

// 最近一次终止结果（main finally 与致命兜底共用，禁止绕过安全判定）
export const terminationState: { outcome: TerminationOutcome | null } = { outcome: null };

/**
 * 锁的安全释放：终止未确认时——PID 三态核验，仅明确 dead 才释放；
 * alive/unknown/无PID → CRITICAL + 保守不释放。返回是否已释放。
 */
export function safeReleaseLock(lockFile: string, termination: TerminationOutcome | null, log: (s: string) => void): LockReleaseResult {
  if (termination && termination.had && !termination.confirmedExited) {
    const st: PidState = termination.pid !== undefined ? pidState(termination.pid) : "unknown";
    if (st !== "dead") {
      log(`[CRITICAL] 子进程(pid=${termination.pid ?? "?"})退出未确认且状态=${st}——保守不释放锁，需人工核查后处理 ${lockFile}`);
      return { releasedOrAbsent: false, errorCode: "CHILD_UNCONFIRMED" }; // 有意保守持锁（非释放失败）
    }
    log("[告警] 子进程退出事件缺失，但核验 PID 明确不存在（dead）——释放锁");
  }
  return releaseLock(lockFile); // 真实结果向上传播
}

/** 致命错误兜底释放：复用 terminationState 同一份终止结果，禁止直接 unlink；结果同样真实 */
export function fatalReleaseLock(lockFile: string, log: (s: string) => void = console.log): LockReleaseResult {
  return safeReleaseLock(lockFile, terminationState.outcome, log);
}

// ── defaultRunner：真实子任务执行（超时闭环，禁止悬挂） ───────────────
/** 仅测试注入：替换可执行路径/入口、拿到子进程句柄（用于真实路径场景构造） */
export interface RunnerTestHooks {
  execPathOverride?: string;
  tsNodeBinOverride?: string;
  onSpawned?: (child: import("child_process").ChildProcess) => void;
}

export function makeRunner(hooks?: RunnerTestHooks): TaskRunner {
  return (entry, args, timeoutMs, events) => new Promise((resolve) => {
    const startedMs = Date.now();
    const tsNodeBin = hooks?.tsNodeBinOverride ?? require.resolve("ts-node/dist/bin.js");
    const child = spawn(hooks?.execPathOverride ?? process.execPath, [tsNodeBin, entry, ...args], {
      cwd: path.resolve(__dirname, ".."),
      env: process.env,
      shell: false,
      stdio: ["ignore", "inherit", "inherit"],
    });
    activeChild = child;
    const pid = child.pid;
    let spawned = false;
    let onSpawnFired = false; // once guard：spawn()返回即触发 + spawn事件fallback，至多一次
    const fireSpawn = () => {
      if (onSpawnFired) return;
      if (child.pid === undefined) return; // spawn失败无PID：不得调用 onSpawn
      onSpawnFired = true;
      spawned = true;
      hooks?.onSpawned?.(child);
      events?.onSpawn?.(child.pid); // 标记原子更新为 running+真实PID 由编排层执行
    };
    fireSpawn();                    // spawn() 返回后 pid 通常已可用——立即触发，最小化无PID窗口
    child.once("spawn", fireSpawn); // fallback（guard 防重复）
    let timedOut = false;
    let settled = false;
    let termTimer: NodeJS.Timeout | null = null;
    let killTimer: NodeJS.Timeout | null = null;
    let hardTimer: NodeJS.Timeout | null = null;

    const settle = (partial: Pick<TaskResult, "exitCode" | "signal" | "exitConfirmed">) => {
      if (settled) return;
      settled = true;
      if (termTimer) clearTimeout(termTimer);
      if (killTimer) clearTimeout(killTimer);
      if (hardTimer) clearTimeout(hardTimer);
      // ★退出未确认时不得清空 activeChild：后续 SIGINT/SIGTERM 仍须能找到并终止
      //   该危险子进程；仅 exitConfirmed=true（真实exit/PID明确dead/spawn前失败）才清
      if (partial.exitConfirmed && activeChild === child) activeChild = null;
      const finishedMs = Date.now();
      resolve({
        ...partial,
        timedOut,
        pid,
        startedAt: new Date(startedMs).toISOString(),
        finishedAt: new Date(finishedMs).toISOString(),
        durationSeconds: Number(((finishedMs - startedMs) / 1000).toFixed(1)),
      });
    };

    child.on("exit", (code, signal) => {
      // 真实 exit 事件：无论 runner Promise 是否已 settle，都必须清理 activeChild
      if (activeChild === child) activeChild = null;
      settle({ exitCode: code, signal: signal ?? null, exitConfirmed: true });
    });
    // error 事件语义不只是"启动失败"：kill 失败等场景也走此事件，且之后不一定有 exit。
    // 必须按 spawned 状态 + PID 三态核验，不得无条件 exitConfirmed=true。
    child.on("error", (e) => {
      const code = (e as NodeJS.ErrnoException)?.code;
      if (!spawned && pid === undefined) {
        console.log(`  [错误] 子进程启动失败(code=${code ?? "?"}): ${e.message}`);
        settle({ exitCode: 1, signal: null, exitConfirmed: true }); // 未曾产生进程
        return;
      }
      const st: PidState = pid !== undefined ? pidState(pid) : "unknown";
      if (st === "dead") {
        console.log(`  [告警] 子进程 error 事件(code=${code ?? "?"})，核验 PID 已消亡（dead）——按已退出处理`);
        settle({ exitCode: null, signal: null, exitConfirmed: true });
      } else {
        console.log(`  [CRITICAL] 子进程 error 事件(code=${code ?? "?"})且 PID(${pid ?? "?"}) 状态=${st}——按退出未确认处理，全链将中止并保守持锁`);
        settle({ exitCode: null, signal: null, exitConfirmed: false });
      }
    });

    termTimer = setTimeout(() => {
      timedOut = true;
      events?.onTerminating?.(); // 标记 state=terminating 由编排层执行
      console.log(`  [超时] ${entry} ${args.join(" ")} 超过 ${Math.round(timeoutMs / 1000)}s，发送 SIGTERM（pid=${pid ?? "?"}）`);
      const r1 = tryKill(child, "SIGTERM", (s) => console.log(`  ${s}`));
      if (r1 === "confirmed_dead") { settle({ exitCode: null, signal: "SIGTERM", exitConfirmed: true }); return; }
      killTimer = setTimeout(() => {
        console.log(`  [超时] SIGTERM ${SIGKILL_GRACE_MS / 1000}s 未退出，发送 SIGKILL（pid=${pid ?? "?"}）`);
        const r2 = tryKill(child, "SIGKILL", (s) => console.log(`  ${s}`));
        if (r2 === "confirmed_dead") { settle({ exitCode: null, signal: "SIGKILL", exitConfirmed: true }); return; }
        // SIGKILL 后最多再等 POST_KILL_WAIT_MS，仍无 exit 事件也必须 resolve（禁止悬挂）
        hardTimer = setTimeout(() => {
          const confirmed = pid !== undefined && pidState(pid) === "dead";
          if (!confirmed) {
            console.log(`  [CRITICAL] SIGKILL 后 ${POST_KILL_WAIT_MS / 1000}s 仍无退出事件且无法证实 pid=${pid ?? "?"} 已消亡——按未确认存活处理`);
          }
          settle({ exitCode: null, signal: "SIGKILL", exitConfirmed: confirmed });
        }, POST_KILL_WAIT_MS);
      }, SIGKILL_GRACE_MS);
    }, timeoutMs);
  });
}

export const defaultRunner: TaskRunner = makeRunner();

// ── 编排主逻辑 ────────────────────────────────────────────────────────
export interface ChainDeps {
  runner: TaskRunner;
  nowFn: () => number;
  sleepFn: (ms: number) => Promise<void>;
  log: (s: string) => void;
  shutdown?: ShutdownRef;
  /** unsafe 隔离标记文件路径（生产=主锁路径+.unsafe；测试注入临时路径） */
  unsafeMarkerFile?: string;
}

export interface DirtyDate { stage: StageId; date: string; reason: string; }

export interface ChainSummary {
  taskRunId: string;
  mode: "dry-run" | "execute";
  startDate: string;
  endDate: string;
  dates: string[];
  deadline: string | null;
  startedAt: string;
  finishedAt: string;
  durationSeconds: number;
  fact: { success: string[]; failed: string[] };
  rawSales: { success: string[]; failed: string[]; skippedByFactFailure: string[] };
  orderProfit: { success: string[]; failed: string[]; skippedByFactFailure: string[] };
  dirtyDates: DirtyDate[];
  deadlineAborted: boolean;
  externalSignalAborted: boolean;
  externalSignal: string | null;
  childExitUnconfirmed: boolean;
  unsafeChildPid: number | null;
  unsafeMarkerCreated: boolean;
  unsafeMarkerPath: string | null;
  unsafeMarkerState: UnsafeMarkerState | null;
  unsafeMarkerWriteFailed: boolean;
  unsafeMarkerErrorCode: string | null;
  unsafeMarkerCleanupFailed: boolean;
  unsafeMarkerCleanupErrorCode: string | null;
  fatalError: boolean;
  fatalErrorMessage: string | null;
  lockReleaseFailed: boolean;
  lockReleaseErrorCode: string | null;
  lockStillPresent: boolean;
  lockConflict: boolean;
  status: "success" | "partial_failed" | "failed" | "dry_run";
}

function emptySummary(taskRunId: string, mode: "dry-run" | "execute", cfg: ParsedConfig, startedMs: number): ChainSummary {
  return {
    taskRunId, mode,
    startDate: cfg.dates[0], endDate: cfg.dates[cfg.dates.length - 1], dates: [...cfg.dates],
    deadline: cfg.deadlineHHmm,
    startedAt: new Date(startedMs).toISOString(), finishedAt: "", durationSeconds: 0,
    fact: { success: [], failed: [] },
    rawSales: { success: [], failed: [], skippedByFactFailure: [] },
    orderProfit: { success: [], failed: [], skippedByFactFailure: [] },
    dirtyDates: [],
    deadlineAborted: false,
    externalSignalAborted: false, externalSignal: null,
    childExitUnconfirmed: false, unsafeChildPid: null,
    unsafeMarkerCreated: false, unsafeMarkerPath: null,
    unsafeMarkerState: null, unsafeMarkerWriteFailed: false, unsafeMarkerErrorCode: null,
    unsafeMarkerCleanupFailed: false, unsafeMarkerCleanupErrorCode: null,
    fatalError: false, fatalErrorMessage: null,
    lockReleaseFailed: false, lockReleaseErrorCode: null, lockStillPresent: false,
    lockConflict: false,
    status: "success",
  };
}

export async function runChain(cfg: ParsedConfig, taskRunId: string, deps: ChainDeps): Promise<ChainSummary> {
  const { runner, nowFn, sleepFn, log } = deps;
  const startedMs = nowFn();
  const summary = emptySummary(taskRunId, cfg.mode, cfg, startedMs);

  const shutdown = deps.shutdown ?? globalShutdown;
  const checkShutdown = (where: string): boolean => {
    if (!shutdown.requested) return false;
    if (!summary.externalSignalAborted) {
      summary.externalSignalAborted = true;
      summary.externalSignal = shutdown.signal;
      log(`  [信号] 检测到外部停止请求(${shutdown.signal ?? "?"}, ${where})——禁止启动新子任务，中止剩余全链`);
    }
    return true;
  };

  const deadlineMs = cfg.deadlineHHmm ? deadlineToMs(cfg.deadlineHHmm, startedMs) : Number.POSITIVE_INFINITY;
  const taskTimeoutMs = cfg.taskTimeoutMinutes * 60 * 1000;
  const factFailed = new Set<string>();

  outer:
  for (const stage of STAGES) {
    if (checkShutdown("进入阶段前")) break;
    log(`\n===== 阶段 ${stage.label} =====`);
    for (let i = 0; i < cfg.dates.length; i++) {
      const date = cfg.dates[i];
      const bucket = summary[stage.id];

      if (checkShutdown("任务启动前")) break outer;

      if (stage.id !== "fact" && factFailed.has(date)) {
        (bucket as { skippedByFactFailure: string[] }).skippedByFactFailure.push(date);
        log(`  [跳过] ${date}：该日 FACT 失败，跳过 ${stage.label}`);
        continue;
      }

      const now = nowFn();
      if (now >= deadlineMs) {
        summary.deadlineAborted = true;
        log(`  [死线] 已到 ${cfg.deadlineHHmm}（Asia/Shanghai），中止剩余全部任务`);
        break outer;
      }
      const effectiveTimeout = Math.min(taskTimeoutMs, deadlineMs - now);

      const args = stage.buildArgs(date);
      const markerFile = deps.unsafeMarkerFile;

      // ★spawn 前：原子创建活动子进程标记（state=starting, PID=null）。
      //   创建失败（含EEXIST）=禁止spawn、任务失败、全链中止（fail-closed）
      if (markerFile) {
        const cr = createUnsafeMarker(markerFile, {
          taskRunId, parentPid: process.pid, unsafeChildPid: null,
          stage: stage.id, date, state: "starting", createdAt: new Date().toISOString(),
        }, log);
        if (!cr.ok) {
          summary.unsafeMarkerWriteFailed = true;
          summary.unsafeMarkerErrorCode = cr.code;
          summary.unsafeMarkerPath = markerFile;
          bucket.failed.push(date);
          if (stage.id === "fact") factFailed.add(date);
          log(`  [CRITICAL] ${date} ${stage.label} 标记创建失败（${cr.code}）——禁止spawn，全链中止。${unsafeManualSteps(markerFile, markerFile.replace(/\.unsafe$/, ""))}`);
          break outer;
        }
        summary.unsafeMarkerCreated = true;
        summary.unsafeMarkerPath = markerFile;
        summary.unsafeMarkerState = "starting";
      }

      // spawn后标记更新失败 → 立即终止该子进程（异步触发，终止结果由runner闭环）
      let markerUpdateFailed: string | null = null;
      const events: RunnerEvents = {
        onSpawn: (pid) => {
          if (!markerFile) return;
          const ur = updateUnsafeMarker(markerFile, { unsafeChildPid: pid ?? null, state: "running" }, log);
          if (ur.ok) {
            summary.unsafeMarkerState = "running";
          } else {
            markerUpdateFailed = ur.code;
            log(`  [CRITICAL] spawn后标记更新失败（${ur.code}）——立即终止该子进程`);
            void terminateActiveTask(SIGKILL_GRACE_MS, log);
          }
        },
        onTerminating: () => {
          if (!markerFile) return;
          if (updateUnsafeMarker(markerFile, { state: "terminating" }, log).ok) {
            summary.unsafeMarkerState = "terminating";
          }
        },
      };

      log(`  ▶ ${date} ${stage.entry} ${args.join(" ")}（超时上限 ${Math.round(effectiveTimeout / 1000)}s）`);
      const r = await runner(stage.entry, args, effectiveTimeout, events);
      const ok = r.exitCode === 0 && !r.timedOut && r.exitConfirmed && markerUpdateFailed === null;

      // ★仅在退出已确认（真实exit事件或PID明确dead）后才删除标记；
      //   只有确认删除/本来不存在才置 state=null——摘要必须与磁盘实际一致
      let cleanupFailedNow = false;
      if (markerFile && r.exitConfirmed) {
        const cr = removeUnsafeMarkerOwned(markerFile, log);
        if (cr.removedOrAbsent) {
          summary.unsafeMarkerState = null;
        } else {
          cleanupFailedNow = true;
          summary.unsafeMarkerCleanupFailed = true;
          summary.unsafeMarkerCleanupErrorCode = cr.errorCode ?? null;
          log(`  [CRITICAL] 标记清理失败（${cr.errorCode ?? "?"}）——标记仍在盘上（${markerFile}），unsafeMarkerState 保持不变`);
        }
      }
      if (markerUpdateFailed !== null) {
        summary.unsafeMarkerWriteFailed = true;
        summary.unsafeMarkerErrorCode = markerUpdateFailed;
      }
      log(`  ${ok ? "✅" : "❌"} ${date} exit=${r.exitCode} signal=${r.signal ?? "-"} timeout=${r.timedOut} exitConfirmed=${r.exitConfirmed} 耗时=${r.durationSeconds}s`);

      if (ok) {
        bucket.success.push(date);
      } else {
        bucket.failed.push(date);
        if (stage.id === "fact") factFailed.add(date);
        if (stage.rewriteStyle) {
          const reason = r.timedOut
            ? "timeout_killed_during_rewrite"
            : r.signal
              ? "signal_exit_during_rewrite"
              : "nonzero_exit_during_rewrite";
          summary.dirtyDates.push({ stage: stage.id, date, reason });
          log(`  [脏数据日] ${date} ${stage.label} 非成功退出（${reason}），标记 dirtyDates（由次日回溯覆盖或获批后手动单日重跑修复）`);
        }
        // ★退出未确认：标记已在盘上（spawn前创建）——补全现场后立即中止整条编排
        if (!r.exitConfirmed) {
          summary.childExitUnconfirmed = true;
          summary.unsafeChildPid = r.pid ?? null;
          if (markerFile) {
            const ur = updateUnsafeMarker(markerFile, {
              unsafeChildPid: r.pid ?? null, state: "terminating", reason: "child_exit_unconfirmed",
            }, log);
            if (ur.ok) {
              summary.unsafeMarkerState = "terminating";
            } else {
              // 更新失败：保留原state，摘要不得与磁盘不一致
              summary.unsafeMarkerWriteFailed = true;
              summary.unsafeMarkerErrorCode = ur.code;
            }
            log(`  [CRITICAL] ${unsafeManualSteps(markerFile, markerFile.replace(/\.unsafe$/, ""))}`);
          } else {
            log("  [告警] 未配置 unsafeMarkerFile（测试注入场景）——生产路径必须配置");
          }
          log(`  [CRITICAL] ${date} ${stage.label} 子进程退出未确认（pid=${r.pid ?? "?"}）——立即中止整条编排，锁将保守不释放`);
          break outer;
        }
        // spawn后标记更新失败：子进程已被终止（退出已确认则标记已删）——全链中止
        if (markerUpdateFailed !== null) {
          log(`  [CRITICAL] ${date} ${stage.label} 标记更新失败（${markerUpdateFailed}）——子进程已终止，全链中止`);
          break outer;
        }
      }

      // ★基础设施清理失败：业务子任务结果已记账（成功仍留success清单），
      //   但编排整体必须failed——立即中止剩余全链，禁止启动下一任务
      if (cleanupFailedNow) {
        log(`  [CRITICAL] ${date} ${stage.label} 标记清理失败——基础设施清理失败，中止剩余全链（业务任务本身${ok ? "已成功" : "已失败"}）`);
        break outer;
      }

      if (checkShutdown("runner返回后")) break outer;

      // 日期间可中断等待：250ms 分片轮询 shutdown 与 deadline
      if (i < cfg.dates.length - 1 && cfg.intervalSeconds > 0) {
        const intervalMs = cfg.intervalSeconds * 1000;
        let waited = 0;
        let abortSleep: "shutdown" | "deadline" | null = null;
        while (waited < intervalMs) {
          if (checkShutdown("sleep中")) { abortSleep = "shutdown"; break; }
          if (nowFn() >= deadlineMs) {
            summary.deadlineAborted = true;
            log(`  [死线] sleep 中到达 ${cfg.deadlineHHmm}（Asia/Shanghai），立即结束等待并中止剩余全部任务`);
            abortSleep = "deadline";
            break;
          }
          const chunk = Math.min(SLEEP_CHECK_MS, intervalMs - waited);
          await sleepFn(chunk);
          waited += chunk;
        }
        if (abortSleep) break outer;
      }
    }
  }

  const finishedMs = nowFn();
  summary.finishedAt = new Date(finishedMs).toISOString();
  summary.durationSeconds = Number(((finishedMs - startedMs) / 1000).toFixed(1));
  summary.status = computeChainStatus(summary);
  return summary;
}

/** 最终状态判定（runChain 结束与 finalizeRun 收口共用同一公式） */
export function computeChainStatus(s: ChainSummary): ChainSummary["status"] {
  if (s.mode === "dry-run") return "dry_run";
  const anyFailed = s.fact.failed.length + s.rawSales.failed.length + s.orderProfit.failed.length > 0;
  const anySkipped = s.rawSales.skippedByFactFailure.length + s.orderProfit.skippedByFactFailure.length > 0;
  if (s.deadlineAborted || s.externalSignalAborted || s.childExitUnconfirmed
    || s.unsafeMarkerWriteFailed || s.unsafeMarkerCleanupFailed
    || s.fatalError || s.lockReleaseFailed || s.lockConflict) return "failed";
  if (anyFailed || anySkipped || s.dirtyDates.length > 0) return "partial_failed";
  return "success";
}

/**
 * ★统一收口（第11版）：SUMMARY_JSON 只能在本函数完成后输出。
 * 顺序：等待信号终止结果 → PID 最终三态复核 → 更新/创建/删除 unsafe 标记 →
 * 记录写入/清理结果 → safeReleaseLock 判定 → 磁盘一致性收口 → 重算最终 status。
 * 特别处理：最初未确认但收口时 PID 已明确 dead → 清理本进程标记、按 dead 放锁、
 * summary 不得再宣称存在危险子进程（不制造永久 unsafe 残留）。
 */
export async function finalizeRun(
  summary: ChainSummary | null,
  sigTerminationPromise: Promise<TerminationOutcome> | null,
  lockFile: string,
  markerFile: string,
  taskRunId: string,
  log: (s: string) => void,
): Promise<void> {
  const sigTermination = sigTerminationPromise ? await sigTerminationPromise : null;
  let effective: TerminationOutcome | null = null;

  const markCleanupResult = (cr: MarkerCleanupResult) => {
    if (!summary) return;
    if (cr.removedOrAbsent) {
      summary.unsafeMarkerState = null;
    } else {
      summary.unsafeMarkerCleanupFailed = true;
      summary.unsafeMarkerCleanupErrorCode = cr.errorCode ?? null;
    }
  };
  const ensureMarkerOnDisk = (pid: number | undefined) => {
    if (fs.existsSync(markerFile)) {
      const ur = updateUnsafeMarker(markerFile, { unsafeChildPid: pid ?? null, state: "terminating", reason: "child_exit_unconfirmed" }, log);
      if (summary) {
        if (ur.ok) summary.unsafeMarkerState = "terminating";
        else { summary.unsafeMarkerWriteFailed = true; summary.unsafeMarkerErrorCode = ur.code; }
      }
    } else {
      const cr = createUnsafeMarker(markerFile, {
        taskRunId, parentPid: process.pid, unsafeChildPid: pid ?? null,
        stage: "signal_termination", date: "-", state: "terminating",
        reason: "child_exit_unconfirmed", createdAt: new Date().toISOString(),
      }, log);
      if (summary) {
        if (cr.ok) { summary.unsafeMarkerCreated = true; summary.unsafeMarkerPath = markerFile; summary.unsafeMarkerState = "terminating"; }
        else if (cr.code !== "EEXIST") { summary.unsafeMarkerWriteFailed = true; summary.unsafeMarkerErrorCode = cr.code; }
      }
    }
  };

  if (sigTermination && sigTermination.had && !sigTermination.confirmedExited) {
    // 信号终止最初未确认 → 收口时 PID 最终三态复核
    const pid = sigTermination.pid;
    const st: PidState = pid !== undefined ? pidState(pid) : "unknown";
    if (st === "dead") {
      log(`[收口] 最初未确认的子进程(pid=${pid}) 最终复核=dead——危险已解除，清理本进程标记，按 dead 结果放锁`);
      markCleanupResult(removeUnsafeMarkerOwned(markerFile, log));
      if (summary) { summary.childExitUnconfirmed = false; summary.unsafeChildPid = null; }
      effective = { had: true, confirmedExited: true, pid };
    } else {
      log(`[收口] 子进程(pid=${pid ?? "?"}) 最终状态=${st}——unsafe 标记必须在盘、锁保守不释放`);
      ensureMarkerOnDisk(pid);
      if (summary) {
        summary.childExitUnconfirmed = true;
        summary.unsafeChildPid = pid ?? summary.unsafeChildPid;
      }
      log(`[CRITICAL] ${unsafeManualSteps(markerFile, lockFile)}`);
      effective = sigTermination;
    }
  } else if (sigTermination && sigTermination.had && sigTermination.confirmedExited) {
    log("[信号] 活动子任务已确认退出");
    if (summary && summary.childExitUnconfirmed) {
      // ★第14版：与早前记录的危险PID对账
      const recordedPid = summary.unsafeChildPid;
      if (recordedPid === null || recordedPid === undefined || sigTermination.pid === recordedPid) {
        // 同一危险子进程被确认终止（或summary未记录PID）→ 解除危险状态
        log(`[收口] 信号确认退出的子进程与记录的危险子进程一致（pid=${sigTermination.pid ?? "?"}）——解除危险状态`);
        summary.childExitUnconfirmed = false;
        summary.unsafeChildPid = null;
        markCleanupResult(removeUnsafeMarkerOwned(markerFile, log));
        effective = sigTermination;
      } else {
        // PID不一致：确认退出的并非记录的危险子进程——不得清除危险状态
        log(`[CRITICAL] PID_MISMATCH：信号确认退出 pid=${sigTermination.pid ?? "?"} 与记录的危险子进程 pid=${recordedPid} 不一致——不清除危险状态，保留标记与主锁`);
        ensureMarkerOnDisk(recordedPid);
        effective = { had: true, confirmedExited: false, pid: recordedPid };
      }
    } else {
      const cr = removeUnsafeMarkerOwned(markerFile, log);
      if (summary && cr.removedOrAbsent && !summary.unsafeMarkerCleanupFailed) summary.unsafeMarkerState = null;
      else if (summary && !cr.removedOrAbsent) markCleanupResult(cr);
      effective = sigTermination;
    }
  } else if (summary && summary.childExitUnconfirmed) {
    // 超时路径未确认 → 同样收口复核
    const pid = summary.unsafeChildPid ?? undefined;
    const st: PidState = pid !== undefined ? pidState(pid) : "unknown";
    if (st === "dead") {
      log(`[收口] 最初未确认的子进程(pid=${pid}) 最终复核=dead——危险已解除，清理本进程标记`);
      markCleanupResult(removeUnsafeMarkerOwned(markerFile, log));
      summary.childExitUnconfirmed = false;
      summary.unsafeChildPid = null;
      effective = { had: true, confirmedExited: true, pid };
    } else {
      log(`[收口] 子进程(pid=${pid ?? "?"}) 最终状态=${st}——unsafe 标记保留、锁保守不释放`);
      effective = { had: true, confirmedExited: false, pid };
    }
  }

  terminationState.outcome = effective;
  const rr = safeReleaseLock(lockFile, effective, log);
  if (summary && !rr.releasedOrAbsent && rr.errorCode !== "CHILD_UNCONFIRMED") {
    // 应释放但删除失败（CHILD_UNCONFIRMED=有意保守持锁，不算释放失败）
    summary.lockReleaseFailed = true;
    summary.lockReleaseErrorCode = rr.errorCode ?? null;
    log(`[CRITICAL] 主锁应释放但删除失败（${rr.errorCode ?? "?"}）——主锁仍在盘上，整体判 failed`);
  }

  // ★磁盘真值收口：summary 必须反映最终盘上状态
  if (summary) {
    summary.lockStillPresent = fs.existsSync(lockFile);
    if (fs.existsSync(markerFile)) {
      summary.unsafeMarkerPath = markerFile;
      try {
        const dm = JSON.parse(fs.readFileSync(markerFile, "utf-8")) as UnsafeMarker;
        if (dm.state) summary.unsafeMarkerState = dm.state;
      } catch { /* 不可解析：保留已知 state */ }
    } else {
      // 标记不存在=磁盘真值 state=null；unsafeMarkerPath 作为历史路径保留（交接包已注明）
      summary.unsafeMarkerState = null;
    }
    summary.status = computeChainStatus(summary);
  }
}

/** 致命错误消息脱敏：长token置换 + 长度上限200 */
function sanitizeFatalMessage(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  return m.replace(/[A-Za-z0-9+/_\-]{24,}/g, "[REDACTED]").slice(0, 200);
}

/**
 * ★execute 主流程（第12版导出，锁获取成功后调用）：
 * 先创建 fallback summary → runChain（同步抛异常/Promise reject 均被捕获，
 * fatalError 落 summary，不得让外层 main().catch 成为正常致命路径）→
 * 必然进入 finalizeRun 完成标记与锁收口 → 返回最终 summary（由调用方唯一输出）。
 */
export async function runExecute(
  cfg: ParsedConfig,
  taskRunId: string,
  lockFile: string,
  markerFile: string,
  deps: Omit<ChainDeps, "unsafeMarkerFile">,
  terminationHolder: { promise: Promise<TerminationOutcome> | null },
): Promise<ChainSummary> {
  let summary: ChainSummary = emptySummary(taskRunId, "execute", cfg, deps.nowFn()); // fallback
  try {
    summary = await runChain(cfg, taskRunId, { ...deps, unsafeMarkerFile: markerFile });
  } catch (e) {
    summary.fatalError = true;
    summary.fatalErrorMessage = sanitizeFatalMessage(e);
    deps.log(`[致命错误] ${summary.fatalErrorMessage}`);
  }
  await finalizeRun(summary, terminationHolder.promise, lockFile, markerFile, taskRunId, deps.log);
  return summary;
}

// ── dry-run 计划打印 ──────────────────────────────────────────────────
function printDryRunPlan(cfg: ParsedConfig, log: (s: string) => void): void {
  log("模式: dry-run（默认；--execute 才会真实执行）");
  log(`日期窗口: ${cfg.dates[0]} ~ ${cfg.dates[cfg.dates.length - 1]}（共 ${cfg.dates.length} 天，执行顺序旧→新）`);
  log(`死线: ${cfg.deadlineHHmm ?? "（dry-run 未指定；execute 必须显式传 --deadline）"}`);
  log(`日期间隔: ${cfg.intervalSeconds}s（250ms分片轮询，可被停止请求/死线打断） ｜ 单任务超时: ${cfg.taskTimeoutMinutes}min（实际取 min(该值, 距死线剩余)）`);
  let total = 0;
  for (const stage of STAGES) {
    log(`\n阶段 ${stage.label}:`);
    for (const d of cfg.dates) {
      log(`  npx ts-node ${stage.entry} ${stage.buildArgs(d).join(" ")}`);
      total++;
    }
  }
  log(`\n总任务数: ${total}`);
  log("[dry-run] 未启动任何子任务、未访问领星API、未写数据库、未获取锁。");
}

// ── CLI 入口 ──────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const log = (s: string) => console.log(s);
  const nowMs = Date.now();
  const taskRunId = `BFD-${new Date(nowMs).toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}-${Math.random().toString(36).slice(2, 6)}`;

  let cfg: ParsedConfig;
  try {
    cfg = parseConfig(process.argv.slice(2), nowMs);
  } catch (e) {
    console.log(`[错误] ${e instanceof Error ? e.message : String(e)}`);
    process.exitCode = 1;
    return;
  }

  log("=".repeat(64));
  log(`方案B 三层每日回溯编排 ｜ taskRunId=${taskRunId}`);
  log("=".repeat(64));

  if (cfg.mode === "dry-run") {
    printDryRunPlan(cfg, log);
    const summary = emptySummary(taskRunId, "dry-run", cfg, nowMs);
    summary.finishedAt = new Date().toISOString();
    summary.status = "dry_run";
    log(`\nSUMMARY_JSON=${JSON.stringify(summary)}`);
    return;
  }

  if (!(await acquireLock(LOCK_FILE, taskRunId, log))) {
    const summary = emptySummary(taskRunId, "execute", cfg, nowMs);
    summary.finishedAt = new Date().toISOString();
    summary.lockConflict = true;
    summary.status = "failed";
    log(`SUMMARY_JSON=${JSON.stringify(summary)}`);
    process.exitCode = 1;
    return;
  }

  // 外部信号：只置停止标志+终止活动子任务；锁由统一 finally 核验后释放
  const terminationHolder: { promise: Promise<TerminationOutcome> | null } = { promise: null };
  const shutdown = getGlobalShutdownRef();
  const onExternalSignal = (sig: string) => {
    if (shutdown.requested) {
      // ★第13版：重复信号不再忽略——若危险子进程句柄仍保留（上次终止未确认），
      //   必须能再次找到并终止（terminateActiveTask 无活动子任务时立即返回 had=false）
      log(`\n[信号] 再次收到 ${sig}：尝试再次终止残留子任务…`);
      terminationHolder.promise = terminateActiveTask(SIGKILL_GRACE_MS, log);
      return;
    }
    shutdown.requested = true;
    shutdown.signal = sig;
    log(`\n[信号] 收到 ${sig}：已置停止标志（禁止启动新子任务），正在终止活动子任务…`);
    // 标记若存在（任务运行中）→ 置 terminating（best-effort，rename原子）
    if (fs.existsSync(`${LOCK_FILE}${UNSAFE_SUFFIX}`)) {
      updateUnsafeMarker(`${LOCK_FILE}${UNSAFE_SUFFIX}`, { state: "terminating", reason: "external_signal" }, log);
    }
    terminationHolder.promise = terminateActiveTask(SIGKILL_GRACE_MS, log);
  };
  process.on("SIGINT", () => onExternalSignal("SIGINT"));
  process.on("SIGTERM", () => onExternalSignal("SIGTERM"));

  // ★execute 主流程：fallback summary + 致命异常不绕过收口 + 唯一一次 SUMMARY 输出
  const summary = await runExecute(cfg, taskRunId, LOCK_FILE, `${LOCK_FILE}${UNSAFE_SUFFIX}`, {
    runner: defaultRunner,
    nowFn: () => Date.now(),
    sleepFn: sleepMs,
    log,
    shutdown,
  }, terminationHolder);

  log(`\nSUMMARY_JSON=${JSON.stringify(summary)}`);
  process.exitCode = summary.status === "success" ? 0 : 1;
}

if (require.main === module) {
  main().catch((e) => {
    console.log(`[致命错误] ${e instanceof Error ? e.message : String(e)}`);
    // 禁止无条件 releaseLock：兜底复用 terminationState 走 safeReleaseLock
    fatalReleaseLock(LOCK_FILE);
    process.exitCode = 1;
  });
}
