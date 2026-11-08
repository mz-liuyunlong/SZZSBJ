// Role-management navigation registry is generated, never hand-edited.
// Usage: node scripts/export-rbac-navigation.mjs [--check]
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const sourcePath = new URL("../src/config/navigation.ts", import.meta.url);
const targetPath = new URL("../../backend/app/modules/iam/navigation_permissions.json", import.meta.url);
const source = readFileSync(sourcePath, "utf8");
const modules = [];
const modulePattern = /^    key: '([^']+)',\r?\n    title: '([^']+)',/gm;
for (const match of source.matchAll(modulePattern)) {
  modules.push({ module_key: match[1], name: match[2], sort_order: modules.length * 10 + 10, pages: [] });
}
const modulesByKey = new Map(modules.map((m) => [m.module_key, m]));
const seen = new Set();
const pagePattern = /\bpage\('([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'([\s\S]*?)(?=\),?\s*(?:\n\s*(?:page\(|\],|\},|\]\)|\/\/|$)))/g;
let matched = 0;
for (const match of source.matchAll(pagePattern)) {
  matched++;
  const [, group, local, title, , options] = match;
  const module = modulesByKey.get(group);
  if (!module) throw new Error("Unknown navigation module " + group);
  const status = options.match(/status\s*:\s*'([^']+)'/)?.[1];
  if (status === "hidden") continue;
  const permission = options.match(/viewPermissionKey\s*:\s*'([^']+)'/)?.[1] ??
    ("page:" + group.replaceAll("_", "-") + ":" + local.replaceAll("_", "-") + ":view");
  const parts = permission.match(/^page:([a-z0-9-]+):([a-z0-9-]+):view$/);
  if (!parts || parts[1].replaceAll("-", "_") !== group) {
    throw new Error("Unsupported page permission " + permission);
  }
  if (seen.has(permission)) {
    const existing = module.pages.find((p) => p.permission_key === permission);
    if (!existing) throw new Error("Aliased permission crosses modules: " + permission);
    existing.name += " / " + title;
    continue;
  }
  seen.add(permission);
  module.pages.push({
    page_key: group + "_" + parts[2].replaceAll("-", "_"),
    name: title,
    permission_key: permission,
    sort_order: module.pages.length * 10 + 10
  });
}
if (matched < 90 || modules.length < 10 || seen.size < 85) {
  throw new Error("Navigation parsing incomplete: pages=" + matched + ", modules=" + modules.length);
}
const expected = JSON.stringify({version: 1, modules}, null, 2) + "\n";
if (process.argv.includes("--check")) {
  if (readFileSync(targetPath, "utf8") !== expected) {
    console.error("RBAC navigation manifest is stale. Run node frontend/scripts/export-rbac-navigation.mjs");
    process.exit(1);
  }
  console.log("RBAC_NAVIGATION_MANIFEST_VALID pages=" + matched + " permissions=" + seen.size);
} else {
  writeFileSync(targetPath, expected);
  console.log("RBAC_NAVIGATION_MANIFEST_UPDATED pages=" + matched + " permissions=" + seen.size);
}
