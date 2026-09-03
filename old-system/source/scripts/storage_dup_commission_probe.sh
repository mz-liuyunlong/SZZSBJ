#!/usr/bin/env bash
# storage_dup_commission_probe.sh —— 只读探针（零写入）
# 【一】核实仓储费是否真双算：自定义时间导入 vs 按账期导入 是否同表、有无区分列、ICP口径实算差额
# 【二】佣金定性：recon.sale 是毛额还是净额、佣金金额在哪、量级多少
exec > /tmp/storage_dup_commission_probe.log 2>&1
echo "storage_dup_commission_probe $(date '+%F %T')"
cd /opt/lingxing-auto || { echo "no /opt/lingxing-auto"; exit 1; }
set -a; . ./.env; set +a
q(){ MYSQL_PWD="$DB_PASSWORD" mysql -h"${DB_HOST:-127.0.0.1}" -P"${DB_PORT:-3306}" -u"$DB_USER" "${DB_NAME:-walmart_ai_data}" -t -e "$1"; }

echo "=============== 【一】仓储费是否真双算 ==============="
echo "--- 1.1 fact_wfs_storage_fee 完整表结构（找「导入类型/批次」区分列）---"
q "SHOW CREATE TABLE fact_wfs_storage_fee\G"

echo ""
echo "--- 1.2 是否还有别的仓储费表（自定义时间导入可能进别处）---"
q "SELECT table_name, table_rows FROM information_schema.tables
    WHERE table_schema=DATABASE() AND (table_name LIKE '%storage%' OR table_name LIKE '%仓储%');"

echo ""
echo "--- 1.3 CN2601 各账期 + 批次/导入信息（看两条跨月账期是不是不同批次）---"
q "SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS 期起, DATE_FORMAT(report_end,'%Y-%m-%d') AS 期止,
          DATEDIFF(report_end,report_start)+1 AS 天数, COUNT(*) AS 行数,
          ROUND(SUM(final_storage_fee),2) AS 金额,
          MIN(created_at) AS 首次写入, MAX(updated_at) AS 最近更新,
          COUNT(DISTINCT task_id) AS 批次数, GROUP_CONCAT(DISTINCT task_id) AS 批次
     FROM fact_wfs_storage_fee WHERE store_id='110687423514268160'
    GROUP BY report_start, report_end ORDER BY report_start;" 2>/dev/null \
|| q "SELECT DATE_FORMAT(report_start,'%Y-%m-%d') AS 期起, DATE_FORMAT(report_end,'%Y-%m-%d') AS 期止,
          DATEDIFF(report_end,report_start)+1 AS 天数, COUNT(*) AS 行数,
          ROUND(SUM(final_storage_fee),2) AS 金额, MIN(created_at) AS 首次写入
     FROM fact_wfs_storage_fee WHERE store_id='110687423514268160'
    GROUP BY report_start, report_end ORDER BY report_start;"

echo ""
echo "--- 1.4 【关键】按 ICP 页面真实口径实算：CN2601 2026-07 仓储费合计 ---"
echo "     (ICP口径 = WHERE DATE_FORMAT(report_start,'%Y-%m') BETWEEN from AND to，不区分账期类型，全表SUM)"
q "SELECT 'ICP实算(含全部账期)' AS 口径, ROUND(SUM(final_storage_fee),2) AS 金额_2026_07
     FROM fact_wfs_storage_fee
    WHERE store_id='110687423514268160' AND DATE_FORMAT(report_start,'%Y-%m')='2026-07';"
q "SELECT '仅14天标准账期' AS 口径, ROUND(SUM(final_storage_fee),2) AS 金额_2026_07
     FROM fact_wfs_storage_fee
    WHERE store_id='110687423514268160' AND DATE_FORMAT(report_start,'%Y-%m')='2026-07'
      AND DATEDIFF(report_end,report_start)+1 <= 15;"
q "SELECT '仅跨月账期(疑似重复)' AS 口径, ROUND(SUM(final_storage_fee),2) AS 金额_2026_07
     FROM fact_wfs_storage_fee
    WHERE store_id='110687423514268160' AND DATE_FORMAT(report_start,'%Y-%m')='2026-07'
      AND DATEDIFF(report_end,report_start)+1 > 15;"

echo ""
echo "--- 1.5 同SKU是否在重叠期内出现两次（双算的直接证据）---"
q "SELECT sku, COUNT(*) AS 出现次数, GROUP_CONCAT(CONCAT(report_start,'~',report_end,':',ROUND(final_storage_fee,2)) ORDER BY report_start SEPARATOR ' | ') AS 各账期金额
     FROM fact_wfs_storage_fee
    WHERE store_id='110687423514268160'
      AND report_start <= '2026-07-31' AND report_end >= '2026-07-11'
    GROUP BY sku HAVING COUNT(*) > 1 ORDER BY 出现次数 DESC LIMIT 12;"

echo ""
echo "--- 1.6 哨兵视角：ICP仓储管道 vs recon账单 storage 类目（差多少=是否虚高）---"
q "SELECT '管道(仓储表)' AS 源, ROUND(SUM(final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee WHERE DATE_FORMAT(report_start,'%Y-%m') BETWEEN '2026-05' AND '2026-08';"
q "SELECT '账单(recon storage)' AS 源, ROUND(-SUM(amount),2) AS 金额
     FROM fact_reconciliation_item
    WHERE fee_category='storage' AND DATE_FORMAT(period_end,'%Y-%m') BETWEEN '2026-05' AND '2026-08';"

echo ""
echo "=============== 【二】佣金定性 ==============="
echo "--- 2.1 recon 全部 fee_category 清单（看有没有佣金类目）---"
q "SELECT fee_category, COUNT(*) AS 行数, ROUND(SUM(amount),2) AS 金额合计
     FROM fact_reconciliation_item WHERE period_end>='2026-05-01'
    GROUP BY fee_category ORDER BY ABS(SUM(amount)) DESC;"

echo ""
echo "--- 2.2 【关键】recon.sale 是毛额还是净额：与结算表对照（同店同月）---"
q "SELECT r.store_id, r.m AS 月,
          r.sale_recon AS recon销售额,
          s.sales_amount AS 结算销售额,
          s.commission_amount AS 结算佣金,
          ROUND(s.sales_amount - ABS(s.commission_amount),2) AS 结算净额_销售减佣金,
          ROUND(r.sale_recon - s.sales_amount,2) AS 差_recon减毛额,
          ROUND(r.sale_recon - (s.sales_amount-ABS(s.commission_amount)),2) AS 差_recon减净额
     FROM (SELECT store_id, DATE_FORMAT(period_end,'%Y-%m') AS m, ROUND(SUM(amount),2) AS sale_recon
             FROM fact_reconciliation_item WHERE fee_category='sale' AND period_end>='2026-06-01'
            GROUP BY store_id, m) r
     JOIN (SELECT store_id, settlement_month AS m, ROUND(SUM(sales_amount),2) AS sales_amount,
                  ROUND(SUM(commission_amount),2) AS commission_amount
             FROM fact_settlement_msku_monthly WHERE settlement_month>='2026-06'
            GROUP BY store_id, m) s
       ON s.store_id=r.store_id AND s.m=r.m
    ORDER BY r.m, r.store_id LIMIT 20;"

echo ""
echo "--- 2.3 佣金量级 + 是否按 msku/item 可拆 ---"
q "SELECT settlement_month AS 月, COUNT(*) AS 行数, COUNT(DISTINCT msku) AS msku数,
          ROUND(SUM(sales_amount),2) AS 销售额, ROUND(SUM(commission_amount),2) AS 佣金,
          ROUND(100*SUM(ABS(commission_amount))/NULLIF(SUM(sales_amount),0),2) AS 佣金率百分比
     FROM fact_settlement_msku_monthly WHERE settlement_month>='2026-05'
    GROUP BY settlement_month ORDER BY 月;"

echo ""
echo "--- 2.4 佣金折扣表现状（探针20已建，看有没有数据）---"
q "SELECT COUNT(*) AS 行数, COUNT(DISTINCT store_id) AS 店铺数,
          ROUND(SUM(saving_amount),2) AS 折扣合计
     FROM fact_commission_saving;" 2>/dev/null \
|| q "SHOW COLUMNS FROM fact_commission_saving;"

echo "=============== 【三】赔付/返还/测评 到底能不能落到 ITEMID ==============="
echo "--- 3.1 recon 店铺级类目现状（哪些类目 item_id 全空、各多少钱）---"
q "SELECT fee_category, COUNT(*) AS 行数,
          SUM(COALESCE(item_id,'')<>'') AS 带item行, SUM(COALESCE(msku,'')<>'') AS 带msku行,
          ROUND(SUM(amount),2) AS 金额
     FROM fact_reconciliation_item
    WHERE period_end>='2026-05-01' AND COALESCE(item_id,'')=''
    GROUP BY fee_category ORDER BY ABS(SUM(amount)) DESC;"

echo ""
echo "--- 3.2 fact_ad_credit_detail（返还/赔付行级留档）有没有 item 信息 ---"
q "SHOW CREATE TABLE fact_ad_credit_detail\G"
q "SELECT fee_category, COUNT(*) AS 行数,
          SUM(COALESCE(item_id,'')<>'') AS 带item行, SUM(COALESCE(msku,'')<>'') AS 带msku行,
          ROUND(SUM(amount),2) AS 金额
     FROM fact_ad_credit_detail GROUP BY fee_category ORDER BY ABS(SUM(amount)) DESC;" 2>/dev/null \
|| echo "(fact_ad_credit_detail 无 item_id/msku/fee_category 列，见上方表结构)"

echo ""
echo "--- 3.3 RAW原始账单行：赔付类是否携带 ItemId/GTIN（决定能否直落）---"
q "SELECT COUNT(*) AS raw样本行 FROM raw_lingxing_api
    WHERE api_path LIKE '%statement%' AND created_at>='2026-08-01' LIMIT 1;"
q "SELECT SUBSTRING(payload,1,1500) AS raw首行样本 FROM raw_lingxing_api
    WHERE api_path LIKE '%statement%' ORDER BY id DESC LIMIT 1;" 2>/dev/null \
|| q "SHOW COLUMNS FROM raw_lingxing_api;"

echo ""
echo "--- 3.4 若需分摊：可选分摊基数的可用性（销售额/销量/广告花费 按item）---"
q "SELECT '按item销售额(recon sale)' AS 基数, COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS item数,
          ROUND(SUM(amount),2) AS 金额
     FROM fact_reconciliation_item
    WHERE fee_category='sale' AND period_end>='2026-05-01' AND COALESCE(item_id,'')<>'';"
q "SELECT '按item广告花费' AS 基数, COUNT(DISTINCT CONCAT(store_id,'|',item_id)) AS item数,
          ROUND(SUM(ad_spend),2) AS 金额
     FROM fact_ads_product_daily
    WHERE platform='walmart' AND stat_date>='2026-05-01' AND COALESCE(item_id,'')<>'';"

echo "=============== 【四】逐账期对账单：仓储/入库 到底漏没漏、重没重 ==============="
echo "（权威=沃尔玛账单 recon 类目金额；账单有钱而管道表无行=漏导；账单无钱=该期本就没发生，不是漏）"

echo "--- 4.1 入库运输：账单 vs 分摊表 逐店逐账期对照 ---"
q "SELECT d.store_name AS 店铺,
          DATE_FORMAT(b.period_start,'%m-%d') AS 期起, DATE_FORMAT(b.period_end,'%m-%d') AS 期止,
          ROUND(-b.bill_amt,2) AS 账单入库运输费,
          ROUND(COALESCE(p.pipe_amt,0),2) AS 分摊表金额,
          ROUND(COALESCE(p.pipe_amt,0)-(-b.bill_amt),2) AS 差额,
          CASE WHEN -b.bill_amt=0 AND COALESCE(p.pipe_amt,0)=0 THEN '本期无发生(正常)'
               WHEN -b.bill_amt<>0 AND COALESCE(p.pipe_amt,0)=0 THEN '❗账单有钱但表无行=漏导'
               WHEN ABS(COALESCE(p.pipe_amt,0)-(-b.bill_amt))<=GREATEST(1,ABS(b.bill_amt)*0.02) THEN '✅一致'
               ELSE '⚠️差异需查' END AS 判定
     FROM (SELECT store_id, period_start, period_end, SUM(amount) AS bill_amt
             FROM fact_reconciliation_item WHERE fee_category='inbound_transport'
              AND period_end>='2026-05-01' GROUP BY store_id, period_start, period_end) b
     LEFT JOIN (SELECT store_id, report_start, report_end, SUM(alloc_amount) AS pipe_amt
                  FROM fact_inbound_freight_alloc GROUP BY store_id, report_start, report_end) p
       ON p.store_id=b.store_id AND p.report_start=b.period_start
     LEFT JOIN dim_store d ON d.store_id=b.store_id
    ORDER BY d.store_name, b.period_start;"

echo ""
echo "--- 4.2 仓储费：账单 vs 仓储表 逐店逐账期对照（含CN2601重叠期真相）---"
q "SELECT d.store_name AS 店铺,
          DATE_FORMAT(b.period_start,'%m-%d') AS 期起, DATE_FORMAT(b.period_end,'%m-%d') AS 期止,
          ROUND(-b.bill_amt,2) AS 账单仓储费,
          ROUND(COALESCE(p.pipe_amt,0),2) AS 仓储表金额,
          ROUND(COALESCE(p.pipe_amt,0)-(-b.bill_amt),2) AS 差额,
          CASE WHEN -b.bill_amt<>0 AND COALESCE(p.pipe_amt,0)=0 THEN '❗账单有钱但表无行=漏导'
               WHEN ABS(COALESCE(p.pipe_amt,0)-(-b.bill_amt))<=GREATEST(1,ABS(b.bill_amt)*0.02) THEN '✅一致'
               ELSE '⚠️差异需查' END AS 判定
     FROM (SELECT store_id, period_start, period_end, SUM(amount) AS bill_amt
             FROM fact_reconciliation_item WHERE fee_category='storage'
              AND period_end>='2026-05-01' GROUP BY store_id, period_start, period_end) b
     LEFT JOIN (SELECT store_id, report_start, report_end, SUM(final_storage_fee) AS pipe_amt
                  FROM fact_wfs_storage_fee GROUP BY store_id, report_start, report_end) p
       ON p.store_id=b.store_id AND p.report_start=b.period_start
     LEFT JOIN dim_store d ON d.store_id=b.store_id
    ORDER BY d.store_name, b.period_start;"

echo ""
echo "--- 4.3 CN2601 决定性一问：7月账单仓储费总额 vs 仓储表7月总额 ---"
q "SELECT '账单(recon storage 7月)' AS 源, ROUND(-SUM(amount),2) AS 金额
     FROM fact_reconciliation_item
    WHERE store_id='110687423514268160' AND fee_category='storage'
      AND period_start>='2026-07-01' AND period_end<='2026-08-07';"
q "SELECT '仓储表(全部账期,ICP口径)' AS 源, ROUND(SUM(final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee
    WHERE store_id='110687423514268160' AND report_start>='2026-07-01' AND report_end<='2026-08-12';"
q "SELECT '仓储表(仅14天账期)' AS 源, ROUND(SUM(final_storage_fee),2) AS 金额
     FROM fact_wfs_storage_fee
    WHERE store_id='110687423514268160' AND report_start>='2026-07-01' AND report_end<='2026-08-12'
      AND DATEDIFF(report_end,report_start)+1<=15;"

echo ""
echo "--- 4.4 账单里还有哪些账期是最新的（判断哪些期是「还没出账单」而非漏导）---"
q "SELECT d.store_name AS 店铺, MAX(p.period_end) AS 账单最新账期止,
          (SELECT MAX(report_end) FROM fact_wfs_storage_fee s WHERE s.store_id=p.store_id) AS 仓储表最新,
          (SELECT MAX(report_end) FROM fact_inbound_freight_alloc i WHERE i.store_id=p.store_id) AS 入库表最新
     FROM fact_reconciliation_period p LEFT JOIN dim_store d ON d.store_id=p.store_id
    GROUP BY p.store_id, d.store_name ORDER BY d.store_name;"
echo "---- done ----"
