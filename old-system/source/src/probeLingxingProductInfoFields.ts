/**
 * probeLingxingProductInfoFields.ts
 *
 * 领星本地产品详情 API 字段探测脚本
 * 接口：POST /erp/sc/routing/data/local_inventory/productInfo
 * 限流：令牌桶容量=1，请求间隔 >= 2 秒
 *
 * 用法（dry-run，只打印请求参数，不调 API）：
 *   npx ts-node src/probeLingxingProductInfoFields.ts --sku=YC00019
 *
 * 真实调用（需要加 --confirm）：
 *   npx ts-node src/probeLingxingProductInfoFields.ts --sku=YC00019 --confirm
 *   npx ts-node src/probeLingxingProductInfoFields.ts --sku=YC00019 --msku=YC00019-1A --item-id=19894166482 --confirm
 *
 * 输出文件：
 *   reports/lingxing_product_info_api_sample.json       —— API 原始返回
 *   reports/lingxing_product_info_fields_inventory.md   —— 字段清单报告
 *   docs/lingxing_product_info_api_notes.md             —— 接口说明文档
 */

import "dotenv/config";
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import { loadConfig } from "./config";
import { LingxingClient, LingxingRequestError } from "./lingxingClient";

// ── 常量 ────────────────────────────────────────────────────────────────────
const API_PATH = "/erp/sc/routing/data/local_inventory/productInfo";
const SLEEP_MS = 2000; // 限流要求：请求间 >= 2s
const TIMEOUT_MS = 30000;

// ── 类型 ────────────────────────────────────────────────────────────────────
interface RawRecord {
  source_system: string;
  api_path: string;
  request_method: string;
  request_params_json: string;
  response_json: string;
  response_code: number | null;
  is_success: boolean;
  error_message: string;
  data_date: string;
  pulled_at: string;
  raw_hash: string;
  extra_json: string;
}

interface FieldInfo {
  path: string;
  exampleValue: unknown;
  type: string;
  isEmpty: boolean;
  occurrences: number;
  suggestedDest: string;
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────
function getArg(name: string): string {
  const prefix = `--${name}=`;
  const found = process.argv.find((a) => a.startsWith(prefix));
  return found ? found.slice(prefix.length).trim() : "";
}

function hasFlag(name: string): boolean {
  return process.argv.includes(`--${name}`);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function getNowISO(): string {
  return new Date().toISOString();
}

function getToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function hashJson(obj: unknown): string {
  return crypto.createHash("md5").update(JSON.stringify(obj)).digest("hex");
}

function ensureDir(dir: string): void {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

// ── 递归字段提取 ─────────────────────────────────────────────────────────────
function extractFields(
  obj: unknown,
  prefix: string,
  map: Map<string, FieldInfo>,
): void {
  if (obj === null || obj === undefined) return;

  if (Array.isArray(obj)) {
    obj.forEach((item) => extractFields(item, prefix, map));
    return;
  }

  if (typeof obj === "object") {
    for (const [key, val] of Object.entries(obj as Record<string, unknown>)) {
      const fieldPath = prefix ? `${prefix}.${key}` : key;
      extractFields(val, fieldPath, map);
    }
    return;
  }

  // 叶子节点
  const existing = map.get(prefix);
  if (existing) {
    existing.occurrences += 1;
    if (existing.isEmpty && obj !== "" && obj !== null) {
      existing.isEmpty = false;
      existing.exampleValue = obj;
    }
  } else {
    map.set(prefix, {
      path: prefix,
      exampleValue: obj,
      type: typeof obj,
      isEmpty: obj === "" || obj === null || obj === undefined,
      occurrences: 1,
      suggestedDest: suggestDest(prefix, obj),
    });
  }
}

// ── 字段去向建议 ─────────────────────────────────────────────────────────────
function suggestDest(fieldPath: string, value: unknown): string {
  const p = fieldPath.toLowerCase();

  // A. dim_product_identity
  if (
    p.includes("item_id") || p.includes("itemid") ||
    p === "data.sku" || p.includes("local_sku") ||
    p.includes("msku") ||
    p.includes("store_id") || p.includes("store_name") ||
    p.includes("lingxing_product_id") || p === "data.id" || p === "data.sid"
  ) return "A. dim_product_identity（身份映射）";

  // B. dim_product
  if (
    p.includes("product_name") || p.includes("local_name") ||
    p.includes("status") || p.includes("fulfillment") ||
    p.includes("category") || p.includes("type")
  ) return "B. dim_product（产品主数据）";

  // C. dim_product_cost_config
  if (
    p.includes("cg_price") || p.includes("purchase") ||
    p.includes("logistics") || p.includes("transport") ||
    p.includes("delivery_fee") || p.includes("shipping") ||
    p.includes("cost")
  ) return "C. dim_product_cost_config（成本配置）";

  // E. 明显无用
  if (
    p.includes("create_time") || p.includes("update_time") ||
    p.includes("operator") || p.includes("remark") ||
    p.includes("audit") || p.includes("tenant")
  ) return "E. 暂不使用（系统内部字段）";

  // D. extra_json
  return "D. extra_json（待确认）";
}

// ── 构造请求参数 ─────────────────────────────────────────────────────────────
interface ProbeCase {
  label: string;
  params: Record<string, unknown>;
}

function buildProbeCases(
  sku: string,
  msku: string,
  itemId: string,
  productId: string,
  limit: number,
): ProbeCase[] {
  const cases: ProbeCase[] = [];

  if (productId) cases.push({ label: `product_id=${productId}`, params: { product_id: productId } });
  if (sku) cases.push({ label: `sku=${sku}`, params: { sku } });
  if (msku) cases.push({ label: `msku=${msku}`, params: { msku } });
  if (itemId) cases.push({ label: `item_id=${itemId}`, params: { item_id: itemId } });

  // 如果没有传任何参数，用空参数试一次探底
  if (cases.length === 0) {
    cases.push({ label: "无参数（探底）", params: {} });
  }

  return cases.slice(0, limit);
}

// ── 主逻辑 ───────────────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const confirm = hasFlag("confirm");
  const sku = getArg("sku");
  const msku = getArg("msku");
  const itemId = getArg("item-id");
  const productId = getArg("product-id");
  const limitRaw = parseInt(getArg("limit"), 10);
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : 5;

  console.log("=".repeat(60));
  console.log("领星本地产品详情 API 字段探测");
  console.log(`接口: ${API_PATH}`);
  console.log(`模式: ${confirm ? "✅ 真实调用" : "dry-run（加 --confirm 才真实请求）"}`);
  console.log(`参数: sku=${sku || "-"} msku=${msku || "-"} item-id=${itemId || "-"} product-id=${productId || "-"}`);
  console.log(`最多请求次数: ${limit}`);
  console.log("=".repeat(60));

  const probeCases = buildProbeCases(sku, msku, itemId, productId, limit);

  if (!confirm) {
    console.log("\n[dry-run] 将会发送的请求参数：");
    probeCases.forEach((c, i) => {
      console.log(`  [${i + 1}] ${c.label}`);
      console.log(`       params: ${JSON.stringify(c.params)}`);
    });
    console.log("\n加 --confirm 才真实调用 API。退出。");
    return;
  }

  // ── 真实调用 ──
  const config = loadConfig();
  config.timeoutMs = TIMEOUT_MS;
  const client = new LingxingClient(config);

  const rawRecords: RawRecord[] = [];
  const fieldMap = new Map<string, FieldInfo>();
  const samples: unknown[] = [];

  for (let i = 0; i < probeCases.length; i++) {
    const c = probeCases[i];
    console.log(`\n[${i + 1}/${probeCases.length}] 请求: ${c.label}`);

    if (i > 0) {
      console.log(`  等待 ${SLEEP_MS}ms（限流保护）...`);
      await sleep(SLEEP_MS);
    }

    const pulledAt = getNowISO();
    let responseJson = "";
    let responseCode: number | null = null;
    let isSuccess = false;
    let errorMessage = "";
    let rawData: unknown = null;

    try {
      const resp = await client.request<unknown>({
        method: "POST",
        path: API_PATH,
        params: c.params,
        timeoutMs: TIMEOUT_MS,
      });

      responseJson = JSON.stringify(resp, null, 2);
      responseCode = Number(resp.code ?? 0);
      isSuccess = true;
      rawData = resp.data;
      console.log(`  ✅ 成功，code=${responseCode}`);
      console.log(`  data 类型: ${Array.isArray(rawData) ? "array" : typeof rawData}`);

      // 提取字段
      extractFields(rawData, "data", fieldMap);
      if (rawData) samples.push(rawData);

    } catch (e) {
      errorMessage = e instanceof LingxingRequestError
        ? e.message
        : (e instanceof Error ? e.message : String(e));
      responseJson = JSON.stringify({ error: errorMessage });
      responseCode = e instanceof LingxingRequestError ? (e.status ?? null) : null;
      console.log(`  ❌ 失败: ${errorMessage}`);
    }

    rawRecords.push({
      source_system: "lingxing",
      api_path: API_PATH,
      request_method: "POST",
      request_params_json: JSON.stringify(c.params),
      response_json: responseJson,
      response_code: responseCode,
      is_success: isSuccess,
      error_message: errorMessage,
      data_date: getToday(),
      pulled_at: pulledAt,
      raw_hash: hashJson({ params: c.params, response: responseJson }),
      extra_json: JSON.stringify({ label: c.label }),
    });
  }

  // ── 写输出文件 ───────────────────────────────────────────────────────────
  const projectRoot = path.resolve(__dirname, "..");
  ensureDir(path.join(projectRoot, "reports"));
  ensureDir(path.join(projectRoot, "docs"));

  // 1. raw_lingxing_api 样本
  const sampleFile = path.join(projectRoot, "reports", "lingxing_product_info_api_sample.json");
  fs.writeFileSync(sampleFile, JSON.stringify({ raw_lingxing_api: rawRecords, samples }, null, 2), "utf-8");
  console.log(`\n✅ 原始数据已保存: reports/lingxing_product_info_api_sample.json`);

  // 2. 字段清单报告
  const fields = Array.from(fieldMap.values()).sort((a, b) => a.path.localeCompare(b.path));

  const destGroups: Record<string, FieldInfo[]> = {
    "A. dim_product_identity（身份映射）": [],
    "B. dim_product（产品主数据）": [],
    "C. dim_product_cost_config（成本配置）": [],
    "D. extra_json（待确认）": [],
    "E. 暂不使用（系统内部字段）": [],
  };
  for (const f of fields) {
    (destGroups[f.suggestedDest] ?? destGroups["D. extra_json（待确认）"]).push(f);
  }

  let md = `# 领星 productInfo API 字段清单\n\n`;
  md += `> 生成时间: ${getNowISO()}\n`;
  md += `> 接口: \`${API_PATH}\`\n`;
  md += `> 探测次数: ${rawRecords.length}，成功: ${rawRecords.filter((r) => r.is_success).length}\n\n`;
  md += `## 字段总览（${fields.length} 个）\n\n`;
  md += `| 字段路径 | 类型 | 示例值 | 是否为空 | 出现次数 | 建议去向 |\n`;
  md += `|---------|------|--------|---------|---------|--------|\n`;
  for (const f of fields) {
    const example = String(f.exampleValue ?? "").slice(0, 40).replace(/\|/g, "\\|");
    md += `| \`${f.path}\` | ${f.type} | ${example} | ${f.isEmpty ? "是" : "否"} | ${f.occurrences} | ${f.suggestedDest} |\n`;
  }

  md += `\n## 按建议去向分类\n\n`;
  for (const [dest, fList] of Object.entries(destGroups)) {
    if (fList.length === 0) continue;
    md += `### ${dest}\n\n`;
    for (const f of fList) {
      md += `- \`${f.path}\` (${f.type}) — 示例: \`${String(f.exampleValue ?? "").slice(0, 60)}\`\n`;
    }
    md += "\n";
  }

  const mdFile = path.join(projectRoot, "reports", "lingxing_product_info_fields_inventory.md");
  fs.writeFileSync(mdFile, md, "utf-8");
  console.log(`✅ 字段清单已保存: reports/lingxing_product_info_fields_inventory.md`);

  // 3. 接口说明文档
  const successRecords = rawRecords.filter((r) => r.is_success);
  const failRecords = rawRecords.filter((r) => !r.is_success);

  let doc = `# 领星 productInfo 接口说明\n\n`;
  doc += `> 生成时间: ${getNowISO()}\n\n`;
  doc += `## 接口基本信息\n\n`;
  doc += `- **接口路径**: \`${API_PATH}\`\n`;
  doc += `- **请求方式**: POST\n`;
  doc += `- **限流**: 令牌桶容量=1，建议请求间隔 >= 2s\n\n`;
  doc += `## 探测结果摘要\n\n`;
  doc += `- 总请求次数: ${rawRecords.length}\n`;
  doc += `- 成功: ${successRecords.length}\n`;
  doc += `- 失败: ${failRecords.length}\n\n`;

  doc += `## 请求参数探测结果\n\n`;
  for (const r of rawRecords) {
    doc += `### ${r.extra_json ? JSON.parse(r.extra_json).label : r.request_params_json}\n\n`;
    doc += `- 参数: \`${r.request_params_json}\`\n`;
    doc += `- 成功: ${r.is_success ? "是" : "否"}\n`;
    doc += `- HTTP 响应码: ${r.response_code ?? "N/A"}\n`;
    if (r.error_message) doc += `- 错误: ${r.error_message}\n`;
    doc += "\n";
  }

  doc += `## 字段统计\n\n`;
  doc += `发现字段总数: **${fields.length}**\n\n`;
  doc += `| 建议去向 | 字段数 |\n|---------|-------|\n`;
  for (const [dest, fList] of Object.entries(destGroups)) {
    if (fList.length > 0) doc += `| ${dest} | ${fList.length} |\n`;
  }

  doc += `\n## 后续同步建议\n\n`;
  doc += `1. 确认接口实际需要哪些请求参数（sku / item_id / product_id）\n`;
  doc += `2. 按字段清单建立 dim_product、dim_product_identity、dim_product_cost_config\n`;
  doc += `3. 限流严格，正式同步建议每次请求间隔 >= 2s，批量时分批错峰\n`;
  doc += `4. 采购成本、头程成本字段确认后接入利润计算链路\n`;

  const docFile = path.join(projectRoot, "docs", "lingxing_product_info_api_notes.md");
  fs.writeFileSync(docFile, doc, "utf-8");
  console.log(`✅ 接口说明已保存: docs/lingxing_product_info_api_notes.md`);

  // ── 控制台汇总 ───────────────────────────────────────────────────────────
  console.log("\n" + "=".repeat(60));
  console.log("探测完成");
  console.log(`字段总数: ${fields.length}`);
  for (const [dest, fList] of Object.entries(destGroups)) {
    if (fList.length > 0) console.log(`  ${dest}: ${fList.length} 个`);
  }
  console.log("=".repeat(60));

  if (fields.length === 0) {
    console.log("\n⚠️  未提取到任何字段，可能原因：");
    console.log("   1. 所有请求都失败了");
    console.log("   2. 接口返回 data=null 或 data=[]");
    console.log("   3. 请求参数不正确，接口拒绝了查询");
    console.log("   建议检查 reports/lingxing_product_info_api_sample.json 查看原始返回");
  }
}

main().catch((e) => {
  console.error("探测脚本异常:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
