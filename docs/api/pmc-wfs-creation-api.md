# PMC WFS 创建货件接口（提交 Walmart）

前缀：`/api/pmc/wfs/pending-packing`。所有写操作都要求人工书面批准；Walmart 只经统一 Walmart 网关（每店云函数 + 写入台账 + 审计表）访问，后端不读取任何 Walmart 凭证。

## 上线开关 `WFS_CREATION_MODE`

| 值 | 效果 |
|---|---|
| `off`（默认） | 不调用 Walmart，提交创建直接拒绝，不占箱子 |
| `probe` | 只允许探测（只读查询近 7 天货件）和分仓预览，不建货件 |
| `single` | 允许创建，每次只能 1 个计划货件（第一次真实测试） |
| `batch` | 允许创建，不限票数 |

非 local / test 环境只有 `single` / `batch` 才允许写库（`creation_service.guard_write`）。

## 接口

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/capabilities` | 登录 | `creation_enabled` / `preview_enabled` / `mode` / `reason` |
| GET | `/creation-defaults?source_account_ref=` | create | WFS 设置 · 创建默认值，附默认预计到仓日期（今天 + 发货日偏移天数，北京时间） |
| POST | `/creation-probe?store_id=` | preview | 只读探测：用该店铺的通道查近 7 天货件，返回状态码和条数 |
| POST | `/allocation-preview` | create | 核对分箱（不变） |
| POST | `/creation-operations` | create | 提交：自动检查 + 占用箱子，状态「待人工批准」。`expected_delivery_at` 可不填，按创建默认值 |
| POST | `/creation-operations/{id}/approve` | approve | 书面批准后排队提交 Walmart |
| POST | `/creation-operations/{id}/reconcile` | reconcile | 立即用我方单号查一次 Walmart |
| POST | `/creation-operations/{id}/retry` | approve | 仅失败的票：重新占箱 → 先查 Walmart → 没有才按同一单号重发 |
| POST | `/creation-operations/{id}/labels/retry` | label-retry | 补取箱唛 |
| GET | `/creation-operations?order_id=` / `/{id}` | 登录 | 记录；每票含 `error_message`、`submissions`、`polls` / `max_polls` / `next_poll_at`、货件 `fc` |
| GET | `/creation-tickets?tab=submitting\|failed\|created&store_id=&keyword=&page=&page_size=` | 登录 | 待创建货件的 提交中 / 创建失败 / 已创建未发货 页签，一行一票 |
| GET | `/creation-ticket-counts?store_id=&keyword=` | 登录 | 三个页签的票数 |
| GET | `/store-creation-defaults` | 登录 | 创建默认值（按店铺）：每店一行，`level` = store / account / default |
| PUT | `/store-creation-defaults/{store_id}` | settings manage | 保存某店铺的创建默认值（运输方式、发货日偏移、托盘 / 混装箱数、承运人、ITS、退货地址），记入设置变更 |

`/creation-defaults` 另收 `store_id`：店铺行 → 账号行 → 8088 默认值；创建弹窗据此带出，弹窗里改的值只用于那一次。
`/orders?arrangement=open` = 打包完成且还有箱子没建货件（待创建页签默认）。

## 任务中心「WFS 创建结果拉取」

提交 Walmart、每 3 分钟查结果、重试都由 数据中心 → 任务中心 的「WFS 创建结果拉取」执行（provider `walmart`，interface_key `wfsCreationResultPoll`，cron `*/3 * * * *`），WFS 没有自己的定时器或 Celery 任务。

- 每次运行处理该账号下：已批准待执行的票 → 提交；提交中且到了查询时间的票 → 用单号查一次；结果待核实的票 → 查一次；页面点了核实结果 / 补取箱唛的票 → 处理一次。每个操作一条运行明细。
- 批准、重试、核实结果、补取箱唛会立即建一次手动运行；任务没注册或被关掉时记一条 `waiting_task_center` 事件，等下一次定时运行。
- 注册：`PMC_WFS_CREATION_TASK_BOOTSTRAP_AUTHORIZED=true PMC_WFS_SOURCE_ACCOUNT_REF=<账号> python scripts/bootstrap_pmc_wfs_creation_task.py`（自动同步默认关，由管理员在任务中心打开）。

## 状态（每个计划货件 = 一票 = 一个 Walmart inbound order，单号 = 票 id）

- `QUEUED` 已批准待执行 → `RUNNING` 提交中。
- Walmart 返回货件 → `SUCCEEDED`，随后取箱唛（箱数按 Walmart 返回的件数 / 箱规，单货件时按本票箱数；混装箱数取创建默认值）。
- Walmart 明确拒绝（4xx）或请求根本没发出 → `FAILED`，`error_message` 为原因，箱子释放。
- 超时、5xx、没有返回货件号 → 保持 `RUNNING`，每 3 分钟用单号查一次，最多 10 次；查到即成功，10 次仍查不到 → `FAILED`（`WFS_RESULT_TIMEOUT`），箱子释放。
- 操作汇总：全部成功 `SUCCEEDED`；有票提交中 `RUNNING`；部分成功其余失败 `PARTIAL`；全部失败 `FAILED`。

## 防重复

1. 前端每次提交带幂等 key；同 key 重放返回原记录，同 key 改内容拒绝。
2. 提交时按 key 和账号加库锁；箱子写入占用表（同一箱同版本只能被占一次）。
3. 必须人工批准才会调用 Walmart。
4. 写入台账以 `create:<票 id>` 为键：上一次结果不明时拒绝再次 POST，只能先查；已成功的键永远不再 POST。
5. 提交中（有票 `RUNNING` / `QUEUED`）时重试接口返回 409 `WFS_SUBMITTING`。
6. 重试先用同一单号查 Walmart，查到就直接记成功；Walmart 端对同一 inboundOrderId 也不会建第二单。

## 服务器配置（只列名字）

- `WFS_CREATION_MODE`（新增）。
- 复用统一 Walmart 网关现有变量：店铺映射 `…_WALMART_SCF_STORE_ID_MAP`、`…_CVM_ROLE`、`…_TARGET_ROLE_ARN`、`…_PROTOCOL`；协议 1 时还需 `…_APPROVED_WRITE_KEYS` 含 `wfs_inbound_shipment_create, wfs_shipment_label, wfs_inbound_preview`，`…_APPROVED_READ_KEYS` 含 `inbound_shipments`；审计 outbox 目录 `…_WALMART_AUDIT_OUTBOX_DIR`。
- 每店云函数须以读写模式部署（`owner-approved-read-write`）。
- Celery worker 照常消费 `integration` 队列（任务中心的 `integration_sync.execute_sync_run` 执行本任务）。
