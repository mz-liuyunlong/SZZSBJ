#!/usr/bin/env bash
# storage_overlap_fix.sh —— CN2601 仓储费重叠账期清理（2026-08-14 需求方批准：备份留档后删）
#
# 背景：fact_wfs_storage_fee 唯一键含账期起止，跨账期不去重会累加。CN2601 除完整的14天标准账期序列外，
#       另有两条跨月账期与之时间重叠，导致 ICP(单品现金利润) 仓储费虚高 $15,464.67：
#         2026-07-01~2026-07-31 (31天, 170行, $9,335.24)  ← 08-02探针阶段验证性导入残留
#         2026-07-14~2026-08-12 (30天, 153行, $6,129.43)  ← 同上
# 证据：剔除这两条后，CN2601 仓储费与沃尔玛账单逐期吻合（06-27~07-11 账单$5,810.57 vs 管道$5,810.56；
#       07-11~07-25 账单$3,922.52 vs 管道$3,922.52；按天摊平全区间差 +$18.86 / 0.1%）。
# 判据从严：只删这两条明确指定的(店铺,账期起,账期止)，不按天数等任何推断条件删除。
#
# 用法：  bash storage_overlap_fix.sh            # DRY-RUN：预览将删内容，零写入
#         bash storage_overlap_fix.sh --commit   # 备份留档 + 删除
exec > /tmp/storage_overlap_fix.log 2>&1
MODE="dry"; [ "$1" = "--commit" ] && MODE="commit"
echo "storage_overlap_fix $(date '+%F %T') MODE=$MODE"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a

cat > /tmp/storage_overlap_fix.sql <<'SQL'
-- 待删账期（严格枚举，不用任何推断条件）
CREATE TEMPORARY TABLE tmp_del (store_id VARCHAR(64), report_start DATE, report_end DATE);
INSERT INTO tmp_del VALUES
 ('110687423514268160','2026-07-01','2026-07-31'),
 ('110687423514268160','2026-07-14','2026-08-12');

-- 预览① 将删的账期与金额
SELECT s.store_id, d.store_name, s.report_start AS 期起, s.report_end AS 期止,
       DATEDIFF(s.report_end,s.report_start)+1 AS 天数, COUNT(*) AS 行数,
       ROUND(SUM(s.final_storage_fee),2) AS 金额, MIN(s.created_at) AS 导入时间,
       MIN(s.source_task_id) AS 批次
  FROM fact_wfs_storage_fee s
  JOIN tmp_del t ON t.store_id=s.store_id AND t.report_start=s.report_start AND t.report_end=s.report_end
  LEFT JOIN dim_store d ON d.store_id=s.store_id
 GROUP BY s.store_id, d.store_name, s.report_start, s.report_end;

SELECT '将删行数合计' AS chk, COUNT(*) AS c, ROUND(SUM(s.final_storage_fee),2) AS 金额
  FROM fact_wfs_storage_fee s
  JOIN tmp_del t ON t.store_id=s.store_id AND t.report_start=s.report_start AND t.report_end=s.report_end;

-- 预览② 删除后保留的账期（应为连续的14天序列）
SELECT s.report_start AS 期起, s.report_end AS 期止, DATEDIFF(s.report_end,s.report_start)+1 AS 天数,
       COUNT(*) AS 行数, ROUND(SUM(s.final_storage_fee),2) AS 金额
  FROM fact_wfs_storage_fee s
 WHERE s.store_id='110687423514268160'
   AND NOT EXISTS (SELECT 1 FROM tmp_del t WHERE t.store_id=s.store_id
                     AND t.report_start=s.report_start AND t.report_end=s.report_end)
 GROUP BY s.report_start, s.report_end ORDER BY s.report_start;

-- 预览③ 删除后 CN2601 各月仓储费（ICP口径：按 report_start 归月）
SELECT DATE_FORMAT(s.report_start,'%Y-%m') AS 月份, ROUND(SUM(s.final_storage_fee),2) AS 删后金额
  FROM fact_wfs_storage_fee s
 WHERE s.store_id='110687423514268160'
   AND NOT EXISTS (SELECT 1 FROM tmp_del t WHERE t.store_id=s.store_id
                     AND t.report_start=s.report_start AND t.report_end=s.report_end)
 GROUP BY 月份 ORDER BY 月份;
SQL

if [ "$MODE" = "commit" ]; then
cat >> /tmp/storage_overlap_fix.sql <<'SQL'
-- ① 备份留档（同构表；INSERT IGNORE 防重跑重复）
CREATE TABLE IF NOT EXISTS fact_wfs_storage_fee_overlap_bak_20260814 LIKE fact_wfs_storage_fee;
INSERT IGNORE INTO fact_wfs_storage_fee_overlap_bak_20260814
SELECT s.* FROM fact_wfs_storage_fee s
  JOIN tmp_del t ON t.store_id=s.store_id AND t.report_start=s.report_start AND t.report_end=s.report_end;
SELECT '备份表行数' AS chk, COUNT(*) AS c,
       ROUND(SUM(final_storage_fee),2) AS 金额 FROM fact_wfs_storage_fee_overlap_bak_20260814;

-- ② 删除（判据与备份完全一致）
DELETE s FROM fact_wfs_storage_fee s
  JOIN tmp_del t ON t.store_id=s.store_id AND t.report_start=s.report_start AND t.report_end=s.report_end;

-- ③ 终检
SELECT '终检:该店剩余账期数' AS chk, COUNT(DISTINCT CONCAT(report_start,'~',report_end)) AS c
  FROM fact_wfs_storage_fee WHERE store_id='110687423514268160';
SELECT '终检:该店非14天账期数(应=0)' AS chk, COUNT(*) AS c FROM (
  SELECT DISTINCT report_start, report_end FROM fact_wfs_storage_fee
   WHERE store_id='110687423514268160' AND DATEDIFF(report_end,report_start)+1<>14) x;
SELECT '终检:全库重叠账期对数(应=0)' AS chk, COUNT(*) AS c FROM (
  SELECT a.store_id FROM (SELECT DISTINCT store_id,report_start,report_end FROM fact_wfs_storage_fee) a
    JOIN (SELECT DISTINCT store_id,report_start,report_end FROM fact_wfs_storage_fee) b
      ON a.store_id=b.store_id
     AND (a.report_start<b.report_start OR (a.report_start=b.report_start AND a.report_end<b.report_end))
     AND a.report_start<=b.report_end AND b.report_start<=a.report_end) y;
SELECT '终检:CN2601 2026-07仓储费(应≈6463.81)' AS chk, ROUND(SUM(final_storage_fee),2) AS 金额
  FROM fact_wfs_storage_fee
 WHERE store_id='110687423514268160' AND DATE_FORMAT(report_start,'%Y-%m')='2026-07';
SELECT '终检:管道vs账单(2026-05~08全店)' AS chk,
       (SELECT ROUND(SUM(final_storage_fee),2) FROM fact_wfs_storage_fee
         WHERE DATE_FORMAT(report_start,'%Y-%m') BETWEEN '2026-05' AND '2026-08') AS 管道,
       (SELECT ROUND(-SUM(amount),2) FROM fact_reconciliation_item
         WHERE fee_category='storage' AND DATE_FORMAT(period_end,'%Y-%m') BETWEEN '2026-05' AND '2026-08') AS 账单;
SQL
fi

MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t < /tmp/storage_overlap_fix.sql
echo "---- done ($MODE) ----"
