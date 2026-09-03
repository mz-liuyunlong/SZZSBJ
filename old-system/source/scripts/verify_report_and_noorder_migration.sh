#!/usr/bin/env bash
# 验证脚本：performanceSummaryReport.ts / noOrderNotify.ts 数据源迁移生产验证
#
# 用途：在生产/新服务器上执行，验证两点：
#   1. report:performance（日报/周报/月报）已改读 MySQL raw_feishu_table(order_profit_daily)，
#      不再读取飞书「5月销售明细_复盘」，不再调用 get_cell_ranges。
#   2. noOrderNotify.ts 负责人来源已改读 dim_product.owner，不再读取飞书「ItemID负责人」(<REDACTED_FEISHU_SHEET_ID>)。
#
# 用法：在项目根目录（package.json 所在目录）执行：
#   bash scripts/verify_report_and_noorder_migration.sh
#
# 本脚本只读、只跑 dry-run（noOrderNotify 不加 --send），不写入任何业务数据，不改 cron，不改库结构。
# 输出的日志会保存到 ./_verify_<时间戳>/ 目录，方便回溯。

set -uo pipefail

LOG_DIR="./_verify_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
echo "验证日志目录: $LOG_DIR"
echo ""

# ── 步骤1：order_profit_daily 数据覆盖范围 ──────────────────────────────────
echo "===== 步骤1: order_profit_daily 覆盖范围 ====="
npx ts-node --transpile-only -e "
require('dotenv/config');
const mysql = require('mysql2/promise');
(async () => {
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? '127.0.0.1',
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? '',
    password: process.env.DB_PASSWORD ?? '',
    database: process.env.DB_NAME ?? 'walmart_ai_data',
  });
  const [rows] = await db.query(
    \"SELECT MIN(data_date) AS min_date, MAX(data_date) AS max_date, COUNT(DISTINCT data_date) AS days FROM raw_feishu_table WHERE sheet_id='<REDACTED_FEISHU_SHEET_ID>'\"
  );
  console.log(JSON.stringify(rows, null, 2));
  await db.end();
})().catch((e) => { console.error('SQL_CHECK_FAILED:', e.message); process.exit(1); });
" 2>&1 | tee "$LOG_DIR/01_coverage_check.log"

# ── 步骤2/3：日报/周报/月报 dry-run ──────────────────────────────────────────
echo ""
echo "===== 步骤2: 日报 dry-run ====="
npm run report:performance -- --mode=daily 2>&1 | tee "$LOG_DIR/02_report_daily.log"

echo ""
echo "===== 步骤3: 周报 dry-run ====="
npm run report:performance -- --mode=weekly 2>&1 | tee "$LOG_DIR/03_report_weekly.log"

echo ""
echo "===== 步骤3: 月报 dry-run ====="
npm run report:performance -- --mode=monthly 2>&1 | tee "$LOG_DIR/04_report_monthly.log"

# ── 步骤4：noOrderNotify dry-run（不加 --send）───────────────────────────────
echo ""
echo "===== 步骤4: noOrderNotify dry-run（不加 --send）====="
npx ts-node src/noOrderNotify.ts 2>&1 | tee "$LOG_DIR/05_no_order_notify.log"

# ── 自动核查：日志中不应再出现旧飞书业务表依赖关键词 ─────────────────────────
echo ""
echo "===== 自动核查：不应再出现旧飞书业务表依赖 ====="
FAIL=0

for f in "$LOG_DIR/02_report_daily.log" "$LOG_DIR/03_report_weekly.log" "$LOG_DIR/04_report_monthly.log"; do
  if grep -q "5月销售明细_复盘\|get_cell_ranges" "$f"; then
    echo "[FAIL] $f 仍出现旧飞书表依赖（5月销售明细_复盘 / get_cell_ranges）"
    FAIL=1
  else
    echo "[PASS] $f 未出现旧飞书表依赖"
  fi
done

if grep -q "ItemID负责人\|<REDACTED_FEISHU_SHEET_ID>" "$LOG_DIR/05_no_order_notify.log"; then
  echo "[FAIL] noOrderNotify 日志仍出现 ItemID负责人 / <REDACTED_FEISHU_SHEET_ID>"
  FAIL=1
else
  echo "[PASS] noOrderNotify 未出现 ItemID负责人 / <REDACTED_FEISHU_SHEET_ID>"
fi

echo ""
echo "验证日志已全部保存到: $LOG_DIR"
echo ""

if [ "$FAIL" -eq 0 ]; then
  cat <<'EOF'
===== 自动核查通过，请人工再确认以下三项后决定是否部署 =====
1) 01_coverage_check.log 里 min_date/max_date/days 是否覆盖：
   - 日报所需的目标日期
   - 周报所需的近7天（上周六~上周五）
   - 月报所需的上个月整月
2) 02/03/04 三份报表日志里的店铺/负责人/销量/毛利润数字是否合理（对比历史播报记录人工判断）
3) 05_no_order_notify.log 里的 商品总数 / 库存>0数 / 匹配到负责人数 / 未匹配负责人数 是否合理

人工确认无误后再部署（不走 git，不改 cron，不改库结构，不重启服务，覆盖前先备份）：
  cp src/performanceSummaryReport.ts src/performanceSummaryReport.ts.bak.$(date +%Y%m%d_%H%M%S)
  cp src/noOrderNotify.ts src/noOrderNotify.ts.bak.$(date +%Y%m%d_%H%M%S)
  # 然后按现有生产上传方式覆盖这两个文件
EOF
else
  echo "===== 存在自动核查未通过项，请勿部署，先排查上面标 [FAIL] 的日志 ====="
fi
