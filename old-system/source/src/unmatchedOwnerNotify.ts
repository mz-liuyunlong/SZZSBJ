/**
 * unmatchedOwnerNotify.ts — 🙋 待认领产品日报 + 绩效扣分状态机（v4，2026-07-22 拍板全量实施）
 *
 * 需求方 2026-07-22 已拍板口径（详见 交付件/需求规格_通报升级四件套.md + 帮助文章 notify_unmatched_owner）：
 *   - 周一日报 = 第 1 次提醒；周四仍未认领 = 第 2 次提醒，二提当期即记扣 5 分/产品；
 *   - 谁认领谁承担扣分；认领结果+扣分随下一期日报「绩效扣分通报」区公布（不单独发）；
 *   - 有扣分才同步黄少如（花名册解析私信）；
 *   - 产品退出清单（认领/归档/停用）后再次出现 → 轮次清零重算（新开一轮）；
 *   - 卡片结构（v2 样板确认）：首次提醒在上 → 二次提醒在下（红）→ 绩效扣分通报（红）；
 *   - 通道改造：webhook 路径取消，应用机器人发 FEISHU_UNMATCHED_CHAT_IDS（CSV，两个管理群）。
 *
 * 状态表：event_owner_claim_alert（EVENT 层，本脚本唯一写入方）
 * 台账：  biz_perf_deduction（append-only，uq_perf_ref 防重复落账）
 * 写入纪律：writeState = --send 且非 --test-card；dry-run / test-card 零写入零真实发送。
 *
 * 用法：
 *   npx ts-node src/unmatchedOwnerNotify.ts               # dry-run：判定+状态迁移预览，零发送零写入
 *   npx ts-node src/unmatchedOwnerNotify.ts --send        # 真实发送 + 状态/台账写入
 *   npx ts-node src/unmatchedOwnerNotify.ts --test-card   # 卡片只发测试群，零写入
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  getTenantToken,
  getTestChatId,
  mirrorToTestEnabled,
  parseListEnv,
  resolveActiveMembers,
  sendCardWithFallbackToChat,
  sendTextToTarget,
} from "./feishuNotify";
import { CardBundle } from "./notifyRules/reminderCards";

const DETAIL_LIMIT = 50;
const PRODUCT_MANAGEMENT_URL = "http://42.193.254.170/admin/#/feishu-raw-sales-data";
const DEDUCT_POINTS = 5;
const CHAT_IDS_ENV = "FEISHU_UNMATCHED_CHAT_IDS"; // CSV：两个管理群 chat_id（应用机器人）
const SUPERVISOR_NAME = (process.env.PERF_SUPERVISOR_NAME ?? "黄少如").trim();

interface UnmatchedProduct extends mysql.RowDataPacket {
  platform: string;
  store_id: string;
  store_name: string | null;
  item_id: string;
  msku: string;
  product_name: string | null;
  owner?: string | null;   // 2026-07-27 仅"建议归档"取数用（待认领查询不选此列，保持 undefined）
}
interface CountRow extends mysql.RowDataPacket { active_total: number; }
interface CycleRow extends mysql.RowDataPacket {
  id: number;
  platform: string;
  store_id: string;
  store_name: string;
  item_id: string;
  msku: string;
  product_name: string;
  cycle_start_date: string;
  first_notified_at: string | null;
  second_notified_at: string | null;
  deduction_points: number;
  claimed_by: string | null;
  announced_at: string | null;
  status: string;
}
interface WfsMissingProduct extends mysql.RowDataPacket {
  platform: string; store_id: string; store_name: string | null;
  item_id: string; msku: string; product_name: string | null; owner: string | null;
}
interface WfsCycleRow extends mysql.RowDataPacket {
  id: number; platform: string; store_id: string; store_name: string;
  item_id: string; msku: string; product_name: string;
  cycle_start_date: string; first_notified_at: string | null; second_notified_at: string | null;
  deduction_points: number; owner_name: string | null; deducted_at: string | null;
  announced_at: string | null; status: string;
}

function dbConfig(): mysql.ConnectionOptions {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true, // 铁律：DATE/DATETIME 读取必须 dateStrings
  };
}
function getErrorMessage(e: unknown): string { return e instanceof Error ? e.message : String(e); }
function normStr(v: unknown): string { return String(v ?? "").trim(); }
function todayCst(): string { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date()); }
function keyOf(p: { platform: string; store_id: string; item_id: string; msku: string }): string {
  return [normStr(p.platform), normStr(p.store_id), normStr(p.item_id), normStr(p.msku)].join("|");
}

// ── 数据读取 ────────────────────────────────────────────────────────────────

async function fetchUnmatchedProducts(db: mysql.Connection): Promise<{ activeTotal: number; items: UnmatchedProduct[] }> {
  const [countRows] = await db.query<CountRow[]>(
    `SELECT COUNT(*) AS active_total FROM dim_product
     WHERE item_id IS NOT NULL AND item_id <> ''
       AND COALESCE(product_management_status, 'active') = 'active'`,
  );
  const [items] = await db.query<UnmatchedProduct[]>(
    `SELECT platform, store_id, store_name, item_id, msku,
            COALESCE(product_name, item_name, '') AS product_name
     FROM dim_product
     WHERE item_id IS NOT NULL AND item_id <> ''
       AND COALESCE(product_management_status, 'active') = 'active'
       AND (owner IS NULL OR TRIM(owner) = '' OR owner = '未分配')
       AND COALESCE(walmart_publish_status, '') <> 'UNPUBLISHED'
     ORDER BY store_name, item_id, msku`,
  );
  return { activeTotal: Number(countRows[0]?.active_total ?? 0), items };
}

// ── 缺 WFS 配送费产品：active 非CS 且 人工(dim_product_cost_config.delivery_fee)与自动(dim_product_wfs_fee_auto.fee)均缺 ──
// 口径与产品管理页一致(feishuRawSalesRoutes 费率解析)，另加"自动费也缺"条件(有自动费=利润准确,不列)。带出 owner=承担负责人。
async function fetchWfsMissing(db: mysql.Connection): Promise<WfsMissingProduct[]> {
  const [rows] = await db.query<WfsMissingProduct[]>(
    `WITH latest_fee_store AS (
       SELECT platform, store_id, item_id, msku, delivery_fee FROM (
         SELECT c.*, ROW_NUMBER() OVER (PARTITION BY platform, COALESCE(store_id,''), item_id, COALESCE(msku,'') ORDER BY effective_date DESC, updated_at DESC, id DESC) AS rn
         FROM dim_product_cost_config c WHERE platform='walmart' AND status='active' AND delivery_fee IS NOT NULL
       ) x WHERE rn=1
     ),
     latest_fee_item AS (
       SELECT platform, item_id, msku, delivery_fee FROM (
         SELECT c.*, ROW_NUMBER() OVER (PARTITION BY platform, item_id, COALESCE(msku,'') ORDER BY effective_date DESC, updated_at DESC, id DESC) AS rn
         FROM dim_product_cost_config c WHERE platform='walmart' AND status='active' AND delivery_fee IS NOT NULL
       ) x WHERE rn=1
     )
     SELECT p.platform, p.store_id, p.store_name, p.item_id, p.msku,
            COALESCE(p.product_name, p.item_name, '') AS product_name, p.owner
     FROM dim_product p
     LEFT JOIN latest_fee_store fs ON fs.platform=p.platform AND COALESCE(fs.store_id,'')=COALESCE(p.store_id,'') AND fs.item_id=p.item_id AND COALESCE(fs.msku,'')=COALESCE(p.msku,'')
     LEFT JOIN latest_fee_item  fi ON fi.platform=p.platform AND fi.item_id=p.item_id AND COALESCE(fi.msku,'')=COALESCE(p.msku,'')
     LEFT JOIN dim_product_wfs_fee_auto dfa ON dfa.platform='walmart' AND dfa.store_id=p.store_id AND dfa.msku=p.msku AND dfa.fee IS NOT NULL
     WHERE p.item_id IS NOT NULL AND p.item_id <> ''
       AND COALESCE(p.product_management_status,'active')='active'
       AND COALESCE(p.msku,'') NOT LIKE 'CS%'
       AND COALESCE(p.walmart_publish_status,'') <> 'UNPUBLISHED'
       AND (COALESCE(fs.delivery_fee, fi.delivery_fee) IS NULL OR COALESCE(fs.delivery_fee, fi.delivery_fee) <= 0)
       AND dfa.fee IS NULL
     ORDER BY store_name, item_id, msku`,
  );
  return rows;
}

// ── 缺 GPT 关键词分析链接：active·非归档·有负责人·未配置 keyword 链接 ──
async function fetchGptKwMissing(db: mysql.Connection): Promise<WfsMissingProduct[]> {
  const [rows] = await db.query<WfsMissingProduct[]>(
    `SELECT p.platform, p.store_id, p.store_name, p.item_id, p.msku,
            COALESCE(p.product_name, p.item_name, '') AS product_name, p.owner
     FROM dim_product p
     WHERE p.item_id IS NOT NULL AND p.item_id <> ''
       AND COALESCE(p.product_management_status,'active')='active'
       AND COALESCE(p.walmart_publish_status,'') <> 'UNPUBLISHED'
       AND p.owner IS NOT NULL AND TRIM(p.owner) <> '' AND p.owner <> '未分配'
       AND NOT EXISTS (SELECT 1 FROM dim_product_gpt_link g
                       WHERE g.item_id = p.item_id AND g.link_type = 'keyword' AND g.url IS NOT NULL AND g.url <> '')
     ORDER BY store_name, item_id, msku`,
  );
  return rows;
}

// ── 缺 GPT 广告分析链接：active·非归档·有负责人·WFS库存连续14天>0·未配置 ads 链接 ──
// "连续14天"口径：近14天(相对最新快照)每个快照 wfs_available_stock>0 且覆盖满14个快照日(HAVING MIN>0 且 COUNT>=14)。
async function fetchGptAdsMissing(db: mysql.Connection): Promise<WfsMissingProduct[]> {
  const [rows] = await db.query<WfsMissingProduct[]>(
    `WITH wfs14 AS (
       SELECT platform, store_id, item_id, msku
       FROM fact_inventory_daily
       WHERE platform='walmart'
         AND snapshot_date > DATE_SUB((SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform='walmart'), INTERVAL 14 DAY)
       GROUP BY platform, store_id, item_id, msku
       HAVING MIN(wfs_available_stock) > 0 AND COUNT(DISTINCT snapshot_date) >= 14
     )
     SELECT p.platform, p.store_id, p.store_name, p.item_id, p.msku,
            COALESCE(p.product_name, p.item_name, '') AS product_name, p.owner
     FROM dim_product p
     JOIN wfs14 w ON w.platform=p.platform AND COALESCE(w.store_id,'')=COALESCE(p.store_id,'') AND w.item_id=p.item_id AND COALESCE(w.msku,'')=COALESCE(p.msku,'')
     WHERE p.item_id IS NOT NULL AND p.item_id <> ''
       AND COALESCE(p.product_management_status,'active')='active'
       AND COALESCE(p.walmart_publish_status,'') <> 'UNPUBLISHED'
       AND p.owner IS NOT NULL AND TRIM(p.owner) <> '' AND p.owner <> '未分配'
       AND NOT EXISTS (SELECT 1 FROM dim_product_gpt_link g
                       WHERE g.item_id = p.item_id AND g.link_type = 'ads' AND g.url IS NOT NULL AND g.url <> '')
     ORDER BY store_name, item_id, msku`,
  );
  return rows;
}

// ── 建议归档候选：所有 active 的 UNPUBLISHED(已下架)，不论有无负责人 ────────────
// 2026-07-27 需求(口径已放宽)：下架品都该提醒清理归档；带出负责人便于管理群知道催谁。
//   已归档(product_management_status<>'active')的不再重复提醒。
async function fetchArchiveCandidates(db: mysql.Connection): Promise<UnmatchedProduct[]> {
  const [rows] = await db.query<UnmatchedProduct[]>(
    `SELECT platform, store_id, store_name, item_id, msku,
            COALESCE(product_name, item_name, '') AS product_name,
            owner
     FROM dim_product
     WHERE item_id IS NOT NULL AND item_id <> ''
       AND COALESCE(product_management_status, 'active') = 'active'
       AND walmart_publish_status = 'UNPUBLISHED'
     ORDER BY store_name, item_id, msku`,
  );
  return rows;
}

/** 店铺名三层兜底（2026-07-18 既有逻辑原样保留） */
async function fetchStoreNameMap(db: mysql.Connection): Promise<Map<string, string>> {
  const m = new Map<string, string>();
  const merge = (rows: mysql.RowDataPacket[], src: string): void => {
    let added = 0;
    for (const r of rows) {
      const id = normStr(r.store_id);
      const name = normStr(r.store_name);
      if (id && name && !m.has(id)) { m.set(id, name); added += 1; }
    }
    if (added) console.log(`  [店铺名] ${src} 补充 ${added} 个`);
  };
  const [p] = await db.query<mysql.RowDataPacket[]>(
    `SELECT store_id, MAX(NULLIF(TRIM(store_name), '')) AS store_name
     FROM dim_product WHERE store_id IS NOT NULL AND store_id <> '' GROUP BY store_id`,
  );
  merge(p, "dim_product");
  try {
    const [cfg] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name FROM dim_store_config WHERE store_id IS NOT NULL AND store_id <> ''`,
    );
    merge(cfg, "dim_store_config");
  } catch (e) { console.log(`  [警告] dim_store_config 店铺名兜底失败（忽略）: ${getErrorMessage(e)}`); }
  try {
    const [inv] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, MAX(NULLIF(TRIM(store_name), '')) AS store_name
       FROM fact_inventory_daily WHERE store_id IS NOT NULL AND store_id <> '' GROUP BY store_id`,
    );
    merge(inv, "fact_inventory_daily");
  } catch (e) { console.log(`  [警告] fact_inventory_daily 店铺名兜底失败（忽略）: ${getErrorMessage(e)}`); }
  return m;
}

// ── 状态机判定（纯读，不写库） ──────────────────────────────────────────────

interface StatePlan {
  firstReminder: UnmatchedProduct[];          // 首提区（含当日已首提的重复运行行）
  secondReminder: { item: UnmatchedProduct; cycle: CycleRow | null; alreadyDeducted: boolean }[]; // 二提区
  newCycles: UnmatchedProduct[];              // 需 insert 的新轮次
  upgrades: CycleRow[];                       // 需升级二提+扣分的行
  claims: { cycle: CycleRow; claimedBy: string }[];   // 检测到认领（本次写 claimed）
  voids: CycleRow[];                          // 退出清单非认领（归档/停用等）→ void
  announce: { cycle: CycleRow; claimedBy: string }[]; // 扣分通报区（含历史 claimed 未公布）
  closeZero: CycleRow[];                      // 认领但无扣分 → 静默关闭
}

async function planState(db: mysql.Connection, items: UnmatchedProduct[]): Promise<StatePlan> {
  const today = todayCst();
  const [cycles] = await db.query<CycleRow[]>(
    `SELECT id, platform, store_id, store_name, item_id, msku, product_name,
            DATE_FORMAT(cycle_start_date, '%Y-%m-%d') AS cycle_start_date,
            first_notified_at, second_notified_at, deduction_points, claimed_by, announced_at, status
     FROM event_owner_claim_alert WHERE status IN ('open', 'claimed')`,
  );
  const openByKey = new Map<string, CycleRow>();
  for (const c of cycles) if (c.status === "open") openByKey.set(keyOf(c), c);
  const currentKeys = new Set(items.map(keyOf));

  const plan: StatePlan = { firstReminder: [], secondReminder: [], newCycles: [], upgrades: [], claims: [], voids: [], announce: [], closeZero: [] };

  for (const it of items) {
    const cyc = openByKey.get(keyOf(it));
    if (!cyc) {
      plan.firstReminder.push(it);
      plan.newCycles.push(it);
    } else if (cyc.second_notified_at) {
      plan.secondReminder.push({ item: it, cycle: cyc, alreadyDeducted: true }); // 已扣分仍未认领，继续二提区展示
    } else if (cyc.cycle_start_date < today) {
      plan.secondReminder.push({ item: it, cycle: cyc, alreadyDeducted: false });
      plan.upgrades.push(cyc);
    } else {
      plan.firstReminder.push(it); // 当日重复运行：仍视为首提，不升级
    }
  }

  // 退出清单的 open 轮次：认领 or 作废
  for (const cyc of cycles) {
    if (cyc.status !== "open" || currentKeys.has(keyOf(cyc))) continue;
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT owner, COALESCE(product_management_status, 'active') AS pms
       FROM dim_product WHERE platform = ? AND store_id = ? AND item_id = ? AND msku = ?`,
      [cyc.platform, cyc.store_id, cyc.item_id, cyc.msku],
    );
    const owner = normStr(rows[0]?.owner);
    const pms = normStr(rows[0]?.pms);
    if (rows.length > 0 && pms === "active" && owner && owner !== "未分配") {
      plan.claims.push({ cycle: cyc, claimedBy: owner });
    } else {
      plan.voids.push(cyc); // 归档/停用/查无此行 → 作废，轮次清零重算
    }
  }

  // 扣分通报区 = 本次新认领(有扣分) + 历史 claimed 未公布（上次发送失败的兜底）
  for (const c of plan.claims) {
    if (Number(c.cycle.deduction_points) > 0) plan.announce.push(c);
    else plan.closeZero.push(c.cycle);
  }
  for (const cyc of cycles) {
    if (cyc.status === "claimed" && !cyc.announced_at) {
      if (Number(cyc.deduction_points) > 0) plan.announce.push({ cycle: cyc, claimedBy: normStr(cyc.claimed_by) });
      else plan.closeZero.push(cyc);
    }
  }
  return plan;
}

interface WfsPlan {
  firstReminder: WfsMissingProduct[];
  secondReminder: { item: WfsMissingProduct; cycle: WfsCycleRow }[];
  newCycles: WfsMissingProduct[];
  upgrades: { cycle: WfsCycleRow; owner: string }[];
  charges: { cycle: WfsCycleRow; owner: string }[];
  exits: WfsCycleRow[];
}

async function planWfsState(db: mysql.Connection, items: WfsMissingProduct[]): Promise<WfsPlan> {
  const today = todayCst();
  const [cycles] = await db.query<WfsCycleRow[]>(
    `SELECT id, platform, store_id, store_name, item_id, msku, product_name,
            DATE_FORMAT(cycle_start_date, '%Y-%m-%d') AS cycle_start_date,
            first_notified_at, second_notified_at, deduction_points, owner_name, deducted_at, announced_at, status
     FROM event_wfs_fee_missing_alert WHERE status = 'open'`,
  );
  const openByKey = new Map<string, WfsCycleRow>();
  for (const c of cycles) openByKey.set(keyOf(c), c);
  const currentKeys = new Set(items.map(keyOf));
  const plan: WfsPlan = { firstReminder: [], secondReminder: [], newCycles: [], upgrades: [], charges: [], exits: [] };
  for (const it of items) {
    const cyc = openByKey.get(keyOf(it));
    const owner = normStr(it.owner);
    const hasOwner = owner !== "" && owner !== "未分配";
    if (!cyc) {
      plan.firstReminder.push(it);
      plan.newCycles.push(it);
    } else if (cyc.second_notified_at) {
      plan.secondReminder.push({ item: it, cycle: cyc });
      if (!cyc.deducted_at && hasOwner) plan.charges.push({ cycle: cyc, owner });
    } else if (cyc.cycle_start_date < today) {
      plan.secondReminder.push({ item: it, cycle: cyc });
      plan.upgrades.push({ cycle: cyc, owner });
      if (hasOwner) plan.charges.push({ cycle: cyc, owner });
    } else {
      plan.firstReminder.push(it);
    }
  }
  for (const cyc of cycles) if (!currentKeys.has(keyOf(cyc))) plan.exits.push(cyc);
  return plan;
}

// ── 卡片构建（v2 样板：首提 → 二提(红) → 绩效扣分通报(红)） ────────────────

function buildPerfCard(args: {
  dateStr: string;
  activeTotal: number;
  plan: StatePlan;
  nameMap: Map<string, string>;
  archiveItems: UnmatchedProduct[];
  wfsPlan: WfsPlan;
  kwPlan: WfsPlan;
  adsPlan: WfsPlan;
  testPrefix: boolean;
}): CardBundle {
  const { plan, nameMap } = args;
  const prefix = args.testPrefix ? "【测试】" : "";
  const title = `${prefix}📋 产品管理提醒通知 ｜ ${args.dateStr}`;
  const storeOf = (p: UnmatchedProduct): string =>
    normStr(p.store_name) || nameMap.get(normStr(p.store_id)) || normStr(p.store_id);
  const totalUnmatched = plan.firstReminder.length + plan.secondReminder.length;
  const newDeduct = plan.upgrades.length;

  const wfsTotal = args.wfsPlan.firstReminder.length + args.wfsPlan.secondReminder.length;
  const kwTotal = args.kwPlan.firstReminder.length + args.kwPlan.secondReminder.length;
  const adsTotal = args.adsPlan.firstReminder.length + args.adsPlan.secondReminder.length;
  if (totalUnmatched === 0 && plan.announce.length === 0 && args.archiveItems.length === 0 && wfsTotal === 0 && args.wfsPlan.charges.length === 0 && kwTotal === 0 && args.kwPlan.charges.length === 0 && adsTotal === 0 && args.adsPlan.charges.length === 0) {
    const text = `当前 active 商品 ${args.activeTotal} 个，暂无待处理的产品管理提醒 ✅`;
    return {
      title,
      card: {
        config: { wide_screen_mode: true },
        header: { template: "green", title: { tag: "plain_text", content: title } },
        elements: [
          { tag: "div", text: { tag: "lark_md", content: text } },
          { tag: "action", actions: [{ tag: "button", text: { tag: "plain_text", content: "打开产品管理页面" }, type: "default", url: PRODUCT_MANAGEMENT_URL }] },
        ],
      },
      fallbackText: `${title}\n${text}\n页面：${PRODUCT_MANAGEMENT_URL}`,
    };
  }

  const elements: Record<string, unknown>[] = [];
  const fb: string[] = [title];
  const meta = `**active 商品** ${args.activeTotal} 个　·　**待认领** ${totalUnmatched} 个　·　**本期新增扣分产品** <font color='red'>**${newDeduct}**</font> 个${args.archiveItems.length ? `　·　**建议归档** ${args.archiveItems.length} 个` : ""}${wfsTotal ? `　·　**缺WFS费** ${wfsTotal} 个` : ""}${kwTotal ? `　·　**缺关键词链接** ${kwTotal} 个` : ""}${adsTotal ? `　·　**缺广告链接** ${adsTotal} 个` : ""}`;
  elements.push({ tag: "div", text: { tag: "lark_md", content: meta } });
  elements.push({ tag: "hr" });
  fb.push(`active 商品：${args.activeTotal} ｜ 待认领：${totalUnmatched} ｜ 本期新增扣分产品：${newDeduct}`);

  let seq = 0;
  const pushGrouped = (list: UnmatchedProduct[], render: (p: UnmatchedProduct) => string, renderFb: (p: UnmatchedProduct) => string): void => {
    const byStore = new Map<string, UnmatchedProduct[]>();
    for (const it of list) {
      const s = storeOf(it) || "-";
      if (!byStore.has(s)) byStore.set(s, []);
      byStore.get(s)!.push(it);
    }
    for (const [store, rows] of byStore) {
      const lines: string[] = [`〔${store}〕（${rows.length} 个）`];
      fb.push(`店铺：${store}（${rows.length} 个）`);
      for (const it of rows) {
        seq += 1;
        lines.push(`${seq}. ${render(it)}`);
        fb.push(`${seq}. ${renderFb(it)}`);
      }
      elements.push({ tag: "div", text: { tag: "lark_md", content: lines.join("\n") } });
    }
  };

  // 区1：首次提醒（在上）
  if (plan.firstReminder.length > 0) {
    elements.push({ tag: "div", text: { tag: "lark_md", content: `**📌 首次提醒（下期仍未认领将升级二次提醒并扣 ${DEDUCT_POINTS} 分）**` } });
    fb.push("", `📌 首次提醒（下期仍未认领将升级二次提醒并扣 ${DEDUCT_POINTS} 分）`);
    pushGrouped(
      plan.firstReminder.slice(0, DETAIL_LIMIT),
      (p) => `**${normStr(p.msku) || "-"}** ｜ ItemID ${normStr(p.item_id) || "-"}`,
      (p) => `MSKU：${normStr(p.msku) || "-"} ｜ ItemID：${normStr(p.item_id) || "-"}`,
    );
    elements.push({ tag: "hr" });
  }

  // 区2：二次提醒（在下，红）
  if (plan.secondReminder.length > 0) {
    elements.push({ tag: "div", text: { tag: "lark_md", content: `<font color='red'>**⚠️【二次提醒】以下产品本期起每个记扣 ${DEDUCT_POINTS} 分，认领者承担**</font>` } });
    fb.push("", `⚠️【二次提醒】以下产品本期起每个记扣 ${DEDUCT_POINTS} 分，认领者承担`);
    pushGrouped(
      plan.secondReminder.slice(0, DETAIL_LIMIT).map((s) => s.item),
      (p) => `**${normStr(p.msku) || "-"}** ｜ ItemID ${normStr(p.item_id) || "-"} <font color='red'>**⚠️【二次提醒】 扣${DEDUCT_POINTS}分**</font>`,
      (p) => `MSKU：${normStr(p.msku) || "-"} ｜ ItemID：${normStr(p.item_id) || "-"} ⚠️【二次提醒】扣${DEDUCT_POINTS}分`,
    );
    elements.push({ tag: "hr" });
  }

  // 区3：绩效扣分通报（红）
  if (plan.announce.length > 0) {
    const lines = [`<font color='red'>**🧾 绩效扣分通报**</font>`];
    fb.push("", "🧾 绩效扣分通报");
    for (const a of plan.announce) {
      lines.push(`**${a.claimedBy || "-"}** 认领二提产品 **${normStr(a.cycle.msku) || "-"}** → <font color='red'>**扣 ${a.cycle.deduction_points} 分**</font>`);
      fb.push(`${a.claimedBy || "-"} 认领二提产品 ${normStr(a.cycle.msku) || "-"} → 扣 ${a.cycle.deduction_points} 分`);
    }
    elements.push({ tag: "div", text: { tag: "lark_md", content: lines.join("\n") } });
    elements.push({ tag: "hr" });
  }

  // 区W1：缺 WFS 费·首次提醒
  if (args.wfsPlan.firstReminder.length > 0) {
    elements.push({ tag: "div", text: { tag: "lark_md", content: `**🚚 缺 WFS 配送费·首次提醒（缺费→利润核算不准；下期仍缺将扣 ${DEDUCT_POINTS} 分）**` } });
    fb.push("", `🚚 缺 WFS 配送费·首次提醒（下期仍缺将扣 ${DEDUCT_POINTS} 分）`);
    pushGrouped(
      args.wfsPlan.firstReminder.slice(0, DETAIL_LIMIT),
      (p) => `**${normStr(p.msku) || "-"}** ｜ ItemID ${normStr(p.item_id) || "-"} ｜ 负责人 ${normStr(p.owner) || "未认领"}`,
      (p) => `MSKU：${normStr(p.msku) || "-"} ｜ ItemID：${normStr(p.item_id) || "-"} ｜ 负责人：${normStr(p.owner) || "未认领"}`,
    );
    elements.push({ tag: "hr" });
  }
  // 区W2：缺 WFS 费·二次提醒（红，扣分）
  if (args.wfsPlan.secondReminder.length > 0) {
    elements.push({ tag: "div", text: { tag: "lark_md", content: `<font color='red'>**⚠️【二次提醒】以下产品缺 WFS 配送费，本期起每个记扣 ${DEDUCT_POINTS} 分，负责人承担**</font>` } });
    fb.push("", `⚠️【二次提醒】缺 WFS 配送费，本期起每个记扣 ${DEDUCT_POINTS} 分，负责人承担`);
    pushGrouped(
      args.wfsPlan.secondReminder.slice(0, DETAIL_LIMIT).map((s) => s.item),
      (p) => `**${normStr(p.msku) || "-"}** ｜ ItemID ${normStr(p.item_id) || "-"} ｜ 负责人 ${normStr(p.owner) || "未认领"} <font color='red'>**⚠️ 扣${DEDUCT_POINTS}分**</font>`,
      (p) => `MSKU：${normStr(p.msku) || "-"} ｜ ItemID：${normStr(p.item_id) || "-"} ｜ 负责人：${normStr(p.owner) || "未认领"} ⚠️扣${DEDUCT_POINTS}分`,
    );
    elements.push({ tag: "hr" });
  }
  // 区W3：缺 WFS 费·绩效扣分通报（红）
  if (args.wfsPlan.charges.length > 0) {
    const wlines = [`<font color='red'>**🧾 缺 WFS 费·绩效扣分通报**</font>`];
    fb.push("", "🧾 缺 WFS 费·绩效扣分通报");
    for (const c of args.wfsPlan.charges) {
      wlines.push(`**${c.owner || "-"}** 缺WFS费产品 **${normStr(c.cycle.msku) || "-"}** → <font color='red'>**扣 ${DEDUCT_POINTS} 分**</font>`);
      fb.push(`${c.owner || "-"} 缺WFS费产品 ${normStr(c.cycle.msku) || "-"} → 扣 ${DEDUCT_POINTS} 分`);
    }
    elements.push({ tag: "div", text: { tag: "lark_md", content: wlines.join("\n") } });
    elements.push({ tag: "hr" });
  }

  // 区W4/W5：缺 GPT 链接（关键词/广告）通用渲染
  const pushLinkRegions = (lp: WfsPlan, emoji: string, name: string): void => {
    if (lp.firstReminder.length > 0) {
      elements.push({ tag: "div", text: { tag: "lark_md", content: `**${emoji} 缺${name}·首次提醒（下期仍缺将扣 ${DEDUCT_POINTS} 分）**` } });
      fb.push("", `${emoji} 缺${name}·首次提醒（下期仍缺将扣 ${DEDUCT_POINTS} 分）`);
      pushGrouped(lp.firstReminder.slice(0, DETAIL_LIMIT),
        (p) => `**${normStr(p.msku) || "-"}** ｜ ItemID ${normStr(p.item_id) || "-"} ｜ 负责人 ${normStr(p.owner) || "-"}`,
        (p) => `MSKU：${normStr(p.msku) || "-"} ｜ ItemID：${normStr(p.item_id) || "-"} ｜ 负责人：${normStr(p.owner) || "-"}`);
      elements.push({ tag: "hr" });
    }
    if (lp.secondReminder.length > 0) {
      elements.push({ tag: "div", text: { tag: "lark_md", content: `<font color='red'>**⚠️【二次提醒】以下产品缺${name}，本期起每个记扣 ${DEDUCT_POINTS} 分，负责人承担**</font>` } });
      fb.push("", `⚠️【二次提醒】缺${name}，本期起每个记扣 ${DEDUCT_POINTS} 分，负责人承担`);
      pushGrouped(lp.secondReminder.slice(0, DETAIL_LIMIT).map((s) => s.item),
        (p) => `**${normStr(p.msku) || "-"}** ｜ ItemID ${normStr(p.item_id) || "-"} ｜ 负责人 ${normStr(p.owner) || "-"} <font color='red'>**⚠️ 扣${DEDUCT_POINTS}分**</font>`,
        (p) => `MSKU：${normStr(p.msku) || "-"} ｜ ItemID：${normStr(p.item_id) || "-"} ｜ 负责人：${normStr(p.owner) || "-"} ⚠️扣${DEDUCT_POINTS}分`);
      elements.push({ tag: "hr" });
    }
    if (lp.charges.length > 0) {
      const zl = [`<font color='red'>**🧾 缺${name}·绩效扣分通报**</font>`];
      fb.push("", `🧾 缺${name}·绩效扣分通报`);
      for (const c of lp.charges) {
        zl.push(`**${c.owner || "-"}** 缺${name}产品 **${normStr(c.cycle.msku) || "-"}** → <font color='red'>**扣 ${DEDUCT_POINTS} 分**</font>`);
        fb.push(`${c.owner || "-"} 缺${name}产品 ${normStr(c.cycle.msku) || "-"} → 扣 ${DEDUCT_POINTS} 分`);
      }
      elements.push({ tag: "div", text: { tag: "lark_md", content: zl.join("\n") } });
      elements.push({ tag: "hr" });
    }
  };
  pushLinkRegions(args.kwPlan, "🔍", "关键词分析链接");
  pushLinkRegions(args.adsPlan, "📈", "广告分析链接");

  // 区4：建议归档（已下架 UNPUBLISHED，无需认领）— 2026-07-27
  if (args.archiveItems.length > 0) {
    elements.push({ tag: "div", text: { tag: "lark_md", content: `**🗄 建议归档（已下架 UNPUBLISHED）**` } });
    fb.push("", "🗄 建议归档（已下架 UNPUBLISHED）");
    pushGrouped(
      args.archiveItems.slice(0, DETAIL_LIMIT),
      (p) => `**${normStr(p.msku) || "-"}** ｜ ItemID ${normStr(p.item_id) || "-"} ｜ 负责人 ${normStr(p.owner) || "无"} ｜ 🗄 建议归档`,
      (p) => `MSKU：${normStr(p.msku) || "-"} ｜ ItemID：${normStr(p.item_id) || "-"} ｜ 负责人：${normStr(p.owner) || "无"} ｜ 建议归档`,
    );
    if (args.archiveItems.length > DETAIL_LIMIT) {
      elements.push({ tag: "div", text: { tag: "lark_md", content: `…其余 ${args.archiveItems.length - DETAIL_LIMIT} 个已下架品请到产品管理页查看` } });
    }
    elements.push({ tag: "hr" });
  }

  const overflow = totalUnmatched - Math.min(totalUnmatched, DETAIL_LIMIT * 2);
  if (plan.firstReminder.length > DETAIL_LIMIT || plan.secondReminder.length > DETAIL_LIMIT) {
    elements.push({ tag: "div", text: { tag: "lark_md", content: `…部分产品未展开（展示上限每区 ${DETAIL_LIMIT} 条${overflow > 0 ? `，另有 ${overflow} 个` : ""}），请到产品管理页查看` } });
  }
  elements.push({ tag: "action", actions: [{ tag: "button", text: { tag: "plain_text", content: "去认领负责人" }, type: "primary", url: PRODUCT_MANAGEMENT_URL }] });
  elements.push({ tag: "note", elements: [{ tag: "plain_text", content: `口径：待认领=负责人为空；缺WFS费=人工/自动配送费均缺；缺关键词/广告链接=有负责人但GPT分析对应链接未配置(广告链接需WFS连续14天有库存)；均首次提醒不扣、二次提醒每个扣${DEDUCT_POINTS}分，待认领归认领者、其余归负责人；详见帮助中心「产品管理提醒通知」` }] });
  fb.push("", `页面：${PRODUCT_MANAGEMENT_URL}`);

  return {
    title,
    card: { config: { wide_screen_mode: true }, header: { template: "purple", title: { tag: "plain_text", content: title } }, elements },
    fallbackText: fb.join("\n"),
  };
}

// ── 状态写入（仅真实发送后执行） ────────────────────────────────────────────

async function commitState(db: mysql.Connection, plan: StatePlan, nameMap: Map<string, string>): Promise<{ deductInserted: number }> {
  const today = todayCst();
  for (const it of plan.newCycles) {
    await db.query(
      `INSERT INTO event_owner_claim_alert
         (platform, store_id, store_name, item_id, msku, product_name, cycle_start_date, first_notified_at, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, NOW(), 'open')
       ON DUPLICATE KEY UPDATE first_notified_at = COALESCE(first_notified_at, NOW())`,
      [normStr(it.platform) || "walmart", normStr(it.store_id), normStr(it.store_name) || nameMap.get(normStr(it.store_id)) || "",
       normStr(it.item_id), normStr(it.msku), normStr(it.product_name), today],
    );
  }
  for (const cyc of plan.upgrades) {
    await db.query(
      `UPDATE event_owner_claim_alert SET second_notified_at = NOW(), deduction_points = ?
       WHERE id = ? AND second_notified_at IS NULL`,
      [DEDUCT_POINTS, cyc.id],
    );
  }
  for (const c of plan.claims) {
    await db.query(
      `UPDATE event_owner_claim_alert SET claimed_by = ?, claimed_detected_at = NOW(), status = 'claimed'
       WHERE id = ? AND status = 'open'`,
      [c.claimedBy, c.cycle.id],
    );
  }
  for (const cyc of plan.voids) {
    await db.query(`UPDATE event_owner_claim_alert SET status = 'void' WHERE id = ? AND status = 'open'`, [cyc.id]);
  }
  let deductInserted = 0;
  for (const a of plan.announce) {
    const [r] = await db.query<mysql.ResultSetHeader>(
      `INSERT IGNORE INTO biz_perf_deduction
         (deduction_date, owner_name, points, biz_type, platform, store_id, item_id, msku, ref_event_id, created_by)
       VALUES (?, ?, ?, 'unclaimed_product', ?, ?, ?, ?, ?, 'unmatchedOwnerNotify')`,
      [today, a.claimedBy, a.cycle.deduction_points, normStr(a.cycle.platform) || "walmart",
       normStr(a.cycle.store_id), normStr(a.cycle.item_id), normStr(a.cycle.msku), a.cycle.id],
    );
    deductInserted += r.affectedRows > 0 ? 1 : 0;
    await db.query(`UPDATE event_owner_claim_alert SET announced_at = NOW(), status = 'closed' WHERE id = ?`, [a.cycle.id]);
  }
  for (const cyc of plan.closeZero) {
    await db.query(`UPDATE event_owner_claim_alert SET announced_at = NOW(), status = 'closed' WHERE id = ? AND status IN ('open','claimed')`, [cyc.id]);
  }
  return { deductInserted };
}

async function commitWfsState(db: mysql.Connection, plan: WfsPlan, nameMap: Map<string, string>): Promise<{ deductInserted: number }> {
  const today = todayCst();
  for (const it of plan.newCycles) {
    await db.query(
      `INSERT INTO event_wfs_fee_missing_alert
         (platform, store_id, store_name, item_id, msku, product_name, cycle_start_date, first_notified_at, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, NOW(), 'open')
       ON DUPLICATE KEY UPDATE first_notified_at = COALESCE(first_notified_at, NOW())`,
      [normStr(it.platform) || "walmart", normStr(it.store_id), normStr(it.store_name) || nameMap.get(normStr(it.store_id)) || "",
       normStr(it.item_id), normStr(it.msku), normStr(it.product_name), today],
    );
  }
  for (const u of plan.upgrades) {
    await db.query(
      `UPDATE event_wfs_fee_missing_alert SET second_notified_at = NOW(), deduction_points = ?
       WHERE id = ? AND second_notified_at IS NULL`,
      [DEDUCT_POINTS, u.cycle.id],
    );
  }
  let deductInserted = 0;
  for (const c of plan.charges) {
    const [r] = await db.query<mysql.ResultSetHeader>(
      `INSERT IGNORE INTO biz_perf_deduction
         (deduction_date, owner_name, points, biz_type, platform, store_id, item_id, msku, ref_event_id, created_by)
       VALUES (?, ?, ?, 'missing_wfs_fee', ?, ?, ?, ?, ?, 'unmatchedOwnerNotify')`,
      [today, c.owner, DEDUCT_POINTS, normStr(c.cycle.platform) || "walmart",
       normStr(c.cycle.store_id), normStr(c.cycle.item_id), normStr(c.cycle.msku), c.cycle.id],
    );
    deductInserted += r.affectedRows > 0 ? 1 : 0;
    await db.query(
      `UPDATE event_wfs_fee_missing_alert SET owner_name = ?, deducted_at = COALESCE(deducted_at, NOW()), announced_at = COALESCE(announced_at, NOW()) WHERE id = ?`,
      [c.owner, c.cycle.id],
    );
  }
  for (const cyc of plan.exits) {
    await db.query(`UPDATE event_wfs_fee_missing_alert SET status = 'closed' WHERE id = ? AND status = 'open'`, [cyc.id]);
  }
  return { deductInserted };
}

// ── 通用链接监督状态机（关键词/广告共用；结构同 planWfsState/commitWfsState，表名+biz_type 参数化） ──
async function planLinkState(db: mysql.Connection, items: WfsMissingProduct[], table: string): Promise<WfsPlan> {
  const today = todayCst();
  const [cycles] = await db.query<WfsCycleRow[]>(
    `SELECT id, platform, store_id, store_name, item_id, msku, product_name,
            DATE_FORMAT(cycle_start_date, '%Y-%m-%d') AS cycle_start_date,
            first_notified_at, second_notified_at, deduction_points, owner_name, deducted_at, announced_at, status
     FROM ${table} WHERE status = 'open'`,
  );
  const openByKey = new Map<string, WfsCycleRow>();
  for (const c of cycles) openByKey.set(keyOf(c), c);
  const currentKeys = new Set(items.map(keyOf));
  const plan: WfsPlan = { firstReminder: [], secondReminder: [], newCycles: [], upgrades: [], charges: [], exits: [] };
  for (const it of items) {
    const cyc = openByKey.get(keyOf(it));
    const owner = normStr(it.owner);
    const hasOwner = owner !== "" && owner !== "未分配";
    if (!cyc) {
      plan.firstReminder.push(it);
      plan.newCycles.push(it);
    } else if (cyc.second_notified_at) {
      plan.secondReminder.push({ item: it, cycle: cyc });
      if (!cyc.deducted_at && hasOwner) plan.charges.push({ cycle: cyc, owner });
    } else if (cyc.cycle_start_date < today) {
      plan.secondReminder.push({ item: it, cycle: cyc });
      plan.upgrades.push({ cycle: cyc, owner });
      if (hasOwner) plan.charges.push({ cycle: cyc, owner });
    } else {
      plan.firstReminder.push(it);
    }
  }
  for (const cyc of cycles) if (!currentKeys.has(keyOf(cyc))) plan.exits.push(cyc);
  return plan;
}

async function commitLinkState(db: mysql.Connection, plan: WfsPlan, nameMap: Map<string, string>, table: string, bizType: string): Promise<{ deductInserted: number }> {
  const today = todayCst();
  for (const it of plan.newCycles) {
    await db.query(
      `INSERT INTO ${table}
         (platform, store_id, store_name, item_id, msku, product_name, cycle_start_date, first_notified_at, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, NOW(), 'open')
       ON DUPLICATE KEY UPDATE first_notified_at = COALESCE(first_notified_at, NOW())`,
      [normStr(it.platform) || "walmart", normStr(it.store_id), normStr(it.store_name) || nameMap.get(normStr(it.store_id)) || "",
       normStr(it.item_id), normStr(it.msku), normStr(it.product_name), today],
    );
  }
  for (const u of plan.upgrades) {
    await db.query(`UPDATE ${table} SET second_notified_at = NOW(), deduction_points = ? WHERE id = ? AND second_notified_at IS NULL`, [DEDUCT_POINTS, u.cycle.id]);
  }
  let deductInserted = 0;
  for (const c of plan.charges) {
    const [r] = await db.query<mysql.ResultSetHeader>(
      `INSERT IGNORE INTO biz_perf_deduction
         (deduction_date, owner_name, points, biz_type, platform, store_id, item_id, msku, ref_event_id, created_by)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unmatchedOwnerNotify')`,
      [today, c.owner, DEDUCT_POINTS, bizType, normStr(c.cycle.platform) || "walmart",
       normStr(c.cycle.store_id), normStr(c.cycle.item_id), normStr(c.cycle.msku), c.cycle.id],
    );
    deductInserted += r.affectedRows > 0 ? 1 : 0;
    await db.query(`UPDATE ${table} SET owner_name = ?, deducted_at = COALESCE(deducted_at, NOW()), announced_at = COALESCE(announced_at, NOW()) WHERE id = ?`, [c.owner, c.cycle.id]);
  }
  for (const cyc of plan.exits) {
    await db.query(`UPDATE ${table} SET status = 'closed' WHERE id = ? AND status = 'open'`, [cyc.id]);
  }
  return { deductInserted };
}

// ── 主流程 ──────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const startedAt = Date.now();
  const doSend = process.argv.includes("--send");
  const testCard = process.argv.includes("--test-card");
  if (testCard && doSend) { console.log("[错误] --test-card 与 --send 禁止同时使用"); process.exit(1); }
  const writeState = doSend && !testCard;
  const dateStr = todayCst();

  console.log("=".repeat(60));
  console.log("🙋 待认领产品日报 + 绩效扣分状态机 v4");
  console.log(`模式: ${testCard ? "test-card（卡片→测试群，零写入）" : doSend ? "真实发送+状态写入" : "dry-run（零发送零写入）"}`);
  console.log("=".repeat(60));

  let status = doSend ? "success" : "dry-run";
  let errorMessage = "";
  let summaryExtra: Record<string, unknown> = {};
  const db = await mysql.createConnection(dbConfig());

  try {
    const { activeTotal, items } = await fetchUnmatchedProducts(db);
    const nameMap = await fetchStoreNameMap(db);
    const plan = await planState(db, items);
    const wfsItems = await fetchWfsMissing(db);
    const wfsPlan = await planWfsState(db, wfsItems);
    console.log(`缺WFS费=${wfsItems.length} ｜ WFS首提=${wfsPlan.firstReminder.length} WFS二提=${wfsPlan.secondReminder.length}（本次落台账=${wfsPlan.charges.length}）`);
    const kwItems = await fetchGptKwMissing(db);
    const kwPlan = await planLinkState(db, kwItems, "event_gpt_kw_missing_alert");
    const adsItems = await fetchGptAdsMissing(db);
    const adsPlan = await planLinkState(db, adsItems, "event_gpt_ads_missing_alert");
    console.log(`缺关键词链接=${kwItems.length}(首提${kwPlan.firstReminder.length}/二提${kwPlan.secondReminder.length}/落账${kwPlan.charges.length}) 缺广告链接=${adsItems.length}(首提${adsPlan.firstReminder.length}/二提${adsPlan.secondReminder.length}/落账${adsPlan.charges.length})`);
    console.log(`active=${activeTotal} 待认领=${items.length} ｜ 首提=${plan.firstReminder.length} 二提=${plan.secondReminder.length}（本期新扣分=${plan.upgrades.length}） 认领=${plan.claims.length} 作废=${plan.voids.length} 扣分通报=${plan.announce.length}`);

    const archiveItems = await fetchArchiveCandidates(db);
    console.log(`建议归档(UNPUBLISHED无负责人)=${archiveItems.length}`);
    const bundle = buildPerfCard({ dateStr, activeTotal, plan, wfsPlan, kwPlan, adsPlan, nameMap, archiveItems, testPrefix: testCard });

    if (testCard) {
      const r = await sendCardWithFallbackToChat("产品管理提醒-测试预览", getTestChatId(), bundle.card, bundle.fallbackText);
      console.log(`[test-card] ok=${r.ok} cardOk=${r.cardOk} fallbackUsed=${r.fallbackUsed}${r.error ? ` error=${r.error}` : ""}`);
      if (r.ok) console.log("NOTIFY_TEST_SENT=1");
      else { status = "failed"; process.exitCode = 1; }
      return;
    }

    if (!doSend) {
      console.log("\n[dry-run] 卡片降级文本预览：");
      console.log("─".repeat(60));
      console.log(bundle.fallbackText);
      console.log("─".repeat(60));
      console.log("[dry-run] 计划状态迁移：insert=%d upgrade=%d claim=%d void=%d announce=%d closeZero=%d（零写入）",
        plan.newCycles.length, plan.upgrades.length, plan.claims.length, plan.voids.length, plan.announce.length, plan.closeZero.length);
      console.log("[dry-run] WFS状态迁移：insert=%d upgrade=%d charge=%d exit=%d（零写入）",
        wfsPlan.newCycles.length, wfsPlan.upgrades.length, wfsPlan.charges.length, wfsPlan.exits.length);
      console.log("[dry-run] 链接监督：KW insert=%d charge=%d ｜ ADS insert=%d charge=%d（零写入）",
        kwPlan.newCycles.length, kwPlan.charges.length, adsPlan.newCycles.length, adsPlan.charges.length);
      return;
    }

    // ── 真实发送：应用机器人 → 两个管理群（webhook 已取消） ──
    const chatIds = parseListEnv(CHAT_IDS_ENV);
    if (chatIds.length === 0) {
      throw new Error(`缺少 ${CHAT_IDS_ENV} 环境变量（CSV 管理群 chat_id），已按拍板取消 webhook 回退，禁止硬编码`);
    }
    let okCount = 0;
    for (let i = 0; i < chatIds.length; i++) {
      const r = await sendCardWithFallbackToChat(`产品管理提醒-群${i + 1}`, chatIds[i], bundle.card, bundle.fallbackText);
      console.log(`  群${i + 1}: ok=${r.ok} cardOk=${r.cardOk} fallbackUsed=${r.fallbackUsed}${r.error ? ` error=${r.error}` : ""}`);
      if (r.ok) okCount += 1;
    }
    if (mirrorToTestEnabled()) {
      const m = await sendCardWithFallbackToChat("产品管理提醒-监督副本", getTestChatId(), bundle.card, bundle.fallbackText);
      console.log(`  [镜像] ${m.ok ? "副本已发测试群" : `副本失败(${m.error ?? "-"})，忽略`}`);
    }
    if (okCount === 0) throw new Error("两个群通道全部发送失败，状态零写入（下次运行自动重试同一轮次）");

    // ── 状态与台账写入（至少一个群成功后提交） ──
    const { deductInserted } = await commitState(db, plan, nameMap);
    const wfsCommit = await commitWfsState(db, wfsPlan, nameMap);
    const kwCommit = await commitLinkState(db, kwPlan, nameMap, "event_gpt_kw_missing_alert", "missing_gpt_keyword");
    const adsCommit = await commitLinkState(db, adsPlan, nameMap, "event_gpt_ads_missing_alert", "missing_gpt_ads");
    console.log(`  状态提交：新轮次=${plan.newCycles.length} 升级二提=${plan.upgrades.length} 认领=${plan.claims.length} 作废=${plan.voids.length} 台账新增=${deductInserted}｜WFS台账=${wfsCommit.deductInserted}｜关键词台账=${kwCommit.deductInserted}｜广告台账=${adsCommit.deductInserted}`);

    // ── 有扣分才同步黄少如（私信） ──
    let supervisorOk: boolean | null = null;
    if (plan.announce.length > 0 || wfsPlan.charges.length > 0 || kwPlan.charges.length > 0 || adsPlan.charges.length > 0) {
      const { targets, warnings } = await resolveActiveMembers([SUPERVISOR_NAME]);
      warnings.forEach((w) => console.log(`  [警告] ${w}`));
      if (targets.length === 1) {
        const lines = [`【绩效扣分同步】${dateStr} 产品管理提醒通知`,
          ...plan.announce.map((a) => `${a.claimedBy} 认领二提产品 ${normStr(a.cycle.msku)}（ItemID ${normStr(a.cycle.item_id)}）→ 扣 ${a.cycle.deduction_points} 分`),
          ...wfsPlan.charges.map((c) => `${c.owner} 缺WFS费产品 ${normStr(c.cycle.msku)}（ItemID ${normStr(c.cycle.item_id)}）→ 扣 ${DEDUCT_POINTS} 分`),
          ...kwPlan.charges.map((c) => `${c.owner} 缺关键词链接 ${normStr(c.cycle.msku)}（ItemID ${normStr(c.cycle.item_id)}）→ 扣 ${DEDUCT_POINTS} 分`),
          ...adsPlan.charges.map((c) => `${c.owner} 缺广告链接 ${normStr(c.cycle.msku)}（ItemID ${normStr(c.cycle.item_id)}）→ 扣 ${DEDUCT_POINTS} 分`),
          `合计 ${plan.announce.length + wfsPlan.charges.length + kwPlan.charges.length + adsPlan.charges.length} 笔，已入台账 biz_perf_deduction。`];
        const token = await getTenantToken();
        const r = await sendTextToTarget(token, targets[0], lines.join("\n"), true);
        supervisorOk = r.ok;
        if (r.ok) {
          if (plan.announce.length > 0) {
            const ids = plan.announce.map((a) => a.cycle.id);
            await db.query(`UPDATE event_owner_claim_alert SET supervisor_synced_at = NOW() WHERE id IN (${ids.map(() => "?").join(",")})`, ids);
          }
          if (wfsPlan.charges.length > 0) {
            const wids = wfsPlan.charges.map((c) => c.cycle.id);
            await db.query(`UPDATE event_wfs_fee_missing_alert SET supervisor_synced_at = NOW() WHERE id IN (${wids.map(() => "?").join(",")})`, wids);
          }
          if (kwPlan.charges.length > 0) {
            const kids = kwPlan.charges.map((c) => c.cycle.id);
            await db.query(`UPDATE event_gpt_kw_missing_alert SET supervisor_synced_at = NOW() WHERE id IN (${kids.map(() => "?").join(",")})`, kids);
          }
          if (adsPlan.charges.length > 0) {
            const aids = adsPlan.charges.map((c) => c.cycle.id);
            await db.query(`UPDATE event_gpt_ads_missing_alert SET supervisor_synced_at = NOW() WHERE id IN (${aids.map(() => "?").join(",")})`, aids);
          }
        }
        console.log(`  黄少如同步: ${r.ok ? "成功" : `失败(${r.error ?? "-"})`}`);
      } else {
        console.log(`  [警告] ${SUPERVISOR_NAME} 未解析到唯一在册接收人，扣分同步跳过（下次运行不重复公布，台账已落）`);
      }
    }
    if (okCount < chatIds.length) { status = "partial"; process.exitCode = 1; }
    summaryExtra = { chatPlanned: chatIds.length, chatOk: okCount, deductInserted, wfsDeductInserted: wfsCommit.deductInserted, kwDeductInserted: kwCommit.deductInserted, adsDeductInserted: adsCommit.deductInserted, supervisorOk };
  } catch (e) {
    status = "failed";
    errorMessage = getErrorMessage(e);
    console.log(`[错误] ${errorMessage}`);
    process.exitCode = 1;
  } finally {
    await db.end().catch(() => undefined);
    console.log(`SUMMARY_JSON=${JSON.stringify({
      task: "unmatchedOwnerNotify", version: "v4_perf", status, errorMessage,
      durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)), ...summaryExtra,
    })}`);
  }
}

if (require.main === module) {
  main().catch((e) => {
    console.log(`[致命错误] ${getErrorMessage(e)}`);
    process.exit(1);
  });
}
