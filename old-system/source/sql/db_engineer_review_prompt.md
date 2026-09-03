# 数据库 Schema 审核请求

## 背景

我们运营一个 Walmart 跨境电商数据仓库，MySQL 8.0，现有广告相关事实表：

- `fact_ads_product_daily`：商品/ITEMID 维度广告数据
- `fact_ads_keyword_daily`：关键词/搜索词维度广告数据

现在需要新接入领星 ERP 的两个 Walmart SP 广告 API，补充两个新维度：

1. **平台维度**（Desktop vs Mobile）：`/basicOpen/multiplatform/ads/reportPlatformSpList`
2. **页面类型维度**：`/basicOpen/multiplatform/ads/queryPageTypeSPList`

这两个维度与现有表不重叠，**不能塞进现有表**（会导致字段为空、唯一键混乱、聚合重复计数）。

---

## 现有表结构（参考）

```sql
-- 商品维度（已有）
CREATE TABLE `fact_ads_product_daily` (
  `id`            BIGINT        NOT NULL AUTO_INCREMENT,
  `stat_date`     DATE          NOT NULL,
  `platform`      VARCHAR(64)   NOT NULL DEFAULT 'walmart',
  `store_id`      VARCHAR(64)   NOT NULL,
  `store_name`    VARCHAR(255),
  `advertiser_id` VARCHAR(64)   NOT NULL,
  `campaign_id`   VARCHAR(64)   NOT NULL,
  `campaign_name` VARCHAR(255),
  `campaign_type` VARCHAR(128),
  `ad_group_id`   VARCHAR(64)   NOT NULL,
  `ad_group_name` VARCHAR(255),
  `item_id`       VARCHAR(64)   NOT NULL,
  `msku`          VARCHAR(128),
  `impressions`   INT           NOT NULL DEFAULT 0,
  `clicks`        INT           NOT NULL DEFAULT 0,
  `ctr`           DECIMAL(18,6),
  `ad_spend`      DECIMAL(18,4) NOT NULL DEFAULT 0,
  `orders`        INT           NOT NULL DEFAULT 0,
  `total_sales`   DECIMAL(18,4) NOT NULL DEFAULT 0,
  `acos`          DECIMAL(18,6),
  `cpc`           DECIMAL(18,6),
  `cvr`           DECIMAL(18,6),
  `roas`          DECIMAL(18,6),
  `source_system` VARCHAR(64)   NOT NULL DEFAULT 'lingxing',
  `source_raw_id` BIGINT,
  `extra_json`    JSON,
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fact_ads_product` (`stat_date`, `platform`, `advertiser_id`, `campaign_id`, `ad_group_id`, `item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 新增表设计（待审核）

```sql
-- ── 表1：SP广告-平台维度 ──────────────────────────────────────
-- 来源 API：/basicOpen/multiplatform/ads/reportPlatformSpList
-- 粒度：stat_date + store_id + advertiser_id + campaign_id + ad_group_id + ad_platform
-- 注：ad_platform = Desktop / Mobile（与现有 platform 字段含义不同，platform 固定为 walmart）

CREATE TABLE IF NOT EXISTS `fact_ads_platform_daily` (
  `id`                   BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_date`            DATE          NOT NULL                COMMENT '统计日期',
  `platform`             VARCHAR(64)   NOT NULL DEFAULT 'walmart' COMMENT '电商平台，固定值 walmart',
  `store_id`             VARCHAR(64)   NOT NULL                COMMENT '店铺ID（映射自 dim_store）',
  `store_name`           VARCHAR(255)                          COMMENT '店铺名称（冗余）',
  `advertiser_id`        VARCHAR(64)   NOT NULL                COMMENT '广告主ID',
  `advertiser_name`      VARCHAR(255)                          COMMENT '广告主名称',
  `campaign_id`          VARCHAR(64)   NOT NULL                COMMENT '广告活动ID',
  `campaign_name`        VARCHAR(255)                          COMMENT '广告活动名称',
  `campaign_status`      VARCHAR(64)                           COMMENT '活动状态: enabled/paused/live/completed等',
  `campaign_type`        VARCHAR(64)                           COMMENT '广告类型: sponsoredProducts/sba/video',
  `ad_group_id`          VARCHAR(64)   NOT NULL                COMMENT '广告组ID',
  `ad_group_name`        VARCHAR(255)                          COMMENT '广告组名称',
  `ad_platform`          VARCHAR(64)   NOT NULL                COMMENT '投放平台: Desktop / Mobile',
  `bid`                  DECIMAL(18,4)                         COMMENT '当前竞价 ($)',
  `impressions`          INT           NOT NULL DEFAULT 0      COMMENT '曝光量',
  `clicks`               INT           NOT NULL DEFAULT 0      COMMENT '点击量',
  `ad_spend`             DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '广告花费 ($)',
  `attributed_orders`    INT           NOT NULL DEFAULT 0      COMMENT '归因广告订单数',
  `attributed_sales`     DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '归因广告销售额 ($)',
  `attributed_units`     INT           NOT NULL DEFAULT 0      COMMENT '归因广告销量',
  `advertised_sku_sales` DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '直接归因销售额 ($)',
  `advertised_sku_units` INT           NOT NULL DEFAULT 0      COMMENT '直接归因销量',
  `other_sku_sales`      DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '间接/关联销售额 ($)',
  `other_sku_units`      INT           NOT NULL DEFAULT 0      COMMENT '间接/关联销量',
  `ctr`                  DECIMAL(18,6)                         COMMENT '点击率 CTR (%)',
  `cpc`                  DECIMAL(18,6)                         COMMENT '点击成本 CPC ($)',
  `cvr`                  DECIMAL(18,6)                         COMMENT '转化率 CVR (%)',
  `acos`                 DECIMAL(18,6)                         COMMENT 'ACoS (%)',
  `roas`                 DECIMAL(18,6)                         COMMENT 'RoAS',
  `aov`                  DECIMAL(18,4)                         COMMENT '平均订单值 AOV ($)',
  `cpa`                  DECIMAL(18,4)                         COMMENT '平均订单成本 CPA ($)',
  `ntb_orders`           INT           NOT NULL DEFAULT 0      COMMENT '品牌新买家订单数',
  `ntb_revenue`          DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '品牌新买家销售额 ($)',
  `ntb_units`            INT           NOT NULL DEFAULT 0      COMMENT '品牌新买家销量',
  `ntb_order_rate`       DECIMAL(18,6)                         COMMENT '品牌新买家订单转化率 (%)',
  `ntb_orders_pct`       DECIMAL(18,6)                         COMMENT '新买家订单占比 (%)',
  `ntb_revenue_pct`      DECIMAL(18,6)                         COMMENT '新买家销售额占比 (%)',
  `ntb_units_pct`        DECIMAL(18,6)                         COMMENT '新买家销量占比 (%)',
  `source_system`        VARCHAR(64)   NOT NULL DEFAULT 'lingxing',
  `source_raw_id`        BIGINT                                COMMENT 'RAW层ID (raw_lingxing_api.id)',
  `extra_json`           JSON                                  COMMENT '扩展字段（含 inStore* 实体店低频数据）',
  `created_at`           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ads_platform` (`stat_date`, `store_id`, `advertiser_id`, `campaign_id`, `ad_group_id`, `ad_platform`),
  KEY `idx_stat_date`   (`stat_date`),
  KEY `idx_store_date`  (`store_id`, `stat_date`),
  KEY `idx_campaign`    (`campaign_id`, `stat_date`),
  KEY `idx_ad_platform` (`ad_platform`, `stat_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='FACT层: SP广告-平台维度 | reportPlatformSpList | 粒度: 日+店铺+活动+广告组+Desktop/Mobile';


-- ── 表2：SP广告-页面类型维度 ─────────────────────────────────
-- 来源 API：/basicOpen/multiplatform/ads/queryPageTypeSPList
-- ⚠️ 以下字段是否实际返回尚未 probe 确认：advertiser_id、campaign_id、ad_group_id
-- ⚠️ page_type 的枚举值尚未确认
-- 粒度初版：stat_date + store_id + campaign_id + ad_group_id + page_type
--   若 probe 确认无 campaign_id/ad_group_id，唯一键改为：stat_date + store_id + page_type

CREATE TABLE IF NOT EXISTS `fact_ads_page_type_daily` (
  `id`                   BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_date`            DATE          NOT NULL                COMMENT '统计日期',
  `platform`             VARCHAR(64)   NOT NULL DEFAULT 'walmart' COMMENT '电商平台，固定值 walmart',
  `store_id`             VARCHAR(64)   NOT NULL                COMMENT '店铺ID',
  `store_name`           VARCHAR(255)                          COMMENT '店铺名称（冗余）',
  `advertiser_id`        VARCHAR(64)                           COMMENT '广告主ID（⚠️ 待probe确认）',
  `campaign_id`          VARCHAR(64)                           COMMENT '广告活动ID（⚠️ 待probe确认）',
  `campaign_name`        VARCHAR(255)                          COMMENT '广告活动名称',
  `ad_group_id`          VARCHAR(64)                           COMMENT '广告组ID（⚠️ 待probe确认）',
  `page_type`            VARCHAR(128)  NOT NULL                COMMENT '页面类型（⚠️ 枚举值待probe确认）',
  `impressions`          INT           NOT NULL DEFAULT 0      COMMENT '曝光量',
  `clicks`               INT           NOT NULL DEFAULT 0      COMMENT '点击量',
  `ad_spend`             DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '广告花费 ($)',
  `attributed_orders`    INT           NOT NULL DEFAULT 0      COMMENT '归因广告订单数',
  `attributed_sales`     DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '归因广告销售额 ($)',
  `attributed_units`     INT           NOT NULL DEFAULT 0      COMMENT '归因广告销量',
  `advertised_sku_sales` DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '直接归因销售额 ($)',
  `advertised_sku_units` INT           NOT NULL DEFAULT 0      COMMENT '直接归因销量',
  `other_sku_sales`      DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '间接/关联销售额 ($)',
  `other_sku_units`      INT           NOT NULL DEFAULT 0      COMMENT '间接/关联销量',
  `ctr`                  DECIMAL(18,6)                         COMMENT '点击率 CTR (%)',
  `cpc`                  DECIMAL(18,6)                         COMMENT '点击成本 CPC ($)',
  `cvr`                  DECIMAL(18,6)                         COMMENT '转化率 CVR (%)',
  `acos`                 DECIMAL(18,6)                         COMMENT 'ACoS (%)',
  `roas`                 DECIMAL(18,6)                         COMMENT 'RoAS',
  `aov`                  DECIMAL(18,4)                         COMMENT '平均订单值 AOV ($)',
  `cpa`                  DECIMAL(18,4)                         COMMENT '平均订单成本 CPA ($)',
  `ntb_orders`           INT           NOT NULL DEFAULT 0      COMMENT '品牌新买家订单数',
  `ntb_revenue`          DECIMAL(18,4) NOT NULL DEFAULT 0      COMMENT '品牌新买家销售额 ($)',
  `ntb_units`            INT           NOT NULL DEFAULT 0      COMMENT '品牌新买家销量',
  `ntb_order_rate`       DECIMAL(18,6)                         COMMENT '品牌新买家订单转化率 (%)',
  `ntb_orders_pct`       DECIMAL(18,6)                         COMMENT '新买家订单占比 (%)',
  `ntb_revenue_pct`      DECIMAL(18,6)                         COMMENT '新买家销售额占比 (%)',
  `ntb_units_pct`        DECIMAL(18,6)                         COMMENT '新买家销量占比 (%)',
  `source_system`        VARCHAR(64)   NOT NULL DEFAULT 'lingxing',
  `source_raw_id`        BIGINT                                COMMENT 'RAW层ID (raw_lingxing_api.id)',
  `extra_json`           JSON                                  COMMENT '扩展字段（probe后按需提升为正式列）',
  `created_at`           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ads_page_type` (`stat_date`, `store_id`, `campaign_id`, `ad_group_id`, `page_type`),
  KEY `idx_stat_date`  (`stat_date`),
  KEY `idx_store_date` (`store_id`, `stat_date`),
  KEY `idx_page_type`  (`page_type`, `stat_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='FACT层: SP广告-页面类型维度 | queryPageTypeSPList | ⚠️ 粒度/唯一键待probe后最终定稿';
```

---

## 请工程师重点审核

**1. 字段类型是否合理？**
- 指标字段（ctr/cvr/acos等）用 `DECIMAL(18,6)` 存百分比原始值（如 2.45 代表 2.45%），是否应改为小数（0.0245）？
- `impressions`、`clicks`、`orders` 用 `INT`，是否有超出范围的风险（单广告组单日超 21亿）？

**2. 唯一键设计是否正确？**
- `fact_ads_platform_daily` 的 UNIQUE KEY 是否完整：`stat_date + store_id + advertiser_id + campaign_id + ad_group_id + ad_platform`？
- `fact_ads_page_type_daily` 的唯一键含可 NULL 字段（`campaign_id`、`ad_group_id`），MySQL 中 NULL 不参与唯一约束，这种设计是否有重复插入风险？

**3. 索引是否够用？**
- 预期查询模式：按 `stat_date` 范围、按 `store_id + stat_date`、按 `campaign_id`
- 现有索引是否覆盖主要查询路径？

**4. `extra_json` 策略是否合理？**
- `fact_ads_platform_daily` 的 `inStore*` 系列字段（实体店归因数据，当前业务不使用）放入 `extra_json`，是否同意此决策？

**5. `fact_ads_page_type_daily` 的待确认项**
- `advertiser_id`、`campaign_id`、`ad_group_id` 设为可 NULL，待实际 probe API 后确认
- 若 probe 确认这三个字段不返回，建议唯一键简化为 `stat_date + store_id + page_type`，是否同意？

**6. 其他建议？**
- 命名规范、字符集、存储引擎等是否有问题？
- 是否需要分区（按月/按年）？当前预估单表日增约 数千行，暂不分区是否合理？
