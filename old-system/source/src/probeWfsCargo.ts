/**
 * probeWfsCargo.ts - WFS货件列表API只读探测（到货提醒项目第一步）
 *
 * 目的：核实文档未明确的真实响应格式，禁止臆测：
 *   1. to_pending/await/receive/closed/cancelled_time 是 epoch 还是 "yyyy-MM-dd HH:mm:ss"
 *   2. 数量字段（declare_num/shipments_num/received_num/dameged_qty）实际类型与空值形态
 *   3. status 与 cargo_status 的实际取值分布
 *   4. 分页 total 类型、单页真实上限
 *
 * 安全边界：
 *   - 只读 API（LingxingClient.assertReadOnlyPath 兜底），零数据库写入，零飞书调用
 *   - 输出做截断与脱敏：不打印完整地址串，只打印结构与样例字段
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeWfsCargo.ts                 # 默认拉最近30天，最多2页
 *   npx ts-node src/probeWfsCargo.ts --days=90       # 扩大创建时间窗
 *   npx ts-node src/probeWfsCargo.ts --status=2,3    # 只看接收中/已关闭
 */

import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const API_PATH = "/cepf/warehouse/api/openApi/queryWFSCargoPage";
const PAGE_LENGTH = 50;
const MAX_PAGES = 2;
const TIMEOUT_MS = 60000;

function getArg(name: string, defaultValue = ""): string {
  const prefix = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : defaultValue;
}

function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** 判定时间戳字段的真实格式 */
function classifyTimeValue(v: unknown): string {
  if (v === null || v === undefined) return "null/undefined";
  const s = String(v).trim();
  if (s === "") return "空字符串";
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) return `datetime字符串("${s}")`;
  if (/^\d{13}$/.test(s)) return `epoch毫秒(${s})`;
  if (/^\d{10}$/.test(s)) return `epoch秒(${s})`;
  if (/^\d+$/.test(s)) return `纯数字长度${s.length}(${s})`;
  return `其他格式("${s.slice(0, 30)}")`;
}

function classifyNumValue(v: unknown): string {
  if (v === null || v === undefined) return "null/undefined";
  if (typeof v === "number") return `number(${v})`;
  const s = String(v).trim();
  if (s === "") return "空字符串";
  return `string("${s}")`;
}

async function main(): Promise<void> {
  const days = Number(getArg("days", "30")) || 30;
  const statusArg = getArg("status", "");
  const statusList = statusArg
    ? statusArg.split(",").map((s) => Number(s.trim())).filter((n) => Number.isInteger(n) && n >= 0 && n <= 4)
    : undefined;

  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - days * 24 * 3600 * 1000);

  console.log("=".repeat(60));
  console.log("WFS货件列表API只读探测");
  console.log(`创建时间窗: ${fmtDate(startDate)} ~ ${fmtDate(endDate)}（${days}天）`);
  console.log(`状态过滤: ${statusList ? statusList.join(",") : "不过滤"}`);
  console.log("=".repeat(60));

  const client = new LingxingClient(loadConfig());

  const timeFields = ["to_pending_time", "to_await_time", "to_receive_time", "to_closed_time", "to_cancelled_time"];
  const numFields = ["declare_num", "shipments_num", "received_num", "dameged_qty"];
  const statusSeen = new Map<string, number>();
  const cargoStatusSeen = new Map<string, number>();
  const timeFormatSeen = new Map<string, Set<string>>();
  const numFormatSeen = new Map<string, Set<string>>();
  let totalRecords = 0;
  let totalGoods = 0;
  let reportedTotal: unknown = null;

  for (let page = 0; page < MAX_PAGES; page++) {
    const params: Record<string, unknown> = {
      start_time: fmtDate(startDate),
      end_time: fmtDate(endDate),
      offset: page * PAGE_LENGTH,
      length: PAGE_LENGTH,
    };
    if (statusList && statusList.length > 0) params.cargo_status_list = statusList;

    const resp = await client.request<{ total?: unknown; records?: unknown[] }>({
      method: "POST",
      path: API_PATH,
      params,
      timeoutMs: TIMEOUT_MS,
    });

    const data = resp.data ?? {};
    reportedTotal = data.total;
    const records = Array.isArray(data.records) ? data.records : [];
    console.log(`\n第 ${page + 1} 页: ${records.length} 条（接口报告 total=${JSON.stringify(reportedTotal)}，类型=${typeof reportedTotal}）`);

    for (const raw of records) {
      totalRecords += 1;
      const r = raw as Record<string, unknown>;

      const st = `status=${JSON.stringify(r.status)}(${typeof r.status}) status_name=${String(r.status_name ?? "")}`;
      statusSeen.set(st, (statusSeen.get(st) ?? 0) + 1);
      const cs = `cargo_status=${String(r.cargo_status ?? "")} / cargo_sync_status=${String(r.cargo_sync_status ?? "")}`;
      cargoStatusSeen.set(cs, (cargoStatusSeen.get(cs) ?? 0) + 1);

      for (const f of timeFields) {
        if (!timeFormatSeen.has(f)) timeFormatSeen.set(f, new Set());
        timeFormatSeen.get(f)!.add(classifyTimeValue(r[f]));
      }

      const goods = Array.isArray(r.cargo_good_list) ? r.cargo_good_list : [];
      totalGoods += goods.length;
      for (const g of goods.slice(0, 5)) {
        const gr = g as Record<string, unknown>;
        for (const f of numFields) {
          if (!numFormatSeen.has(f)) numFormatSeen.set(f, new Set());
          numFormatSeen.get(f)!.add(classifyNumValue(gr[f]));
        }
      }
    }

    // 第一条完整结构样例（脱敏：不打印地址与创建人）
    if (page === 0 && records.length > 0) {
      const sample = { ...(records[0] as Record<string, unknown>) };
      delete sample.distribution_addresses;
      delete sample.return_addresses;
      delete sample.creator;
      console.log("\n── 首条记录结构样例（已脱敏地址/创建人）──");
      console.log(JSON.stringify(sample, null, 2).slice(0, 3000));
    }

    if (records.length < PAGE_LENGTH) break;
  }

  console.log("\n" + "=".repeat(60));
  console.log("探测结论汇总");
  console.log("=".repeat(60));
  console.log(`货件记录数: ${totalRecords}，商品明细行数: ${totalGoods}`);

  console.log("\n[1] 状态时间戳字段真实格式（设计文档待定项）:");
  for (const [f, set] of timeFormatSeen) console.log(`  ${f}: ${[...set].join(" | ")}`);

  console.log("\n[2] 数量字段真实类型:");
  for (const [f, set] of numFormatSeen) console.log(`  ${f}: ${[...set].join(" | ")}`);

  console.log("\n[3] status 取值分布:");
  for (const [k, v] of statusSeen) console.log(`  ${v} × ${k}`);

  console.log("\n[4] cargo_status / cargo_sync_status 取值分布:");
  for (const [k, v] of cargoStatusSeen) console.log(`  ${v} × ${k}`);

  console.log("\n探测完成（零写入）。请把本输出粘贴回设计文档 §二 修订格式假设。");
}

main().catch((e) => {
  console.error("probeWfsCargo 失败:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
