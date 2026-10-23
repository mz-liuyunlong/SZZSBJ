# 入库批次店铺、负责人选项数据源决策

2026-10-20；总体状态 READY_FOR_PRP；范围：店铺、当前产品负责人。负责人要求参考产品管理、销售、采购现有选项实现；继续此前授权 dev，不建分支、不提交。本决策是原 pmc-domestic-filter-options-decision.md 在入库 MART 上的衔接，不改原收货接口。

## 调查

| 调查项 | 证据和结论 |
|---|---|
| 旧页面 | 提供的截图：店铺选项空、负责人及状态禁用；新页面 DomesticWarehousePage.tsx 传 storeOptions=[] |
| 旧 API / 文件 | pmc_domestic/router.py filter-options；repository.py 查询 DWD 收货表。旧收货表无本次入库数据，不能直接换 URL 沿用 |
| 读取表 | 当前版本 mart_domestic_inbound_batch_board + gov_domestic_board_publications；名称 dim_lingxing_stores；负责人 dwd_lingxing_sku_identity_index + dwd_lingxing_sku_product_info_current |
| 表写入方 | 入库 publisher；既有 data_pages 店铺同步与 SKU detail 同步，均不在本次改动 |
| 脚本 / 外部 API / cron | 复用既有同步结果；本次 GET 不调领星、不新增定时 |
| 人工写库入口 | 不适用，无人工补写选项 |
| 外部重新获取 | 可由现有同步负责，不在页面按请求实时拉取 |
| 少量配置 | 业务身份不能硬编码；状态枚举是能力声明，不是业务事实 |
| 短期 / 长期 | REBUILD_SYNC：复用已落库当前版本和现有 DIM/DWD；旧系统仅只读参考，不作在线回退 |

## 契约及边界

GET /api/pmc/domestic/inbound-batches/filter-options，可重复 warehouse_id <=50；返回 stores/owners 的 {value,label}、statuses 的 {value,label,disabled,reason}，owner_basis=current_product_owner；统一 envelope 和 InboundMeta。选项覆盖权限账号和仓库内全部当前版本行，不受页码、所选店铺、负责人、搜索约束。名称缺失或冲突用 ID，不取任意名称；多人同名保留各 UID。SKU 身份须 active 唯一，身份 account/provider/id 完全匹配，沿用旧接口安全逻辑。

列表与汇总新增 owner_uid 重复参数 <=50，账号+SKU EXISTS 关联；OR 同字段、AND 跨字段，不增加主表行数。负责人为现在的产品负责人，非入库时历史负责人；选项接口采集时间指批次来源采集时间，不能表示主数据同一快照。metadata列明 DIM/DWD 依赖。

权限沿用 pmc:domestic-batch:read 及已有页面策略/可信账号范围，不跨调需要额外权限的产品/销售接口，不改权限模型；GET 无业务写入、无 Celery。无 migration、无生产连接。

业务状态独立：用户已明确六种业务状态，并答复“没有，按交接文档补做后端数据方案”。当前无打包/发货业务源，不实现伪筛选；六项返回 disabled=true/reason。状态数据建设另见 PRPs/pmc-domestic-business-status.md（候选，待审批），不阻塞店铺/负责人实现。
