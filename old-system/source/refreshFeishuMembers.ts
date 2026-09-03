// Refresh dim_feishu_member (open_id, name) from a Feishu group's member roster.
// Any project can then read name->open_id from MySQL.
// Dry-run by default; pass --write to upsert into the DB. Duplicate display names are skipped.
import * as mysql from "mysql2/promise";
const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;
const fs = require("fs");
const path = require("path");

const DEFAULT_CHAT_ID = "oc_6b819b42aab6efe7a60ef9b008a2fd90";

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

// DB creds: read ONLY from the .env file (avoid polluted shell env), force TCP.
function fileEnv(key: string): string {
  try {
    const txt = fs.readFileSync(path.join(__dirname, "..", ".env"), "utf-8");
    for (const line of txt.split(/\r?\n/)) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (m && m[1] === key) {
        let v = m[2].trim();
        // strip surrounding quotes the way the shell would
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

async function listMembers(token: string, chatId: string): Promise<{ name: string; openId: string }[]> {
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
    if (r.data.code !== 0) throw new Error("list members failed: " + JSON.stringify(r.data));
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

async function main() {
  const write = process.argv.includes("--write");
  const appId = envv("FEISHU_APP_ID");
  const appSecret = envv("FEISHU_APP_SECRET");
  const chatId = envv("FEISHU_OWNER_CHAT_ID") || DEFAULT_CHAT_ID;
  if (!appId || !appSecret) { console.log("[ERR] missing FEISHU_APP_ID / FEISHU_APP_SECRET in .env"); process.exit(1); }
  console.log("chat_id =", chatId, " mode =", write ? "WRITE" : "DRY-RUN");

  const token = await getToken(appId, appSecret);
  const members = await listMembers(token, chatId);
  console.log("roster members fetched:", members.length);

  const byName = new Map<string, Set<string>>();
  for (const m of members) {
    if (!byName.has(m.name)) byName.set(m.name, new Set());
    byName.get(m.name)!.add(m.openId);
  }
  const rows: [string, string][] = []; // [open_id, name]
  const conflicts: string[] = [];
  for (const [name, ids] of byName.entries()) {
    if (ids.size === 1) rows.push([[...ids][0], name]);
    else conflicts.push(name + "(" + ids.size + ")");
  }
  console.log("unique resolvable names:", rows.length);
  if (conflicts.length) console.log("[WARN] duplicate names skipped:", conflicts.join(", "));

  try {
    const owners = Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname, "..", "config", "ownerOpenIds.json"), "utf-8")));
    const nameSet = new Set(rows.map((r) => r[1]));
    const missing = owners.filter((n) => !nameSet.has(n));
    console.log("current owners:", owners.length, " matched in roster:", owners.length - missing.length);
    if (missing.length) console.log("[INFO] owners NOT found in roster:", missing.join(", "));
  } catch (e) { /* ignore */ }

  if (!write) { console.log("DRY-RUN: nothing written. Re-run with --write to upsert into dim_feishu_member"); return; }

  let dbHost = fileEnv("DB_HOST") || "127.0.0.1";
  if (dbHost === "localhost") dbHost = "127.0.0.1"; // force TCP, matches working CLI/cron
  const dbPort = Number(fileEnv("DB_PORT") || "3306");
  const dbUser = fileEnv("DB_USER");
  const dbPass = fileEnv("DB_PASSWORD");
  const dbName = fileEnv("DB_NAME") || "walmart_ai_data";
  console.log("DB connect -> host=" + dbHost + " port=" + dbPort + " user=" + dbUser + " db=" + dbName + " (password len=" + dbPass.length + ")");
  const db = await mysql.createConnection({
    host: dbHost,
    port: dbPort,
    user: dbUser,
    password: dbPass,
    database: dbName,
    charset: "utf8mb4",
  });
  try {
    if (rows.length) {
      await db.query(
        "INSERT INTO dim_feishu_member (open_id, name) VALUES ? ON DUPLICATE KEY UPDATE name = VALUES(name)",
        [rows],
      );
    }
    const [cnt]: any = await db.query("SELECT COUNT(*) AS c FROM dim_feishu_member");
    console.log("upserted rows:", rows.length, " table total:", cnt[0].c);
  } finally {
    await db.end();
  }
}

main().catch((e) => {
  const body = e && e.response && e.response.data;
  console.log("ERROR:", e && e.message ? e.message : String(e), body ? " body: " + JSON.stringify(body) : "");
  process.exit(1);
});
