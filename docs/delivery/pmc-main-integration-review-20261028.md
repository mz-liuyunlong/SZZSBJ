> 历史记录，已被本日 PMC 范围整改取代。下文保留共享调度的结论已撤销，不代表当前实现或验收状态。当前证据见 [范围整改](pmc-scope-rectification-20261028.md)。

# PMC 与最新主线集成审查

基准 main：34f237a。仅在 develop 处理，不合并 PR、不部署、不执行生产迁移。

## 恢复与清理

- Vite 默认 API 代理恢复为 127.0.0.1:8010。
- 撤回任务中心全局导航强制指向采购专用帮助页；保留独立采购 SOP 文件。
- 注册采购父任务不再关闭旧来源 schedule_enabled 或清空 next_run_at。调度器仅在同账号父任务已启用且已开启调度时避免重复派发，不写坏旧配置；父任务未启用时旧任务继续执行。旧来源手动操作只在父任务启用时施加统一入口限制。
- 配置请求失败直接向上报错；dashboard 可回退到 runs，但两者都失败时抛错，不再把失败伪装成空数据。
- 844152e 已删除本分支缓存、截图、合并备份和个人计划；本轮不恢复这些文件。main 自带的 WFS 计划和广告历史备份不在本分支新增范围，保留以免删除他人交付。当前 PR 不新增运行缓存、日志或调试截图。

## 保留的共享变更与边界

| 文件或模块 | 必要性、影响与测试 |
|---|---|
| integration_sync execution、repository、pipeline | 采购父子运行复用现有治理、锁、重试和记录，不新增任务系统；处理按采购 handler/key 分支，商品、销售、广告、财务仍走各自路径；保留 main 的异常熔断和 WFS 等代码 |
| scheduler、service | 上述采购入口与防重复派发；注册不等于授权迁移调度。测试覆盖旧配置保留、父子派发及已有全量调度测试 |
| 任务中心 API、日志与配置 UI | 展示统一采购入口、3h 配置和阶段日志；失败需进入已有错误 UI，不能当空列表。保留商品依赖折叠，按账号隔离；新增双请求失败测试 |
| core/config 与 .env.example | 保留 PMC_DOMESTIC_PASSCODE_SHA256 的可选 SecretStr 配置与空示例；不保存实际散列或密钥，不改变其他字段。保留 main 的中央加密密钥配置与 Decodo 修复 |
| CI | 保留 develop push 触发，原 dev/main 和其他专项不删除；国内仓 job 加入草稿 PostgreSQL 验收，要求不允许 skip 冒充通过 |
| navigation | 撤回采购专用全局帮助覆盖；保留 main 导航功能 |

## 完整迁移分支与逐项 DDL

不修改既有迁移 ID 或 down_revision，不使用 stamp。

- main：0060 → 20261026_0061_wfs_fee_detection_evidence → 20261027_0062_sync_anomaly_center → 20261027_0063_ai_runtime → 20261027_0064_ai_runtime_skill_context → 20261028_0065_listing_evaluation_runs → 20261028_0066_walmart_monitor_listing_projection。
- PMC：20261022_0054_merge_walmart_identity_and_domestic_packing → 20261026_0055_purchase_board_draft_no。
- 20261027_0061_merge_purchase_main 合并采购 0055 和 20261026_0060_merge_listing_business_heads；无建表、改列、约束或索引 DDL。
- 20261028_0062_packing_pending_edit 依赖采购 merge 0061。
- 新增 20261028_0067_merge_pmc_main，两个父节点为打包 0062 和 main 0066；空 merge，无建表、改列、数据或索引写入。最终只有这一 head。

| 迁移 | 表、字段、约束、索引 |
|---|---|
| 采购 0055 | dwd_purchase_order_line_item.draft_no、dws_purchase_board.draft_no：各新增 nullable varchar(64)；无新索引、约束、回填或其他表变更 |
| 采购 merge 0061 | 只有版本图合并；不修改业务表 |
| 打包 0062 | 新表 ops_domestic_packing_pending_edits：candidate_id UUID 主键；source_account_ref varchar(128) 非空；base_candidate_version varchar(64) 非空；requested_qty integer 非空；customs varchar(16) 非空；edit_reason varchar(500) 可空；draft_snapshot_json JSONB 非空；actor_uid varchar(128) 非空；updated_at timestamptz 非空。CHECK requested_qty BETWEEN 1 AND 1000000；CHECK customs IN ('default','declare','skip')。非唯一 btree 索引 ix_ops_domestic_packing_pending_edits_source_account_ref(source_account_ref)。无外键或其他联合唯一约束 |
| merge 0067 | 只收拢两个分支；无业务 DDL |

以上三份 PMC 历史脚本本轮不改，main 已存在的 0061–0066 原样保留。数字重复不等于完整 revision ID 重复。

## 验收状态

本地迁移图与采购同步回归 36 passed；任务中心相关前端测试执行记录以最终报告为准。空库、既有 0049/0061 到当前 head 的真实 PostgreSQL 测试已随新 head 更新，必须由隔离 CI 实际执行。

本文件记录修复方案和范围，远端是否通过必须以本轮合并提交的 Actions 为准；旧 e010518 的通过不能代替本轮结果。生产库实时版本未查询，生产升级不在本次授权内。
