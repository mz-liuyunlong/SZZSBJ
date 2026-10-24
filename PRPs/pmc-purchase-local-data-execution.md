# 采购看板本地数据导入执行记录（2026-10-20）

负责人授权将采购看板涉及的数据及依赖全部同步到本地，生产禁止写入。沿用 dev，不创建分支、不提交推送，不修改应用代码、表结构、.env 或服务配置。现有 PRP：pmc-purchase-board.md；数据源决策仍为 pmc-purchase-board-decision.md 的 REBUILD_SYNC，不改变生产来源权威。

## 来源和目标

来源是生产既有 primary 数据快照，经已验证 SSH 传输；源端 REPEATABLE READ、default_transaction_read_only=on、transaction_read_only=on，并核对身份指纹。最终快照时间 2026-10-20 18:21:30 Asia/Shanghai。目标严格限定 local 127.0.0.1:55432/szzsbj_dev/public，szzsbj_test 未写入，生产未写入或重启。没有重新采集领星：采购源数据最新观察时间 2026-10-17 18:00:43 Asia/Shanghai；SKU 当前资料是较新生产快照。

## 逐表结果

| 表 | 本轮导入源记录 | 导入后本地记录 | 用途 |
|---|---:|---:|---|
| `dwd_purchase_plan` | 1119 | 1119 | 采购计划与待采购下钻 |
| `dwd_purchase_order` | 784 | 784 | 采购单头 |
| `dwd_purchase_order_line_item` | 867 | 867 | 采购单明细×计划 |
| `dws_purchase_board` | 867 | 867 | 看板列表、汇总、详情 |
| `dws_purchase_sku_cycle` | 652 | 652 | 采购周期 |
| `dws_purchase_pending` | 709 | 711 | 待处理指标，非待采购计划API总数 |
| `rule_purchase_thresholds` | 1 | 1 | 既有版本阈值 |
| `ods_lingxing_purchase_plans` | 1861 | 1861 | 采购计划来源证据 |
| `ods_lingxing_purchase_orders` | 1399 | 1399 | 采购单来源证据 |
| `ods_lingxing_purchase_order_items` | 1519 | 1519 | 采购明细来源证据 |
| `ods_lingxing_receipt_orders` | 1263 | 1263 | 收货单头 |
| `ods_lingxing_receipt_order_items` | 1353 | 1353 | 收货明细 |
| `dim_lingxing_stores` | 9 | 9 | 店铺 |
| `dim_walmart_listings` | 3223 | 3223 | ItemID、Listing 归属 |
| `dwd_lingxing_sku_identity_index` | 1435 | 1435 | 有效 SKU 身份 |
| `dwd_lingxing_sku_product_info_current` | 1435 | 1435 | 负责人和默认采购交期 |
| `gov_integration_sync_runs` | 90 | 92 | 实际引用任务及父任务（71成功、19失败的历史记录） |
| `ods_api_raw_request_refs` | 311 | 322 | 实际引用的请求元数据 |
| `products` | 1301 | 1301 | SKU 关联产品父记录 |
| `dwd_lingxing_sku_product_info_snapshots` | 1435 | 1435 | 当前资料引用快照 |
| `gov_data_lineage` | 11600 | 14437 | 相关当前记录每条最新血缘证据 |
| `gov_integration_sync_configs` | 5 | 10 | 来源配置，全部关闭、无定时 |
| `gov_integration_interfaces` | 5 | 10 | 来源接口登记，outbound_enabled=false |
| `ods_api_raw_blobs` | 311 | 322 | 实际引用的原始响应 |
| `gov_integration_sync_run_work_items` | 311 | 322 | 实际引用的任务项 |
| `gov_parse_jobs` | 311 | 311 | 实际引用的解析记录 |
| `gov_raw_retention_policies` | 4 | 9 | 原始响应留存规则 |
| `manual_purchase_cycle_override` | 0 | 0 | 源端无人工覆盖，不造数据 |

治理表保留国内仓原有行，所以总数大于源导入数；仅复制看板业务依赖及每条相关记录最新血缘，不复制同一任务的无关 RAW、所有历史重复血缘、事件、锁、调度状态或认证会话。全部业务种子取 primary 的生产现有完整范围，未套用国内仓30天限制。

## 写入和回滚边界

先完整备份本地 custom-format dump 并通过 pg_restore --list 校验。业务记录为空时才允许首次导入；27张非空源表按外键依赖排序、任务父子排序，在一个本地事务中导入，保持 FK 和检查约束开启。使用原始 JSON 文本和 PostgreSQL numeric 语义，避免金额经浮点序列化。导入参数逐批与存储值比对通过。

本地默认规则与源规则自然键 rule_key+version 相同、ID 不同；保留本地种子 ID，复制源字段（业务阈值一致，批准时间对齐来源）。其余源 ID 保留。现有共享治理行不覆盖，发现差异即拒绝。导入接口关闭 outbound_enabled，配置关闭 is_enabled、schedule_enabled、schedule_cron、next_run_at；原国内仓治理配置也保持关闭。所有导入表均无 serial/identity 序列需要校准。

导入后仅使用现有 PmcPurchaseDwsRefresher 在本地按 2026-10-20 重算 DWS；未调用供应商，规则不变。列表867、周期652；待处理709→711是日期重算结果。阶段 S0=9、S3=92、S9=766。源采集时间与 calculated_at 严格区分。首次重算已提交，随后的证据查询误用 observed_at 列失败；改为 source_observed_at 后只读验证通过，没有重复重算。

原国内仓 MART1454行、IAM用户29人保持；不迁移用户会话，不修改登录、权限或来源范围。数据库写入不涉及 Alembic 迁移。

备份仅存本地 Codex artifact，包含本地敏感数据，不放 Git、不上传。回滚需要独立确认受影响的后续本地工作，再使用导入前备份恢复到本地；不得向生产恢复。

## 验证

真实本地数据库、只读事务、测试进程合成鉴权/primary scope 下，列表867行/每页50、汇总、采购详情、带收货记录的详情、SKU周期、待采购计划196条、产品管理负责人17项接口均200。店铺、负责人筛选验证有匹配记录且结果归属一致。DWS待处理711与待采购计划196为不同数据口径。国内仓选项顺带恢复为9店铺、12负责人。

匿名接口仍401。没有使用真人密码或生产会话，不把合成鉴权测试当成已登录浏览器验收。前端按已有接口读取本地库，正常登录后刷新 /pmc/purchase-board 验收。

Navicat脚本：docs/delivery/local-purchase-import-verification.sql，7条SQL已在本地只读事务真实运行通过；先选择szzsbj_dev。脚本仅展示本地业务明细，不读取密码哈希、Token。

前期导出因同批历史日志超出预算中止，未产生数据库写入；最终改为记录实际引用依赖和最新血缘后完整成功。原始业务快照及备份只在 Git 外 artifact，不写代码仓库。

备份：1360920字节，SHA256 `38ec811eebce51dc02c3b12f9de385193a5ff8e5ab5823d13489e2dd49e667ed`；源压缩快照SHA256 `2db3f866c863232f58f3d0a98d693c123bb48925ad9561fdca69a03074b325fd`。详细安全证据在 purchase-local-import-20261020 的 import-evidence.json、refresh-evidence.json、route-evidence.json。
