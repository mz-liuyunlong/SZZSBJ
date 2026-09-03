// Build config/groupRoster.json (name -> open_id) from a Feishu group's member roster.
// Reads members of FEISHU_OWNER_CHAT_ID (default below). Duplicate display names are skipped.
// Dry-run by default; pass --write to actually write the file (with backup).
const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;
const fs = require("fs");
const path = require("path");

const DEFAULT_CHAT_ID = "oc_6b819b42aab6efe7a60ef9b008a2fd90";

function loadEnvVar(key: string): string {
  if (process.env[key]) return String(process.env[key]).trim();
  try {
    const envPath = path.join(__dirname, "..", ".env");
    const txt = fs.readFileSync(envPath, "utf-8");
    for (const line of txt.split(/\r?\n/)) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (m && m[1] === key) return m[2].trim();
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
        params: { member_id_type: "open_id", page_size: 100, page_token: pageToken || undefined },
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
  const appId = loadEnvVar("FEISHU_APP_ID");
  const appSecret = loadEnvVar("FEISHU_APP_SECRET");
  const chatId = loadEnvVar("FEISHU_OWNER_CHAT_ID") || DEFAULT_CHAT_ID;
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
  const roster: Record<string, string> = {};
  const conflicts: string[] = [];
  for (const [name, ids] of byName.entries()) {
    if (ids.size === 1) roster[name] = [...ids][0];
    else conflicts.push(name + "(" + ids.size + ")");
  }
  console.log("unique resolvable names:", Object.keys(roster).length);
  if (conflicts.length) console.log("[WARN] duplicate names skipped:", conflicts.join(", "));

  const cfgPath = path.join(__dirname, "..", "config", "ownerOpenIds.json");
  let owners: string[] = [];
  try { owners = Object.keys(JSON.parse(fs.readFileSync(cfgPath, "utf-8"))); } catch (e) { owners = []; }
  if (owners.length) {
    const missing = owners.filter((n) => !(n in roster));
    console.log("current owners:", owners.length, " matched in roster:", owners.length - missing.length);
    if (missing.length) console.log("[INFO] owners NOT found in roster (fall back to group):", missing.join(", "));
  }

  if (!write) { console.log("DRY-RUN: nothing written. Re-run with --write to save groupRoster.json"); return; }

  const outPath = path.join(__dirname, "..", "config", "groupRoster.json");
  try { if (fs.existsSync(outPath)) fs.copyFileSync(outPath, outPath + ".bak." + Date.now()); } catch (e) {}
  const ordered: Record<string, string> = {};
  for (const k of Object.keys(roster).sort((a, b) => a.localeCompare(b, "zh-CN"))) ordered[k] = roster[k];
  fs.writeFileSync(outPath, JSON.stringify(ordered, null, 2) + "\n", "utf-8");
  console.log("WROTE", outPath, " entries =", Object.keys(ordered).length);
}

main().catch((e) => { console.log("ERROR:", e && e.message ? e.message : String(e)); process.exit(1); });
