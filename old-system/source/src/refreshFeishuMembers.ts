// Refresh dim_feishu_member from the company Feishu directory (contact API).
// 花名册口径（2026-07-11 需求方定稿）：在册=在职(active)，不在册=离职(left)。
// 公司通讯录是人员在册状态的唯一来源。
//
// v2.2 字段解析修复（相对 v2.1，依据 2026-07-11 只读诊断）：
//   a. children 实际返回 open_department_id（非 department_id）——改为兼容读取，
//      并全程去掉 department_id_type 参数（统一用接口默认 open_department_id 类型，
//      修复"子部门ID类型错配导致 400 invalid department_id / BFS 断在根部门"）
//   b. find_by_department 返回项无 name 字段——姓名三级兜底：
//      item.name(如有) → 库内已有 open_id->name 映射 → 用户详情接口补取
//   b2.★无姓名=硬安全阀：兜底后仍有无名人员 → 本次零写入(dry-run与--write均exit 2)，
//      不upsert/不标记left/不恢复active/不改last_seen_at——负责人链路(下拉/保存校验/
//      提醒/清空)全部按姓名关联，空名会破坏完整链路，禁止入库
//   b3. 不输出任何 open_id/union_id(含脱敏片段)，仅输出无名人数
//   b4. 重名/新增/恢复/姓名变化统计在三级兜底完成后计算，空名不进任何名单
//   c. upsert 不用空名覆盖已有姓名：name = IF(VALUES(name)='', name, VALUES(name))
//   d. 写入前安全阀顺序：部门遍历完整(失败即throw) → 唯一open_id数>0 →
//      无名人数=0 → 拉取数>=当前在册70% → 人工确认 would LEFT 名单
// v2.1 安全补丁（相对 v2）：
//   1. --legacy-chat 仅为只读诊断工具：与 --write 同用直接 exit 1；
//      群成员数据永远不能修改 employment_status / 重新激活人员
//   2. 安全阀失败=零写入：拉取0人 或 拉取<当前在册70% → 不 upsert 不标记，exit 2
//   3. 正式 write 全程事务：upsert + 离册标记 同一事务，任一步失败 rollback
//   4. dry-run 输出完整 diff：部门数/唯一人员数/当前在册数/新增/恢复在册/姓名变化/
//      would mark LEFT/安全阀结果（只输出姓名，不输出 open_id）
//   5. dry-run 与 write 使用同一套 diff 计算，预览即执行口径
//
// Dry-run by default; pass --write to apply.
import * as mysql from "mysql2/promise";
const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;
const fs = require("fs");
const path = require("path");

const SAFETY_MIN_RATIO = 0.7; // 拉取人数低于当前在册的该比例时：零写入告警

function envv(key: string): string {
  if (process.env[key]) return String(process.env[key]).trim();
  try {
    const txt = fs.readFileSync(path.join(__dirname, "..", ".env"), "utf-8");
    for (const line of txt.split(/\r?\n/)) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (m && m[1] === key) return m[2].trim();
    }
  } catch (e) { /* ignore */ }
  return "";
}

function fileEnv(key: string): string {
  try {
    const txt = fs.readFileSync(path.join(__dirname, "..", ".env"), "utf-8");
    for (const line of txt.split(/\r?\n/)) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (m && m[1] === key) {
        let v = m[2].trim();
        if (v.length >= 2 && ((v[0] === '"' && v[v.length - 1] === '"') || (v[0] === "'" && v[v.length - 1] === "'"))) {
          v = v.slice(1, -1);
        }
        return v;
      }
    }
  } catch (e) { /* ignore */ }
  return "";
}

async function getToken(appId: string, appSecret: string): Promise<string> {
  const r = await axios.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    { app_id: appId, app_secret: appSecret },
    { headers: { "Content-Type": "application/json" }, timeout: 15000 },
  );
  if (r.data.code !== 0) throw new Error("token failed: " + JSON.stringify(r.data));
  return r.data.tenant_access_token as string;
}

// ---- legacy: 固定群成员（只读诊断，禁止写库） ----
async function listChatMembers(token: string, chatId: string): Promise<{ name: string; openId: string }[]> {
  const out: { name: string; openId: string }[] = [];
  let pageToken = "";
  while (true) {
    const r = await axios.get(
      "https://open.feishu.cn/open-apis/im/v1/chats/" + chatId + "/members",
      {
        params: { member_id_type: "open_id", page_size: 50, page_token: pageToken || undefined },
        headers: { Authorization: "Bearer " + token },
        timeout: 15000,
      },
    );
    if (r.data.code !== 0) throw new Error("list chat members failed: " + JSON.stringify(r.data));
    const d = r.data.data;
    for (const it of (d.items || [])) {
      const name = (it.name || "").trim();
      const openId = (it.member_id || "").trim();
      if (name && openId) out.push({ name, openId });
    }
    if (!d.has_more) break;
    pageToken = d.page_token || "";
  }
  return out;
}

// ---- 通讯录部门遍历（BFS 自根部门0，全量分页） ----
async function listAllDepartmentIds(token: string): Promise<string[]> {
  const ids: string[] = ["0"];
  const queue: string[] = ["0"];
  const seen = new Set<string>(["0"]);
  while (queue.length) {
    const dept = queue.shift()!;
    let pageToken = "";
    while (true) {
      const r = await axios.get(
        "https://open.feishu.cn/open-apis/contact/v3/departments/" + encodeURIComponent(dept) + "/children",
        {
          // v2.2: 不传 department_id_type，统一走接口默认 open_department_id 类型
          params: { page_size: 50, page_token: pageToken || undefined },
          headers: { Authorization: "Bearer " + token },
          timeout: 15000,
        },
      );
      if (r.data.code !== 0) throw new Error("list departments failed(dept=" + dept + "): " + JSON.stringify(r.data));
      const d = r.data.data || {};
      for (const it of (d.items || [])) {
        // v2.2: 实测返回字段为 open_department_id，兼容读取
        const id = String(it.open_department_id || it.department_id || "").trim();
        if (id && !seen.has(id)) {
          seen.add(id);
          ids.push(id);
          queue.push(id);
        }
      }
      if (!d.has_more) break;
      pageToken = d.page_token || "";
    }
  }
  return ids;
}

async function listDirectoryMembers(token: string): Promise<{ members: { name: string; openId: string }[]; deptCount: number }> {
  const deptIds = await listAllDepartmentIds(token);
  const byOpenId = new Map<string, string>();
  for (const dept of deptIds) {
    let pageToken = "";
    while (true) {
      const r = await axios.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/find_by_department",
        {
          params: {
            // v2.2: 不传 department_id_type（子部门ID为 open_department_id 类型，错配会400）
            department_id: dept,
            user_id_type: "open_id",
            page_size: 50,
            page_token: pageToken || undefined,
          },
          headers: { Authorization: "Bearer " + token },
          timeout: 15000,
        },
      );
      if (r.data.code !== 0) throw new Error("find_by_department failed(dept=" + dept + "): " + JSON.stringify(r.data));
      const d = r.data.data || {};
      for (const it of (d.items || [])) {
        // v2.2: 实测返回项无 name 字段，只按 open_id 收人，姓名后续三级兜底补齐
        const name = String(it.name || "").trim();
        const openId = String(it.open_id || "").trim();
        if (openId && !byOpenId.has(openId)) byOpenId.set(openId, name);
      }
      if (!d.has_more) break;
      pageToken = d.page_token || "";
    }
  }
  return {
    members: [...byOpenId.entries()].map(([openId, name]) => ({ name, openId })),
    deptCount: deptIds.length,
  };
}

// v2.2: 用户详情接口补取姓名（find_by_department 不返回 name 时的第三级兜底）
async function fetchUserName(token: string, openId: string): Promise<string> {
  try {
    const r = await axios.get(
      "https://open.feishu.cn/open-apis/contact/v3/users/" + encodeURIComponent(openId),
      {
        params: { user_id_type: "open_id" },
        headers: { Authorization: "Bearer " + token },
        timeout: 15000,
      },
    );
    if (r.data.code !== 0) return "";
    return String(r.data?.data?.user?.name || "").trim();
  } catch (e) {
    return "";
  }
}

async function main() {
  const write = process.argv.includes("--write");
  const legacyChat = process.argv.includes("--legacy-chat");

  // 安全规则1：legacy-chat 仅只读诊断，禁止写库
  if (legacyChat && write) {
    console.log("[ERR] --legacy-chat 仅为只读诊断工具，禁止与 --write 同用（花名册唯一来源=公司通讯录）");
    process.exit(1);
  }

  const appId = envv("FEISHU_APP_ID");
  const appSecret = envv("FEISHU_APP_SECRET");
  if (!appId || !appSecret) { console.log("[ERR] missing FEISHU_APP_ID / FEISHU_APP_SECRET in .env"); process.exit(1); }
  console.log("source =", legacyChat ? "LEGACY chat roster (READ-ONLY diagnostic)" : "company directory (contact API)",
              " mode =", write ? "WRITE" : "DRY-RUN");

  const token = await getToken(appId, appSecret);
  let members: { name: string; openId: string }[];
  let deptCount = 0;
  if (legacyChat) {
    const chatId = envv("FEISHU_OWNER_CHAT_ID");
    if (!chatId) { console.log("[ERR] legacy-chat mode but no FEISHU_OWNER_CHAT_ID"); process.exit(1); }
    members = await listChatMembers(token, chatId);
    console.log("[诊断] 群成员数:", members.length, "（仅对照参考，不影响在册状态）");
  } else {
    const r = await listDirectoryMembers(token);
    members = r.members;
    deptCount = r.deptCount;
  }

  let dbHost = fileEnv("DB_HOST") || "127.0.0.1";
  if (dbHost === "localhost") dbHost = "127.0.0.1";
  const db = await mysql.createConnection({
    host: dbHost,
    port: Number(fileEnv("DB_PORT") || "3306"),
    user: fileEnv("DB_USER"),
    password: fileEnv("DB_PASSWORD"),
    database: fileEnv("DB_NAME") || "walmart_ai_data",
    charset: "utf8mb4",
  });

  try {
    const [existingRows]: any = await db.query(
      "SELECT open_id, name, employment_status FROM dim_feishu_member");
    const existing = new Map<string, { name: string; status: string }>();
    let activeCount = 0;
    for (const r of existingRows) {
      existing.set(String(r.open_id), { name: String(r.name), status: String(r.employment_status) });
      if (String(r.employment_status) === "active") activeCount += 1;
    }

    // ---- v2.2 姓名三级兜底：item.name → 库内已有映射 → 用户详情接口 → '' ----
    let nameFromDb = 0;
    let nameFromDetail = 0;
    let namelessCount = 0;
    if (!legacyChat) {
      for (const m of members) {
        if (m.name) continue;
        const known = existing.get(m.openId);
        if (known && known.name) {
          m.name = known.name;
          nameFromDb += 1;
          continue;
        }
        const detailName = await fetchUserName(token, m.openId);
        if (detailName) {
          m.name = detailName;
          nameFromDetail += 1;
        } else {
          namelessCount += 1; // b3: 不输出任何 open_id/union_id 片段，仅计数
        }
      }
      console.log(`姓名兜底: 库内补齐 ${nameFromDb} 人, 详情接口补齐 ${nameFromDetail} 人, 仍无名 ${namelessCount} 人`);
    }

    // b4: 重名统计在三级兜底完成后计算，空名不进名单
    const nameCount = new Map<string, number>();
    for (const m of members) {
      if (!m.name) continue;
      nameCount.set(m.name, (nameCount.get(m.name) || 0) + 1);
    }
    const dupNames = [...nameCount.entries()].filter(([, c]) => c > 1).map(([n, c]) => n + "(" + c + ")");

    // ---- diff 计算（dry-run 与 write 共用同一口径） ----
    const fetchedIds = new Set(members.map((m) => m.openId));
    const added = members.filter((m) => m.name && !existing.has(m.openId)).map((m) => m.name);
    const restored = members.filter((m) => m.name && existing.get(m.openId)?.status === "left").map((m) => m.name);
    const renamed = members
      .filter((m) => m.name && existing.has(m.openId) && existing.get(m.openId)!.name !== m.name)
      .map((m) => existing.get(m.openId)!.name + " -> " + m.name);
    const wouldLeft = [...existing.entries()]
      .filter(([id, v]) => v.status === "active" && !fetchedIds.has(id))
      .map(([, v]) => v.name);

    // ---- 报告 ----
    console.log("departments discovered:", legacyChat ? "(legacy N/A)" : deptCount);
    console.log("roster members fetched (unique by open_id):", members.length);
    console.log("current active in table:", activeCount);
    if (dupNames.length) console.log("[WARN] duplicate display names:", dupNames.join(", "));
    console.log("新增名单:", added.length ? added.join(", ") : "(none)");
    console.log("恢复在册名单:", restored.length ? restored.join(", ") : "(none)");
    console.log("姓名变化名单:", renamed.length ? renamed.join(", ") : "(none)");
    console.log("would mark LEFT:", wouldLeft.length ? wouldLeft.join(", ") : "(none)");

    // legacy-chat 到此为止（只读诊断，不做安全阀/写入判断）
    if (legacyChat) {
      console.log("LEGACY 诊断完成：本模式永不写库。");
      return;
    }

    // ---- 安全阀（失败=零写入，exit 2） ----
    let valveMsg = "OK";
    let valveOk = true;
    if (members.length === 0) {
      valveOk = false;
      valveMsg = "拉取人数=0";
    } else if (namelessCount > 0) {
      // 硬安全阀：空名会破坏负责人链路（下拉/保存校验/提醒/清空全按姓名关联）
      valveOk = false;
      valveMsg = `目录中有 ${namelessCount} 人无法解析姓名，请补充用户基本信息权限或可信姓名来源`;
    } else if (members.length < Math.ceil(activeCount * SAFETY_MIN_RATIO)) {
      valveOk = false;
      valveMsg = `拉取 ${members.length} < 当前在册 ${activeCount} 的70%`;
    }
    console.log("安全阀结果:", valveOk ? "通过" : `[ALARM] ${valveMsg} — 本次零写入`);
    if (!valveOk) {
      process.exitCode = 2;
      return; // 零写入：不 upsert、不标记 left、不恢复 active、不改 last_seen_at
    }

    if (!write) {
      console.log("DRY-RUN: nothing written. Re-run with --write to apply.");
      return;
    }

    // ---- 正式写入（单事务：upsert + 离册标记，失败整体回滚） ----
    await db.beginTransaction();
    try {
      const rows = members.map((m) => [m.openId, m.name]);
      await db.query(
        `INSERT INTO dim_feishu_member (open_id, name, employment_status, last_seen_at)
         VALUES ${rows.map(() => "(?, ?, 'active', NOW())").join(", ")}
         ON DUPLICATE KEY UPDATE
           name = IF(VALUES(name) = '', name, VALUES(name)),
           employment_status = 'active',
           left_detected_at = NULL,
           last_seen_at = NOW()`,
        rows.flat(),
      );
      const [r]: any = await db.query(
        `UPDATE dim_feishu_member
            SET employment_status = 'left', left_detected_at = NOW()
          WHERE employment_status = 'active' AND open_id NOT IN (?)`,
        [members.map((m) => m.openId)],
      );
      await db.commit();
      console.log("WRITE 完成: upserted", rows.length, " newly marked left:", Number(r.affectedRows || 0));
    } catch (e) {
      await db.rollback();
      console.log("[ERR] 写入失败已回滚:", e instanceof Error ? e.message : String(e));
      process.exitCode = 1;
      return;
    }

    const [cnt]: any = await db.query(
      "SELECT employment_status AS s, COUNT(*) AS c FROM dim_feishu_member GROUP BY employment_status");
    console.log("table status:", JSON.stringify(cnt));
  } finally {
    await db.end();
  }
}

main().catch((e) => {
  const body = e && e.response && e.response.data;
  console.log("ERROR:", e && e.message ? e.message : String(e), body ? " body: " + JSON.stringify(body) : "");
  process.exit(1);
});
