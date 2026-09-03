#!/bin/bash
# 从飞书 ItemID负责人表读取所有负责人，批量查 open_id，更新 config/ownerOpenIds.json
# 用法：bash scripts/refresh-owner-openids.sh

set -e
cd "$(dirname "$0")/.."

LARK_CLI="./scripts/lark-cli"
SHEET_TOKEN="<REDACTED_FEISHU_SPREADSHEET_TOKEN>"
SHEET_ID="<REDACTED_FEISHU_SHEET_ID>"
OUT="config/ownerOpenIds.json"

echo "正在读取负责人表..."

python3 - << 'PYEOF'
import subprocess, json, sys, os

LARK_CLI = "./scripts/lark-cli"
SHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>"
SHEET_ID = "<REDACTED_FEISHU_SHEET_ID>"
OUT = "config/ownerOpenIds.json"

# 1. 读取表格
result = subprocess.run(
    [LARK_CLI, "api", "GET",
     "/open-apis/sheets/v2/spreadsheets/%s/values/%s!A1:U3000" % (SHEET_TOKEN, SHEET_ID)],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE
)
data = json.loads(result.stdout.decode("utf-8"))
rows = data.get("data", {}).get("valueRange", {}).get("values", [])
if not rows:
    print("表格无数据，退出"); sys.exit(1)

headers = [str(h).strip().replace(" ", "").lower() for h in rows[0]]
owner_idx = next((i for i, h in enumerate(headers) if h == "负责人"), -1)
if owner_idx < 0:
    print("找不到负责人列，退出"); sys.exit(1)

names = sorted(set(
    str(r[owner_idx]).strip()
    for r in rows[1:]
    if len(r) > owner_idx and str(r[owner_idx]).strip() and str(r[owner_idx]).strip() != "None"
))
print("共找到 %d 个负责人: %s" % (len(names), ", ".join(names)))

# 2. 读取现有映射（保留已有的）
existing = {}
if os.path.exists(OUT):
    with open(OUT, "r", encoding="utf-8") as f:
        existing = json.load(f)

# 3. 批量查 open_id（跳过已有的）
mapping = dict(existing)
for name in names:
    if name in mapping:
        print("  %s: 已有，跳过" % name)
        continue
    r = subprocess.run(
        [LARK_CLI, "contact", "+search-user", "--query", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        d = json.loads(r.stdout.decode("utf-8"))
        users = [u for u in d.get("data", {}).get("users", []) if not u.get("is_cross_tenant")]
        if users:
            mapping[name] = users[0]["open_id"]
            print("  %s: %s" % (name, users[0]["open_id"]))
        else:
            print("  %s: 未找到（非公司账号，跳过）" % name)
    except Exception as e:
        print("  %s: 查询失败 (%s)" % (name, e))

# 4. 写入文件
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(mapping, f, ensure_ascii=False, indent=2)
print("\n已更新 %s（共 %d 条）" % (OUT, len(mapping)))
PYEOF
