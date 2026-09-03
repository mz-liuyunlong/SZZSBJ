/**
 * runNotifyTests.ts - 批B通报测试模式串行执行器（notify:test:all）v2
 *
 * 顺序：无订单 → 低利润 → 业绩日报 → 自动广告检查
 * 规则（2026-07-11 第2版定稿）：
 *   1. 严格串行，禁止并发；任务之间至少间隔 60 秒（防飞书频控）
 *   2. 每个任务独立记录：exitCode / notifySentMarker / durationSeconds
 *   3. ★成功条件 = exitCode=0 且 输出含 NOTIFY_TEST_SENT=1
 *      （exit 0 但未实际发送不得判成功）
 *   4. 单任务失败不阻断后续任务；任一任务未确认发送，整体 exit 1
 *   5. 实时透传子进程日志，同时捕获 stdout/stderr 供标记判定
 *   6. 四项全部通过时，测试群应实际收到4类【测试】消息
 *
 * 用法：npm run notify:test:all
 */

import { spawn } from "child_process";

const GAP_MS = 60000;
const SENT_MARKER = "NOTIFY_TEST_SENT=1";

interface TaskDef {
  name: string;
  cmd: string;
  args: string[];
}

const TASKS: TaskDef[] = [
  { name: "无订单通报", cmd: "npx", args: ["ts-node", "src/noOrderNotify.ts", "--test-send"] },
  { name: "低利润通报", cmd: "npx", args: ["ts-node", "src/lowProfitNotify.ts", "--test-send"] },
  { name: "业绩日报", cmd: "npm", args: ["run", "report:performance", "--", "--mode=daily", "--test-send"] },
  { name: "自动广告检查", cmd: "npx", args: ["ts-node", "src/checkAutoAdSearchTermImport.ts", "--test-send", "--force-preview-test"] },
];

interface TaskResult {
  name: string;
  exitCode: number;
  notifySentMarker: boolean;
  durationSeconds: number;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** 运行子进程：实时透传日志，同时捕获输出用于 NOTIFY_TEST_SENT 标记判定 */
function runTask(t: TaskDef): Promise<{ exitCode: number; output: string }> {
  return new Promise((resolve) => {
    const child = spawn(t.cmd, t.args, { cwd: process.cwd(), env: process.env });
    let output = "";
    child.stdout.on("data", (d: Buffer) => {
      const s = d.toString();
      output += s;
      process.stdout.write(s);
    });
    child.stderr.on("data", (d: Buffer) => {
      const s = d.toString();
      output += s;
      process.stderr.write(s);
    });
    child.on("close", (code) => resolve({ exitCode: code ?? 1, output }));
    child.on("error", (e) => {
      console.log(`[错误] 子进程启动失败: ${e.message}`);
      resolve({ exitCode: 1, output });
    });
  });
}

async function main(): Promise<void> {
  console.log("=".repeat(60));
  console.log("批B通报测试模式串行执行（--test-send，只发测试群）");
  console.log(`任务数: ${TASKS.length} ｜ 任务间隔: ${GAP_MS / 1000}s（防频控，禁止并发）`);
  console.log(`成功条件: exitCode=0 且 输出含 ${SENT_MARKER}`);
  console.log("=".repeat(60));

  const results: TaskResult[] = [];
  for (let i = 0; i < TASKS.length; i++) {
    const t = TASKS[i];
    console.log(`\n[${i + 1}/${TASKS.length}] ▶ ${t.name}`);
    console.log("-".repeat(60));
    const started = Date.now();
    const r = await runTask(t);
    const durationSeconds = Number(((Date.now() - started) / 1000).toFixed(1));
    const notifySentMarker = r.output.includes(SENT_MARKER);
    results.push({ name: t.name, exitCode: r.exitCode, notifySentMarker, durationSeconds });
    console.log("-".repeat(60));
    console.log(`[${i + 1}/${TASKS.length}] ${t.name} 完成: exit=${r.exitCode} ｜ 发送确认=${notifySentMarker ? "是" : "否"} ｜ 耗时=${durationSeconds}s`);
    if (i < TASKS.length - 1) {
      console.log(`等待 ${GAP_MS / 1000}s 后执行下一任务...`);
      await sleep(GAP_MS);
    }
  }

  console.log("\n" + "=".repeat(60));
  console.log("测试汇总：");
  let allOk = true;
  for (const r of results) {
    const ok = r.exitCode === 0 && r.notifySentMarker;
    if (!ok) allOk = false;
    console.log(`  ${ok ? "✅" : "❌"} ${r.name} ｜ exit=${r.exitCode} ｜ 确认发送=${r.notifySentMarker ? "是" : "否"} ｜ 耗时=${r.durationSeconds}s`);
  }
  const passCount = results.filter((r) => r.exitCode === 0 && r.notifySentMarker).length;
  console.log(`通过 ${passCount} / ${results.length}（通过=exit 0 且确认发送）`);
  if (!allOk) process.exitCode = 1;
}

main().catch((e) => {
  console.log(`[致命错误] ${e instanceof Error ? e.message : String(e)}`);
  process.exitCode = 1;
});
