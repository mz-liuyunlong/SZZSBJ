/**
 * checkDeploySyncSentinel.ts — 代码一致性哨兵（SOP §3.11.7-4 的自动化落地，2026-08-24 需求方立规）
 *
 * 定位：确定性规则引擎（同输入必同输出，归 BIZ，非 AI）。跑在生产，检查「生产侧不可抵赖项」，
 *       异常才发飞书通报需求方；Mac 侧未部署改动不属于本哨兵职责（生产够不到 Mac，属正常状态）。
 *
 * 检查项（v1）：
 *   ①受管文件漂移：src/ admin-frontend/src/ sql/ context/ 当前 md5 对照
 *     「零号基线(context/DEPLOY_BASELINE_*.tsv 取最新) + 部署台账(context/DEPLOY_LEDGER.md)」——
 *     变更/新增/消失的文件若在台账中查无登记 = 未走流程的改动 → 报警。
 *   ②AppleDouble：受管目录出现 ._* 文件 = 发生过整目录/通配 scp → 报警。
 *   ③crontab：md5 对照 context/DEPLOY_BASELINE_CRON.txt 首列；不符 = 定时任务被动过而无票 → 报警。
 *   ④systemd：关键服务 is-active；inactive → 报警。
 *   （v2 候选：*.bak 备份缺失核对、nginx 配置 md5。）
 *
 * cron（部署时另行走票挂载，建议）：
 *   40 8 * * 1  cd /opt/lingxing-auto && npx ts-node src/checkDeploySyncSentinel.ts --send >> logs/deploy-sync-sentinel.log 2>&1
 *
 * 用法：
 *   npx ts-node src/checkDeploySyncSentinel.ts                # dry-run：只打印，零发送
 *   npx ts-node src/checkDeploySyncSentinel.ts --send         # 异常才真发（个人，SYNC_SENTINEL_NOTIFY，默认陈佳聪）
 *   npx ts-node src/checkDeploySyncSentinel.ts --test-send    # 发测试群（上线前通报测试铁律用）
 *   npx ts-node src/checkDeploySyncSentinel.ts --force-report # 无异常也发一份正常报告（验证链路）
 *
 * 铁律：本脚本全程只读（文件系统/crontab/systemctl 只读查询），零写库、零写文件、零修复动作。
 * 退出码：0=全部通过；2=存在异常（cron 日志可辨）。
 */

import "dotenv/config";
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import { execFile } from "child_process";
import { promisify } from "util";
import { getNotifyTenantToken, getTestChatId, resolveActiveMembers, sendTextToTarget } from "./feishuNotify";

const pExecFile = promisify(execFile);

const ROOT = process.cwd();
const MANAGED_DIRS = ["src", "admin-frontend/src", "sql", "context"];
const MANAGED_EXTS = new Set([".ts", ".tsx", ".sql", ".md"]);
const NOTIFY_NAME = (process.env.SYNC_SENTINEL_NOTIFY ?? "陈佳聪").trim();
const SERVICES = (process.env.SYNC_SENTINEL_SERVICES ??
  "lingxing-admin,lingxing-api-key-manager,ads-ai-api,asin-kw-backend,gpt-api-tunnel,asin-kw-frontend,walmart-meeting-server")
  .split(",").map((s) => s.trim()).filter(Boolean);

/** 与 2026-08-24 第2轮探测同口径的排除规则（改动必须双侧同步改，否则对不上基线） */
function isExcluded(relPath: string): boolean {
  const base = path.basename(relPath);
  if (base.startsWith("._")) return true;
  if (base.includes(".bak")) return true;
  if (base.includes(".macbak")) return true;
  if (base.endsWith(".ref")) return true;
  if (relPath.includes("_bak")) return true;
  if (relPath.includes("_prod_pull")) return true;
  if (relPath.includes("_pre_signoff")) return true;
  if (relPath.includes("_ARCHIVED")) return true;
  return false;
}

function walk(dir: string, out: string[], appleDouble: string[]): void {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return; // 目录不存在按空处理，交由基线比对暴露
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    const rel = path.relative(ROOT, full);
    if (e.isDirectory()) {
      walk(full, out, appleDouble);
    } else if (e.isFile()) {
      if (e.name.startsWith("._") && !rel.includes("_pre_signoff") && !rel.includes("_ARCHIVED")) {
        appleDouble.push(rel);
        continue;
      }
      if (isExcluded(rel)) continue;
      if (!MANAGED_EXTS.has(path.extname(e.name))) continue;
      out.push(rel);
    }
  }
}

function md5File(relPath: string): string {
  const buf = fs.readFileSync(path.join(ROOT, relPath));
  return crypto.createHash("md5").update(buf).digest("hex");
}

function latestBaselineFile(): string | null {
  const ctxDir = path.join(ROOT, "context");
  let names: string[];
  try {
    names = fs.readdirSync(ctxDir).filter((n) => /^DEPLOY_BASELINE_\d{8}\.tsv$/.test(n)).sort();
  } catch {
    return null;
  }
  return names.length ? path.join(ctxDir, names[names.length - 1]) : null;
}

function loadBaseline(file: string): Map<string, string> {
  const map = new Map<string, string>();
  const lines = fs.readFileSync(file, "utf8").split("\n");
  for (const line of lines) {
    const idx = line.indexOf("\t");
    if (idx <= 0) continue;
    map.set(line.slice(0, idx).trim(), line.slice(idx + 1).trim());
  }
  return map;
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const doSend = args.includes("--send");
  const testSend = args.includes("--test-send");
  const forceReport = args.includes("--force-report");

  const anomalies: string[] = [];
  const infos: string[] = [];

  // ── ①受管文件漂移：基线 + 台账解释 ────────────────────────────────
  const baselinePath = latestBaselineFile();
  if (!baselinePath) {
    anomalies.push("① 找不到零号基线 context/DEPLOY_BASELINE_*.tsv（哨兵无基准，本身即异常）");
  } else {
    const baseline = loadBaseline(baselinePath);
    let ledgerText = "";
    try {
      ledgerText = fs.readFileSync(path.join(ROOT, "context", "DEPLOY_LEDGER.md"), "utf8");
    } catch {
      anomalies.push("① 台账 context/DEPLOY_LEDGER.md 缺失（未走流程的删除，或哨兵早于台账部署）");
    }
    const current: string[] = [];
    const appleDouble: string[] = [];
    for (const d of MANAGED_DIRS) walk(path.join(ROOT, d), current, appleDouble);
    const currentSet = new Set(current);
    const inLedger = (rel: string): boolean =>
      ledgerText.includes(rel) || ledgerText.includes(path.basename(rel));

    let changed = 0, added = 0, removed = 0;
    for (const rel of current) {
      const cur = md5File(rel);
      const base = baseline.get(rel);
      if (base === undefined) {
        added++;
        if (!inLedger(rel)) anomalies.push(`① 未登记的新增文件：${rel}（md5=${cur}，基线与台账均查无）`);
      } else if (base !== cur) {
        changed++;
        if (!inLedger(rel)) anomalies.push(`① 未登记的内容变更：${rel}（基线=${base.slice(0, 8)}… 现值=${cur.slice(0, 8)}…，台账查无）`);
      }
    }
    baseline.forEach((_v, rel) => {
      if (!currentSet.has(rel)) {
        removed++;
        if (!inLedger(rel)) anomalies.push(`① 未登记的文件消失：${rel}（在基线中、现已不存在，台账查无）`);
      }
    });
    infos.push(`① 受管文件 ${current.length} 个｜较基线：变更${changed} 新增${added} 消失${removed}（基线=${path.basename(baselinePath)}）`);

    // ── ②AppleDouble ────────────────────────────────────────────────
    if (appleDouble.length) {
      anomalies.push(`② 受管目录出现 ${appleDouble.length} 个 ._ 文件（整目录/通配 scp 的物证）：${appleDouble.slice(0, 10).join("、")}${appleDouble.length > 10 ? " …" : ""}`);
    } else {
      infos.push("② AppleDouble：0（干净）");
    }
  }

  // ── ③crontab 基线 ──────────────────────────────────────────────────
  const cronBaseFile = path.join(ROOT, "context", "DEPLOY_BASELINE_CRON.txt");
  if (!fs.existsSync(cronBaseFile)) {
    infos.push("③ crontab：未配置基线文件 context/DEPLOY_BASELINE_CRON.txt，本项跳过（提示：应尽快建立）");
  } else {
    const expected = fs.readFileSync(cronBaseFile, "utf8").trim().split(/\s+/)[0] ?? "";
    try {
      const { stdout } = await pExecFile("crontab", ["-l"]);
      const actual = crypto.createHash("md5").update(stdout).digest("hex");
      if (actual !== expected) {
        anomalies.push(`③ crontab 已变更且未更新基线：期望=${expected.slice(0, 8)}… 现值=${actual.slice(0, 8)}…（有票变更请同票更新基线文件；无票=越权改动）`);
      } else {
        infos.push("③ crontab：与基线一致");
      }
    } catch (e) {
      anomalies.push(`③ crontab -l 执行失败：${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // ── ④systemd 服务 ─────────────────────────────────────────────────
  const inactive: string[] = [];
  for (const svc of SERVICES) {
    try {
      const { stdout } = await pExecFile("systemctl", ["is-active", svc]);
      if (stdout.trim() !== "active") inactive.push(`${svc}=${stdout.trim()}`);
    } catch {
      inactive.push(`${svc}=inactive/未知`);
    }
  }
  if (inactive.length) anomalies.push(`④ 服务非 active：${inactive.join("、")}`);
  else infos.push(`④ 服务：${SERVICES.length} 个全部 active`);

  // ── 汇总与通报 ─────────────────────────────────────────────────────
  const now = new Date().toISOString().replace("T", " ").slice(0, 19);
  const header = anomalies.length
    ? `🚨 代码一致性哨兵：发现 ${anomalies.length} 项异常（${now} UTC）`
    : `✅ 代码一致性哨兵：全部通过（${now} UTC）`;
  const body = [header, "", ...anomalies.map((a, i) => `${i + 1}. ${a}`),
    anomalies.length ? "" : undefined,
    "—— 概况 ——", ...infos,
    "", "处置指引：异常项先查 context/DEPLOY_LEDGER.md 与 _deploy_tmp/audit/ 回执；台账解释不了的改动按 SOP §3.11.7-3 追查是哪一单、哪一侧。本哨兵零修复动作。",
  ].filter((x): x is string => x !== undefined).join("\n");

  console.log(body);

  const shouldNotify = anomalies.length > 0 || forceReport;
  if (!shouldNotify) {
    console.log("\n[静默] 无异常且未指定 --force-report，不发送。");
    return;
  }
  if (!doSend && !testSend) {
    console.log("\n[dry-run] 未指定 --send / --test-send，仅打印。");
    return;
  }
  const token = await getNotifyTenantToken();
  if (testSend) {
    const r = await sendTextToTarget(token, { type: "chat", label: `测试群(原目标:${NOTIFY_NAME})`, id: getTestChatId() }, body, true);
    console.log(`\n发送(测试群) ok=${r.ok}`);
    if (r.ok) console.log("NOTIFY_TEST_SENT=1");
  } else {
    const { targets, warnings } = await resolveActiveMembers([NOTIFY_NAME]);
    warnings.forEach((w) => console.log(`[WARN] ${w}`));
    if (!targets.length) {
      console.log(`[ERROR] 花名册解析不到通知目标「${NOTIFY_NAME}」，无法发送`);
      process.exitCode = 2;
      return;
    }
    const r = await sendTextToTarget(token, targets[0], body, true);
    console.log(`\n发送(${targets[0].label}) ok=${r.ok}`);
  }
  if (anomalies.length) process.exitCode = 2;
}

main().catch((e) => {
  console.error(`[FATAL] ${e instanceof Error ? e.stack ?? e.message : String(e)}`);
  process.exitCode = 2;
});
