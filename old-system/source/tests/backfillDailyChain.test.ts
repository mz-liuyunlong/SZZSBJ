/**
 * backfillDailyChain.test.ts - 方案B编排脚本测试（第14版）
 *
 * 分组参数（生产验收一次全量跑，无参数=全量）：
 *   --skip-real9 跳过第9版真实进程重型用例；--only-real9 只跑第9版重型用例
 *
 * 运行：npx ts-node tests/backfillDailyChain.test.ts
 * 约定：Node 原生 assert，失败非0退出。
 * 说明：绝大多数用例注入 runner/时钟/停止标志，零真实子进程；
 *       双进程并发锁用例按验收要求启动两个真实 Node 测试进程（仅抢测试锁文件，
 *       不运行任何同步脚本、不碰数据库/API/生产锁路径）。
 */

import * as assert from "assert";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { spawn } from "child_process";
import {
  parseConfig, runChain, deadlineToMs,
  acquireLock, releaseLock, setActiveChildForTest, terminateActiveTask, safeReleaseLock,
  fatalReleaseLock, terminationState, pidState, __setPidStateForTest, makeRunner,
  updateUnsafeMarker, removeUnsafeMarkerOwned, RunnerEvents, finalizeRun, computeChainStatus, runExecute,
  ParsedConfig, ChainDeps, TaskResult, TaskRunner, KillableChild, ShutdownRef, TerminationOutcome,
} from "../src/backfillDailyChain";
import type { ChildProcess } from "child_process";

let passed = 0;
let failed = 0;
const failures: string[] = [];

function t(name: string, fn: () => void | Promise<void>): Promise<void> {
  return Promise.resolve()
    .then(fn)
    .then(() => { passed++; console.log(`  ✅ ${name}`); })
    .catch((e) => { failed++; failures.push(name); console.log(`  ❌ ${name}: ${e instanceof Error ? e.message : e}`); });
}

// 固定"现在"：2026-07-12 10:00 上海 = 2026-07-12 02:00 UTC
const NOW = Date.UTC(2026, 6, 12, 2, 0, 0);

function okResult(seconds = 1): TaskResult {
  return { exitCode: 0, signal: null, timedOut: false, exitConfirmed: true, startedAt: "t0", finishedAt: "t1", durationSeconds: seconds };
}
function failResult(): TaskResult {
  return { exitCode: 1, signal: null, timedOut: false, exitConfirmed: true, startedAt: "t0", finishedAt: "t1", durationSeconds: 1 };
}
function timeoutResult(): TaskResult {
  return { exitCode: null, signal: "SIGKILL", timedOut: true, exitConfirmed: true, startedAt: "t0", finishedAt: "t1", durationSeconds: 900 };
}
function signalResult(): TaskResult {
  return { exitCode: null, signal: "SIGTERM", timedOut: false, exitConfirmed: true, startedAt: "t0", finishedAt: "t1", durationSeconds: 5 };
}
function unconfirmedResult(pid: number): TaskResult {
  return { exitCode: null, signal: "SIGKILL", timedOut: true, exitConfirmed: false, pid, startedAt: "t0", finishedAt: "t1", durationSeconds: 925 };
}

function mkCfg(over: Partial<ParsedConfig> = {}): ParsedConfig {
  return {
    mode: "execute",
    dates: ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"],
    deadlineHHmm: "19:10",
    intervalSeconds: 0,
    taskTimeoutMinutes: 15,
    ...over,
  };
}

interface Call { entry: string; date: string; timeoutMs: number; }

function mkDeps(rules: Array<{ entryIncludes: string; date?: string; result: TaskResult }>, nowSeq?: number[]): { deps: ChainDeps; calls: Call[] } {
  const calls: Call[] = [];
  let nowIdx = 0;
  const runner: TaskRunner = (entry, args, timeoutMs) => {
    const date = args[0].startsWith("--date=") ? args[0].slice(7) : args[0];
    calls.push({ entry, date, timeoutMs });
    const hit = rules.find((r) => entry.includes(r.entryIncludes) && (r.date === undefined || r.date === date));
    return Promise.resolve(hit ? { ...hit.result } : okResult());
  };
  const deps: ChainDeps = {
    runner,
    nowFn: () => (nowSeq && nowIdx < nowSeq.length ? nowSeq[nowIdx++] : NOW),
    sleepFn: () => Promise.resolve(),
    log: () => { /* 静默 */ },
  };
  return { deps, calls };
}

function mkShutdown(): ShutdownRef {
  return { requested: false, signal: null };
}

// ── 确定性 fs 故障注入（与 root/non-root 无关；只命中明确路径；finally 恢复） ──
// eslint-disable-next-line @typescript-eslint/no-var-requires
const rawFsMod = require("fs") as Record<string, (...a: unknown[]) => unknown>;
interface FsFault { method: "unlinkSync" | "writeFileSync" | "renameSync"; path: string; code: string; active: () => boolean; }
async function withFsFaults<T>(faults: FsFault[], fn: () => Promise<T>): Promise<T> {
  const origs = new Map<string, (...a: unknown[]) => unknown>();
  for (const f of faults) {
    if (!origs.has(f.method)) origs.set(f.method, rawFsMod[f.method]);
  }
  for (const m of origs.keys()) {
    const orig = origs.get(m)!;
    rawFsMod[m] = (p: unknown, ...rest: unknown[]) => {
      for (const f of faults) {
        if (f.method === m && typeof p === "string" && p === f.path && f.active()) {
          const e: NodeJS.ErrnoException = new Error(f.code);
          e.code = f.code;
          throw e;
        }
      }
      return orig(p, ...rest);
    };
  }
  try {
    return await fn();
  } finally {
    for (const [m, orig] of origs) rawFsMod[m] = orig;
  }
}

function mkFakeChild(events: string[], opts: { exitOnTerm: boolean }): KillableChild {
  let exitCb: (() => void) | null = null;
  return {
    pid: 424242,
    kill(sig?: NodeJS.Signals): boolean {
      events.push(`kill:${sig}`);
      if ((sig === "SIGTERM" && opts.exitOnTerm) || sig === "SIGKILL") {
        setTimeout(() => exitCb && exitCb(), 5);
      }
      return true;
    },
    once(_ev: "exit", cb: (...args: unknown[]) => void): unknown {
      exitCb = cb as () => void;
      return this;
    },
  };
}

const SKIP_REAL9 = process.argv.includes("--skip-real9");
const ONLY_REAL9 = process.argv.includes("--only-real9");

async function main(): Promise<void> {
  if (!ONLY_REAL9) {
  console.log("== 参数校验 ==");

  await t("默认窗口 = T-6~T-2 共5天（上海口径）", () => {
    const cfg = parseConfig([], NOW);
    assert.strictEqual(cfg.mode, "dry-run");
    assert.deepStrictEqual(cfg.dates, ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]);
  });
  await t("显式日期优先于 days/end-offset", () => {
    const cfg = parseConfig(["--start-date=2026-07-01", "--end-date=2026-07-03", "--days=9"], NOW);
    assert.deepStrictEqual(cfg.dates, ["2026-07-01", "2026-07-02", "2026-07-03"]);
  });
  await t("--execute 未传 --deadline → 抛错", () => {
    assert.throws(() => parseConfig(["--execute"], NOW), /--deadline/);
  });
  await t("--execute --deadline=19:10 通过", () => {
    const cfg = parseConfig(["--execute", "--deadline=19:10"], NOW);
    assert.strictEqual(cfg.mode, "execute");
    assert.strictEqual(cfg.deadlineHHmm, "19:10");
  });
  await t("非法死线格式拒绝", () => {
    assert.throws(() => parseConfig(["--execute", "--deadline=25:00"], NOW), /HH:mm/);
    assert.throws(() => parseConfig(["--execute", "--deadline=1910"], NOW), /格式错误|HH:mm/);
  });
  await t("非法日期拒绝", () => {
    assert.throws(() => parseConfig(["--start-date=2026-02-30", "--end-date=2026-03-01"], NOW), /非法/);
  });
  await t("起止倒置拒绝", () => {
    assert.throws(() => parseConfig(["--start-date=2026-07-05", "--end-date=2026-07-01"], NOW), /不得晚于/);
  });
  await t("跨度超过31天拒绝", () => {
    assert.throws(() => parseConfig(["--start-date=2026-01-01", "--end-date=2026-03-01"], NOW), /上限|超过/);
  });
  await t("days 上限校验", () => {
    assert.throws(() => parseConfig(["--days=32"], NOW), /1~31/);
    assert.throws(() => parseConfig(["--days=0"], NOW), /1~31/);
  });
  await t("单传 start-date 或 end-date 拒绝", () => {
    assert.throws(() => parseConfig(["--start-date=2026-07-01"], NOW), /成对/);
  });
  await t("未知参数拒绝（防拼写绕过）", () => {
    assert.throws(() => parseConfig(["--execute", "--dead-line=19:10"], NOW), /未知/);
  });
  await t("interval-seconds 上限3600（防持锁滞留）", () => {
    assert.throws(() => parseConfig(["--interval-seconds=3601"], NOW), /0~3600/);
    assert.strictEqual(parseConfig(["--interval-seconds=3600"], NOW).intervalSeconds, 3600);
  });

  console.log("== 死线换算 ==");
  await t("19:10 上海 = 11:10 UTC 当天", () => {
    assert.strictEqual(new Date(deadlineToMs("19:10", NOW)).toISOString(), "2026-07-12T11:10:00.000Z");
  });

  console.log("== PID 三态探测 ==");
  await t("pidState：自身=alive；不存在PID=dead；注入EPERM=unknown", () => {
    assert.strictEqual(pidState(process.pid), "alive");
    assert.strictEqual(pidState(999999999), "dead");
    __setPidStateForTest((pid) => (pid === 55555 ? "unknown" : undefined));
    assert.strictEqual(pidState(55555), "unknown"); // 模拟EPERM
    __setPidStateForTest(null);
  });

  console.log("== 编排链路（mock runner） ==");

  await t("全部成功：三阶段×5日，status=success，任务序=阶段串行+日期旧→新", async () => {
    const { deps, calls } = mkDeps([]);
    const s = await runChain(mkCfg(), "T1", deps);
    assert.strictEqual(s.status, "success");
    assert.strictEqual(calls.length, 15);
    assert.strictEqual(s.fact.success.length, 5);
    assert.strictEqual(s.rawSales.success.length, 5);
    assert.strictEqual(s.orderProfit.success.length, 5);
    assert.ok(calls.slice(0, 5).every((c) => c.entry.includes("syncLingxingDailyToDb")));
    assert.deepStrictEqual(calls.slice(0, 5).map((c) => c.date), mkCfg().dates);
    assert.ok(calls.slice(5, 10).every((c) => c.entry.includes("syncLingxingToRawFeishu")));
    assert.ok(calls.slice(10, 15).every((c) => c.entry.includes("syncOrderProfitDaily")));
  });

  await t("某日FACT失败：该日明细与订单利润均跳过，其余日期继续", async () => {
    const { deps, calls } = mkDeps([{ entryIncludes: "syncLingxingDailyToDb", date: "2026-07-08", result: failResult() }]);
    const s = await runChain(mkCfg(), "T2", deps);
    assert.strictEqual(s.status, "partial_failed");
    assert.deepStrictEqual(s.fact.failed, ["2026-07-08"]);
    assert.deepStrictEqual(s.rawSales.skippedByFactFailure, ["2026-07-08"]);
    assert.deepStrictEqual(s.orderProfit.skippedByFactFailure, ["2026-07-08"]);
    assert.strictEqual(calls.length, 5 + 4 + 4);
  });

  await t("某日明细(RAW)失败：同日订单利润仍执行", async () => {
    const { deps } = mkDeps([{ entryIncludes: "syncLingxingToRawFeishu", date: "2026-07-09", result: failResult() }]);
    const s = await runChain(mkCfg(), "T3", deps);
    assert.deepStrictEqual(s.rawSales.failed, ["2026-07-09"]);
    assert.ok(s.orderProfit.success.includes("2026-07-09"));
    assert.strictEqual(s.status, "partial_failed");
  });

  await t("某日订单利润失败：仅记失败，不影响其他日期", async () => {
    const { deps } = mkDeps([{ entryIncludes: "syncOrderProfitDaily", date: "2026-07-06", result: failResult() }]);
    const s = await runChain(mkCfg(), "T4", deps);
    assert.deepStrictEqual(s.orderProfit.failed, ["2026-07-06"]);
    assert.strictEqual(s.orderProfit.success.length, 4);
    assert.strictEqual(s.status, "partial_failed");
  });

  await t("多日期混合失败：计数与清单准确", async () => {
    const { deps } = mkDeps([
      { entryIncludes: "syncLingxingDailyToDb", date: "2026-07-06", result: failResult() },
      { entryIncludes: "syncLingxingToRawFeishu", date: "2026-07-07", result: failResult() },
      { entryIncludes: "syncOrderProfitDaily", date: "2026-07-10", result: failResult() },
    ]);
    const s = await runChain(mkCfg(), "T5", deps);
    assert.deepStrictEqual(s.fact.failed, ["2026-07-06"]);
    assert.deepStrictEqual(s.rawSales.failed, ["2026-07-07"]);
    assert.deepStrictEqual(s.rawSales.skippedByFactFailure, ["2026-07-06"]);
    assert.deepStrictEqual(s.orderProfit.failed, ["2026-07-10"]);
    assert.ok(s.orderProfit.success.includes("2026-07-07"));
    assert.strictEqual(s.status, "partial_failed");
  });

  await t("启动前死线已到：零任务执行，deadlineAborted=true，status=failed", async () => {
    const late = deadlineToMs("19:10", NOW) + 1000;
    const { deps, calls } = mkDeps([], [late, late, late]);
    const s = await runChain(mkCfg(), "T6", deps);
    assert.strictEqual(s.deadlineAborted, true);
    assert.strictEqual(s.status, "failed");
    assert.strictEqual(calls.length, 0);
  });

  await t("运行中到达死线：中止剩余任务", async () => {
    const dl = deadlineToMs("19:10", NOW);
    const seq = [NOW, NOW, dl + 1, dl + 2, dl + 3];
    const { deps, calls } = mkDeps([], seq);
    const s = await runChain(mkCfg(), "T7", deps);
    assert.strictEqual(s.deadlineAborted, true);
    assert.strictEqual(calls.length, 1);
    assert.strictEqual(s.status, "failed");
  });

  await t("单任务超时上限 = min(15分钟, 距死线剩余)", async () => {
    const dl = deadlineToMs("19:10", NOW);
    const nearDeadline = dl - 5 * 60 * 1000;
    const { deps, calls } = mkDeps([], [nearDeadline, nearDeadline, dl + 1]);
    await runChain(mkCfg({ dates: ["2026-07-06"] }), "T8", deps);
    assert.strictEqual(calls.length, 1);
    assert.strictEqual(calls[0].timeoutMs, 5 * 60 * 1000);
  });

  console.log("== dirtyDates ==");

  await t("重写阶段超时击杀 → dirty(timeout)；FACT超时不记脏", async () => {
    const { deps } = mkDeps([
      { entryIncludes: "syncLingxingDailyToDb", date: "2026-07-06", result: timeoutResult() },
      { entryIncludes: "syncOrderProfitDaily", date: "2026-07-08", result: timeoutResult() },
    ]);
    const s = await runChain(mkCfg(), "T9", deps);
    assert.deepStrictEqual(s.dirtyDates, [{ stage: "orderProfit", date: "2026-07-08", reason: "timeout_killed_during_rewrite" }]);
    assert.ok(s.fact.failed.includes("2026-07-06"));
  });

  await t("RAW普通exit=1 → dirty(nonzero_exit_during_rewrite)", async () => {
    const { deps } = mkDeps([{ entryIncludes: "syncLingxingToRawFeishu", date: "2026-07-07", result: failResult() }]);
    const s = await runChain(mkCfg(), "T9b", deps);
    assert.deepStrictEqual(s.dirtyDates, [{ stage: "rawSales", date: "2026-07-07", reason: "nonzero_exit_during_rewrite" }]);
  });

  await t("订单利润普通exit=1 → dirty(nonzero)", async () => {
    const { deps } = mkDeps([{ entryIncludes: "syncOrderProfitDaily", date: "2026-07-09", result: failResult() }]);
    const s = await runChain(mkCfg(), "T9c", deps);
    assert.deepStrictEqual(s.dirtyDates, [{ stage: "orderProfit", date: "2026-07-09", reason: "nonzero_exit_during_rewrite" }]);
  });

  await t("FACT普通exit=1 → 不记 dirty（upsert幂等）", async () => {
    const { deps } = mkDeps([{ entryIncludes: "syncLingxingDailyToDb", date: "2026-07-06", result: failResult() }]);
    const s = await runChain(mkCfg(), "T9d", deps);
    assert.deepStrictEqual(s.dirtyDates, []);
  });

  await t("重写阶段信号退出（非超时） → dirty(signal_exit_during_rewrite)", async () => {
    const { deps } = mkDeps([{ entryIncludes: "syncOrderProfitDaily", date: "2026-07-08", result: signalResult() }]);
    const s = await runChain(mkCfg(), "T9e", deps);
    assert.deepStrictEqual(s.dirtyDates, [{ stage: "orderProfit", date: "2026-07-08", reason: "signal_exit_during_rewrite" }]);
  });

  console.log("== 子进程退出未确认（SIGKILL后无exit） ==");

  await t("RAW任务退出未确认：spawn前置标记保留+补全现场，立即中止全链", async () => {
    const marker = path.join(os.tmpdir(), `bfd-um-${process.pid}-${Date.now()}.unsafe`);
    const { deps, calls } = mkDeps([{ entryIncludes: "syncLingxingToRawFeishu", date: "2026-07-07", result: unconfirmedResult(31337) }]);
    deps.unsafeMarkerFile = marker;
    const s = await runChain(mkCfg(), "U1", deps);
    assert.strictEqual(calls.length, 7);
    assert.deepStrictEqual(s.rawSales.failed, ["2026-07-07"]);
    assert.deepStrictEqual(s.dirtyDates, [{ stage: "rawSales", date: "2026-07-07", reason: "timeout_killed_during_rewrite" }]);
    assert.strictEqual(s.childExitUnconfirmed, true);
    assert.strictEqual(s.unsafeChildPid, 31337);
    assert.strictEqual(s.status, "failed");
    // ★标记在 spawn 前已创建（前置式），未确认时保留并补全现场
    assert.strictEqual(s.unsafeMarkerCreated, true);
    assert.strictEqual(s.unsafeMarkerPath, marker);
    assert.strictEqual(s.unsafeMarkerState, "terminating");
    const m = JSON.parse(fs.readFileSync(marker, "utf-8"));
    assert.strictEqual(m.unsafeChildPid, 31337);
    assert.strictEqual(m.stage, "rawSales");
    assert.strictEqual(m.date, "2026-07-07");
    assert.strictEqual(m.state, "terminating");
    assert.strictEqual(m.reason, "child_exit_unconfirmed");
    assert.strictEqual(m.parentPid, process.pid);
    fs.unlinkSync(marker);
  });

  await t("确认退出的任务：标记随任务创建并在exit确认后删除（全成功链末尾无标记）", async () => {
    const marker = path.join(os.tmpdir(), `bfd-umok-${process.pid}-${Date.now()}.unsafe`);
    const { deps } = mkDeps([]);
    deps.unsafeMarkerFile = marker;
    const s = await runChain(mkCfg(), "U0", deps);
    assert.strictEqual(s.status, "success");
    assert.strictEqual(fs.existsSync(marker), false); // 每任务确认退出即删
    assert.strictEqual(s.unsafeMarkerState, null);
    assert.strictEqual(s.unsafeMarkerCleanupFailed, false); // 删除成功→state=null 一致
  });

  await t("FACT任务退出未确认：立即中止、不记dirty、前置标记保留", async () => {
    const marker = path.join(os.tmpdir(), `bfd-um2-${process.pid}-${Date.now()}.unsafe`);
    const { deps, calls } = mkDeps([{ entryIncludes: "syncLingxingDailyToDb", date: "2026-07-06", result: unconfirmedResult(31338) }]);
    deps.unsafeMarkerFile = marker;
    const s = await runChain(mkCfg(), "U2", deps);
    assert.strictEqual(calls.length, 1);
    assert.deepStrictEqual(s.dirtyDates, []);
    assert.strictEqual(s.childExitUnconfirmed, true);
    assert.strictEqual(s.unsafeChildPid, 31338);
    assert.strictEqual(s.unsafeMarkerCreated, true);
    assert.strictEqual(fs.existsSync(marker), true);
    assert.strictEqual(s.status, "failed");
    fs.unlinkSync(marker);
  });

  await t("退出未确认 → main口径：safeReleaseLock 以 alive PID 保守不放锁", async () => {
    __setPidStateForTest((pid) => (pid === 31337 ? "alive" : undefined));
    const lockU = path.join(os.tmpdir(), `bfd-u-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(lockU, "U3", () => {}), true);
    const outcome: TerminationOutcome = { had: true, confirmedExited: false, pid: 31337 };
    const logs: string[] = [];
    assert.strictEqual(safeReleaseLock(lockU, outcome, (s) => logs.push(s)).releasedOrAbsent, false);
    assert.strictEqual(fs.existsSync(lockU), true);
    assert.ok(logs.some((l) => l.includes("CRITICAL")));
    __setPidStateForTest(null);
    fs.unlinkSync(lockU);
  });

  console.log("== safeReleaseLock 三态 ==");

  await t("未确认+PID unknown（EPERM）→ 保守不放锁", async () => {
    __setPidStateForTest((pid) => (pid === 41001 ? "unknown" : undefined));
    const lk = path.join(os.tmpdir(), `bfd-sr-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(lk, "SR1", () => {}), true);
    assert.strictEqual(safeReleaseLock(lk, { had: true, confirmedExited: false, pid: 41001 }, () => {}).releasedOrAbsent, false);
    assert.strictEqual(fs.existsSync(lk), true);
    __setPidStateForTest(null);
    fs.unlinkSync(lk);
  });

  await t("未确认+PID 明确dead → 核验后释放", async () => {
    const lk = path.join(os.tmpdir(), `bfd-sr2-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(lk, "SR2", () => {}), true);
    assert.strictEqual(safeReleaseLock(lk, { had: true, confirmedExited: false, pid: 999999999 }, () => {}).releasedOrAbsent, true);
    assert.strictEqual(fs.existsSync(lk), false);
  });

  console.log("== 汇总JSON字段完整性 ==");
  await t("包含全部字段（含第6版新增）", async () => {
    const { deps } = mkDeps([]);
    const s = await runChain(mkCfg(), "T10", deps);
    for (const k of ["taskRunId", "mode", "startDate", "endDate", "dates", "deadline", "startedAt", "finishedAt",
      "durationSeconds", "fact", "rawSales", "orderProfit", "dirtyDates", "deadlineAborted",
      "externalSignalAborted", "externalSignal", "childExitUnconfirmed", "unsafeChildPid",
      "unsafeMarkerCreated", "unsafeMarkerPath", "unsafeMarkerState",
      "unsafeMarkerWriteFailed", "unsafeMarkerErrorCode",
      "unsafeMarkerCleanupFailed", "unsafeMarkerCleanupErrorCode",
      "fatalError", "fatalErrorMessage", "lockReleaseFailed", "lockReleaseErrorCode",
      "lockStillPresent", "lockConflict", "status"]) {
      assert.ok(k in s, `缺少字段 ${k}`);
    }
  });

  console.log("== 第10版：onSpawn立即触发 / 标记清理结果 / tmp清理 ==");

  await t("V10-1. spawn返回即有PID：onSpawn只调一次，spawn事件不重复触发", async () => {
    let count = 0;
    const runner = makeRunner({ tsNodeBinOverride: "-e" });
    const events: RunnerEvents = { onSpawn: () => { count++; } };
    const r = await runner("process.exit(0)", [], 60000, events);
    assert.strictEqual(r.exitConfirmed, true);
    await new Promise((r2) => setTimeout(r2, 100)); // 等spawn事件fallback也走完
    assert.strictEqual(count, 1); // ★至多一次
  });

  await t("V10-2. spawn失败无PID：onSpawn零调用", async () => {
    let count = 0;
    const runner = makeRunner({ execPathOverride: "/nonexistent/no-such-node" });
    const events: RunnerEvents = { onSpawn: () => { count++; } };
    const r = await runner("-e", ["1"], 60000, events);
    assert.strictEqual(r.exitConfirmed, true);
    assert.strictEqual(count, 0);
    setActiveChildForTest(null);
  });

  await t("V10-3. removeUnsafeMarkerOwned：不存在=true / 成功删除=true", () => {
    const f = path.join(os.tmpdir(), `bfd10-rm-${process.pid}-${Date.now()}`);
    assert.deepStrictEqual(removeUnsafeMarkerOwned(f, () => {}), { removedOrAbsent: true });
    fs.writeFileSync(f, JSON.stringify({ parentPid: process.pid, taskRunId: "X" }));
    assert.deepStrictEqual(removeUnsafeMarkerOwned(f, () => {}), { removedOrAbsent: true });
    assert.strictEqual(fs.existsSync(f), false);
  });

  await t("V10-4. removeUnsafeMarkerOwned：归属其他PID→NOT_OWNER不删 / 不可解析→UNPARSEABLE不删", () => {
    const f = path.join(os.tmpdir(), `bfd10-rm2-${process.pid}-${Date.now()}`);
    fs.writeFileSync(f, JSON.stringify({ parentPid: 999999999, taskRunId: "OTHER" }));
    const r1 = removeUnsafeMarkerOwned(f, () => {});
    assert.strictEqual(r1.removedOrAbsent, false);
    assert.strictEqual(r1.errorCode, "NOT_OWNER");
    assert.strictEqual(fs.existsSync(f), true);
    fs.writeFileSync(f, "broken");
    const r2 = removeUnsafeMarkerOwned(f, () => {});
    assert.strictEqual(r2.removedOrAbsent, false);
    assert.strictEqual(r2.errorCode, "UNPARSEABLE");
    assert.strictEqual(fs.existsSync(f), true);
    fs.unlinkSync(f);
  });

  await t("V10-5. removeUnsafeMarkerOwned：unlink EACCES（确定性注入）→false+错误码，文件保留", async () => {
    const f = path.join(os.tmpdir(), `bfd10-rm3-${process.pid}-${Date.now()}.unsafe`);
    fs.writeFileSync(f, JSON.stringify({ parentPid: process.pid, taskRunId: "X" }));
    const r = await withFsFaults(
      [{ method: "unlinkSync", path: f, code: "EACCES", active: () => true }],
      async () => removeUnsafeMarkerOwned(f, () => {}),
    );
    assert.strictEqual(r.removedOrAbsent, false);
    assert.strictEqual(r.errorCode, "EACCES");
    assert.strictEqual(fs.existsSync(f), true);
    fs.unlinkSync(f);
  });

  await t("V10-6. updateUnsafeMarker rename失败：正式标记原样、tmp不残留、返回原始错误码", () => {
    const f = path.join(os.tmpdir(), `bfd10-up-${process.pid}-${Date.now()}`);
    const orig = JSON.stringify({ parentPid: process.pid, taskRunId: "X", state: "starting" });
    fs.writeFileSync(f, orig);
    // fs 命名空间为只读 getter（委托底层CJS模块）——补丁打在底层模块上
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const rawFs = require("fs") as { renameSync: typeof fs.renameSync };
    const realRename = rawFs.renameSync;
    rawFs.renameSync = () => {
      const e: NodeJS.ErrnoException = new Error("EXDEV"); e.code = "EXDEV"; throw e;
    };
    let r;
    try {
      r = updateUnsafeMarker(f, { state: "running" }, () => {});
    } finally {
      rawFs.renameSync = realRename;
    }
    assert.strictEqual(r.ok, false);
    assert.strictEqual((r as { ok: false; code: string }).code, "EXDEV"); // 原始rename错误码
    assert.strictEqual(fs.readFileSync(f, "utf-8"), orig);                 // 正式标记原样
    assert.strictEqual(fs.existsSync(`${f}.tmp.${process.pid}`), false);   // tmp 不残留
    fs.unlinkSync(f);
  });

  console.log("== 第11版：清理失败→整体失败 / 收口最终复核（A~D） ==");

  await t("V11-A. 三阶段业务全成功但末任务标记unlink失败（确定性注入）：业务留success、整体failed、摘要与磁盘一致", async () => {
    const marker = path.join(os.tmpdir(), `bfd11-a-${process.pid}-${Date.now()}.unsafe`);
    let taskNo = 0;
    const runner: TaskRunner = () => {
      taskNo++;
      return Promise.resolve(okResult());
    };
    const deps: ChainDeps = { runner, nowFn: () => NOW, sleepFn: () => Promise.resolve(), log: () => {}, shutdown: mkShutdown(), unsafeMarkerFile: marker };
    const s = await withFsFaults(
      [{ method: "unlinkSync", path: marker, code: "EACCES", active: () => taskNo === 3 }], // 仅末任务清理失败
      () => runChain(mkCfg({ dates: ["2026-07-06"] }), "V11A", deps),
    );
    assert.deepStrictEqual(s.fact.success, ["2026-07-06"]);        // 业务任务保留success
    assert.deepStrictEqual(s.rawSales.success, ["2026-07-06"]);
    assert.deepStrictEqual(s.orderProfit.success, ["2026-07-06"]);
    assert.strictEqual(s.unsafeMarkerCleanupFailed, true);
    assert.strictEqual(s.unsafeMarkerCleanupErrorCode, "EACCES");
    assert.notStrictEqual(s.unsafeMarkerState, null);              // state 非null
    assert.strictEqual(fs.existsSync(marker), true);               // 标记仍在盘
    assert.strictEqual(s.status, "failed");                        // ★整体failed，不得success
    fs.unlinkSync(marker);
  });

  await t("V11-B. 第一阶段标记清理失败（确定性注入）：FACT记success、RAW与订单利润零启动、failed", async () => {
    const marker = path.join(os.tmpdir(), `bfd11-b-${process.pid}-${Date.now()}.unsafe`);
    const calls: Call[] = [];
    const runner: TaskRunner = (entry, args, timeoutMs) => {
      calls.push({ entry, date: args[0], timeoutMs });
      return Promise.resolve(okResult());
    };
    const deps: ChainDeps = { runner, nowFn: () => NOW, sleepFn: () => Promise.resolve(), log: () => {}, shutdown: mkShutdown(), unsafeMarkerFile: marker };
    const s = await withFsFaults(
      [{ method: "unlinkSync", path: marker, code: "EACCES", active: () => true }],
      () => runChain(mkCfg({ dates: ["2026-07-06"] }), "V11B", deps),
    );
    assert.strictEqual(calls.length, 1);                           // ★RAW/订单利润零启动
    assert.deepStrictEqual(s.fact.success, ["2026-07-06"]);
    assert.strictEqual(s.rawSales.success.length + s.rawSales.failed.length, 0);
    assert.strictEqual(s.orderProfit.success.length + s.orderProfit.failed.length, 0);
    assert.strictEqual(s.status, "failed");
    fs.unlinkSync(marker);
  });

  await t("V11-C. 信号终止最初未确认但收口前子进程真实退出：无unsafe残留、不宣称危险、按dead放锁", async () => {
    // 取一个"已真实死亡"的PID：spawn即退出的真实子进程
    const quick = spawn(process.execPath, ["-e", "process.exit(0)"], { shell: false });
    const deadPid: number = quick.pid!;
    await new Promise<void>((res) => quick.once("exit", () => res()));
    await new Promise((r2) => setTimeout(r2, 50));
    assert.strictEqual(pidState(deadPid), "dead");

    const base = path.join(os.tmpdir(), `bfd11-c-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V11C", () => {}), true);
    fs.writeFileSync(marker, JSON.stringify({ taskRunId: "V11C", parentPid: process.pid, unsafeChildPid: deadPid, stage: "rawSales", date: "2026-07-07", state: "terminating", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() }));
    const s = { ...(await runChain(mkCfg({ dates: ["2026-07-06"] }), "V11C-sum", mkDeps([]).deps)) }; // 基础summary骨架
    s.externalSignalAborted = true; s.externalSignal = "SIGTERM";
    const sigTerm: TerminationOutcome = { had: true, confirmedExited: false, pid: deadPid };
    await finalizeRun(s, Promise.resolve(sigTerm), base, marker, "V11C", () => {});
    assert.strictEqual(fs.existsSync(marker), false);   // ★无unsafe残留
    assert.strictEqual(s.childExitUnconfirmed, false);  // ★不得宣称仍有危险子进程
    assert.strictEqual(s.unsafeMarkerState, null);
    assert.strictEqual(fs.existsSync(base), false);     // ★锁按dead结果安全释放
    assert.strictEqual(s.status, "failed");             // externalSignalAborted 仍failed（链被中断）
  });

  await t("V11-D. 信号终止最终仍alive：标记在盘、摘要完整、failed、锁不释放", async () => {
    const sleeper = spawn(process.execPath, ["-e", "setTimeout(() => {}, 15000)"], { shell: false });
    await new Promise((r2) => setTimeout(r2, 100));
    const alivePid: number = sleeper.pid!;
    const base = path.join(os.tmpdir(), `bfd11-d-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V11D", () => {}), true);
    fs.writeFileSync(marker, JSON.stringify({ taskRunId: "V11D", parentPid: process.pid, unsafeChildPid: alivePid, stage: "fact", date: "2026-07-06", state: "running", createdAt: new Date().toISOString() }));
    const s = { ...(await runChain(mkCfg({ dates: ["2026-07-06"] }), "V11D-sum", mkDeps([]).deps)) };
    s.externalSignalAborted = true; s.externalSignal = "SIGTERM";
    const sigTerm: TerminationOutcome = { had: true, confirmedExited: false, pid: alivePid };
    const logs: string[] = [];
    await finalizeRun(s, Promise.resolve(sigTerm), base, marker, "V11D", (x) => logs.push(x));
    assert.strictEqual(fs.existsSync(marker), true);    // ★标记必须在盘
    assert.strictEqual(s.childExitUnconfirmed, true);
    assert.strictEqual(s.unsafeChildPid, alivePid);
    assert.strictEqual(s.unsafeMarkerState, "terminating"); // 收口更新+磁盘一致
    assert.strictEqual(s.status, "failed");
    assert.strictEqual(fs.existsSync(base), true);      // ★锁保守不释放
    assert.ok(logs.some((l) => l.includes("CRITICAL")));
    sleeper.kill("SIGKILL");
    fs.unlinkSync(base); fs.unlinkSync(marker);
  });

  console.log("== 第12版：致命异常SUMMARY / 主锁释放真实结果 ==");

  await t("V12-1. runner同步抛异常：fallback summary、fatalError、收口完成、failed", async () => {
    const base = path.join(os.tmpdir(), `bfd12-1-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V12-1", () => {}), true);
    const throwingRunner: TaskRunner = () => { throw new Error("sync-boom secretTOKENvalue1234567890abcdef"); };
    const s = await runExecute(mkCfg({ dates: ["2026-07-06"] }), "V12-1", base, marker,
      { runner: throwingRunner, nowFn: () => Date.now(), sleepFn: () => Promise.resolve(), log: () => {}, shutdown: mkShutdown() },
      { promise: null });
    assert.strictEqual(s.fatalError, true);
    assert.ok(s.fatalErrorMessage!.includes("sync-boom"));
    assert.ok(s.fatalErrorMessage!.includes("[REDACTED]"));       // 长token脱敏
    assert.ok(s.fatalErrorMessage!.length <= 200);
    assert.strictEqual(s.status, "failed");
    // 收口完成：锁按无未确认子进程正常释放，磁盘真值一致
    assert.strictEqual(fs.existsSync(base), false);
    assert.strictEqual(s.lockStillPresent, false);
    assert.strictEqual(fs.existsSync(marker), true);              // 任务的starting标记残留（异常中断，fail-closed）
    assert.notStrictEqual(s.unsafeMarkerState, null);
    fs.unlinkSync(marker);
  });

  await t("V12-2. runner Promise reject：同样落 fatalError 且收口完成", async () => {
    const base = path.join(os.tmpdir(), `bfd12-2-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V12-2", () => {}), true);
    const rejectingRunner: TaskRunner = () => Promise.reject(new Error("reject-boom"));
    const s = await runExecute(mkCfg({ dates: ["2026-07-06"] }), "V12-2", base, marker,
      { runner: rejectingRunner, nowFn: () => Date.now(), sleepFn: () => Promise.resolve(), log: () => {}, shutdown: mkShutdown() },
      { promise: null });
    assert.strictEqual(s.fatalError, true);
    assert.ok(s.fatalErrorMessage!.includes("reject-boom"));
    assert.strictEqual(s.status, "failed");
    assert.strictEqual(fs.existsSync(base), false);
    try { fs.unlinkSync(marker); } catch {}
  });

  await t("V12-3. 主锁unlink EACCES（确定性注入）：safeReleaseLock=false、锁仍在、fatalReleaseLock同样不误报", async () => {
    const base = path.join(os.tmpdir(), `bfd12-3-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(base, "V12-3", () => {}), true);
    const logs: string[] = [];
    const r = await withFsFaults(
      [{ method: "unlinkSync", path: base, code: "EACCES", active: () => true }],
      async () => safeReleaseLock(base, null, (x) => logs.push(x)),
    );
    assert.strictEqual(r.releasedOrAbsent, false);
    assert.strictEqual(r.errorCode, "EACCES");
    assert.strictEqual(fs.existsSync(base), true);                // 主锁仍在
    // fatalReleaseLock 同样不得误报成功
    terminationState.outcome = null;
    const r2 = await withFsFaults(
      [{ method: "unlinkSync", path: base, code: "EACCES", active: () => true }],
      async () => fatalReleaseLock(base, () => {}),
    );
    assert.strictEqual(r2.releasedOrAbsent, false);
    assert.strictEqual(r2.errorCode, "EACCES");
    assert.strictEqual(fs.existsSync(base), true);
    fs.unlinkSync(base);
  });

  await t("V12-4. finalizeRun遇主锁删除失败：lockReleaseFailed、lockStillPresent、failed、摘要与磁盘一致", async () => {
    const base = path.join(os.tmpdir(), `bfd12-4-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V12-4", () => {}), true);
    const s = { ...(await runChain(mkCfg({ dates: ["2026-07-06"] }), "V12-4-sum", mkDeps([]).deps)) };
    await withFsFaults(
      [{ method: "unlinkSync", path: base, code: "EACCES", active: () => true }],
      () => finalizeRun(s, null, base, marker, "V12-4", () => {}),
    );
    assert.strictEqual(s.lockReleaseFailed, true);
    assert.strictEqual(s.lockReleaseErrorCode, "EACCES");
    assert.strictEqual(s.lockStillPresent, true);
    assert.strictEqual(fs.existsSync(base), true);
    assert.strictEqual(s.status, "failed");                       // ★应释放但失败→整体failed
    fs.unlinkSync(base);
  });

  await t("V12-5. releaseLock四态：不存在true/本进程true/他人NOT_OWNER/不可解析UNPARSEABLE", async () => {
    const f = path.join(os.tmpdir(), `bfd12-5-${process.pid}-${Date.now()}`);
    assert.strictEqual(releaseLock(f).releasedOrAbsent, true);    // 不存在
    fs.writeFileSync(f, JSON.stringify({ pid: process.pid, taskRunId: "X", startedAt: "t" }));
    assert.strictEqual(releaseLock(f).releasedOrAbsent, true);    // 本进程删除成功
    fs.writeFileSync(f, JSON.stringify({ pid: 999999999, taskRunId: "O", startedAt: "t" }));
    const r1 = releaseLock(f);
    assert.deepStrictEqual(r1, { releasedOrAbsent: false, errorCode: "NOT_OWNER" });
    fs.writeFileSync(f, "broken");
    const r2 = releaseLock(f);
    assert.deepStrictEqual(r2, { releasedOrAbsent: false, errorCode: "UNPARSEABLE" });
    fs.unlinkSync(f);
  });

  console.log("== 第13版：activeChild 生命周期（真实路径A/B/C） ==");

  await t("V13-A. 真实子进程error未确认→首次终止被拦(kill异常)仍保留句柄→第二次终止 had=true 且真实杀死", async () => {
    let handle: ChildProcess | null = null;
    const runner = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        handle = c;
        const e: NodeJS.ErrnoException = new Error("EPERM");
        e.code = "EPERM";
        setTimeout(() => c.emit("error", e), 50);
      },
    });
    const r = await runner("setTimeout(() => {}, 15000)", [], 60000);
    assert.strictEqual(r.exitConfirmed, false); // 未确认，句柄保留（runner settle 不清空）
    const realPid = (handle as unknown as ChildProcess).pid!;
    assert.strictEqual(pidState(realPid), "alive");
    // 首次终止：让真实 child.kill 抛 EPERM（monkeypatch 句柄方法）→ 未确认
    const h = handle as unknown as ChildProcess;
    const realKill = h.kill.bind(h);
    (h as { kill: (s?: NodeJS.Signals) => boolean }).kill = () => {
      const e: NodeJS.ErrnoException = new Error("EPERM"); e.code = "EPERM"; throw e;
    };
    const t1 = await terminateActiveTask(50, () => {}, 50);
    assert.strictEqual(t1.had, true);
    assert.strictEqual(t1.confirmedExited, false);      // 首次未确认
    assert.strictEqual(pidState(realPid), "alive");     // 危险子进程仍在
    // ★第二次终止：句柄必须仍被找到并真实杀死
    (h as { kill: (s?: NodeJS.Signals) => boolean }).kill = realKill;
    const t2 = await terminateActiveTask(2000, () => {});
    assert.strictEqual(t2.had, true);                   // ★必须 had=true
    assert.strictEqual(t2.confirmedExited, true);
    await new Promise((r2) => setTimeout(r2, 100));
    assert.strictEqual(pidState(realPid), "dead");      // ★真实终止成功
  });

  await t("V13-B. 未确认后子进程自然exit→exit事件清理activeChild→再终止 had=false", async () => {
    let handle: ChildProcess | null = null;
    const runner = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        handle = c;
        const e: NodeJS.ErrnoException = new Error("EPERM");
        e.code = "EPERM";
        setTimeout(() => c.emit("error", e), 50);
      },
    });
    const r = await runner("setTimeout(() => {}, 15000)", [], 60000);
    assert.strictEqual(r.exitConfirmed, false);
    const h = handle as unknown as ChildProcess;
    h.kill("SIGKILL"); // 子进程随后自然退出
    await new Promise<void>((res) => h.once("exit", () => res()));
    await new Promise((r2) => setTimeout(r2, 50));
    const t1 = await terminateActiveTask(200, () => {});
    assert.strictEqual(t1.had, false);                  // ★exit事件已清理句柄
  });

  await t("V13-C. confirmed退出路径：activeChild已清理→终止 had=false", async () => {
    const runner = makeRunner({ tsNodeBinOverride: "-e" });
    const r = await runner("process.exit(0)", [], 60000);
    assert.strictEqual(r.exitConfirmed, true);          // 正常确认退出
    const t1 = await terminateActiveTask(200, () => {});
    assert.strictEqual(t1.had, false);                  // ★确认路径必清理
  });

  console.log("== 第14版：收口摘要真值对账（A/B/C） ==");

  await t("V14-A. runner先未确认+信号确认同一PID退出：危险解除、标记与锁清理、仍因信号中止failed", async () => {
    const quick = spawn(process.execPath, ["-e", "process.exit(0)"], { shell: false });
    const deadPid: number = quick.pid!;
    await new Promise<void>((res) => quick.once("exit", () => res()));
    await new Promise((r2) => setTimeout(r2, 50));
    const base = path.join(os.tmpdir(), `bfd14-a-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V14A", () => {}), true);
    fs.writeFileSync(marker, JSON.stringify({ taskRunId: "V14A", parentPid: process.pid, unsafeChildPid: deadPid, stage: "rawSales", date: "2026-07-07", state: "terminating", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() }));
    const s = { ...(await runChain(mkCfg({ dates: ["2026-07-06"] }), "V14A-sum", mkDeps([]).deps)) };
    s.childExitUnconfirmed = true;      // runner先未确认
    s.unsafeChildPid = deadPid;
    s.externalSignalAborted = true; s.externalSignal = "SIGTERM";
    const sigTerm: TerminationOutcome = { had: true, confirmedExited: true, pid: deadPid }; // 信号确认同一PID退出
    await finalizeRun(s, Promise.resolve(sigTerm), base, marker, "V14A", () => {});
    assert.strictEqual(s.childExitUnconfirmed, false);  // ★危险解除
    assert.strictEqual(s.unsafeChildPid, null);
    assert.strictEqual(fs.existsSync(marker), false);   // ★标记不存在
    assert.strictEqual(fs.existsSync(base), false);     // ★主锁不存在
    assert.strictEqual(s.lockStillPresent, false);
    assert.strictEqual(s.status, "failed");             // ★仍因 externalSignalAborted failed
  });

  await t("V14-B. 危险PID与信号确认PID不一致：PID_MISMATCH、不清除危险、标记与锁保留", async () => {
    const sleeper = spawn(process.execPath, ["-e", "setTimeout(() => {}, 15000)"], { shell: false });
    await new Promise((r2) => setTimeout(r2, 100));
    const dangerPid: number = sleeper.pid!;                 // 记录的危险子进程（仍alive）
    const quick = spawn(process.execPath, ["-e", "process.exit(0)"], { shell: false });
    const otherPid: number = quick.pid!;                    // 信号确认退出的另一个PID
    await new Promise<void>((res) => quick.once("exit", () => res()));
    const base = path.join(os.tmpdir(), `bfd14-b-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V14B", () => {}), true);
    fs.writeFileSync(marker, JSON.stringify({ taskRunId: "V14B", parentPid: process.pid, unsafeChildPid: dangerPid, stage: "fact", date: "2026-07-06", state: "running", createdAt: new Date().toISOString() }));
    const s = { ...(await runChain(mkCfg({ dates: ["2026-07-06"] }), "V14B-sum", mkDeps([]).deps)) };
    s.childExitUnconfirmed = true;
    s.unsafeChildPid = dangerPid;
    s.externalSignalAborted = true; s.externalSignal = "SIGTERM";
    const sigTerm: TerminationOutcome = { had: true, confirmedExited: true, pid: otherPid };
    const logs: string[] = [];
    await finalizeRun(s, Promise.resolve(sigTerm), base, marker, "V14B", (x) => logs.push(x));
    assert.strictEqual(s.childExitUnconfirmed, true);   // ★不得清除
    assert.strictEqual(s.unsafeChildPid, dangerPid);
    assert.strictEqual(fs.existsSync(marker), true);    // ★标记保留
    assert.strictEqual(fs.existsSync(base), true);      // ★主锁保留
    assert.strictEqual(s.status, "failed");
    assert.ok(logs.some((l) => l.includes("PID_MISMATCH")));
    sleeper.kill("SIGKILL");
    fs.unlinkSync(base); fs.unlinkSync(marker);
  });

  await t("V14-C. 无外部信号，收口复核危险PID已dead：危险解除、标记与锁清理", async () => {
    const quick = spawn(process.execPath, ["-e", "process.exit(0)"], { shell: false });
    const deadPid: number = quick.pid!;
    await new Promise<void>((res) => quick.once("exit", () => res()));
    await new Promise((r2) => setTimeout(r2, 50));
    const base = path.join(os.tmpdir(), `bfd14-c-${process.pid}-${Date.now()}`);
    const marker = `${base}.unsafe`;
    assert.strictEqual(await acquireLock(base, "V14C", () => {}), true);
    fs.writeFileSync(marker, JSON.stringify({ taskRunId: "V14C", parentPid: process.pid, unsafeChildPid: deadPid, stage: "orderProfit", date: "2026-07-08", state: "terminating", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() }));
    const s = { ...(await runChain(mkCfg({ dates: ["2026-07-06"] }), "V14C-sum", mkDeps([]).deps)) };
    s.childExitUnconfirmed = true;
    s.unsafeChildPid = deadPid;
    await finalizeRun(s, null, base, marker, "V14C", () => {});  // ★无外部信号
    assert.strictEqual(s.childExitUnconfirmed, false);
    assert.strictEqual(s.unsafeChildPid, null);
    assert.strictEqual(fs.existsSync(marker), false);
    assert.strictEqual(fs.existsSync(base), false);
    assert.strictEqual(s.lockStillPresent, false);
  });

  console.log("== 危险子进程隔离标记（A~G） ==");

  const umBase = path.join(os.tmpdir(), `bfd-un-${process.pid}-${Date.now()}`);
  const umLock = umBase;                 // 主锁
  const umMarker = `${umBase}.unsafe`;   // unsafe 标记（acquireLock 内部按 主锁+.unsafe 查找）

  await t("A. 父锁PID已dead+unsafeChildPid仍alive：第二次acquireLock=false，主锁不被清理", async () => {
    fs.writeFileSync(umLock, JSON.stringify({ pid: 999999999, taskRunId: "DEAD-PARENT", startedAt: "2026-01-01T00:00:00.000Z" }));
    const markerContent = JSON.stringify({ taskRunId: "X", parentPid: 999999999, unsafeChildPid: process.pid, stage: "rawSales", date: "2026-07-07", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() });
    fs.writeFileSync(umMarker, markerContent);
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(umLock, "A1", (s) => logs.push(s)), false);
    assert.strictEqual(fs.existsSync(umLock), true);   // 主锁未被当陈旧清理
    assert.strictEqual(fs.readFileSync(umMarker, "utf-8"), markerContent); // 标记原样
    assert.ok(logs.some((l) => l.includes("人工处置步骤")));
    fs.unlinkSync(umLock); fs.unlinkSync(umMarker);
  });

  await t("B. unsafeChildPid状态unknown（EPERM）→ fail-closed拒绝", async () => {
    __setPidStateForTest((pid) => (pid === 88888 ? "unknown" : undefined));
    fs.writeFileSync(umMarker, JSON.stringify({ taskRunId: "X", parentPid: 1, unsafeChildPid: 88888, stage: "fact", date: "2026-07-06", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() }));
    assert.strictEqual(await acquireLock(umLock, "B1", () => {}), false);
    assert.strictEqual(fs.existsSync(umMarker), true);
    __setPidStateForTest(null);
    fs.unlinkSync(umMarker);
  });

  await t("C. unsafe标记损坏或无PID → fail-closed且不删除", async () => {
    fs.writeFileSync(umMarker, "broken-marker");
    const logs1: string[] = [];
    assert.strictEqual(await acquireLock(umLock, "C1", (s) => logs1.push(s)), false);
    assert.strictEqual(fs.readFileSync(umMarker, "utf-8"), "broken-marker");
    assert.ok(logs1.some((l) => l.includes("不可解析")));
    // 无 unsafeChildPid 字段
    fs.writeFileSync(umMarker, JSON.stringify({ taskRunId: "X", parentPid: 1, stage: "fact", date: "-", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() }));
    const logs2: string[] = [];
    assert.strictEqual(await acquireLock(umLock, "C2", (s) => logs2.push(s)), false);
    assert.ok(logs2.some((l) => l.includes("缺失")));
    assert.strictEqual(fs.existsSync(umMarker), true);
    fs.unlinkSync(umMarker);
  });

  await t("D. unsafeChildPid明确dead → 仍fail-closed（防PID复用），标记原样", async () => {
    const markerContent = JSON.stringify({ taskRunId: "X", parentPid: 1, unsafeChildPid: 999999998, stage: "orderProfit", date: "2026-07-08", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() });
    fs.writeFileSync(umMarker, markerContent);
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(umLock, "D1", (s) => logs.push(s)), false);
    assert.strictEqual(fs.readFileSync(umMarker, "utf-8"), markerContent);
    assert.ok(logs.some((l) => l.includes("dead") && l.includes("人工处置步骤")));
    fs.unlinkSync(umMarker);
  });

  await t("E. runner返回exitConfirmed=false后：activeChild保留，terminateActiveTask仍能终止危险子进程", async () => {
    let handle: ChildProcess | null = null;
    const runner = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        handle = c;
        const e: NodeJS.ErrnoException = new Error("EPERM");
        e.code = "EPERM";
        setTimeout(() => c.emit("error", e), 50);
      },
    });
    const r = await runner("setTimeout(() => {}, 8000)", [], 60000);
    assert.strictEqual(r.exitConfirmed, false);
    const realPid = (handle as unknown as ChildProcess).pid!;
    assert.strictEqual(pidState(realPid), "alive"); // 危险子进程确实还活着
    // ★关键：activeChild 未被清空，信号收口仍能找到并真实终止它
    const term = await terminateActiveTask(2000, () => {});
    assert.strictEqual(term.had, true);
    assert.strictEqual(term.confirmedExited, true); // SIGTERM 真实杀死并收到 exit
    await new Promise((r2) => setTimeout(r2, 100));
    assert.strictEqual(pidState(realPid), "dead");  // 真实进程已消亡
  });

  await t("F. 未确认后子进程稍后真实exit：activeChild被清理、无重复resolve", async () => {
    let handle: ChildProcess | null = null;
    const runner = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        handle = c;
        const e: NodeJS.ErrnoException = new Error("EPERM");
        e.code = "EPERM";
        setTimeout(() => c.emit("error", e), 50);
      },
    });
    const r = await runner("setTimeout(() => {}, 8000)", [], 60000);
    assert.strictEqual(r.exitConfirmed, false); // runner 已 settle（无重复resolve由settled守卫保证）
    const h = handle as unknown as ChildProcess;
    h.kill("SIGKILL"); // 子进程随后真实退出
    await new Promise<void>((res) => h.once("exit", () => res()));
    await new Promise((r2) => setTimeout(r2, 50));
    // ★真实 exit 事件必须清理 activeChild
    const term = await terminateActiveTask(200, () => {});
    assert.strictEqual(term.had, false);
  });

  await t("G. 双真实进程：父PID已dead的主锁+unsafeChildPid仍alive的标记——两进程均拒绝且文件不变", async () => {
    const gBase = path.join(os.tmpdir(), `bfd-g-${process.pid}-${Date.now()}`);
    // 先启动一个真实存活的"危险子进程"
    const sleeper = spawn(process.execPath, ["-e", "setTimeout(() => {}, 20000)"], { shell: false });
    await new Promise((r2) => setTimeout(r2, 100));
    const lockContent = JSON.stringify({ pid: 999999999, taskRunId: "DEAD-PARENT", startedAt: "2026-01-01T00:00:00.000Z" });
    const markerContent = JSON.stringify({ taskRunId: "G", parentPid: 999999999, unsafeChildPid: sleeper.pid, stage: "rawSales", date: "2026-07-07", reason: "child_exit_unconfirmed", createdAt: new Date().toISOString() });
    fs.writeFileSync(gBase, lockContent);
    fs.writeFileSync(`${gBase}.unsafe`, markerContent);
    const modPath = path.resolve(__dirname, "../src/backfillDailyChain");
    const script = `
      const m = require(process.argv[1]);
      (async () => {
        const ok = await m.acquireLock(process.argv[2], "G-" + process.pid, () => {});
        console.log("ACQ=" + ok);
      })().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(2); });
    `;
    const run = (): Promise<string> => new Promise((resolve) => {
      const c = spawn(process.execPath, ["-r", "ts-node/register/transpile-only", "-e", script, modPath, gBase], {
        cwd: path.resolve(__dirname, ".."), env: process.env, shell: false,
      });
      let out = "";
      c.stdout.on("data", (d: Buffer) => { out += d.toString(); });
      c.stderr.on("data", (d: Buffer) => { out += d.toString(); });
      c.on("close", () => resolve(out));
    });
    const [a, b] = await Promise.all([run(), run()]);
    assert.ok(a.includes("ACQ=false") && b.includes("ACQ=false"), `两进程都应拒绝 A=${JSON.stringify(a)} B=${JSON.stringify(b)}`);
    assert.strictEqual(fs.readFileSync(gBase, "utf-8"), lockContent);           // 主锁未被清理
    assert.strictEqual(fs.readFileSync(`${gBase}.unsafe`, "utf-8"), markerContent); // 标记原样
    sleeper.kill("SIGKILL");
    fs.unlinkSync(gBase); fs.unlinkSync(`${gBase}.unsafe`);
  });

  console.log("== 单实例锁 ==");
  const tmpLock = path.join(os.tmpdir(), `bfd-test-lock-${process.pid}-${Date.now()}`);

  await t("空锁可获取，重复获取被自身有效锁拒绝", async () => {
    assert.strictEqual(await acquireLock(tmpLock, "L1", () => {}), true);
    assert.strictEqual(await acquireLock(tmpLock, "L2", () => {}), false);
    releaseLock(tmpLock);
    assert.strictEqual(fs.existsSync(tmpLock), false);
  });

  await t("陈旧锁（PID明确dead）经cleanup互斥清理重取", async () => {
    fs.writeFileSync(tmpLock, JSON.stringify({ pid: 999999999, taskRunId: "DEAD", startedAt: "2026-01-01T00:00:00.000Z" }));
    assert.strictEqual(await acquireLock(tmpLock, "L3", () => {}), true);
    const cur = JSON.parse(fs.readFileSync(tmpLock, "utf-8"));
    assert.strictEqual(cur.pid, process.pid);
    assert.strictEqual(fs.existsSync(`${tmpLock}.cleanup`), false); // cleanup锁已释放
    releaseLock(tmpLock);
  });

  await t("锁持有者PID状态unknown（EPERM）→ 保守拒绝且不删除", async () => {
    __setPidStateForTest((pid) => (pid === 66666 ? "unknown" : undefined));
    fs.writeFileSync(tmpLock, JSON.stringify({ pid: 66666, taskRunId: "EPERM", startedAt: new Date().toISOString() }));
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(tmpLock, "L3b", (s) => logs.push(s)), false);
    assert.strictEqual(fs.existsSync(tmpLock), true);
    assert.ok(logs.some((l) => l.includes("状态未知")));
    __setPidStateForTest(null);
    fs.unlinkSync(tmpLock);
  });

  await t("锁内容损坏或写入中 → 保守拒绝且不删除（75ms重读后仍拒绝）", async () => {
    fs.writeFileSync(tmpLock, "not-json");
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(tmpLock, "L4", (s) => logs.push(s)), false);
    assert.strictEqual(fs.readFileSync(tmpLock, "utf-8"), "not-json");
    assert.ok(logs.some((l) => l.includes("保守按锁冲突处理")));
    fs.unlinkSync(tmpLock);
  });

  await t("空锁文件（写入中竞态）→ 拒绝且不覆盖", async () => {
    fs.writeFileSync(tmpLock, "");
    assert.strictEqual(await acquireLock(tmpLock, "L5", () => {}), false);
    assert.strictEqual(fs.readFileSync(tmpLock, "utf-8"), "");
    fs.unlinkSync(tmpLock);
  });

  await t("半截JSON → 拒绝且不删除", async () => {
    fs.writeFileSync(tmpLock, '{"pid": 1234, "taskRun');
    assert.strictEqual(await acquireLock(tmpLock, "L6", () => {}), false);
    assert.strictEqual(fs.existsSync(tmpLock), true);
    fs.unlinkSync(tmpLock);
  });

  await t("等待期间锁被正常释放 → 重读发现消失可原子重取", async () => {
    fs.writeFileSync(tmpLock, "not-json");
    const p = acquireLock(tmpLock, "L7", () => {});
    await new Promise((r) => setTimeout(r, 20));
    fs.unlinkSync(tmpLock);
    assert.strictEqual(await p, true);
    releaseLock(tmpLock);
  });

  await t("cleanup锁被存活进程持有 → 不清理主锁，等待后重试主锁失败=冲突退出", async () => {
    fs.writeFileSync(tmpLock, JSON.stringify({ pid: 999999999, taskRunId: "DEAD", startedAt: "2026-01-01T00:00:00.000Z" }));
    fs.writeFileSync(`${tmpLock}.cleanup`, JSON.stringify({ pid: process.pid, taskRunId: "CLEANER", startedAt: new Date().toISOString() }));
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(tmpLock, "L8", (s) => logs.push(s)), false);
    assert.strictEqual(fs.existsSync(tmpLock), true);           // 主锁未被删
    assert.strictEqual(fs.existsSync(`${tmpLock}.cleanup`), true); // 他人cleanup锁未被删
    assert.ok(logs.some((l) => l.includes("正在处理陈旧锁")));
    fs.unlinkSync(tmpLock); fs.unlinkSync(`${tmpLock}.cleanup`);
  });

  await t("cleanup锁损坏 → fail-closed保守拒绝且不删除", async () => {
    fs.writeFileSync(tmpLock, JSON.stringify({ pid: 999999999, taskRunId: "DEAD", startedAt: "2026-01-01T00:00:00.000Z" }));
    fs.writeFileSync(`${tmpLock}.cleanup`, "broken");
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(tmpLock, "L9", (s) => logs.push(s)), false);
    assert.ok(logs.some((l) => l.includes("不可解析") && l.includes("人工核查")));
    assert.strictEqual(fs.readFileSync(`${tmpLock}.cleanup`, "utf-8"), "broken"); // 未被删除或覆盖
    assert.strictEqual(fs.existsSync(tmpLock), true);
    fs.unlinkSync(tmpLock); fs.unlinkSync(`${tmpLock}.cleanup`);
  });

  await t("★残留cleanup锁（持有者已死）→ fail-closed：不自动删除+人工提示+冲突退出", async () => {
    fs.writeFileSync(tmpLock, JSON.stringify({ pid: 999999999, taskRunId: "DEAD", startedAt: "2026-01-01T00:00:00.000Z" }));
    const staleCleanup = JSON.stringify({ pid: 999999998, taskRunId: "DEAD-CLEANER", startedAt: "2026-01-01T00:00:00.000Z" });
    fs.writeFileSync(`${tmpLock}.cleanup`, staleCleanup);
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(tmpLock, "L10", (s) => logs.push(s)), false);
    assert.strictEqual(fs.existsSync(`${tmpLock}.cleanup`), true);                 // 不自动删除
    assert.strictEqual(fs.readFileSync(`${tmpLock}.cleanup`, "utf-8"), staleCleanup); // 内容原样
    assert.strictEqual(fs.existsSync(tmpLock), true);                              // 主锁也不动
    assert.ok(logs.some((l) => l.includes("人工核查")));
    fs.unlinkSync(tmpLock); fs.unlinkSync(`${tmpLock}.cleanup`);
  });

  await t("残留cleanup锁双进程并发：两个真实进程都必须拒绝且都不删除", async () => {
    const rl = path.join(os.tmpdir(), `bfd-cleanupstale-${process.pid}-${Date.now()}`);
    fs.writeFileSync(rl, JSON.stringify({ pid: 999999999, taskRunId: "STALE", startedAt: "2026-01-01T00:00:00.000Z" }));
    const staleCleanup = JSON.stringify({ pid: 999999998, taskRunId: "DEAD-CLEANER", startedAt: "2026-01-01T00:00:00.000Z" });
    fs.writeFileSync(`${rl}.cleanup`, staleCleanup);
    const modPath = path.resolve(__dirname, "../src/backfillDailyChain");
    const script = `
      const m = require(process.argv[1]);
      (async () => {
        const ok = await m.acquireLock(process.argv[2], "CSR-" + process.pid, () => {});
        console.log("ACQ=" + ok);
      })().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(2); });
    `;
    const run = (): Promise<string> => new Promise((resolve) => {
      const c = spawn(process.execPath, ["-r", "ts-node/register/transpile-only", "-e", script, modPath, rl], {
        cwd: path.resolve(__dirname, ".."), env: process.env, shell: false,
      });
      let out = "";
      c.stdout.on("data", (d: Buffer) => { out += d.toString(); });
      c.stderr.on("data", (d: Buffer) => { out += d.toString(); });
      c.on("close", () => resolve(out));
    });
    const [a, b] = await Promise.all([run(), run()]);
    assert.ok(a.includes("ACQ=false") && b.includes("ACQ=false"), `两进程都应拒绝 A=${JSON.stringify(a)} B=${JSON.stringify(b)}`);
    assert.strictEqual(fs.readFileSync(`${rl}.cleanup`, "utf-8"), staleCleanup); // 谁都没删
    assert.strictEqual(fs.existsSync(rl), true);
    fs.unlinkSync(rl); fs.unlinkSync(`${rl}.cleanup`);
  });

  console.log("== defaultRunner 真实路径（真实子进程，非mock TaskResult） ==");

  await t("R1. spawn失败（可执行文件不存在，无有效PID）→ exitConfirmed=true, exit=1", async () => {
    const runner = makeRunner({ execPathOverride: "/nonexistent/no-such-node-binary" });
    const r = await runner("-e", ["1"], 60000);
    assert.strictEqual(r.exitConfirmed, true);
    assert.strictEqual(r.exitCode, 1);
    setActiveChildForTest(null); // 清理登记
  });

  await t("R2. spawn成功后error（如kill失败）且PID仍alive → exitConfirmed=false", async () => {
    let handle: ChildProcess | null = null;
    const runner = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        handle = c;
        const e: NodeJS.ErrnoException = new Error("EPERM (simulated kill failure)");
        e.code = "EPERM";
        setTimeout(() => c.emit("error", e), 50);
      },
    });
    const r = await runner("setTimeout(() => {}, 5000)", [], 60000);
    assert.strictEqual(r.exitConfirmed, false); // 进程仍在跑，不得确认退出
    assert.ok(r.pid !== undefined);
    if (handle) (handle as ChildProcess).kill("SIGKILL"); // 测试收尾清理真实子进程
    setActiveChildForTest(null);
    await new Promise((r2) => setTimeout(r2, 100));
  });

  await t("R3. error后无exit且PID alive → runChain 中止链并标记 childExitUnconfirmed", async () => {
    let handle: ChildProcess | null = null;
    const runner = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        handle = c;
        const e: NodeJS.ErrnoException = new Error("EPERM");
        e.code = "EPERM";
        setTimeout(() => c.emit("error", e), 50);
      },
    });
    // 用单日期单阶段无法直接构造——直接以runner结果驱动链：包一层只对FACT日期1生效
    const chainRunner: TaskRunner = async (entry, args, timeoutMs) => {
      if (entry.includes("syncLingxingDailyToDb") && args[0] === "--date=2026-07-06") {
        return runner("setTimeout(() => {}, 5000)", [], timeoutMs); // 真实子进程真实error路径
      }
      return okResult();
    };
    const deps: ChainDeps = { runner: chainRunner, nowFn: () => NOW, sleepFn: () => Promise.resolve(), log: () => {}, shutdown: mkShutdown() };
    const s = await runChain(mkCfg(), "R3", deps);
    assert.strictEqual(s.childExitUnconfirmed, true);
    assert.ok(s.unsafeChildPid !== null);
    assert.strictEqual(s.status, "failed");
    if (handle) (handle as ChildProcess).kill("SIGKILL");
    setActiveChildForTest(null);
    await new Promise((r2) => setTimeout(r2, 100));
  });

  await t("R4. error时PID已明确dead → exitConfirmed=true", async () => {
    const runner = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        // 摘除runner的exit处理（保留error路径），等真实进程消亡后再触发error
        c.removeAllListeners("exit");
        const poll = setInterval(() => {
          if (c.pid !== undefined && pidState(c.pid) === "dead") {
            clearInterval(poll);
            const e: NodeJS.ErrnoException = new Error("late error after death");
            e.code = "EPERM";
            c.emit("error", e);
          }
        }, 20);
      },
    });
    const r = await runner("process.exit(0)", [], 60000);
    assert.strictEqual(r.exitConfirmed, true); // PID核验明确dead → 按已退出
    setActiveChildForTest(null);
  });

  console.log("== 双进程真实并发抢陈旧锁 ==");

  await t("两个真实Node进程同时抢同一把陈旧锁：恰好一个成功，失败者不删成功者新锁", async () => {
    const raceLock = path.join(os.tmpdir(), `bfd-race2p-${process.pid}-${Date.now()}`);
    fs.writeFileSync(raceLock, JSON.stringify({ pid: 999999999, taskRunId: "STALE", startedAt: "2026-01-01T00:00:00.000Z" }));
    const modPath = path.resolve(__dirname, "../src/backfillDailyChain");
    // 脚本串含 backfillDailyChain 字样（经 modPath），胜者 cmdline 可被对方判为有效锁
    const script = `
      const m = require(process.argv[1]);
      (async () => {
        const ok = await m.acquireLock(process.argv[2], "RACER-" + process.pid, () => {});
        console.log("ACQ=" + ok);
        if (ok) {
          await new Promise((r) => setTimeout(r, 800));
          console.log("LOCK_EXISTS=" + require("fs").existsSync(process.argv[2]));
        }
      })().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(2); });
    `;
    const runRacer = (): Promise<{ out: string; code: number | null }> => new Promise((resolve) => {
      const c = spawn(process.execPath, ["-r", "ts-node/register/transpile-only", "-e", script, modPath, raceLock], {
        cwd: path.resolve(__dirname, ".."), env: process.env, shell: false,
      });
      let out = "";
      c.stdout.on("data", (d: Buffer) => { out += d.toString(); });
      c.stderr.on("data", (d: Buffer) => { out += d.toString(); });
      c.on("close", (code) => resolve({ out, code }));
    });
    const [a, b] = await Promise.all([runRacer(), runRacer()]);
    const trues = [a, b].filter((r) => r.out.includes("ACQ=true"));
    const falses = [a, b].filter((r) => r.out.includes("ACQ=false"));
    assert.strictEqual(trues.length, 1, `期望恰好1个成功，实际输出 A=${JSON.stringify(a.out)} B=${JSON.stringify(b.out)}`);
    assert.strictEqual(falses.length, 1);
    assert.ok(trues[0].out.includes("LOCK_EXISTS=true"), "成功者持有期间主锁必须始终存在");
    try { fs.unlinkSync(raceLock); } catch { /* 残留清理 */ }
    try { fs.unlinkSync(`${raceLock}.cleanup`); } catch { /* 无残留则忽略 */ }
  });

  console.log("== 可中断 sleep（真实计时） ==");

  await t("长interval期间置停止标志 → 约1秒内退出，不等完整interval", async () => {
    const shutdown = mkShutdown();
    const deps: ChainDeps = {
      runner: async () => okResult(),
      nowFn: () => Date.now(),
      sleepFn: (ms) => new Promise((r) => setTimeout(r, ms)),
      log: () => {}, shutdown,
    };
    const cfg = mkCfg({ dates: ["2026-07-06", "2026-07-07"], intervalSeconds: 10, deadlineHHmm: "23:59" });
    setTimeout(() => { shutdown.requested = true; shutdown.signal = "SIGTERM"; }, 300);
    const st = Date.now();
    const s = await runChain(cfg, "SLP1", deps);
    const elapsed = Date.now() - st;
    assert.ok(elapsed < 2000, `应约1秒内退出，实际 ${elapsed}ms`);
    assert.strictEqual(s.externalSignalAborted, true);
    assert.strictEqual(s.status, "failed");
  });

  await t("sleep期间到达deadline → 立即结束等待并中止，不等完整interval", async () => {
    // 虚拟时钟：起点=当日19:10(上海)前400ms，随真实时间推进
    const dl = deadlineToMs("19:10", NOW);
    const virtStart = dl - 400;
    const realStart = Date.now();
    const deps: ChainDeps = {
      runner: async () => okResult(),
      nowFn: () => virtStart + (Date.now() - realStart),
      sleepFn: (ms) => new Promise((r) => setTimeout(r, ms)),
      log: () => {},
      shutdown: mkShutdown(),
    };
    const cfg = mkCfg({ dates: ["2026-07-06", "2026-07-07"], intervalSeconds: 10 });
    const st = Date.now();
    const s = await runChain(cfg, "SLP2", deps);
    const elapsed = Date.now() - st;
    assert.ok(elapsed < 2000, `应在死线到达后立即退出，实际 ${elapsed}ms`);
    assert.strictEqual(s.deadlineAborted, true);
    assert.strictEqual(s.status, "failed");
  });

  console.log("== 外部信号收口（fake 子进程） ==");

  await t("terminateActiveTask：SIGTERM 后子进程退出 → confirmedExited=true", async () => {
    const events: string[] = [];
    setActiveChildForTest(mkFakeChild(events, { exitOnTerm: true }));
    const r = await terminateActiveTask(1000, () => {});
    assert.deepStrictEqual({ had: r.had, confirmed: r.confirmedExited }, { had: true, confirmed: true });
    assert.deepStrictEqual(events, ["kill:SIGTERM"]);
  });

  await t("terminateActiveTask：SIGTERM 无效 → 宽限后 SIGKILL（退出=confirmed）", async () => {
    const events: string[] = [];
    setActiveChildForTest(mkFakeChild(events, { exitOnTerm: false }));
    const r = await terminateActiveTask(50, () => {});
    assert.deepStrictEqual({ had: r.had, confirmed: r.confirmedExited }, { had: true, confirmed: true });
    assert.deepStrictEqual(events, ["kill:SIGTERM", "kill:SIGKILL"]);
  });

  await t("terminateActiveTask：无活动子进程 → had=false", async () => {
    setActiveChildForTest(null);
    const r = await terminateActiveTask(50, () => {});
    assert.strictEqual(r.had, false);
  });

  console.log("== 外部信号竞态（集成场景） ==");

  await t("A. RAW运行中收SIGTERM：终止+dirty，后续零启动，摘要完整failed，锁序正确", async () => {
    const lockA = path.join(os.tmpdir(), `bfd-race-a-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(lockA, "RACE-A", () => {}), true);
    const shutdown = mkShutdown();
    const calls: Call[] = [];
    const lockSeenDuringKill: boolean[] = [];
    const runner: TaskRunner = (entry, args, timeoutMs) => {
      const date = args[0].startsWith("--date=") ? args[0].slice(7) : args[0];
      calls.push({ entry, date, timeoutMs });
      if (entry.includes("syncLingxingToRawFeishu") && date === "2026-07-07") {
        shutdown.requested = true;
        shutdown.signal = "SIGTERM";
        lockSeenDuringKill.push(fs.existsSync(lockA));
        return Promise.resolve(signalResult());
      }
      return Promise.resolve(okResult());
    };
    const deps: ChainDeps = { runner, nowFn: () => NOW, sleepFn: () => Promise.resolve(), log: () => {}, shutdown };
    const s = await runChain(mkCfg(), "RACE-A", deps);
    assert.strictEqual(fs.existsSync(lockA), true);
    assert.deepStrictEqual(lockSeenDuringKill, [true]);
    assert.deepStrictEqual(s.rawSales.failed, ["2026-07-07"]);
    assert.deepStrictEqual(s.dirtyDates, [{ stage: "rawSales", date: "2026-07-07", reason: "signal_exit_during_rewrite" }]);
    assert.strictEqual(calls.length, 7);
    assert.ok(!calls.some((c) => c.entry.includes("syncOrderProfitDaily")));
    assert.strictEqual(s.externalSignalAborted, true);
    assert.strictEqual(s.externalSignal, "SIGTERM");
    assert.strictEqual(s.status, "failed");
    assert.strictEqual(safeReleaseLock(lockA, { had: true, confirmedExited: true, pid: 424242 }, () => {}).releasedOrAbsent, true);
    assert.strictEqual(fs.existsSync(lockA), false);
  });

  await t("B. FACT运行中收SIGTERM：后续零启动、不记dirty、externalSignalAborted", async () => {
    const shutdown = mkShutdown();
    const calls: Call[] = [];
    const runner: TaskRunner = (entry, args, timeoutMs) => {
      const date = args[0].startsWith("--date=") ? args[0].slice(7) : args[0];
      calls.push({ entry, date, timeoutMs });
      if (entry.includes("syncLingxingDailyToDb") && date === "2026-07-06") {
        shutdown.requested = true;
        shutdown.signal = "SIGTERM";
        return Promise.resolve(signalResult());
      }
      return Promise.resolve(okResult());
    };
    const deps: ChainDeps = { runner, nowFn: () => NOW, sleepFn: () => Promise.resolve(), log: () => {}, shutdown };
    const s = await runChain(mkCfg(), "RACE-B", deps);
    assert.strictEqual(calls.length, 1);
    assert.deepStrictEqual(s.dirtyDates, []);
    assert.strictEqual(s.externalSignalAborted, true);
    assert.strictEqual(s.status, "failed");
  });

  await t("C. 日期间sleep时收信号：不启动下一任务，摘要完整，正常放锁", async () => {
    const lockC = path.join(os.tmpdir(), `bfd-race-c-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(lockC, "RACE-C", () => {}), true);
    const shutdown = mkShutdown();
    const calls: Call[] = [];
    const runner: TaskRunner = (entry, args, timeoutMs) => {
      const date = args[0].startsWith("--date=") ? args[0].slice(7) : args[0];
      calls.push({ entry, date, timeoutMs });
      return Promise.resolve(okResult());
    };
    const sleepFn = (_ms: number): Promise<void> => {
      shutdown.requested = true;
      shutdown.signal = "SIGINT";
      return Promise.resolve();
    };
    const deps: ChainDeps = { runner, nowFn: () => NOW, sleepFn, log: () => {}, shutdown };
    const s = await runChain(mkCfg({ intervalSeconds: 1 }), "RACE-C", deps);
    assert.strictEqual(calls.length, 1);
    assert.strictEqual(s.externalSignalAborted, true);
    assert.strictEqual(s.externalSignal, "SIGINT");
    assert.strictEqual(s.status, "failed");
    assert.strictEqual(s.dirtyDates.length, 0);
    assert.strictEqual(safeReleaseLock(lockC, { had: false, confirmedExited: true }, () => {}).releasedOrAbsent, true);
  });

  await t("D. SIGKILL后无法确认退出：不打印确认、CRITICAL、保守不放锁", async () => {
    const events: string[] = [];
    const stubborn: KillableChild = {
      pid: process.pid,
      kill(sig?: NodeJS.Signals): boolean { events.push(`kill:${sig}`); return true; },
      once(): unknown { return this; },
    };
    setActiveChildForTest(stubborn);
    const logs: string[] = [];
    const r = await terminateActiveTask(30, (s) => logs.push(s), 30);
    assert.strictEqual(r.confirmedExited, false);
    assert.deepStrictEqual(events, ["kill:SIGTERM", "kill:SIGKILL"]);
    assert.ok(logs.some((l) => l.includes("[CRITICAL]")));
    assert.ok(!logs.some((l) => l.includes("已确认退出")));
    const lockD = path.join(os.tmpdir(), `bfd-race-d-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(lockD, "RACE-D", () => {}), true);
    const logs2: string[] = [];
    assert.strictEqual(safeReleaseLock(lockD, r, (s) => logs2.push(s)).releasedOrAbsent, false);
    assert.strictEqual(fs.existsSync(lockD), true);
    assert.ok(logs2.some((l) => l.includes("CRITICAL")));
    fs.unlinkSync(lockD);
    setActiveChildForTest(null); // 未确认句柄按第13版设计被保留——测试显式复位
  });

  await t("E. 致命兜底不得绕过安全放锁：safeReleaseLock=false 后 main级异常，锁仍在", async () => {
    __setPidStateForTest((pid) => (pid === process.pid ? "alive" : undefined));
    const lockE = path.join(os.tmpdir(), `bfd-race-e-${process.pid}-${Date.now()}`);
    assert.strictEqual(await acquireLock(lockE, "RACE-E", () => {}), true);
    const unconfirmed: TerminationOutcome = { had: true, confirmedExited: false, pid: process.pid };
    terminationState.outcome = unconfirmed;
    assert.strictEqual(safeReleaseLock(lockE, unconfirmed, () => {}).releasedOrAbsent, false);
    const logsE: string[] = [];
    assert.strictEqual(fatalReleaseLock(lockE, (s) => logsE.push(s)).releasedOrAbsent, false);
    assert.strictEqual(fs.existsSync(lockE), true);
    assert.ok(logsE.some((l) => l.includes("CRITICAL")));
    terminationState.outcome = null;
    __setPidStateForTest(null);
    fs.unlinkSync(lockE);
  });

  await t("F. kill抛EPERM（PID仍alive）→ confirmedExited=false + CRITICAL", async () => {
    const logsF: string[] = [];
    const eperm: KillableChild = {
      pid: process.pid,
      kill(): boolean { const e: NodeJS.ErrnoException = new Error("EPERM"); e.code = "EPERM"; throw e; },
      once(): unknown { return this; },
    };
    setActiveChildForTest(eperm);
    const r = await terminateActiveTask(30, (s) => logsF.push(s), 30);
    assert.strictEqual(r.confirmedExited, false);
    assert.ok(logsF.some((l) => l.includes("[CRITICAL]") && l.includes("EPERM")));
    // ★第13版：未确认→句柄保留，第二次终止仍 had=true
    const r2 = await terminateActiveTask(30, () => {}, 30);
    assert.strictEqual(r2.had, true);
    setActiveChildForTest(null);
  });

  await t("G. kill抛ESRCH → 明确不存在 → confirmedExited=true", async () => {
    const esrch: KillableChild = {
      pid: 999999999,
      kill(): boolean { const e: NodeJS.ErrnoException = new Error("ESRCH"); e.code = "ESRCH"; throw e; },
      once(): unknown { return this; },
    };
    setActiveChildForTest(esrch);
    const r = await terminateActiveTask(30, () => {}, 30);
    assert.strictEqual(r.confirmedExited, true);
  });

  await t("F2. kill返回false且PID仍alive → 未证实，最终confirmedExited=false", async () => {
    const logsF2: string[] = [];
    const refusing: KillableChild = {
      pid: process.pid,
      kill(): boolean { return false; }, // 信号发送失败
      once(): unknown { return this; },
    };
    setActiveChildForTest(refusing);
    const r = await terminateActiveTask(30, (s) => logsF2.push(s), 30);
    assert.strictEqual(r.confirmedExited, false);
    assert.ok(logsF2.some((l) => l.includes("发送失败")));
    setActiveChildForTest(null); // 未确认句柄保留——显式复位
  });

  } // end 核心区（!ONLY_REAL9）

  if (!SKIP_REAL9) {
  console.log("== 第9版：前置标记生命周期（真实进程A~G） ==");

  const P_TMP = fs.mkdtempSync(path.join(os.tmpdir(), "bfd9-"));
  const modPath = path.resolve(__dirname, "../src/backfillDailyChain");

  const parentScript = `
    const m = require(process.argv[1]);
    const lock = process.argv[2];
    const childCode = process.argv[3];
    const timeoutMin = Number(process.argv[4] || "15");
    (async () => {
      const ok = await m.acquireLock(lock, "P-" + process.pid, () => {});
      if (!ok) { console.log("PACQ=false"); process.exit(3); }
      console.log("PACQ=true");
      const base = m.makeRunner({ tsNodeBinOverride: "-e" });
      const runner = (e, a, tms, ev) => base(childCode, [], tms, ev);
      const cfg = { mode: "execute", dates: ["2026-07-06"], deadlineHHmm: "23:59", intervalSeconds: 0, taskTimeoutMinutes: timeoutMin };
      const deps = { runner, nowFn: () => Date.now(), sleepFn: (ms) => new Promise((r) => setTimeout(r, ms)),
        log: () => {}, shutdown: { requested: false, signal: null }, unsafeMarkerFile: lock + ".unsafe" };
      const s = await m.runChain(cfg, "PRT", deps);
      console.log("CHAIN_DONE=" + s.status);
    })().catch((e) => { console.error(e); process.exit(2); });
  `;

  const spawnParent = (lock: string, childCode: string, timeoutMin: string): ChildProcess =>
    spawn(process.execPath, ["-r", "ts-node/register/transpile-only", "-e", parentScript, modPath, lock, childCode, timeoutMin], {
      cwd: path.resolve(__dirname, ".."), env: process.env, shell: false, stdio: ["ignore", "pipe", "pipe"],
    });

  const pollMarker = async (marker: string, cond: (m: Record<string, unknown>) => boolean, timeoutMs: number): Promise<Record<string, unknown> | null> => {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        const m = JSON.parse(fs.readFileSync(marker, "utf-8"));
        if (cond(m)) return m;
      } catch { /* 尚未写入 */ }
      await new Promise((r) => setTimeout(r, 100));
    }
    return null;
  };

  const runRacers = async (lock: string): Promise<string[]> => {
    const script = `
      const m = require(process.argv[1]);
      (async () => {
        const ok = await m.acquireLock(process.argv[2], "R9-" + process.pid, () => {});
        console.log("ACQ=" + ok);
      })().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(2); });
    `;
    const run = (): Promise<string> => new Promise((resolve) => {
      const c = spawn(process.execPath, ["-r", "ts-node/register/transpile-only", "-e", script, modPath, lock], {
        cwd: path.resolve(__dirname, ".."), env: process.env, shell: false,
      });
      let out = "";
      c.stdout.on("data", (d: Buffer) => { out += d.toString(); });
      c.stderr.on("data", (d: Buffer) => { out += d.toString(); });
      c.on("close", () => resolve(out));
    });
    return Promise.all([run(), run()]);
  };

  await t("9A. 子任务运行中SIGKILL父进程：子存活+标记在盘+双新进程均拒绝", async () => {
    const lock = path.join(P_TMP, "a.lock");
    const marker = `${lock}.unsafe`;
    const parent = spawnParent(lock, "setTimeout(() => {}, 30000)", "15");
    const m = await pollMarker(marker, (x) => x.state === "running" && Number.isInteger(x.unsafeChildPid), 15000);
    assert.ok(m, "应在15s内观察到 state=running 的标记");
    const childPid = m!.unsafeChildPid as number;
    parent.kill("SIGKILL"); // ★父进程被SIGKILL
    await new Promise<void>((res) => parent.once("exit", () => res()));
    assert.strictEqual(pidState(childPid), "alive");      // 危险子进程仍存活
    assert.strictEqual(fs.existsSync(marker), true);      // 标记已在盘上（前置式）
    const [ra, rb] = await runRacers(lock);
    assert.ok(ra.includes("ACQ=false") && rb.includes("ACQ=false"), `双新进程均须拒绝 A=${ra} B=${rb}`);
    assert.strictEqual(fs.existsSync(marker), true);      // 标记未被删
    process.kill(childPid, "SIGKILL");                     // 测试收尾
    try { fs.unlinkSync(lock); } catch {} try { fs.unlinkSync(marker); } catch {}
  });

  await t("9B. SIGTERM→SIGKILL等待窗内SIGKILL父进程：标记terminating在盘+新实例拒绝", async () => {
    const lock = path.join(P_TMP, "b.lock");
    const marker = `${lock}.unsafe`;
    // 子任务无视SIGTERM；单任务超时约1.2s → 进入10s SIGKILL宽限窗
    const parent = spawnParent(lock, 'process.on("SIGTERM", () => {}); setTimeout(() => {}, 30000)', "0.02");
    const m = await pollMarker(marker, (x) => x.state === "terminating", 20000);
    assert.ok(m, "应观察到 state=terminating");
    const childPid = m!.unsafeChildPid as number;
    parent.kill("SIGKILL"); // ★宽限窗内击杀父进程
    await new Promise<void>((res) => parent.once("exit", () => res()));
    assert.strictEqual(fs.existsSync(marker), true);
    const [ra, rb] = await runRacers(lock);
    assert.ok(ra.includes("ACQ=false") && rb.includes("ACQ=false"));
    if (Number.isInteger(childPid) && pidState(childPid) === "alive") process.kill(childPid, "SIGKILL");
    try { fs.unlinkSync(lock); } catch {} try { fs.unlinkSync(marker); } catch {}
  });

  await t("9C. TOCTOU：入口检查后他进程写入标记 → 最终false且自建主锁已释放", async () => {
    const lock = path.join(P_TMP, "c.lock");
    const marker = `${lock}.unsafe`;
    const markerContent = JSON.stringify({ taskRunId: "TOCTOU", parentPid: 1, unsafeChildPid: process.pid, stage: "fact", date: "2026-07-06", state: "running", createdAt: new Date().toISOString() });
    const logs: string[] = [];
    const ok = await acquireLock(lock, "C9", (s) => logs.push(s), {
      afterEntryCheck: () => fs.writeFileSync(marker, markerContent), // 模拟他进程此刻写入
    });
    assert.strictEqual(ok, false);
    assert.strictEqual(fs.existsSync(lock), false);   // 自己刚建的主锁已释放
    assert.strictEqual(fs.readFileSync(marker, "utf-8"), markerContent); // 标记未删
    assert.ok(logs.some((l) => l.includes("建锁后复查")));
    try { fs.unlinkSync(marker); } catch {}
  });

  await t("9D. spawn前标记创建EACCES（确定性注入）→ 子进程零启动、unsafeMarkerWriteFailed、全链中止", async () => {
    const marker = path.join(P_TMP, "x.unsafe");
    const calls: Call[] = [];
    const runner: TaskRunner = (entry, args, timeoutMs) => {
      calls.push({ entry, date: args[0], timeoutMs });
      return Promise.resolve(okResult());
    };
    const deps: ChainDeps = { runner, nowFn: () => NOW, sleepFn: () => Promise.resolve(), log: () => {}, shutdown: mkShutdown(), unsafeMarkerFile: marker };
    const s = await withFsFaults(
      [{ method: "writeFileSync", path: marker, code: "EACCES", active: () => true }],
      () => runChain(mkCfg(), "D9", deps),
    );
    assert.strictEqual(calls.length, 0);                 // ★零spawn
    assert.strictEqual(s.unsafeMarkerWriteFailed, true);
    assert.strictEqual(s.unsafeMarkerErrorCode, "EACCES");
    assert.strictEqual(s.status, "failed");
    assert.strictEqual(fs.existsSync(marker), false);
  });

  await t("9E. spawn后标记更新失败（确定性注入tmp写入）：子进程被立即终止、全链中止、摘要与磁盘一致", async () => {
    const marker = path.join(P_TMP, "y.unsafe");
    const tmpPath = `${marker}.tmp.${process.pid}`;
    let realPid: number | undefined;
    let updatePhase = false;
    const base = makeRunner({
      tsNodeBinOverride: "-e",
      onSpawned: (c) => {
        realPid = c.pid;
        updatePhase = true; // 此后对 tmp 的写入注入 EACCES → running 更新失败
      },
    });
    const runner: TaskRunner = (_e, _a, tms, ev) => base("setTimeout(() => {}, 15000)", [], tms, ev);
    const deps: ChainDeps = { runner, nowFn: () => Date.now(), sleepFn: (ms) => new Promise((r) => setTimeout(r, ms)), log: () => {}, shutdown: mkShutdown(), unsafeMarkerFile: marker };
    const s = await withFsFaults(
      [{ method: "writeFileSync", path: tmpPath, code: "EACCES", active: () => updatePhase }],
      () => runChain(mkCfg({ dates: ["2026-07-06"], deadlineHHmm: "23:59" }), "E9", deps),
    );
    assert.strictEqual(s.unsafeMarkerWriteFailed, true);
    assert.strictEqual(s.unsafeMarkerErrorCode, "EACCES");
    assert.strictEqual(s.status, "failed");
    assert.ok(realPid !== undefined);
    // ★子进程已被立即终止（SIGTERM链路，最多等数秒收敛）
    const deadBy = Date.now() + 5000;
    while (pidState(realPid!) !== "dead" && Date.now() < deadBy) await new Promise((r) => setTimeout(r, 100));
    assert.strictEqual(pidState(realPid!), "dead");
    // 摘要与磁盘一致：本注入下清理unlink为真实操作且成功→标记已删、state=null
    assert.strictEqual(fs.existsSync(marker), false);
    assert.strictEqual(s.unsafeMarkerState, null);
    assert.strictEqual(s.unsafeMarkerCleanupFailed, false);
  });

  await t("9F. 子进程正常exit：标记删除、后续可正常获取锁", async () => {
    const lock = path.join(P_TMP, "f.lock");
    const marker = `${lock}.unsafe`;
    const base = makeRunner({ tsNodeBinOverride: "-e" });
    const runner: TaskRunner = (_e, _a, tms, ev) => base("process.exit(0)", [], tms, ev);
    const deps: ChainDeps = { runner, nowFn: () => Date.now(), sleepFn: (ms) => new Promise((r) => setTimeout(r, ms)), log: () => {}, shutdown: mkShutdown(), unsafeMarkerFile: marker };
    const s = await runChain(mkCfg({ dates: ["2026-07-06"], deadlineHHmm: "23:59" }), "F9", deps);
    assert.strictEqual(s.status, "success");
    assert.strictEqual(fs.existsSync(marker), false);   // ★标记已删
    assert.strictEqual(await acquireLock(lock, "F9b", () => {}), true); // 后续可正常获取
    releaseLock(lock);
  });

  await t("9G. 标记state=starting且PID为null（starting期父进程崩溃）→ 后续fail-closed", async () => {
    const lock = path.join(P_TMP, "g.lock");
    const marker = `${lock}.unsafe`;
    fs.writeFileSync(marker, JSON.stringify({ taskRunId: "G9", parentPid: 999999999, unsafeChildPid: null, stage: "fact", date: "2026-07-06", state: "starting", createdAt: new Date().toISOString() }));
    const logs: string[] = [];
    assert.strictEqual(await acquireLock(lock, "G9", (s) => logs.push(s)), false);
    assert.strictEqual(fs.existsSync(marker), true);
    assert.ok(logs.some((l) => l.includes("starting") || l.includes("缺失")));
    try { fs.unlinkSync(marker); } catch {}
  });

  await t("V11-E. CLI每次运行只输出一次SUMMARY_JSON且在收口后（execute过期死线路径+无残留）", async () => {
    // 用已过死线的 execute：获取锁→deadlineAborted→finalize收口→输出唯一SUMMARY→退出非0
    const cliScript = path.resolve(__dirname, "../src/backfillDailyChain.ts");
    const out: string = await new Promise((resolve) => {
      const c = spawn(process.execPath, ["-r", "ts-node/register/transpile-only", cliScript,
        "--execute", "--deadline=00:00", "--start-date=2026-07-06", "--end-date=2026-07-06"], {
        cwd: path.resolve(__dirname, ".."), env: process.env, shell: false,
      });
      let o = "";
      c.stdout.on("data", (d: Buffer) => { o += d.toString(); });
      c.stderr.on("data", (d: Buffer) => { o += d.toString(); });
      c.on("close", (code) => resolve(`${o}\nEXIT=${code}`));
    });
    const summaryCount = (out.match(/SUMMARY_JSON=/g) ?? []).length;
    assert.strictEqual(summaryCount, 1, `SUMMARY_JSON 应恰好1次，实际${summaryCount}`);
    assert.ok(out.includes("EXIT=1"));                       // deadlineAborted → 非0
    assert.ok(out.includes('"deadlineAborted":true'));
    // 收口后输出：SUMMARY 出现在最后（其后无锁/标记操作日志）
    const idx = out.indexOf("SUMMARY_JSON=");
    assert.ok(!out.slice(idx).includes("[收口]"), "SUMMARY_JSON 后不得再有收口动作");
    // 无残留（真实 /tmp 路径，本sandbox隔离）
    assert.strictEqual(fs.existsSync("/tmp/lingxing-backfill-daily-chain.lock"), false);
    assert.strictEqual(fs.existsSync("/tmp/lingxing-backfill-daily-chain.lock.unsafe"), false);
  });

  try {
    for (const f of fs.readdirSync(P_TMP)) {
      const p = path.join(P_TMP, f);
      if (fs.statSync(p).isDirectory()) {
        try { fs.chmodSync(p, 0o755); } catch {}
        for (const f2 of fs.readdirSync(p)) { try { fs.unlinkSync(path.join(p, f2)); } catch {} }
        try { fs.rmdirSync(p); } catch {}
      } else { try { fs.unlinkSync(p); } catch {} }
    }
    fs.rmdirSync(P_TMP);
  } catch { /* 残留由 /tmp 自清 */ }
  } // end 第9版重型区

  console.log("\n" + "=".repeat(50));
  console.log(`测试结果: ${passed} 通过 / ${failed} 失败`);
  if (failed > 0) {
    console.log(`失败用例: ${failures.join(", ")}`);
    process.exitCode = 1;
  }
}

main().catch((e) => { console.log(`[致命] ${e}`); process.exitCode = 1; });
