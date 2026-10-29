# 打包审批 GTIN 标签数据源决策

日期：2026-10-28。接口总体状态：READY_FOR_PRP。此状态只允许编写 PRP，不表示批准实现。

| 前置调查项 | 证据与结论 |
|---|---|
| 旧页面 | old-walmar-flie/features/pmc-domestic-warehouse/drafts/demo-v7.html 的 openLbl 打开 /labels/MSKU_GTIN14.pdf |
| 旧 API / 文件 | 无动态产品标签接口；labels/make_label.py、build_labels.py 预生成静态 PDF |
| 读取表 | 新系统 dim_walmart_listings；当前候选及待审批修改用于确定目标身份 |
| 表写入方 | integration_sync/data_pages_real_sync.py 写入维表，候选沿用现有发布和修改流程 |
| cron / 脚本 / 外部 API | 旧生成脚本读取 CSV 和 Demo JSON；新标签接口不触发同步或外部 API，调度频率不属于本任务 |
| 人工写库入口 | 标签能力无写库；用户仅通过已有修改流程改变目标身份 |
| 外部重新获取 | 不需要；使用既有同步维表，缺失时阻断并提示同步资料 |
| 少量配置数据 | 不用于替代商品身份；版式作为明确标签模板维护 |
| 短期策略 | 按候选当前目标身份读取唯一 Listing，校验版本及 GTIN 后生成 PDF |
| 长期策略 | 延续同一新系统身份来源；不维护平行商品主数据 |

分类：PDF 为 NEW_SYSTEM_OWNED 派生产物；Listing 复用既有同步维表，不新增同步或表。无 NEED_OWNER_DECISION 数据集。

字段血缘：候选 source_account_ref + store_id + item_id + sku 对应维表 source_account_ref + store_id + item_id + local_sku；输出 msku、gtin 来自唯一匹配的当前 Listing。不得由客户端自由传入条码内容覆盖身份。GTIN 保留字符串及前导零，格式和校验位失败均阻断。旧文件仅只读参考，退出条件为不建立运行依赖。

风险：本地存在并行未提交修改，实施前重读最新候选保存逻辑；刷新前后的身份可能变化，必须比较版本。历史审批标签、OWS 标签均不在本轮范围。
