# 0103 新品管理 Listing 独立首批采购

状态：负责人已在 2026-11-28 对话确认方案一及固定当前店铺，并授权代码实现；本地验收候选。数据源决策见 docs/data-sources/decisions/sku-progress-listing-purchase-0103-decision.md。新增0103迁移接在 `20261128_0102_woocommerce_store_config` 后，并更新单 head 测试；不改 WooCommerce 迁移本身。仅新增迁移和新品域现有查询、采购、适配器及页面的定向改动，不改0100、不改负责人、上架筛选、统计卡、请求机制、PMC 公共代码、审批工作台、全局 CSS、运行环境或生产配置。

目标：同 SKU/店铺的两个 Listing 各20件；独立采购计划/采购进度/国内发货展示，独立勾选与当前行确认，ID/MSKU 左对齐；基础信息与推进状态继续 SKU 合并。迁移先验证旧事件证据，无法归属的旧记录保持 NULL 并阻止重复采购。新唯一索引按 SKU 业务记录+店铺+Item ID；NOT VALID identity check 禁止新 NULL 写入但保留历史未知；非空表拒绝降级。保留 store 事务锁以及全部真实写门禁。批量每 Listing 单独回执，不重试未知结果。无真实国内发货证据继续待确认。使用既有 Shared ReportFacetSelect、ReportTableShell、WalmartProductIdCell、CopyableTextCell 与 Ant 表单；仅本页局部 CSS 修正，不新增 Shared。

验收：同店不同 Item ID 不互相阻塞；相同 Item ID 不重复发送；旧 NULL claim 阻塞该 SKU/店铺；未知结果不重试；固定20、真实身份、等级风险及权限不降级；不同 Listing 状态独立，筛选按 SKU 去重；负责人和外置上架筛选不变。新增迁移需要单独授权的实际执行；源码安装不连接任何 DB。完整 PostgreSQL 集成验证、CI、页面验收仍需进行。
