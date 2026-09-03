/**
 * adsItemSpendAlloc.ts — 按品广告费统一口径（一处计算，多处读取）
 *
 * 需求方拍板（2026-08-25，见 DATABASE_MAP「SV视频广告 itemId='1001' 定案」节）：
 *   商品的广告花费 = 其名下所有广告的全部花费。SV 报表中无商品ID的行（占位 itemId，如 '1001'，
 *   即视频素材侧统计行）的花费/曝光/点击/订单/销售额，按其所属广告组回归组内商品：
 *   多商品组按当日花费比例分摊；当日组内商品花费全 0 按曝光比例；再全 0 均分。全历史统一口径。
 *
 * 用法：消费方把 `FROM fact_ads_product_daily` 换成 `FROM ${adjustedAdsFactSql()} <别名>`，
 *   列名与原表一致：stat_date/platform/store_id/store_name/campaign_id/campaign_name/campaign_type/
 *   ad_group_id/ad_group_name/item_id/msku/impressions/clicks/ad_spend/orders/total_sales。
 *   其余 WHERE/GROUP BY 逻辑零改动。原始表零写入零改动；店铺/全库花费合计不变（钱从无主行移到商品行）。
 *
 * 边界（如实声明）：
 *   - 无商品ID行优先并入「同日同组」的商品行（现网 100% 命中，probe3/6 实证）；同日无商品行时
 *     并入该组全历史花费最大的商品（防御分支，现网无此形态）；组内从无任何商品行的孤儿组不并入
 *     （现网不存在；如出现，其花费不进按品口径，只体现在原始表/发票对账）。
 *   - 发票对账、reportV2Reconcile、P7 哨兵均读原始表，不受本口径影响。
 */

/** 无商品ID占位行判定（alias 为表别名，空串=不加前缀） */
export function adsPhCond(alias = ""): string {
  const p = alias ? `${alias}.` : "";
  return `CHAR_LENGTH(${p}item_id) <= 5 AND ${p}item_id REGEXP '^[0-9]+$' AND COALESCE(TRIM(${p}msku),'') = ''`;
}

/** 调整后的按品广告事实子查询（含尾部别名占位由调用方提供，如 `${adjustedAdsFactSql()} fa`） */
export function adjustedAdsFactSql(): string {
  return `(
    SELECT stat_date, platform, store_id, store_name, campaign_id, campaign_name, campaign_type,
           ad_group_id, ad_group_name, item_id, msku,
           impressions, clicks, ad_spend, orders, total_sales
    FROM fact_ads_product_daily
    WHERE NOT (${adsPhCond()})
    UNION ALL
    SELECT ph.stat_date, ph.platform, ph.store_id, ph.store_name, ph.campaign_id, ph.campaign_name, ph.campaign_type,
           ph.ad_group_id, ph.ad_group_name, w.item_id, w.msku,
           ROUND(ph.impressions * w.wt), ROUND(ph.clicks * w.wt), ph.ad_spend * w.wt,
           ROUND(ph.orders * w.wt), ph.total_sales * w.wt
    FROM fact_ads_product_daily ph
    JOIN (
      SELECT stat_date, store_id, campaign_id, ad_group_id, item_id, msku,
             CASE WHEN SUM(ad_spend)    OVER g > 0 THEN ad_spend    / (SUM(ad_spend)    OVER g)
                  WHEN SUM(impressions) OVER g > 0 THEN impressions / (SUM(impressions) OVER g)
                  ELSE 1 / (COUNT(*) OVER g) END AS wt
      FROM fact_ads_product_daily
      WHERE NOT (${adsPhCond()})
      WINDOW g AS (PARTITION BY stat_date, store_id, campaign_id, ad_group_id)
    ) w ON w.stat_date = ph.stat_date AND w.store_id = ph.store_id
       AND w.campaign_id = ph.campaign_id AND w.ad_group_id = ph.ad_group_id
    WHERE ${adsPhCond("ph")}
    UNION ALL
    SELECT ph.stat_date, ph.platform, ph.store_id, ph.store_name, ph.campaign_id, ph.campaign_name, ph.campaign_type,
           ph.ad_group_id, ph.ad_group_name, d.item_id, d.msku,
           ph.impressions, ph.clicks, ph.ad_spend, ph.orders, ph.total_sales
    FROM fact_ads_product_daily ph
    JOIN (
      SELECT store_id, campaign_id, ad_group_id, item_id, msku,
             ROW_NUMBER() OVER (PARTITION BY store_id, campaign_id, ad_group_id
                                ORDER BY SUM(ad_spend) DESC, SUM(impressions) DESC) AS rn
      FROM fact_ads_product_daily
      WHERE NOT (${adsPhCond()})
      GROUP BY store_id, campaign_id, ad_group_id, item_id, msku
    ) d ON d.store_id = ph.store_id AND d.campaign_id = ph.campaign_id
       AND d.ad_group_id = ph.ad_group_id AND d.rn = 1
    WHERE ${adsPhCond("ph")}
      AND NOT EXISTS (
        SELECT 1 FROM fact_ads_product_daily r
        WHERE NOT (${adsPhCond("r")})
          AND r.stat_date = ph.stat_date AND r.store_id = ph.store_id
          AND r.campaign_id = ph.campaign_id AND r.ad_group_id = ph.ad_group_id
      )
  )`;
}
