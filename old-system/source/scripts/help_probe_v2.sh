#!/usr/bin/env bash
# help_probe_v2.sh —— 只读：帮助中心盘点（修正列名 content_md）+ 广告类帮助文取样，供SEM帮助文对齐风格
exec > /tmp/help_probe_v2.log 2>&1
echo "help_probe_v2 $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }
qr(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -N -B -e "$1"; }

echo "===== 1. 帮助文全清单（分组/标题/字数/更新人/时间）====="
q "SELECT page_key, group_name AS 分组, group_sort AS 组序, LEFT(title,36) AS 标题,
          CHAR_LENGTH(COALESCE(content_md,'')) AS 正文字数, is_active AS 启用,
          updated_by AS 更新人, updated_at AS 更新时间
     FROM dim_page_help ORDER BY group_sort, sort, page_key;"

echo ""
echo "===== 2. SEM 相关帮助文（预期 0）====="
q "SELECT COUNT(*) AS SEM相关条数 FROM dim_page_help
    WHERE page_key LIKE '%sem%' OR title LIKE '%SEM%' OR COALESCE(content_md,'') LIKE '%SEM%';"

echo ""
echo "===== 3. 仓储费/入库运输 导入相关帮助文（防重方案需配套说明）====="
q "SELECT page_key, LEFT(title,36) AS 标题, CHAR_LENGTH(COALESCE(content_md,'')) AS 字数
     FROM dim_page_help
    WHERE COALESCE(content_md,'') LIKE '%仓储%' OR COALESCE(content_md,'') LIKE '%入库运输%' OR title LIKE '%仓储%';"

echo ""
echo "===== 4. 分组一览（新增SEM帮助文该挂哪个组）====="
q "SELECT group_name AS 分组, MIN(group_sort) AS 组序, COUNT(*) AS 文章数,
          GROUP_CONCAT(page_key ORDER BY sort SEPARATOR ', ') AS 该组文章
     FROM dim_page_help GROUP BY group_name ORDER BY MIN(group_sort);"

echo ""
echo "===== 5. 取样：广告类帮助文正文（对齐写作风格与结构）====="
qr "SELECT CONCAT('--- page_key=', page_key, ' | ', title, ' | target_url=', target_url, ' ---\n',
                 LEFT(COALESCE(content_md,''), 1800))
      FROM dim_page_help WHERE page_key='ads_upload_page';"
echo ""
qr "SELECT CONCAT('--- page_key=', page_key, ' | ', title, ' ---\n', LEFT(COALESCE(content_md,''), 1200))
      FROM dim_page_help WHERE page_key='notify_auto_ad_import';"

echo ""
echo "===== 6. 附：查 sendBusinessReportNotify.ts 线上时间戳（本地与线上md5不一致，需定新旧）====="
ls -l --time-style=long-iso /opt/lingxing-auto/src/sendBusinessReportNotify.ts 2>/dev/null
echo "--- 线上文件头20行（看有无改动痕迹）---"
head -20 /opt/lingxing-auto/src/sendBusinessReportNotify.ts 2>/dev/null
echo "---- done ----"
