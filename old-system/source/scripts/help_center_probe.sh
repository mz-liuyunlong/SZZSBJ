#!/usr/bin/env bash
# help_center_probe.sh —— 只读：盘点帮助中心 dim_page_help 现状，确认 SEM 模块是否缺帮助文
exec > /tmp/help_center_probe.log 2>&1
echo "help_center_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "===== 1. dim_page_help 表结构 ====="
q "SHOW CREATE TABLE dim_page_help\G"

echo ""
echo "===== 2. 现有帮助文全清单（page_key / 标题 / 正文长度 / 更新人 / 更新时间）====="
q "SELECT page_key, LEFT(COALESCE(title,''),40) AS 标题, CHAR_LENGTH(COALESCE(content,'')) AS 正文字数,
          COALESCE(updated_by,'') AS 更新人, updated_at AS 更新时间
     FROM dim_page_help ORDER BY updated_at DESC;"

echo ""
echo "===== 3. 是否存在 SEM 相关帮助文（预期：无）====="
q "SELECT COUNT(*) AS SEM相关条数 FROM dim_page_help
    WHERE page_key LIKE '%sem%' OR COALESCE(title,'') LIKE '%SEM%' OR COALESCE(content,'') LIKE '%SEM%';"

echo ""
echo "===== 4. 是否存在 仓储费/入库运输 导入相关帮助文（本次防重方案需配套）====="
q "SELECT page_key, LEFT(COALESCE(title,''),40) AS 标题, CHAR_LENGTH(COALESCE(content,'')) AS 字数
     FROM dim_page_help
    WHERE COALESCE(content,'') LIKE '%仓储%' OR COALESCE(content,'') LIKE '%入库运输%'
       OR COALESCE(title,'') LIKE '%仓储%';"

echo ""
echo "===== 5. 帮助文与页面的挂载方式（看 page_key 命名规律，供新增SEM帮助文取名）====="
q "SELECT page_key FROM dim_page_help ORDER BY page_key;"
echo "---- done ----"
