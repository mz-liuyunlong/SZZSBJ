# 新品表现 WFS 首次可售日期筛选

状态：本地实现候选；待完整编译、真实数据验收与 PR 审查。

既有 GET `/api/new-products/summary` 和 `/api/new-products/listings` 新增两个可选日期参数：

- `first_wfs_start_date`：YYYY-MM-DD，LA 业务日期，含起始日。
- `first_wfs_end_date`：YYYY-MM-DD，LA 业务日期，含结束日。

必须同时提供或同时省略；不完整、倒序或无效日期返回 422。省略时保持原有查询范围，包含首次可售日期未知的商品；指定日期时排除未知日期，不用上架、首单等日期代替。

数据源：复用 `performance_list_scope.scoped_projection` 的既有授权账号、Listing 小批量测品范围、按账号/店铺/Item ID 精确匹配的 `biz_new_product_performance_current.first_wfs_available_date_la`，缺失时使用 `listing_wfs_first_stock_la_locked.first_wfs_available_date_la`。口径与现有新品分析看板一致。列表在分页前筛选完整身份集合，统计卡及状态、负责人、评级选项基于同一日期范围。保留原有数据权限、统计定义、评分、利润计算和审批语义。无表、迁移、外部调用、定时任务或数据写入；保留旧客户端无日期时的行为。

本次仅新增新品表现明细筛选，原有分析看板与 CSV 导出范围不变。
