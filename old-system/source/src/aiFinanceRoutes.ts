/**
 * aiFinanceRoutes.ts — AI财务系统 · 只读查询路由（2026-08-12，隔离新模块 批1）
 * 挂载：/api/finance（adminServer；全局 authMiddleware）
 *
 * GET /credits/list             返还明细（fact_ad_credit_detail 行级 + dim_store 店名）+ kpi + latest_sync_time
 * GET /commission-savings/list  佣金折扣（fact_commission_saving 账期聚合 + dim_store 店名）+ kpi + latest_sync_time
 *
 * 铁律：本路由全程只读（仅 SELECT）；前端只经本路由读 FACT/DIM 层，不直查 RAW；
 *   不写任何表、不碰人工备注列；连接从环境变量读，禁止硬编码密钥。
 */
import { Router, Request, Response, NextFunction } from "express";
import * as mysql from "mysql2/promise";
import { requireAuth, requirePermission, AuthedRequest } from "./authMiddleware";
import { adjustedAdsFactSql } from "./adsItemSpendAlloc";

const router = Router();
const FX_PERM = "finance_fx"; // 汇率写权限键（超管绕过；授权=dim_app_user_permission 加行）
// 导入门禁（2026-08-13 批12c）：仓储/入库运输 CSV 导入 = 超管 或 角色「财务」 或 权限 finance_import。
// 需求方：财务角色(翁骏/陈玉/陈虹霓)即可导入，不必设超管；finance_import 为未来非财务例外授权口子。
const IMPORT_ROLE = "财务";
const IMPORT_PERM = "finance_import";
const canImportUser = (u?: { isSuperadmin?: boolean; roles?: Set<string>; permissions?: Set<string> }): boolean =>
  !!(u && (u.isSuperadmin || (u.roles?.has(IMPORT_ROLE) ?? false) || (u.permissions?.has(IMPORT_PERM) ?? false)));
function requireImport(req: AuthedRequest, res: Response, next: NextFunction): void {
  const u = req.user;
  if (!u) { res.status(401).json({ error: "未登录" }); return; }
  if (canImportUser(u)) { next(); return; }
  res.status(403).json({ error: "无导入权限（需财务角色或 finance_import 授权）" });
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
}
const n2 = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const r2 = (v: number): number => Math.round(v * 100) / 100;

// ── 返还明细（行级；含自发现 other:* 类目）─────────────────────────────────
// 2026-08-19 需求方拍板：「广告返还积分」(ad_credit) 源改为 Walmart Connect 广告发票内抵扣
//   （fact_onsite_ads_invoice_head.total_credits_applied，发票号可溯）。原因（数据实锤）：
//   Seller Center 通道同一笔credit在 statement 与发票两边都留痕（CN2602 $228.93双计），
//   Credit Card 通道 statement 完全无痕（漏计）——statement 侧 ad_credit 行降级不再计入本页。
//   其余类目仍取 statement（fact_ad_credit_detail），零改动。
router.get("/credits/list", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT d.id, d.platform, d.store_id, COALESCE(s.store_name, d.store_id) AS store_name,
              DATE_FORMAT(d.posted_date,'%Y-%m-%d') AS posted_date,
              DATE_FORMAT(d.period_start,'%Y-%m-%d') AS period_start,
              DATE_FORMAT(d.period_end,'%Y-%m-%d')   AS period_end,
              d.fee_category, d.transaction_type, d.transaction_desc,
              d.amount, d.currency_code, d.campaign_id, d.source_ref, d.remark
         FROM fact_ad_credit_detail d
         LEFT JOIN dim_store s ON s.platform = d.platform AND s.store_id = d.store_id
        WHERE d.fee_category <> 'ad_credit'
       UNION ALL
       SELECT -h.id AS id, h.platform, h.store_id,
              COALESCE(NULLIF(h.store_name,''), s2.store_name, h.store_id) AS store_name,
              DATE_FORMAT(COALESCE(h.charge_date, h.invoice_date, h.period_end),'%Y-%m-%d') AS posted_date,
              DATE_FORMAT(h.period_start,'%Y-%m-%d') AS period_start,
              DATE_FORMAT(h.period_end,'%Y-%m-%d')   AS period_end,
              'ad_credit' AS fee_category, 'Connect Invoice' AS transaction_type,
              CONCAT('Connect发票内广告返还抵扣 · 发票号 ', h.invoice_number,
                     CASE WHEN h.charge_date IS NULL THEN '（待扣款）' ELSE '' END) AS transaction_desc,
              ABS(h.total_credits_applied) AS amount, 'USD' AS currency_code,
              '-' AS campaign_id, h.invoice_number AS source_ref, h.remark
         FROM fact_onsite_ads_invoice_head h
         LEFT JOIN dim_store s2 ON s2.platform = h.platform AND s2.store_id = h.store_id
        WHERE h.total_credits_applied <> 0
        ORDER BY posted_date DESC, id DESC`);
    const kpi = { credit_sum: 0, reversal_sum: 0, net_sum: 0, cnt: rows.length, category_cnt: 0 };
    const cats = new Set<string>();
    for (const r of rows) {
      const a = n2(r.amount);
      if (a >= 0) kpi.credit_sum += a; else kpi.reversal_sum += a;
      cats.add(String(r.fee_category));
    }
    kpi.credit_sum = r2(kpi.credit_sum); kpi.reversal_sum = r2(kpi.reversal_sum);
    kpi.net_sum = r2(kpi.credit_sum + kpi.reversal_sum); kpi.category_cnt = cats.size;
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT GREATEST(COALESCE((SELECT MAX(updated_at) FROM fact_ad_credit_detail),'1970-01-01'),
                       COALESCE((SELECT MAX(updated_at) FROM fact_onsite_ads_invoice_head),'1970-01-01')) AS t`);
    res.json({ rows, kpi, categories: Array.from(cats).sort(), latest_sync_time: String(syncRows[0]?.t ?? "") });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

// ── 佣金折扣（店铺×账期×MSKU×激励计划聚合；信息指标，不参与现金守恒）──────────
router.get("/commission-savings/list", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT c.id, c.platform, c.store_id, COALESCE(s.store_name, c.store_id) AS store_name,
              DATE_FORMAT(c.period_start,'%Y-%m-%d') AS period_start,
              DATE_FORMAT(c.period_end,'%Y-%m-%d')   AS period_end,
              c.msku, c.item_id, c.incentive_program, c.saving_amount, c.txn_count, c.currency_code, c.remark
         FROM fact_commission_saving c
         LEFT JOIN dim_store s ON s.platform = c.platform AND s.store_id = c.store_id
        ORDER BY c.period_start DESC, c.store_id ASC, c.saving_amount DESC`);
    const kpi = { saving_sum: 0, txn_sum: 0, cnt: rows.length, program_cnt: 0 };
    const programs = new Set<string>();
    for (const r of rows) {
      kpi.saving_sum += n2(r.saving_amount); kpi.txn_sum += n2(r.txn_count);
      programs.add(String(r.incentive_program));
    }
    kpi.saving_sum = r2(kpi.saving_sum); kpi.program_cnt = programs.size;
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(MAX(updated_at), '1970-01-01') AS t FROM fact_commission_saving`);
    res.json({ rows, kpi, programs: Array.from(programs).sort(), latest_sync_time: String(syncRows[0]?.t ?? "") });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

// ── 财务工具 · 月度汇率（2026-08-12 批3；biz_finance_exchange_rate 人工层）─────
// 读=登录即可；写=requireAuth+requirePermission('finance_fx')（超管绕过）。
// 只 upsert 不删除（不可删历史）；updated_by 记实际操作人。
interface FxUser { username?: string; display_name?: string; isSuperadmin?: boolean; permissions?: Set<string>; roles?: Set<string> }
const fxUser = (req: Request): FxUser | undefined => (req as { user?: FxUser }).user;

router.get("/fx/list", async (req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, rate_month, currency_pair, rate, remark, created_by, updated_by,
              DATE_FORMAT(updated_at,'%Y-%m-%d %H:%i') AS updated_at
         FROM biz_finance_exchange_rate ORDER BY rate_month DESC, currency_pair ASC`);
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(MAX(updated_at), '1970-01-01') AS t FROM biz_finance_exchange_rate`);
    const u = fxUser(req);
    const canWrite = !!(u && (u.isSuperadmin || (u.permissions?.has(FX_PERM) ?? false)));
    res.json({ rows, can_write: canWrite, latest_sync_time: String(syncRows[0]?.t ?? "") });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

router.post("/fx/upsert", requireAuth, requirePermission(FX_PERM), async (req: Request, res: Response): Promise<void> => {
  const b = (req.body ?? {}) as Record<string, unknown>;
  const month = String(b.rate_month ?? "").trim();
  const rate = Number(b.rate);
  const remark = String(b.remark ?? "").trim().slice(0, 255);
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) { res.status(400).json({ error: "rate_month 需为 yyyy-MM" }); return; }
  if (!Number.isFinite(rate) || rate <= 0 || rate >= 100) { res.status(400).json({ error: "汇率需为 0~100 之间的数值（1美元兑人民币）" }); return; }
  const u = fxUser(req);
  const actor = String(u?.display_name ?? u?.username ?? "").trim() || "admin_ui";
  const db = await getDb();
  try {
    await db.query(
      `INSERT INTO biz_finance_exchange_rate (rate_month, currency_pair, rate, remark, created_by, updated_by)
       VALUES (?, 'USD/CNY', ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE rate=VALUES(rate), remark=VALUES(remark), updated_by=VALUES(updated_by)`,
      [month, rate, remark, actor, actor]);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

// ── 财务工具 · 领星汇率（2026-08-13 批7d；只读展示，主口径 my_rate）───────────
// 需求方 2026-08-13 决定：财务工具页不再人工录入汇率，直接取领星值。
//   · 主口径 = fact_lingxing_fx_rate.my_rate（领星「我的汇率」，官方文档：系统首先使用该汇率数据）
//   · 领星算单品成本(wfs_stock_price 等)用的就是它，我方折算必须同源
//   · 人工台账 biz_finance_exchange_rate 与 /fx/list、/fx/upsert 接口**保留不删**（历史审计+兜底），
//     仅前端不再提供写入入口
// 实测口径提醒：领星摊费用时按 cash_date 的**上一个月** my_rate 折算
//   （4月单隐含6.8367≈3月my_rate 6.8348；5月单隐含6.85≈4月my_rate 6.8500）。
router.get("/fx/lingxing", async (req: Request, res: Response): Promise<void> => {
  const q = (req.query ?? {}) as Record<string, unknown>;
  const cur = String(q.currency ?? "USD").trim().toUpperCase();
  const db = await getDb();
  try {
    const where = cur && cur !== "ALL" ? "WHERE currency_code=?" : "";
    const args = cur && cur !== "ALL" ? [cur] : [];
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, rate_month, currency_code, currency_name, icon,
              ROUND(rate_org,4) AS rate_org, ROUND(my_rate,4) AS my_rate,
              DATE_FORMAT(lx_update_time,'%Y-%m-%d %H:%i') AS lx_update_time,
              DATE_FORMAT(updated_at,'%Y-%m-%d %H:%i') AS synced_at
         FROM fact_lingxing_fx_rate ${where}
        ORDER BY rate_month DESC, currency_code ASC`, args);
    const [curRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT currency_code, MAX(currency_name) AS currency_name, COUNT(*) AS n
         FROM fact_lingxing_fx_rate GROUP BY currency_code ORDER BY currency_code`);
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(MAX(updated_at), '1970-01-01') AS t FROM fact_lingxing_fx_rate`);
    const u = fxUser(req);
    const canWrite = !!(u && (u.isSuperadmin || (u.permissions?.has(FX_PERM) ?? false)));
    res.json({
      rows, can_write: canWrite, can_import: canImportUser(u),
      currencies: curRows.map((c) => ({ code: String(c.currency_code), name: String(c.currency_name ?? "") })),
      latest_sync_time: String(syncRows[0]?.t ?? ""),
    });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

// ── 财务工具 · 仓储费CSV导入（2026-08-12 批4；Seller Center WFS「仓储」报告）─────
// 报告结构（2026-08-12 真实样例实锤）：行1=店铺缩写；汇总块("Report start date"…行+值行，
//   第3列=Total storage fees)；明细表头("GTIN","SKU",…22列)；表头下一行=英文说明行(跳过)；
//   数据行 GTIN 带 Excel 保护符 ="…"。守恒门禁：ΣFinal storage fee ↔ 头部Total，差>±$0.5整批拒绝。
// 写入：RAW(raw_walmart_storage_csv, RAW-first) → FACT(fact_wfs_storage_fee, uq幂等覆盖)；
//   item_id=dim_product 店铺内SKU唯一命中才填（禁猜）。权限同汇率（超管/finance_fx）。

function csvLine(line: string): string[] {
  const out: string[] = []; let cur = ""; let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQ) {
      if (ch === '"') { if (line[i + 1] === '"') { cur += '"'; i++; } else { inQ = false; } }
      else cur += ch;
    } else if (ch === '"') inQ = true;
    else if (ch === ",") { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}
const cellClean = (v: string): string => v.replace(/^=/, "").replace(/^"+|"+$/g, "").trim();
const numOf = (v: string): number => { const n = Number(String(v).replace(/[$,]/g, "")); return Number.isFinite(n) ? n : 0; };

router.get("/stores", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name FROM dim_store WHERE platform='walmart' ORDER BY store_name`);
    res.json({ stores: rows });
  } catch (e) { res.status(500).json({ error: e instanceof Error ? e.message : String(e) }); }
  finally { await db.end().catch(() => undefined); }
});

router.get("/storage/list", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      // 2026-08-14 需求方拍板：以 RAW 批次(row_no=0)为主表 LEFT JOIN 事实聚合 →
      //   空报告(该期无沃尔玛承运费用/无仓储费)也留一条 0 记录，人工一眼可辨「已导过=空」与「没导过」。
      //   同(店,期)多次重导只取最新一次批次，避免历史批次显示为 0 造成误解。
      `SELECT b.store_id, COALESCE(s.store_name, b.store_id) AS store_name,
              DATE_FORMAT(b.report_start,'%Y-%m-%d') AS report_start,
              DATE_FORMAT(b.report_end,'%Y-%m-%d') AS report_end,
              b.task_id, b.operator,
              DATE_FORMAT(b.created_at,'%Y-%m-%d %H:%i') AS imported_at,
              COALESCE(f.sku_cnt,0) AS sku_cnt,
              COALESCE(f.fee_sum,0) AS fee_sum,
              COALESCE(f.discount_sum,0) AS discount_sum
         FROM (SELECT r.store_id, r.report_start, r.report_end, r.task_id, r.operator, r.created_at,
                      ROW_NUMBER() OVER (PARTITION BY r.store_id, r.report_start, r.report_end
                                         ORDER BY r.created_at DESC, r.task_id DESC) AS rn
                 FROM raw_walmart_storage_csv r WHERE r.row_no = 0) b
         LEFT JOIN dim_store s ON s.platform='walmart' AND s.store_id=b.store_id
         LEFT JOIN (SELECT store_id, report_start, report_end, COUNT(*) AS sku_cnt,
                           ROUND(SUM(final_storage_fee),2) AS fee_sum,
                           ROUND(SUM(discount_savings),2) AS discount_sum
                      FROM fact_wfs_storage_fee GROUP BY store_id, report_start, report_end) f
                ON f.store_id=b.store_id AND f.report_start=b.report_start AND f.report_end=b.report_end
        WHERE b.rn = 1
        ORDER BY b.report_end DESC, store_name ASC`);
    // operator 已由 RAW 主表直出，无需二次查询
    res.json({ rows });
  } catch (e) { res.status(500).json({ error: e instanceof Error ? e.message : String(e) }); }
  finally { await db.end().catch(() => undefined); }
});

router.post("/storage-import", requireAuth, requireImport, async (req: Request, res: Response): Promise<void> => {
  const b = (req.body ?? {}) as Record<string, unknown>;
  const storeId = String(b.store_id ?? "").trim();
  const filename = String(b.filename ?? "").trim().slice(0, 200);
  const content = String(b.content ?? "");
  const u = fxUser(req);
  const actor = String(u?.display_name ?? u?.username ?? "").trim() || "admin_ui";
  if (!storeId) { res.status(400).json({ error: "store_id 必填" }); return; }
  if (!content || content.length < 100) { res.status(400).json({ error: "CSV内容为空或过短" }); return; }
  if (content.length > 8 * 1024 * 1024) { res.status(400).json({ error: "文件过大（>8MB），请确认是单店铺仓储报告" }); return; }

  // 解析
  const lines = content.split(/\r\n|\n|\r/);
  let sumHeaderIdx = -1, detHeaderIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const c = csvLine(lines[i]).map(cellClean);
    if (sumHeaderIdx < 0 && c[0] === "Report start date") sumHeaderIdx = i;
    if (detHeaderIdx < 0 && c[0] === "GTIN" && c[1] === "SKU") detHeaderIdx = i;
    if (sumHeaderIdx >= 0 && detHeaderIdx >= 0) break;
  }
  if (sumHeaderIdx < 0 || detHeaderIdx < 0) {
    res.status(400).json({ error: "格式不符：未找到汇总块(Report start date)或明细表头(GTIN,SKU)。请确认是 Seller Center WFS「仓储」报告原始CSV" }); return;
  }
  const sumVals = csvLine(lines[sumHeaderIdx + 1] ?? "").map(cellClean);
  const reportStart = sumVals[0] ?? "", reportEnd = sumVals[1] ?? "";
  const totalReported = numOf(sumVals[2] ?? "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(reportStart) || !/^\d{4}-\d{2}-\d{2}$/.test(reportEnd) || reportStart >= reportEnd) {
    res.status(400).json({ error: `汇总块报告期异常：${reportStart} ~ ${reportEnd}` }); return;
  }
  const header = csvLine(lines[detHeaderIdx]).map(cellClean);
  const col = (name: string): number => header.indexOf(name);
  // 2026-08-19 新旧双版式兼容（真实样例实锤）：新版件均量表头由 "Standard: average units available"
  // 改为 "Standard: average daily units available"，长期列 "(366-450)"→"(366-450 days)"、"(451+)"→"(450+ days)"。
  // 旧精确匹配会拒收新版报告 → 改用正则模糊匹配，两版式均放行；语义不变。
  const colRe = (re: RegExp): number => header.findIndex((h) => re.test(h));
  const idx = {
    gtin: col("GTIN"), sku: col("SKU"),
    avgStd: colRe(/^Standard: average (daily )?units available$/),
    avgLt1: colRe(/^Long-term \(366-450( days)?\): average (daily )?units available$/),
    avgLt2: colRe(/^Long-term \((451\+|450\+)( days)?\): average (daily )?units available$/),
    days: col("Days in report period"), final: col("Final storage fee"),
  };
  const missing = Object.entries(idx).filter(([, v]) => v < 0).map(([k]) => k);
  if (missing.length) { res.status(400).json({ error: `明细表头缺列：${missing.join(",")}（报告版式可能已变，需核对）` }); return; }
  // 2026-08-12 实锤：旧版报告(约6月中旬前)只有20列，无 Original Amount/Discount Savings（NSS仓储折扣
  // 上线后才加列）→ 两列可选：缺列时 original=final、discount=0。旧版 Item ID 列有值，优先取报告自带。
  const optOriginal = col("Original Amount");
  const optDiscount = col("Discount Savings");
  const optItemId = col("Item ID");
  // 2026-08-19 需求方拍板「所有数据都保留」：新版11列（尺寸4+单件日费率4+件均量peak/366-450/450+）
  // 全部可选解析；旧版报告缺列 → 存 NULL（前端显示 —），不报错不臆测。
  const optNew = {
    lengthIn: colRe(/^Length \(in\)$/), widthIn: colRe(/^Width \(in\)$/),
    heightIn: colRe(/^Height \(in\)$/), weightLb: colRe(/^Weight \(lb\)$/),
    feeStd: colRe(/^Standard: daily storage fee per unit$/),
    feePeak: colRe(/^Peak: daily storage fee per unit$/),
    feeLt366: colRe(/^Long-term \(366-450( days)?\): daily storage fee per unit$/),
    feeLt450: colRe(/^Long-term \((451\+|450\+)( days)?\): daily storage fee per unit$/),
    avgPeak: colRe(/^Peak: average (daily )?units available$/),
  };

  interface SRow { gtin: string; sku: string; reportItemId: string; avgStd: number; avgLt: number; days: number; final: number; original: number; discount: number; raw: string;
    lengthIn: number | null; widthIn: number | null; heightIn: number | null; weightLb: number | null;
    feeStd: number | null; feePeak: number | null; feeLt366: number | null; feeLt450: number | null;
    avgPeak: number | null; avgLt366: number | null; avgLt450: number | null }
  const dataRows: SRow[] = [];
  for (let i = detHeaderIdx + 1; i < lines.length; i++) {
    if (!lines[i] || !lines[i].trim()) continue;
    const c = csvLine(lines[i]).map(cellClean);
    const gtin = (c[idx.gtin] ?? "").replace(/[^0-9]/g, "");
    const sku = c[idx.sku] ?? "";
    if (gtin.length < 8 || !sku) continue; // 说明行/杂行跳过
    const fin = numOf(c[idx.final] ?? "");
    const reportItemId = optItemId >= 0 ? (c[optItemId] ?? "").replace(/[^0-9]/g, "") : "";
    const optNum = (colIdx: number): number | null => colIdx >= 0 ? numOf(c[colIdx] ?? "") : null;
    dataRows.push({
      gtin, sku, reportItemId,
      avgStd: numOf(c[idx.avgStd] ?? ""), avgLt: numOf(c[idx.avgLt1] ?? "") + numOf(c[idx.avgLt2] ?? ""),
      days: Math.round(numOf(c[idx.days] ?? "")), final: fin,
      original: optOriginal >= 0 ? numOf(c[optOriginal] ?? "") : fin,
      discount: optDiscount >= 0 ? numOf(c[optDiscount] ?? "") : 0, raw: lines[i],
      lengthIn: optNum(optNew.lengthIn), widthIn: optNum(optNew.widthIn),
      heightIn: optNum(optNew.heightIn), weightLb: optNum(optNew.weightLb),
      feeStd: optNum(optNew.feeStd), feePeak: optNum(optNew.feePeak),
      feeLt366: optNum(optNew.feeLt366), feeLt450: optNum(optNew.feeLt450),
      avgPeak: optNum(optNew.avgPeak),
      avgLt366: optNum(idx.avgLt1), avgLt450: optNum(idx.avgLt2),
    });
  }
  // 2026-08-14 需求方拍板：**空报告也照常导入并留 0 记录**（该期确无仓储费属正常），
  //   便于人工区分「已导过=空」与「根本没导」，避免误判漏导。守恒校验仅在有数据行时执行。
  const totalComputed = Math.round(dataRows.reduce((a, r) => a + r.final, 0) * 100) / 100;
  if (dataRows.length && Math.abs(totalComputed - totalReported) > 0.5) {
    res.status(400).json({ error: `守恒不平，整批拒绝：ΣFinal=${totalComputed} vs 报告头部Total=${totalReported}（差${Math.round((totalComputed - totalReported) * 100) / 100}）` }); return;
  }

  const db = await getDb();
  try {
    const [[st]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name FROM dim_store WHERE platform='walmart' AND store_id=? LIMIT 1`, [storeId]) as unknown as [mysql.RowDataPacket[]];
    if (!st) { res.status(400).json({ error: `store_id ${storeId} 不在 dim_store` }); return; }

    // ===== 防重：账期重叠拒收（2026-08-14 需求方拍板）=====
    // 唯一键含 report_start/report_end，跨账期不去重会累加 → 曾致 CN2601 仓储费虚高 $15,464.68。
    // 规则：同账期重导=覆盖更新（放行）；与已有账期【时间相交但起止不同】=拒收并指出撞了哪一期。
    // 合法的合并账期（如 28 天报告，与任何已有期都不相交）不受影响。
    const [ovl] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS rs, DATE_FORMAT(report_end,'%Y-%m-%d') AS re,
              COUNT(*) AS rows_cnt, ROUND(SUM(final_storage_fee),2) AS amt
         FROM fact_wfs_storage_fee
        WHERE platform='walmart' AND store_id=?
          AND NOT (report_start=? AND report_end=?)
          AND report_start <= ? AND ? <= report_end
        GROUP BY report_start, report_end ORDER BY report_start LIMIT 5`,
      [storeId, reportStart, reportEnd, reportEnd, reportStart]);
    if ((ovl as mysql.RowDataPacket[]).length) {
      const conflicts = (ovl as mysql.RowDataPacket[])
        .map((o) => `${String(o.rs)}~${String(o.re)}（${o.rows_cnt}行/$${o.amt}）`).join("、");
      res.status(400).json({
        error: `账期重叠，已拒收：本次 ${reportStart} ~ ${reportEnd} 与已存在的 ${conflicts} 时间相交，` +
               `同时入库会造成重复累加。请改用与已有账期一致的标准账期报告；确需替换请先联系管理员清理冲突账期。`,
      }); return;
    }

    const day = new Date();
    const ymd = `${day.getFullYear()}${String(day.getMonth() + 1).padStart(2, "0")}${String(day.getDate()).padStart(2, "0")}`;
    const [[seqRow]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(DISTINCT task_id) AS n FROM raw_walmart_storage_csv WHERE task_id LIKE ?`, [`WMSTOR-${ymd}-%`]) as unknown as [mysql.RowDataPacket[]];
    const taskId = `WMSTOR-${ymd}-${String(Number(seqRow?.n ?? 0) + 1).padStart(4, "0")}`;

    // RAW-first（含汇总行 row_no=0）
    await db.query(
      `INSERT INTO raw_walmart_storage_csv (task_id, store_id, operator, report_start, report_end, row_no, row_json, raw_hash)
       VALUES (?,?,?,?,?,0,?,MD5(?))`,
      [taskId, storeId, actor, reportStart, reportEnd,
       JSON.stringify({ filename, summary: sumVals.slice(0, 7), total_reported: totalReported }), content.slice(0, 2000)]);
    for (let i = 0; i < dataRows.length; i++) {
      const r = dataRows[i];
      await db.query(
        `INSERT INTO raw_walmart_storage_csv (task_id, store_id, operator, report_start, report_end, row_no, row_json, raw_hash)
         VALUES (?,?,?,?,?,?,?,MD5(?))`,
        [taskId, storeId, actor, reportStart, reportEnd, i + 1, JSON.stringify({ line: r.raw }), r.raw]);
    }

    // 空报告：RAW 汇总行已留档（列表可见 0 记录），后续按品写库全部跳过并直接返回。
    //   必须早返回——否则下方 `msku IN (...)` 会拼出空 IN () 触发 SQL 语法错误。
    if (!dataRows.length) {
      res.json({ ok: true, task_id: taskId, report_start: reportStart, report_end: reportEnd,
        rows: 0, total_computed: 0, total_reported: totalReported, diff: 0, item_mapped: 0, empty: true,
        message: `该报告期（${reportStart} ~ ${reportEnd}）报告内无数据行，已留 0 记录（该期确无仓储费，属正常）` });
      return;
    }

    // item_id 映射（店铺内SKU唯一命中）
    const [mapRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT msku, item_id FROM dim_product WHERE platform='walmart' AND store_id=? AND msku IN (${dataRows.map(() => "?").join(",")})
       GROUP BY msku, item_id`, [storeId, ...dataRows.map((r) => r.sku)]);
    const byMsku = new Map<string, Set<string>>();
    for (const m of mapRows) {
      const k = String(m.msku); if (!byMsku.has(k)) byMsku.set(k, new Set());
      byMsku.get(k)!.add(String(m.item_id));
    }
    let mapped = 0, upserts = 0;
    for (const r of dataRows) {
      const ids = byMsku.get(r.sku);
      // 优先取报告自带 Item ID（旧版报告有值=平台一手数据）；缺失再用产品档案唯一命中
      const itemId = r.reportItemId.length >= 8 ? r.reportItemId
        : (ids && ids.size === 1 ? Array.from(ids)[0] : "");
      if (itemId) mapped++;
      await db.query(
        `INSERT INTO fact_wfs_storage_fee (platform, store_id, sku, gtin, item_id, report_start, report_end,
            days_in_period, avg_units_standard, avg_units_longterm, final_storage_fee, original_amount, discount_savings, source_task_id,
            length_in, width_in, height_in, weight_lb,
            unit_fee_standard, unit_fee_peak, unit_fee_lt366, unit_fee_lt450,
            avg_units_peak, avg_units_lt366, avg_units_lt450)
         VALUES ('walmart',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
         ON DUPLICATE KEY UPDATE gtin=VALUES(gtin), item_id=IF(VALUES(item_id)='' , item_id, VALUES(item_id)),
            days_in_period=VALUES(days_in_period), avg_units_standard=VALUES(avg_units_standard),
            avg_units_longterm=VALUES(avg_units_longterm), final_storage_fee=VALUES(final_storage_fee),
            original_amount=VALUES(original_amount), discount_savings=VALUES(discount_savings),
            source_task_id=VALUES(source_task_id),
            length_in=COALESCE(VALUES(length_in), length_in), width_in=COALESCE(VALUES(width_in), width_in),
            height_in=COALESCE(VALUES(height_in), height_in), weight_lb=COALESCE(VALUES(weight_lb), weight_lb),
            unit_fee_standard=COALESCE(VALUES(unit_fee_standard), unit_fee_standard),
            unit_fee_peak=COALESCE(VALUES(unit_fee_peak), unit_fee_peak),
            unit_fee_lt366=COALESCE(VALUES(unit_fee_lt366), unit_fee_lt366),
            unit_fee_lt450=COALESCE(VALUES(unit_fee_lt450), unit_fee_lt450),
            avg_units_peak=COALESCE(VALUES(avg_units_peak), avg_units_peak),
            avg_units_lt366=COALESCE(VALUES(avg_units_lt366), avg_units_lt366),
            avg_units_lt450=COALESCE(VALUES(avg_units_lt450), avg_units_lt450)`,
        [storeId, r.sku, r.gtin, itemId, reportStart, reportEnd,
         r.days, r.avgStd, r.avgLt, r.final, r.original, r.discount, taskId,
         r.lengthIn, r.widthIn, r.heightIn, r.weightLb,
         r.feeStd, r.feePeak, r.feeLt366, r.feeLt450,
         r.avgPeak, r.avgLt366, r.avgLt450]);
      upserts++;
    }
    // 2026-08-18 批4a：账单驱动式仓储日摊——导入落FACT成功后异步触发全量重展开（fire-and-forget，
    // 展开脚本自带守恒断言与幂等；失败只记日志不影响导入响应；订单利润V2实时查询自动生效）
    // 2026-08-19 加固：spawn 的 ENOENT 类失败走异步 error 事件，try/catch 捕不到；且 stdio:"ignore"
    // 会丢弃子进程全部输出（SUMMARY_JSON 无痕）。改为输出落盘 logs/storage_expand.log + error/exit 监听，
    // 成败可查、失败有痕迹；仍为 fire-and-forget，不影响导入响应，不改导入逻辑。
    try {
      const { spawn } = await import("child_process");
      const fsMod = await import("fs");
      const pathMod = await import("path");
      const logDir = pathMod.join(process.cwd(), "logs");
      if (!fsMod.existsSync(logDir)) fsMod.mkdirSync(logDir, { recursive: true });
      const expandLog = pathMod.join(logDir, "storage_expand.log");
      const outFd = fsMod.openSync(expandLog, "a");
      fsMod.writeSync(outFd, `\n[${new Date().toISOString()}] [storage-import] spawn expand task=${taskId}\n`);
      const child = spawn("npx", ["ts-node", "src/expandStorageFeeDaily.ts", "--confirm-write"],
        { cwd: process.cwd(), detached: true, stdio: ["ignore", outFd, outFd] });
      child.on("error", (e: Error) => {
        try { fsMod.writeSync(outFd, `[${new Date().toISOString()}] [storage-import] spawn ERROR task=${taskId}: ${e.message}\n`); } catch { /* noop */ }
        console.error(`[storage-import] 展开子进程启动失败(不影响导入) task=${taskId}:`, e.message);
      });
      child.on("exit", (code: number | null) => {
        try {
          fsMod.writeSync(outFd, `[${new Date().toISOString()}] [storage-import] expand exit code=${code} task=${taskId}\n`);
          fsMod.closeSync(outFd);
        } catch { /* noop */ }
        if (code !== 0) console.error(`[storage-import] 展开子进程退出码=${code} task=${taskId}，详见 logs/storage_expand.log`);
      });
      child.unref();
      console.log(`[storage-import] 已触发仓储日摊展开 task=${taskId}（输出落盘 logs/storage_expand.log）`);
    } catch (spawnErr) {
      console.error("[storage-import] 展开触发失败(不影响导入):", spawnErr instanceof Error ? spawnErr.message : String(spawnErr));
    }
    res.json({ ok: true, task_id: taskId, report_start: reportStart, report_end: reportEnd,
      rows: dataRows.length, upserts, item_mapped: mapped,
      total_reported: totalReported, total_computed: totalComputed,
      diff: Math.round((totalComputed - totalReported) * 100) / 100,
      daily_expand_triggered: true });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

// ── 财务工具 · 入库运输CSV导入（2026-08-12 批5；WFS「入库运输」报告，账期口径）─────
// 版式（真实样例实锤）：行1=店铺缩写；行2/3=ReportingPeriod_StartDate/EndDate 头+值；
//   明细表头("Shipment ID","Delivery Date",…18列)；下一行=英文说明行(跳过)；
//   数据行 Shipment ID 带 ="…"，同一货件多行(Base/燃油附加/DAS等Reason Code)，Actual Charge 带$。
// 分摊：货件Σ运费→按货件内SKU已发货数占比分摊（shipped主口径；缺发货数退declare并标记；
//   货件档案匹配不到→msku='' 整额留存 alloc_basis='none'，回补后重导覆盖）。
router.get("/inbound/list", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      // 同 storage/list：RAW 批次为主表，空报告留 0 记录（该期无沃尔玛承运运费属正常，非漏导）
      `SELECT b.store_id, COALESCE(s.store_name, b.store_id) AS store_name,
              DATE_FORMAT(b.report_start,'%Y-%m-%d') AS report_start,
              DATE_FORMAT(b.report_end,'%Y-%m-%d') AS report_end,
              b.task_id, b.operator,
              DATE_FORMAT(b.created_at,'%Y-%m-%d %H:%i') AS imported_at,
              COALESCE(a.shipment_cnt,0) AS shipment_cnt,
              COALESCE(a.alloc_rows,0) AS alloc_rows,
              COALESCE(a.freight_sum,0) AS freight_sum,
              COALESCE(a.unmatched_sum,0) AS unmatched_sum
         FROM (SELECT r.store_id, r.report_start, r.report_end, r.task_id, r.operator, r.created_at,
                      ROW_NUMBER() OVER (PARTITION BY r.store_id, r.report_start, r.report_end
                                         ORDER BY r.created_at DESC, r.task_id DESC) AS rn
                 FROM raw_walmart_inbound_csv r WHERE r.row_no = 0) b
         LEFT JOIN dim_store s ON s.platform='walmart' AND s.store_id=b.store_id
         LEFT JOIN (SELECT store_id, report_start, report_end,
                           COUNT(DISTINCT cargo_code) AS shipment_cnt, COUNT(*) AS alloc_rows,
                           ROUND(SUM(alloc_amount),2) AS freight_sum,
                           ROUND(SUM(IF(alloc_basis='none', alloc_amount, 0)),2) AS unmatched_sum
                      FROM fact_inbound_freight_alloc WHERE report_start IS NOT NULL
                     GROUP BY store_id, report_start, report_end) a
                ON a.store_id=b.store_id AND a.report_start=b.report_start AND a.report_end=b.report_end
        WHERE b.rn = 1
        ORDER BY b.report_end DESC, store_name ASC`);
    // operator 已由 RAW 主表直出，无需二次查询
    res.json({ rows });
  } catch (e) { res.status(500).json({ error: e instanceof Error ? e.message : String(e) }); }
  finally { await db.end().catch(() => undefined); }
});

router.post("/inbound-import", requireAuth, requireImport, async (req: Request, res: Response): Promise<void> => {
  const b = (req.body ?? {}) as Record<string, unknown>;
  const storeId = String(b.store_id ?? "").trim();
  const filename = String(b.filename ?? "").trim().slice(0, 200);
  const content = String(b.content ?? "");
  const u = fxUser(req);
  const actor = String(u?.display_name ?? u?.username ?? "").trim() || "admin_ui";
  if (!storeId) { res.status(400).json({ error: "store_id 必填" }); return; }
  if (!content || content.length < 100) { res.status(400).json({ error: "CSV内容为空或过短" }); return; }
  if (content.length > 8 * 1024 * 1024) { res.status(400).json({ error: "文件过大（>8MB）" }); return; }

  const lines = content.split(/\r\n|\n|\r/);
  let perHeaderIdx = -1, detHeaderIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const c = csvLine(lines[i]).map(cellClean);
    if (perHeaderIdx < 0 && c[0] === "ReportingPeriod_StartDate") perHeaderIdx = i;
    if (detHeaderIdx < 0 && c[0] === "Shipment ID" && c[1] === "Delivery Date") detHeaderIdx = i;
    if (perHeaderIdx >= 0 && detHeaderIdx >= 0) break;
  }
  if (perHeaderIdx < 0 || detHeaderIdx < 0) {
    res.status(400).json({ error: "格式不符：未找到 ReportingPeriod 头或明细表头(Shipment ID,Delivery Date)。请确认是 WFS「入库运输」报告原始CSV" }); return;
  }
  const perVals = csvLine(lines[perHeaderIdx + 1] ?? "").map(cellClean);
  const reportStart = perVals[0] ?? "", reportEnd = perVals[1] ?? "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(reportStart) || !/^\d{4}-\d{2}-\d{2}$/.test(reportEnd) || reportStart >= reportEnd) {
    res.status(400).json({ error: `报告期异常：${reportStart} ~ ${reportEnd}` }); return;
  }
  const header = csvLine(lines[detHeaderIdx]).map(cellClean);
  const iCargo = header.indexOf("Shipment ID");
  const iCharge = header.indexOf("Actual Charge");
  const iService = header.indexOf("Service Type");
  const iReason = header.indexOf("Reason Code");
  if (iCargo < 0 || iCharge < 0) { res.status(400).json({ error: "明细表头缺列：Shipment ID / Actual Charge（版式可能已变，需核对）" }); return; }

  interface IRow { cargo: string; charge: number; service: string; reason: string; raw: string }
  const dataRows: IRow[] = [];
  for (let i = detHeaderIdx + 1; i < lines.length; i++) {
    if (!lines[i] || !lines[i].trim()) continue;
    const c = csvLine(lines[i]).map(cellClean);
    const cargo = (c[iCargo] ?? "").toUpperCase();
    if (!/^[0-9A-Z]{5,20}$/.test(cargo) || !/[0-9]/.test(cargo)) continue; // 说明行/杂行跳过
    dataRows.push({ cargo, charge: numOf(c[iCharge] ?? ""), service: c[iService] ?? "", reason: c[iReason] ?? "", raw: lines[i] });
  }
  // 2026-08-14 需求方拍板：空报告不再拒收，照常导入并留 0 记录。
  //   实证：入库运输费仅对「使用沃尔玛承运(Walmart preferred carrier)」的货件收取，
  //   自送/第三方货代的货件不产生此费用 → 报告为空属正常。留 0 记录可让人工区分「已导=空」与「没导」。
  const byCargo = new Map<string, number>();
  for (const r of dataRows) byCargo.set(r.cargo, (byCargo.get(r.cargo) ?? 0) + r.charge);
  const freightTotal = Math.round(dataRows.reduce((a, r) => a + r.charge, 0) * 100) / 100;

  const db = await getDb();
  try {
    const [[st]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id FROM dim_store WHERE platform='walmart' AND store_id=? LIMIT 1`, [storeId]) as unknown as [mysql.RowDataPacket[]];
    if (!st) { res.status(400).json({ error: `store_id ${storeId} 不在 dim_store` }); return; }

    // ===== 防重：账期重叠拒收（同 storage-import 口径）=====
    const [ovl] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS rs, DATE_FORMAT(report_end,'%Y-%m-%d') AS re,
              COUNT(*) AS rows_cnt, ROUND(SUM(alloc_amount),2) AS amt
         FROM fact_inbound_freight_alloc
        WHERE platform='walmart' AND store_id=? AND report_start IS NOT NULL
          AND NOT (report_start=? AND report_end=?)
          AND report_start <= ? AND ? <= report_end
        GROUP BY report_start, report_end ORDER BY report_start LIMIT 5`,
      [storeId, reportStart, reportEnd, reportEnd, reportStart]);
    if ((ovl as mysql.RowDataPacket[]).length) {
      const conflicts = (ovl as mysql.RowDataPacket[])
        .map((o) => `${String(o.rs)}~${String(o.re)}（${o.rows_cnt}行/$${o.amt}）`).join("、");
      res.status(400).json({
        error: `账期重叠，已拒收：本次 ${reportStart} ~ ${reportEnd} 与已存在的 ${conflicts} 时间相交，` +
               `同时入库会造成重复累加。请改用与已有账期一致的标准账期报告；确需替换请先联系管理员清理冲突账期。`,
      }); return;
    }

    const day = new Date();
    const ymd = `${day.getFullYear()}${String(day.getMonth() + 1).padStart(2, "0")}${String(day.getDate()).padStart(2, "0")}`;
    const [[seqRow]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(DISTINCT task_id) AS n FROM raw_walmart_inbound_csv WHERE task_id LIKE ?`, [`WMINB-${ymd}-%`]) as unknown as [mysql.RowDataPacket[]];
    const taskId = `WMINB-${ymd}-${String(Number(seqRow?.n ?? 0) + 1).padStart(4, "0")}`;

    // RAW-first
    await db.query(
      `INSERT INTO raw_walmart_inbound_csv (task_id, store_id, operator, report_start, report_end, row_no, row_json, raw_hash)
       VALUES (?,?,?,?,?,0,?,MD5(?))`,
      [taskId, storeId, actor, reportStart, reportEnd,
       JSON.stringify({ filename, freight_total: freightTotal, shipments: byCargo.size }), content.slice(0, 2000)]);
    for (let i = 0; i < dataRows.length; i++) {
      await db.query(
        `INSERT INTO raw_walmart_inbound_csv (task_id, store_id, operator, report_start, report_end, row_no, row_json, raw_hash)
         VALUES (?,?,?,?,?,?,?,MD5(?))`,
        [taskId, storeId, actor, reportStart, reportEnd, i + 1, JSON.stringify({ line: dataRows[i].raw }), dataRows[i].raw]);
    }

    // 空报告：RAW 汇总行已留档（列表可见 0 记录），后续货件匹配/分摊全部跳过并直接返回。
    //   必须早返回——否则下方 `cargo_code IN (...)` 会拼出空 IN () 触发 SQL 语法错误。
    if (!dataRows.length) {
      res.json({ ok: true, task_id: taskId, report_start: reportStart, report_end: reportEnd,
        rows: 0, shipments: 0, freight_total: 0, matched_shipments: 0, alloc_rows: 0, unmatched_total: 0, empty: true,
        message: `该报告期（${reportStart} ~ ${reportEnd}）报告内无数据行，已留 0 记录` +
                 `（入库运输费仅对使用沃尔玛承运的货件收取，本期无此费用属正常）` });
      return;
    }

    // 货件档案匹配（cargo_code→shipment_id）+ 明细
    const cargos = Array.from(byCargo.keys());
    const [shipRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT cargo_code, shipment_id FROM fact_wfs_shipment
        WHERE platform='walmart' AND store_id=? AND cargo_code IN (${cargos.map(() => "?").join(",")})`,
      [storeId, ...cargos]);
    const cargoToShip = new Map<string, string>();
    for (const r of shipRows) cargoToShip.set(String(r.cargo_code).toUpperCase(), String(r.shipment_id));
    const shipIds = Array.from(new Set(Array.from(cargoToShip.values())));
    const itemsByShip = new Map<string, Array<{ msku: string; shipped: number; declared: number }>>();
    if (shipIds.length) {
      const [itemRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT shipment_id, msku, SUM(COALESCE(shipments_num,0)) AS shipped, SUM(COALESCE(declare_num,0)) AS declared
           FROM fact_wfs_shipment_item WHERE platform='walmart' AND store_id=? AND shipment_id IN (${shipIds.map(() => "?").join(",")})
          GROUP BY shipment_id, msku`, [storeId, ...shipIds]);
      for (const r of itemRows) {
        const k = String(r.shipment_id);
        if (!itemsByShip.has(k)) itemsByShip.set(k, []);
        itemsByShip.get(k)!.push({ msku: String(r.msku), shipped: Number(r.shipped ?? 0), declared: Number(r.declared ?? 0) });
      }
    }
    // item_id 映射（店铺内msku唯一命中）
    const allMskus = Array.from(new Set(Array.from(itemsByShip.values()).flat().map((x) => x.msku))).filter(Boolean);
    const byMsku = new Map<string, Set<string>>();
    if (allMskus.length) {
      const [mapRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT msku, item_id FROM dim_product WHERE platform='walmart' AND store_id=? AND msku IN (${allMskus.map(() => "?").join(",")}) GROUP BY msku, item_id`,
        [storeId, ...allMskus]);
      for (const m of mapRows) {
        const k = String(m.msku); if (!byMsku.has(k)) byMsku.set(k, new Set());
        byMsku.get(k)!.add(String(m.item_id));
      }
    }

    const settleMonth = reportEnd.slice(0, 7);
    // 重建口径（批5c，批5d修正作用域）：同一货件**在本报告期内**的旧分摊行先清除再重写。
    // 必须带 report_start/report_end：同一货件会跨账期分次扣费（实锤 7106481WFA 在05-02~05-15与05-16~05-29各有扣费），
    // 不限定账期会误删其他账期的分摊行。
    // 依据：这些行全部由本CSV派生，RAW层(raw_walmart_inbound_csv)原文永久留存可回溯；
    // 不清除则「先整额留存(none)→回补货件档案后重导」会同时残留 none 行与新明细行=重复计费。
    let purgedRows = 0;
    for (const cg of cargos) {
      const dres = (await db.query(
        `DELETE FROM fact_inbound_freight_alloc
          WHERE platform='walmart' AND store_id=? AND cargo_code=? AND report_start=? AND report_end=?`,
        [storeId, cg, reportStart, reportEnd])) as unknown as [{ affectedRows?: number }];
      purgedRows += Number(dres[0]?.affectedRows ?? 0);
    }
    let allocRows = 0, matched = 0; const unmatched: string[] = [];
    for (const [cargo, total] of byCargo.entries()) {
      const shipId = cargoToShip.get(cargo);
      const items = shipId ? (itemsByShip.get(shipId) ?? []) : [];
      const useShipped = items.some((x) => x.shipped > 0);
      const basisRows = items.filter((x) => (useShipped ? x.shipped > 0 : x.declared > 0));
      if (!shipId || !basisRows.length) {
        unmatched.push(cargo);
        await db.query(
          `INSERT INTO fact_inbound_freight_alloc (platform, store_id, cargo_code, shipment_id, settlement_month,
              report_start, report_end, msku, item_id, declare_num, freight_total, alloc_amount, alloc_basis, source_task_id)
           VALUES ('walmart',?,?,?,?,?,?,'','',0,?,?,'none',?)
           ON DUPLICATE KEY UPDATE shipment_id=VALUES(shipment_id), settlement_month=VALUES(settlement_month),
              report_start=VALUES(report_start), report_end=VALUES(report_end), freight_total=VALUES(freight_total),
              alloc_amount=VALUES(alloc_amount), alloc_basis='none', source_task_id=VALUES(source_task_id)`,
          [storeId, cargo, shipId ?? "", settleMonth, reportStart, reportEnd, total, total, taskId]);
        allocRows++;
        continue;
      }
      matched++;
      const basisSum = basisRows.reduce((a, x) => a + (useShipped ? x.shipped : x.declared), 0);
      let allocated = 0;
      for (let k = 0; k < basisRows.length; k++) {
        const it = basisRows[k];
        const qty = useShipped ? it.shipped : it.declared;
        const amt = k === basisRows.length - 1
          ? Math.round((total - allocated) * 10000) / 10000  // 尾差归末行，Σ分摊=货件总额精确守恒
          : Math.round((total * qty / basisSum) * 10000) / 10000;
        allocated = Math.round((allocated + amt) * 10000) / 10000;
        const ids = byMsku.get(it.msku);
        const itemId = ids && ids.size === 1 ? Array.from(ids)[0] : "";
        await db.query(
          `INSERT INTO fact_inbound_freight_alloc (platform, store_id, cargo_code, shipment_id, settlement_month,
              report_start, report_end, msku, item_id, declare_num, freight_total, alloc_amount, alloc_basis, source_task_id)
           VALUES ('walmart',?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON DUPLICATE KEY UPDATE shipment_id=VALUES(shipment_id), settlement_month=VALUES(settlement_month),
              report_start=VALUES(report_start), report_end=VALUES(report_end), item_id=IF(VALUES(item_id)='', item_id, VALUES(item_id)),
              declare_num=VALUES(declare_num), freight_total=VALUES(freight_total),
              alloc_amount=VALUES(alloc_amount), alloc_basis=VALUES(alloc_basis), source_task_id=VALUES(source_task_id)`,
          [storeId, cargo, shipId, settleMonth, reportStart, reportEnd, it.msku, itemId, qty,
           total, amt, useShipped ? "shipped" : "declare", taskId]);
        allocRows++;
      }
    }
    res.json({ ok: true, task_id: taskId, report_start: reportStart, report_end: reportEnd,
      rows: dataRows.length, shipments: byCargo.size, matched_shipments: matched,
      unmatched_shipments: unmatched, freight_total: freightTotal, alloc_rows: allocRows, purged_rows: purgedRows });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

// ── 财务工具 · 入库运输「未匹配留存」重分摊（2026-08-12 批5c）───────────────────
// 背景：导入时货件档案(fact_wfs_shipment)里查不到该 cargo_code，运费无法落到SKU，
//   整额挂在货件上(msku='' alloc_basis='none')。这是**中间态**，不允许长期挂账。
// 处置阶梯：
//   ① 重新匹配(match)：货件回补同步后档案已存在 → 按已发货数占比正常分摊（最优，可溯源）；
//   ② 二次分摊(pool)：档案永久缺失（平台幽灵货件/历史遗留）→ 按**同账期同店铺已分摊运费金额占比**
//      摊到该账期的SKU上，alloc_basis='pool' 单独标记，保证 Σ入账 = Σ账单，钱不留在货件上；
//   ③ 该账期一条已分摊行都没有 → 保持 none 并回报，需先补货件档案（不猜、不乱摊）。
// 守恒：每个货件独立重建（先 DELETE 该 cargo 全部行再写入），尾差归末行，Σ分摊 = 货件账单额。
router.get("/inbound/unmatched", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT a.store_id, COALESCE(s.store_name, a.store_id) AS store_name, a.cargo_code,
              DATE_FORMAT(a.report_start,'%Y-%m-%d') AS report_start, DATE_FORMAT(a.report_end,'%Y-%m-%d') AS report_end,
              ROUND(a.alloc_amount,2) AS amount, a.source_task_id AS task_id
         FROM fact_inbound_freight_alloc a
         LEFT JOIN dim_store s ON s.platform=a.platform AND s.store_id=a.store_id
        WHERE a.alloc_basis='none' AND a.alloc_amount <> 0
        ORDER BY a.report_end DESC, a.store_id ASC, a.cargo_code ASC`);
    res.json({ rows, total: Math.round(rows.reduce((x, r) => x + Number(r.amount ?? 0), 0) * 100) / 100 });
  } catch (e) { res.status(500).json({ error: e instanceof Error ? e.message : String(e) }); }
  finally { await db.end().catch(() => undefined); }
});

router.post("/inbound/reallocate", requireAuth, requireImport, async (req: Request, res: Response): Promise<void> => {
  const b = (req.body ?? {}) as Record<string, unknown>;
  const storeId = String(b.store_id ?? "").trim();          // 空=全部店铺
  const cargoOne = String(b.cargo_code ?? "").trim().toUpperCase(); // 空=全部未匹配货件
  const allowPool = b.pool === true || String(b.pool ?? "") === "1"; // 是否允许二次分摊兜底
  const u = fxUser(req);
  const actor = String(u?.display_name ?? u?.username ?? "").trim() || "admin_ui";

  const db = await getDb();
  try {
    const w: string[] = ["a.alloc_basis='none'", "a.alloc_amount <> 0"];
    const pa: unknown[] = [];
    if (storeId) { w.push("a.store_id=?"); pa.push(storeId); }
    if (cargoOne) { w.push("a.cargo_code=?"); pa.push(cargoOne); }
    const [pend] = await db.query<mysql.RowDataPacket[]>(
      `SELECT a.store_id, a.cargo_code, a.alloc_amount AS amount, a.settlement_month,
              DATE_FORMAT(a.report_start,'%Y-%m-%d') AS report_start, DATE_FORMAT(a.report_end,'%Y-%m-%d') AS report_end,
              a.source_task_id AS task_id
         FROM fact_inbound_freight_alloc a WHERE ${w.join(" AND ")}
        ORDER BY a.report_end DESC, a.cargo_code ASC`, pa);
    if (!pend.length) { res.json({ ok: true, handled: 0, results: [], note: "没有待处理的未匹配留存" }); return; }

    const results: Array<Record<string, unknown>> = [];
    let matchedCnt = 0, pooledCnt = 0, stillCnt = 0, movedAmt = 0;

    for (const p of pend) {
      const sid = String(p.store_id), cargo = String(p.cargo_code).toUpperCase();
      const total = Math.round(Number(p.amount ?? 0) * 10000) / 10000;
      const rs = String(p.report_start ?? ""), re = String(p.report_end ?? "");
      const sm = String(p.settlement_month ?? re.slice(0, 7));
      const tid = String(p.task_id ?? "");

      // ① 重新匹配货件档案
      const [shipRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT shipment_id FROM fact_wfs_shipment WHERE platform='walmart' AND store_id=? AND cargo_code=? LIMIT 1`, [sid, cargo]);
      let basis: Array<{ msku: string; qty: number }> = [];
      let basisName = "";
      const shipId = shipRows.length ? String(shipRows[0].shipment_id) : "";
      if (shipId) {
        const [items] = await db.query<mysql.RowDataPacket[]>(
          `SELECT msku, SUM(COALESCE(shipments_num,0)) AS shipped, SUM(COALESCE(declare_num,0)) AS declared
             FROM fact_wfs_shipment_item WHERE platform='walmart' AND store_id=? AND shipment_id=? GROUP BY msku`, [sid, shipId]);
        const useShipped = items.some((x) => Number(x.shipped ?? 0) > 0);
        basis = items
          .map((x) => ({ msku: String(x.msku), qty: Number(useShipped ? x.shipped : x.declared) || 0 }))
          .filter((x) => x.msku && x.qty > 0);
        if (basis.length) basisName = useShipped ? "shipped" : "declare";
      }

      // ② 二次分摊兜底：同店铺同账期已分摊运费占比
      if (!basisName && allowPool) {
        const [pool] = await db.query<mysql.RowDataPacket[]>(
          `SELECT msku, ROUND(SUM(alloc_amount),4) AS w FROM fact_inbound_freight_alloc
            WHERE platform='walmart' AND store_id=? AND report_start=? AND report_end=?
              AND alloc_basis IN ('shipped','declare') AND msku<>''
            GROUP BY msku HAVING w > 0`, [sid, rs, re]);
        basis = pool.map((x) => ({ msku: String(x.msku), qty: Number(x.w) || 0 })).filter((x) => x.qty > 0);
        if (basis.length) basisName = "pool";
      }

      if (!basisName || !basis.length) {
        stillCnt++;
        results.push({ store_id: sid, cargo_code: cargo, amount: total, result: "still_none",
          note: shipId ? "货件档案存在但无发货/申报明细" : (allowPool ? "该账期无任何已分摊行，无法二次分摊；请先回补货件档案" : "货件档案仍缺失（未开启二次分摊）") });
        continue;
      }

      // item_id 映射
      const mk = Array.from(new Set(basis.map((x) => x.msku)));
      const idMap = new Map<string, string>();
      const [mapRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT msku, item_id FROM dim_product WHERE platform='walmart' AND store_id=? AND msku IN (${mk.map(() => "?").join(",")}) GROUP BY msku, item_id`,
        [sid, ...mk]);
      const cnt = new Map<string, Set<string>>();
      for (const m of mapRows) {
        const k = String(m.msku); if (!cnt.has(k)) cnt.set(k, new Set());
        cnt.get(k)!.add(String(m.item_id));
      }
      for (const [k, v] of cnt.entries()) if (v.size === 1) idMap.set(k, Array.from(v)[0]);

      // 该货件在本账期内整体重建：先删本账期旧行（含本条 none），再按基数写入（不跨账期）
      await db.query(
        `DELETE FROM fact_inbound_freight_alloc
          WHERE platform='walmart' AND store_id=? AND cargo_code=? AND report_start=? AND report_end=?`,
        [sid, cargo, rs, re]);
      const sum = basis.reduce((x, y) => x + y.qty, 0);
      let acc = 0;
      for (let k = 0; k < basis.length; k++) {
        const amt = k === basis.length - 1
          ? Math.round((total - acc) * 10000) / 10000
          : Math.round((total * basis[k].qty / sum) * 10000) / 10000;
        acc = Math.round((acc + amt) * 10000) / 10000;
        await db.query(
          `INSERT INTO fact_inbound_freight_alloc (platform, store_id, cargo_code, shipment_id, settlement_month,
              report_start, report_end, msku, item_id, declare_num, freight_total, alloc_amount, alloc_basis, source_task_id)
           VALUES ('walmart',?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON DUPLICATE KEY UPDATE shipment_id=VALUES(shipment_id), settlement_month=VALUES(settlement_month),
              report_start=VALUES(report_start), report_end=VALUES(report_end),
              item_id=IF(VALUES(item_id)='', item_id, VALUES(item_id)), declare_num=VALUES(declare_num),
              freight_total=VALUES(freight_total), alloc_amount=VALUES(alloc_amount),
              alloc_basis=VALUES(alloc_basis), source_task_id=VALUES(source_task_id)`,
          [sid, cargo, shipId, sm, rs, re, basis[k].msku, idMap.get(basis[k].msku) ?? "",
           basisName === "pool" ? 0 : basis[k].qty, total, amt, basisName, tid]);
      }
      movedAmt = Math.round((movedAmt + total) * 100) / 100;
      if (basisName === "pool") pooledCnt++; else matchedCnt++;
      results.push({ store_id: sid, cargo_code: cargo, amount: total,
        result: basisName === "pool" ? "pooled" : "matched", basis: basisName, sku_rows: basis.length });
    }

    res.json({ ok: true, actor, handled: pend.length, matched: matchedCnt, pooled: pooledCnt,
      still_none: stillCnt, moved_amount: movedAmt, results });
  } catch (e) { res.status(500).json({ error: e instanceof Error ? e.message : String(e) }); }
  finally { await db.end().catch(() => undefined); }
});

// ═══════════════════════════════════════════════════════════════════════════
// 单品现金利润（2026-08-13 批12；取值口径定稿 v1 + 需求方三项拍板：
//   自然月区间多选 / 主币CNY可切USD / 早期评估区页底）
// 记账规则终稿（TASK_CHANGE_LOG 2026-08-13）：切点 2026-05-01；期初=05-01 WFS快照×财务一刀价；
//   切点前采购/头程现金不计；期初池按月FIFO消耗（耗尽即停，防双算）；
//   老货切点后补入不进池（现金口径真实反映）；海外仓不计、惠州仓只进资产KPI。
// 类目分桶（syncWalmartBillDaily CATEGORY_MAP 实证 slug）：
//   EXCLUDED（专管道替代，只进哨兵）: storage / inbound_transport / ad_platform
//   店铺级行: sem / review_accelerator；msku为空或映射不中的其余类目 → 店铺级其他
//   按品分桶: sale | refund_* | 赔付返还(lost/found/damage_warehouse/wfs_refund/ad_credit/
//     wfs_discount_adjustment/inventory_transfer) | WFS配送(wfs_fulfillment) | 其他按品(剩余全部，
//     含佣金类 other:* —— 佣金 slug 尚未实证单列，净额不丢)
// 币种：recon/ads/storage/inbound=USD；purchase/firstmile/期初消耗=CNY；
//   每月按「上一个月领星 my_rate」互折（与领星摊费口径同源），双币同时返回。
// ═══════════════════════════════════════════════════════════════════════════
const ICP_CUTOFF = "2026-05-01";
const ICP_CUTOFF_M = "2026-05";
const ICP_EXCLUDED = new Set(["storage", "inbound_transport", "ad_platform"]);
const ICP_COMP = new Set(["lost_inventory", "found_inventory", "damage_warehouse", "wfs_refund", "ad_credit", "wfs_discount_adjustment", "inventory_transfer"]);
// 虚拟SKU（非真实库存/测评壳）：整行豁免，收入/成本/销量/早期区全部剔除（需求方 2026-08-13 拍板）
const ICP_VIRTUAL = new Set(["XY2007", "DC001", "QH888"]);

function icpPrevMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 2, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
function icpMonths(from: string, to: string): string[] {
  const out: string[] = [];
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  let cur = new Date(Date.UTC(fy, fm - 1, 1));
  const last = new Date(Date.UTC(ty, tm - 1, 1));
  while (cur <= last && out.length < 24) {
    out.push(`${cur.getUTCFullYear()}-${String(cur.getUTCMonth() + 1).padStart(2, "0")}`);
    cur = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1));
  }
  return out;
}
const icpR2 = (v: number): number => Math.round(v * 100) / 100;

interface IcpCell { c: number; u: number } // c=CNY u=USD 双币
interface IcpRow {
  store_id: string; store_name: string; sku: string;
  sale: IcpCell; refund: IcpCell; comp: IcpCell; wfs_fee: IcpCell; other_item: IcpCell;
  ads: IcpCell; storage: IcpCell; inbound: IcpCell;
  purchase: IcpCell; firstmile: IcpCell; opening_cost: IcpCell;
  sold_qty: number; opening_used_qty: number;
  revenue: IcpCell; expense: IcpCell; profit: IcpCell;
  mskus?: string[]; item_ids?: string[];
}

router.get("/item-cash-profit", async (req: Request, res: Response): Promise<void> => {
  const q = (req.query ?? {}) as Record<string, unknown>;
  const nowM = new Date().toISOString().slice(0, 7);
  let from = String(q.from ?? ICP_CUTOFF_M).trim() || ICP_CUTOFF_M;
  let to = String(q.to ?? nowM).trim() || nowM;
  if (!/^\d{4}-\d{2}$/.test(from)) from = ICP_CUTOFF_M;
  if (!/^\d{4}-\d{2}$/.test(to)) to = nowM;
  if (from < ICP_CUTOFF_M) from = ICP_CUTOFF_M;
  if (to < from) to = from;
  const storeFilter = String(q.store_id ?? "").trim();
  const months = icpMonths(from, to);
  const db = await getDb();
  try {
    // ── 汇率：month → 折算率（上一个月 my_rate，退 rate_org）──
    const [fxRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT rate_month, my_rate, rate_org FROM fact_lingxing_fx_rate WHERE currency_code='USD'`);
    const fxRaw = new Map<string, { my: number; org: number }>();
    for (const r of fxRows) fxRaw.set(String(r.rate_month), { my: Number(r.my_rate) || 0, org: Number(r.rate_org) || 0 });
    const rateOf = (m: string): number => {
      const p = fxRaw.get(icpPrevMonth(m));
      return p ? (p.my > 0 ? p.my : p.org) : 0;
    };
    const fxMissing: string[] = [];
    const cellAdd = (cell: IcpCell, m: string, amt: number, cur: "USD" | "CNY"): void => {
      const r = rateOf(m);
      if (cur === "USD") { cell.u += amt; if (r > 0) cell.c += amt * r; else if (!fxMissing.includes(m)) fxMissing.push(m); }
      else { cell.c += amt; if (r > 0) cell.u += amt / r; else if (!fxMissing.includes(m)) fxMissing.push(m); }
    };
    const zc = (): IcpCell => ({ c: 0, u: 0 });

    // ── msku→sku 映射（唯一命中才用）+ sku→msku 反向（展示列）──
    const [mapRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT msku, MAX(sku) AS sku FROM fact_inventory_daily
        WHERE COALESCE(sku,'')<>'' AND msku<>'' GROUP BY msku HAVING COUNT(DISTINCT sku)=1`);
    const m2s = new Map<string, string>();
    const skuMskus = new Map<string, Set<string>>(); // sku → 该品下所有 msku（展示）
    for (const r of mapRows) {
      const msku = String(r.msku), sku = String(r.sku);
      m2s.set(msku, sku);
      if (!skuMskus.has(sku)) skuMskus.set(sku, new Set());
      skuMskus.get(sku)!.add(msku);
    }
    const isVirtual = (sku: string): boolean => ICP_VIRTUAL.has(sku);

    // ── 行容器 ──
    const rows = new Map<string, IcpRow>();
    const storeNames = new Map<string, string>();
    const rowOf = (store: string, sku: string): IcpRow => {
      const k = `${store}||${sku}`;
      let r = rows.get(k);
      if (!r) {
        r = { store_id: store, store_name: storeNames.get(store) ?? store, sku,
          sale: zc(), refund: zc(), comp: zc(), wfs_fee: zc(), other_item: zc(),
          ads: zc(), storage: zc(), inbound: zc(), purchase: zc(), firstmile: zc(), opening_cost: zc(),
          sold_qty: 0, opening_used_qty: 0, revenue: zc(), expense: zc(), profit: zc() };
        rows.set(k, r);
      }
      return r;
    };
    interface StoreRow { store_id: string; store_name: string; sem: IcpCell; review: IcpCell; comp: IcpCell; other: IcpCell; ads_unmapped: IcpCell; purchase_unmapped: IcpCell; unmapped_cnt: number }
    const storeRows = new Map<string, StoreRow>();
    const sRowOf = (store: string): StoreRow => {
      let r = storeRows.get(store);
      if (!r) { r = { store_id: store, store_name: storeNames.get(store) ?? store, sem: zc(), review: zc(), comp: zc(), other: zc(), ads_unmapped: zc(), purchase_unmapped: zc(), unmapped_cnt: 0 }; storeRows.set(store, r); }
      return r;
    };

    // ── 店铺名 + 有效 dim_store 白名单（结算坏id修复/晶彩绝伦剔除）──
    const [stRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name FROM dim_store WHERE platform='walmart'`);
    for (const r of stRows) storeNames.set(String(r.store_id), String(r.store_name));
    const validStore = new Set(storeNames.keys());
    const validArr = Array.from(validStore);
    const fixCache = new Map<string, string | null>();
    // 领星结算 storeId 数字精度损坏（末位差 ±<=16；id 超 Number 安全整数，按字符串比对：
    // 前缀完全相同 + 末4位数值差<=16），就近映射回 dim_store 合法 id；晶彩绝伦无候选→null 剔除。
    const closeId = (a: string, b: string): boolean => {
      if (a.length !== b.length || a.length < 5) return false;
      if (a.slice(0, -4) !== b.slice(0, -4)) return false;
      return Math.abs(Number(a.slice(-4)) - Number(b.slice(-4))) <= 16;
    };
    const normStore = (id: string): string | null => {
      if (!id) return null;
      if (validStore.has(id)) return id;
      if (fixCache.has(id)) return fixCache.get(id)!;
      let hit: string | null = null;
      for (const v of validArr) { if (closeId(v, id)) { hit = v; break; } }
      fixCache.set(id, hit); return hit;
    };

    // ── dim_product：广告 item_id 退路 + msku→item_id 展示 ──
    const [dpRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, msku, item_id FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>''`);
    const adsItemToMsku = new Map<string, string | null>(); // store||item_id → msku（歧义置 null）
    const storeMskuItems = new Map<string, Set<string>>(); // store||msku → item_ids
    for (const r of dpRows) {
      const st = String(r.store_id), it = String(r.item_id), mk = String(r.msku);
      const ik = `${st}||${it}`;
      if (!adsItemToMsku.has(ik)) adsItemToMsku.set(ik, mk);
      else if (adsItemToMsku.get(ik) !== mk) adsItemToMsku.set(ik, null);
      const mkk = `${st}||${mk}`;
      if (!storeMskuItems.has(mkk)) storeMskuItems.set(mkk, new Set());
      storeMskuItems.get(mkk)!.add(it);
    }

    // ── 发货单头程 sku→店铺份额（采购 sid=0 按此回填/分摊，需求方拍板：经发货单按SKU归属）──
    const [shipRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, sku, SUM(delivery_num) AS qty FROM fact_shipping_first_let
        WHERE match_status='matched' AND store_id<>'' GROUP BY store_id, sku`);
    const shipShare = new Map<string, Map<string, number>>(); // sku → store → qty
    for (const r of shipRows) {
      const st = normStore(String(r.store_id)); if (!st) continue;
      const sku = String(r.sku); const qy = Number(r.qty) || 0; if (!sku || qy <= 0) continue;
      if (!shipShare.has(sku)) shipShare.set(sku, new Map());
      const m = shipShare.get(sku)!; m.set(st, (m.get(st) ?? 0) + qy);
    }
    let purchaseUnattr = 0; // 无发货归属的切点后采购（CNY）

    const storeCond = storeFilter ? " AND store_id=? " : " ";
    const sf = (base: unknown[]): unknown[] => storeFilter ? [...base, storeFilter] : base;

    // ── ① 回款 recon（USD；EXCLUDED 类目只进哨兵）──
    const [recon] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, msku, fee_category, DATE_FORMAT(period_end,'%Y-%m') AS m, ROUND(SUM(amount),4) AS amt
         FROM fact_reconciliation_item
        WHERE DATE_FORMAT(period_end,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, msku, fee_category, m`, sf([from, to]));
    const sentinelPipe = { storage: 0, inbound: 0, ad: 0 };
    let reconAll = 0;
    for (const r of recon) {
      const store = String(r.store_id), cat = String(r.fee_category), m = String(r.m), amt = Number(r.amt) || 0;
      reconAll = icpR2(reconAll + amt);
      if (ICP_EXCLUDED.has(cat)) {
        if (cat === "storage") sentinelPipe.storage += amt;
        else if (cat === "inbound_transport") sentinelPipe.inbound += amt;
        else sentinelPipe.ad += amt;
        continue;
      }
      if (cat === "sem") { cellAdd(sRowOf(store).sem, m, amt, "USD"); continue; }
      if (cat === "review_accelerator") { cellAdd(sRowOf(store).review, m, amt, "USD"); continue; }
      const msku = String(r.msku ?? "");
      const sku = msku ? (m2s.get(msku) ?? "") : "";
      if (sku && isVirtual(sku)) continue; // 虚拟SKU整行豁免
      if (!sku) {
        // 无品归店铺级：赔付返还类目单列，其余进「其他店铺级」（R3 实证赔付7类目 100% 无 msku）
        const sr = sRowOf(store);
        if (ICP_COMP.has(cat)) cellAdd(sr.comp, m, amt, "USD");
        else cellAdd(sr.other, m, amt, "USD");
        if (msku) sr.unmapped_cnt += 1;
        continue;
      }
      const row = rowOf(store, sku);
      if (cat === "sale") cellAdd(row.sale, m, amt, "USD");
      else if (cat.startsWith("refund_")) cellAdd(row.refund, m, amt, "USD");
      else if (ICP_COMP.has(cat)) cellAdd(row.comp, m, amt, "USD");
      else if (cat === "wfs_fulfillment") cellAdd(row.wfs_fee, m, amt, "USD");
      else cellAdd(row.other_item, m, amt, "USD");
    }

    // ── ② 广告（USD；msku 空退 store+item_id→dim_product 映射；R5 实证 msku 99% 为空）──
    // 2026-08-25 需求方拍板：按品广告费含SV无商品ID行(占位1001类)分摊——统一口径见 adsItemSpendAlloc.ts
    const [ads] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(msku,'') AS msku, COALESCE(item_id,'') AS item_id,
              DATE_FORMAT(stat_date,'%Y-%m') AS m, ROUND(SUM(ad_spend),4) AS amt
         FROM ${adjustedAdsFactSql()} fa
        WHERE platform='walmart' AND DATE_FORMAT(stat_date,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, msku, item_id, m`, sf([from, to]));
    let adsPipeTotal = 0;
    for (const r of ads) {
      const store = String(r.store_id), m = String(r.m), amt = Number(r.amt) || 0;
      adsPipeTotal += amt;
      const msku = String(r.msku), itemId = String(r.item_id);
      let sku = msku ? (m2s.get(msku) ?? "") : "";
      if (!sku && itemId) { const mk = adsItemToMsku.get(`${store}||${itemId}`); if (mk) sku = m2s.get(mk) ?? ""; }
      if (sku && isVirtual(sku)) continue; // 虚拟SKU豁免
      if (!sku) { cellAdd(sRowOf(store).ads_unmapped, m, -amt, "USD"); continue; } // 未映射广告单列
      cellAdd(rowOf(store, sku).ads, m, amt, "USD");
    }

    // ── ③ 仓储费（USD；表内 sku 列实为 MSKU，需映射）──
    const [stor] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, sku AS msku, DATE_FORMAT(report_start,'%Y-%m') AS m, ROUND(SUM(final_storage_fee),4) AS amt
         FROM fact_wfs_storage_fee
        WHERE DATE_FORMAT(report_start,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, msku, m`, sf([from, to]));
    let storPipeTotal = 0;
    for (const r of stor) {
      const store = String(r.store_id), m = String(r.m), amt = Number(r.amt) || 0;
      storPipeTotal += amt;
      const sku = m2s.get(String(r.msku)) ?? String(r.msku); // 报告SKU多与本地SKU同名，映射不中时按原名
      if (isVirtual(sku)) continue; // 虚拟SKU豁免
      cellAdd(rowOf(store, sku).storage, m, amt, "USD");
    }

    // ── ④ 入库运输分摊（USD）──
    const [inb] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, msku, DATE_FORMAT(report_start,'%Y-%m') AS m, ROUND(SUM(alloc_amount),4) AS amt
         FROM fact_inbound_freight_alloc
        WHERE DATE_FORMAT(report_start,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, msku, m`, sf([from, to]));
    let inbPipeTotal = 0;
    for (const r of inb) {
      const store = String(r.store_id), m = String(r.m), amt = Number(r.amt) || 0;
      inbPipeTotal += amt;
      const sku = m2s.get(String(r.msku)) ?? "";
      if (sku && isVirtual(sku)) continue; // 虚拟SKU豁免
      if (!sku) { cellAdd(sRowOf(store).other, m, -amt, "USD"); continue; }
      cellAdd(rowOf(store, sku).inbound, m, amt, "USD");
    }

    // ── ⑤ 采购现金（CNY；仅切点后；sid 有效→直接归店，sid=0/无效→按发货单 sku 份额分摊）──
    // 不在 SQL 里按 sid 过滤（sid=0 需先分摊再按店铺筛），全量取回后于 JS 归属
    const [pur] = await db.query<mysql.RowDataPacket[]>(
      `SELECT i.sid AS store_id, i.sku, DATE_FORMAT(c.order_time,'%Y-%m') AS m, ROUND(SUM(i.amount),4) AS amt
         FROM fact_purchase_cash_item i JOIN fact_purchase_cash c ON c.order_sn=i.order_sn
        WHERE c.order_time >= ? AND DATE_FORMAT(c.order_time,'%Y-%m') BETWEEN ? AND ?
          AND c.status_text <> '已作废'
        GROUP BY i.sid, i.sku, m`,
      [ICP_CUTOFF, from, to]);
    for (const r of pur) {
      const sku = String(r.sku), m = String(r.m), amt = Number(r.amt) || 0;
      if (isVirtual(sku)) continue; // 虚拟SKU豁免
      const sid = normStore(String(r.store_id));
      if (sid) { // 采购单已带有效店铺
        if (storeFilter && sid !== storeFilter) continue;
        cellAdd(rowOf(sid, sku).purchase, m, amt, "CNY");
        continue;
      }
      // sid=0/无效：按发货单 sku 份额分摊到实际发货店铺
      const share = shipShare.get(sku);
      if (!share || share.size === 0) {
        if (storeFilter) continue; // 无归属采购不进单店视图
        purchaseUnattr = icpR2(purchaseUnattr + amt);
        continue;
      }
      let tot = 0; for (const q of share.values()) tot += q;
      const entries = Array.from(share.entries());
      let allocated = 0;
      for (let i2 = 0; i2 < entries.length; i2++) {
        const [st2, q2] = entries[i2];
        const isLast = i2 === entries.length - 1;
        const part = isLast ? icpR2(amt - allocated) : icpR2(amt * q2 / tot);
        allocated = icpR2(allocated + part);
        if (part === 0) continue;
        if (storeFilter && st2 !== storeFilter) continue;
        cellAdd(rowOf(st2, sku).purchase, m, part, "CNY");
      }
    }

    // ── ⑥ 头程现金（CNY；cash_date≥切点；仅唯一命中行；排除作废/预估）──
    const [fm] = await db.query<mysql.RowDataPacket[]>(
      `SELECT l.store_id, l.sku, DATE_FORMAT(l.cash_date,'%Y-%m') AS m,
              ROUND(SUM(l.per_first_let_cost * l.delivery_num),4) AS amt
         FROM fact_shipping_first_let l
         JOIN fact_shipping_order o ON o.platform=l.platform AND o.shipping_code=l.shipping_code
        WHERE l.match_status='matched' AND l.store_id<>'' AND l.value_source<>'预估费用'
          AND o.shipping_status<>'已作废' AND l.cash_date >= ?
          AND DATE_FORMAT(l.cash_date,'%Y-%m') BETWEEN ? AND ? ${storeFilter ? " AND l.store_id=? " : " "}
        GROUP BY l.store_id, l.sku, m`,
      storeFilter ? [ICP_CUTOFF, from, to, storeFilter] : [ICP_CUTOFF, from, to]);
    for (const r of fm) {
      const sku = String(r.sku); if (isVirtual(sku)) continue; // 虚拟SKU豁免
      cellAdd(rowOf(String(r.store_id), sku).firstmile, String(r.m), Number(r.amt) || 0, "CNY");
    }

    // ── ⑦ 期初池 FIFO 消耗（CNY；销量=结算月度 localSku；从切点月推进到 to）──
    const [openRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT sku, snap_qty_0501, opening_unit_cost FROM biz_finance_opening_cost WHERE cutoff_date=?`, [ICP_CUTOFF]);
    const pool = new Map<string, { qty: number; unit: number }>();
    let openingValue = 0;
    for (const r of openRows) {
      const qy = Number(r.snap_qty_0501) || 0, un = Number(r.opening_unit_cost) || 0;
      pool.set(String(r.sku), { qty: qy, unit: un });
      openingValue = icpR2(openingValue + qy * un);
    }
    const [salesRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, settlement_month AS m, JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.localSku')) AS sku,
              SUM(sales_num) AS qty
         FROM fact_settlement_msku_monthly
        WHERE settlement_month BETWEEN ? AND ?
        GROUP BY store_id, m, sku`, [ICP_CUTOFF_M, to]);
    // sku×月 总销量 + 店铺份额（store_id 经 normStore 修复领星精度损坏；虚拟SKU/晶彩绝伦剔除）
    const salesBySkuM = new Map<string, number>();
    const salesByStore = new Map<string, number>();
    for (const r of salesRows) {
      const sku = String(r.sku ?? ""); if (!sku || isVirtual(sku)) continue;
      const store = normStore(String(r.store_id)); if (!store) continue;
      const k = `${sku}||${r.m}`;
      salesBySkuM.set(k, (salesBySkuM.get(k) ?? 0) + Number(r.qty));
      salesByStore.set(`${k}||${store}`, (salesByStore.get(`${k}||${store}`) ?? 0) + Number(r.qty));
    }
    let consumedValueAll = 0; // 全时段累计消耗额（期初恒等哨兵真实核算）
    const fifoMonths = icpMonths(ICP_CUTOFF_M, to);
    for (const m of fifoMonths) {
      for (const [sku, p] of pool.entries()) {
        if (p.qty <= 0) continue;
        const sold = salesBySkuM.get(`${sku}||${m}`) ?? 0;
        if (sold <= 0) continue;
        const consume = Math.min(p.qty, sold);
        p.qty -= consume;
        consumedValueAll = icpR2(consumedValueAll + consume * p.unit);
        if (m < from || m > to) continue; // 池照常推进，只有选中区间才计成本
        // 按店铺销量份额分摊消耗（Σ=SKU 消耗总量）
        let allocated = 0; const shares: Array<{ store: string; q: number }> = [];
        for (const [k2, q2] of salesByStore.entries()) {
          if (k2.startsWith(`${sku}||${m}||`)) shares.push({ store: k2.split("||")[2], q: Number(q2) });
        }
        for (let i2 = 0; i2 < shares.length; i2++) {
          const isLast = i2 === shares.length - 1;
          const cq = isLast ? consume - allocated : Math.round(consume * shares[i2].q / sold);
          allocated += cq;
          if (cq <= 0) continue;
          if (storeFilter && shares[i2].store !== storeFilter) continue;
          const row = rowOf(shares[i2].store, sku);
          row.opening_used_qty += cq;
          cellAdd(row.opening_cost, m, cq * p.unit, "CNY");
        }
      }
    }
    let poolRemainQty = 0, poolRemainValue = 0;
    for (const p of pool.values()) { poolRemainQty += p.qty; poolRemainValue = icpR2(poolRemainValue + p.qty * p.unit); }

    // 区间销量落行（展示列）
    for (const [k, qy] of salesByStore.entries()) {
      const [sku, m, store] = k.split("||");
      if (m < from || m > to) continue;
      if (storeFilter && store !== storeFilter) continue;
      rowOf(store, sku).sold_qty += Number(qy);
    }

    // ── 汇总列 ──
    const fin = (c0: IcpCell): IcpCell => ({ c: icpR2(c0.c), u: icpR2(c0.u) });
    const outRows: IcpRow[] = [];
    for (const r of rows.values()) {
      r.store_name = storeNames.get(r.store_id) ?? r.store_id;
      const rev: IcpCell = { c: r.sale.c + r.refund.c + r.comp.c, u: r.sale.u + r.refund.u + r.comp.u };
      // recon 扣费列为账单负号；管道成本列为正数成本
      const exp: IcpCell = {
        c: -r.wfs_fee.c - r.other_item.c + r.ads.c + r.storage.c + r.inbound.c + r.purchase.c + r.firstmile.c + r.opening_cost.c,
        u: -r.wfs_fee.u - r.other_item.u + r.ads.u + r.storage.u + r.inbound.u + r.purchase.u + r.firstmile.u + r.opening_cost.u,
      };
      r.revenue = fin(rev); r.expense = fin(exp);
      r.profit = { c: icpR2(rev.c - exp.c), u: icpR2(rev.u - exp.u) };
      (["sale", "refund", "comp", "wfs_fee", "other_item", "ads", "storage", "inbound", "purchase", "firstmile", "opening_cost"] as const)
        .forEach((f) => { r[f] = fin(r[f]); });
      // 展示：该 sku 的 msku 列表 + item_id 列表（本店铺）
      const mks = Array.from(skuMskus.get(r.sku) ?? []);
      r.mskus = mks.slice(0, 12);
      const its = new Set<string>();
      for (const mk of mks) for (const it of storeMskuItems.get(`${r.store_id}||${mk}`) ?? []) its.add(it);
      r.item_ids = Array.from(its).slice(0, 12);
      outRows.push(r);
    }
    outRows.sort((a, b) => b.profit.c - a.profit.c);

    // ── 惠州仓资产 KPI（需求方：国内仓计资产、海外仓不计）──
    const [[hz]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT ROUND(SUM(stock_cost),2) AS v, SUM(balance_num) AS q FROM fact_lingxing_batch
        WHERE wh_name='惠州仓库' AND balance_num>0`) as unknown as [mysql.RowDataPacket[]];

    // ── 早期评估区（2026-01~04：收入=recon 按月；成本=一刀价×结算销量）──
    const [earlyRecon] = await db.query<mysql.RowDataPacket[]>(
      `SELECT msku, DATE_FORMAT(period_end,'%Y-%m') AS m, ROUND(SUM(amount),4) AS amt
         FROM fact_reconciliation_item
        WHERE DATE_FORMAT(period_end,'%Y-%m') < ? ${storeCond}
        GROUP BY msku, m`, sf([ICP_CUTOFF_M]));
    const [earlySales] = await db.query<mysql.RowDataPacket[]>(
      `SELECT JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.localSku')) AS sku, SUM(sales_num) AS qty
         FROM fact_settlement_msku_monthly WHERE settlement_month < ? ${storeCond}
        GROUP BY sku`, sf([ICP_CUTOFF_M]));
    const openUnit = new Map<string, number>();
    for (const r of openRows) openUnit.set(String(r.sku), Number(r.opening_unit_cost) || 0);
    interface EarlyRow { sku: string; revenue_usd: number; sold_qty: number; cost_cny: number | null }
    const earlyMap = new Map<string, EarlyRow>();
    const eRowOf = (sku: string): EarlyRow => {
      let r = earlyMap.get(sku);
      if (!r) { r = { sku, revenue_usd: 0, sold_qty: 0, cost_cny: openUnit.has(sku) ? 0 : null }; earlyMap.set(sku, r); }
      return r;
    };
    let earlyStoreLevel = 0;
    for (const r of earlyRecon) {
      const sku = m2s.get(String(r.msku ?? "")) ?? "";
      if (sku && isVirtual(sku)) continue; // 虚拟SKU豁免
      if (!sku) { earlyStoreLevel = icpR2(earlyStoreLevel + Number(r.amt)); continue; }
      eRowOf(sku).revenue_usd = icpR2(eRowOf(sku).revenue_usd + Number(r.amt));
    }
    for (const r of earlySales) {
      const sku = String(r.sku ?? ""); if (!sku || isVirtual(sku)) continue;
      const er = eRowOf(sku);
      er.sold_qty += Number(r.qty);
      if (er.cost_cny !== null) er.cost_cny = icpR2(er.cost_cny + Number(r.qty) * (openUnit.get(sku) ?? 0));
    }
    const early = Array.from(earlyMap.values()).sort((a, b) => b.revenue_usd - a.revenue_usd);

    // ── 哨兵（USD 口径比对；阈值前端标注）──
    const [[tp]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT ROUND(SUM(total_payable),2) AS v FROM fact_reconciliation_period
        WHERE DATE_FORMAT(period_end,'%Y-%m') BETWEEN ? AND ? ${storeCond}`, sf([from, to])) as unknown as [mysql.RowDataPacket[]];
    const sentinels = [
      { name: "回款完整性", expect: Number(tp?.v ?? 0), actual: icpR2(reconAll), note: "Σ对账明细 = Σ账期Total Payable（USD）" },
      { name: "广告管道vs账单", expect: icpR2(-sentinelPipe.ad), actual: icpR2(adsPipeTotal), note: "fact_ads_product_daily vs recon ad_platform（USD；SEM单列不含）" },
      { name: "仓储管道vs账单", expect: icpR2(-sentinelPipe.storage), actual: icpR2(storPipeTotal), note: "仓储报告导入 vs recon storage（USD；账期起日对齐）" },
      { name: "入库运输管道vs账单", expect: icpR2(-sentinelPipe.inbound), actual: icpR2(inbPipeTotal), note: "分摊表 vs recon inbound_transport（USD）" },
      { name: "期初恒等", expect: icpR2(openingValue), actual: icpR2(consumedValueAll + poolRemainValue), note: "全时段累计消耗额 + 池余量 = 期初 ¥1,576,231.25（FIFO 真实核算）" },
    ].map((x) => ({ ...x, diff: icpR2(x.actual - x.expect), ok: Math.abs(x.actual - x.expect) <= Math.max(50, Math.abs(x.expect) * 0.02) }));

    res.json({
      from, to, months, cutoff: ICP_CUTOFF,
      kpi: {
        opening_value: icpR2(openingValue),
        pool_remain_qty: poolRemainQty, pool_remain_value: icpR2(poolRemainValue),
        huizhou_value: Number(hz?.v ?? 0), huizhou_qty: Number(hz?.q ?? 0),
        profit_cny: icpR2(outRows.reduce((x, r) => x + r.profit.c, 0)),
        profit_usd: icpR2(outRows.reduce((x, r) => x + r.profit.u, 0)),
      },
      rows: outRows,
      store_rows: [
        ...Array.from(storeRows.values()).map((r0) => ({
          ...r0, store_name: storeNames.get(r0.store_id) ?? r0.store_id,
          sem: fin(r0.sem), review: fin(r0.review), comp: fin(r0.comp),
          other: fin(r0.other), ads_unmapped: fin(r0.ads_unmapped), purchase_unmapped: fin(r0.purchase_unmapped),
        })),
        // 无发货归属的切点后采购（全店视图才出现；单店已过滤）
        ...(purchaseUnattr !== 0 && !storeFilter ? [{
          store_id: "__UNATTR_PURCHASE__", store_name: "（未归属采购·待发货单补全店铺）",
          sem: zc(), review: zc(), comp: zc(), other: zc(), ads_unmapped: zc(),
          purchase_unmapped: { c: icpR2(purchaseUnattr), u: rateOf(to) > 0 ? icpR2(purchaseUnattr / rateOf(to)) : 0 },
          unmapped_cnt: 0,
        }] : []),
      ],
      early, early_store_level_usd: earlyStoreLevel,
      sentinels, fx_missing: fxMissing,
      excluded_note: "海外仓/Miami虚拟库存/XY2007/DC001/QH888 整行豁免；切点前采购头程现金不计（一刀切）；佣金已含在回款销售净额（沃尔玛结算口径），不单列避免双算",
    });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

export default router;
