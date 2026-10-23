# 国内仓筛选选项数据源决策

日期：2026-10-19。接口总体状态：READY_FOR_PRP。NEED_OWNER_DECISION：无。
批准证据：负责人确认已审阅的 domestic-warehouse-filter-options-plan.md 范围，回复“同意补齐后端，按当前产品负责人”。批准仅覆盖本地代码实现和合成测试；不授权生产连接、真实同步或部署。

## 前置调查

完整证据见 docs/frontend/domestic-warehouse-filter-options-plan.md 的兼容问题和调查表。旧页面、旧API、旧文件和人工写库不适用：本次只增强新系统已存在页面，不读旧系统。既有参考为 Listing 的 filter-options 和采购看板的产品负责人选项；前者按名称作 value，不直接复用其契约。
既有写入方为国内仓发布链路、店铺同步 data_pages_real_sync 和 SKU 详情同步链路；不改变其脚本、定时任务或外部 API。少量配置名单不适用，不以静态配置替代业务主数据。外部重新获取由既有同步负责，页面不直接拉取领星。

## 最终结论与血缘

| 数据集 | 策略/层 | 权威来源及变换 | 消费 |
|---|---|---|---|
| 可见批次及店铺ID | REBUILD_SYNC（复用既有同步）/ 既有DWD | dwd_domestic_receipt_batch + dwd_domestic_receipt_batch_link，同账号关联 | options.stores.value及store_id筛选 |
| 店铺名称 | REBUILD_SYNC（复用既有同步）/ 既有DIM | dim_lingxing_stores，source_account_ref + store_id；名称歧义或缺失返回ID | options.stores.label |
| 当前负责人 | REBUILD_SYNC（复用既有同步）/ 既有DWD | dwd_lingxing_sku_identity_index + dwd_lingxing_sku_product_info_current，同账号+SKU，identity_id/provider/account一致，active身份唯一，非空UID；多身份不猜归属 | options.owners及owner_uid筛选 |

短期和长期均复用已落库来源；不建表、不读ODS/RAW/旧库、不新增同步；无旧库退出步骤。API 权限沿用 pmc:domestic-batch:read 与当前页面策略，全部查询按 trusted source-account scope 限制。姓名不是身份；UID、store_id 均保留字符串，名称仅展示。选项只覆盖可见批次，不局限沃尔玛。筛选为当前负责人，不能表达收货时历史归属。
同SKU多身份、负责人缺失、店铺名歧义必须保留为未知，不用任意 max 值做业务决定。跨账号相同ID按既有列表的ID筛选语义一起匹配，但不任意选取冲突名称。选项无虚构数量，无统一快照时间承诺。缺表/服务异常按统一错误处理，不回退旧源或硬编码。

字段契约：stores/owners 为 {value:string,label:string}[]；value分别为来源store_id、owner_uid；label来自唯一名称或ID；不改原始来源、不做数字转换、不改时间口径。meta.source_objects列明实际依赖。只读接口无Celery、无业务审计写入，沿用请求追踪。
