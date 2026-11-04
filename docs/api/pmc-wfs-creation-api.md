# PMC WFS 创建货件接口（提交 Walmart）

前缀：`/api/pmc/wfs/pending-packing`。「确认创建」即发出（Rocky 2026-11-04 取消单独的「待批准」：点确认的人就是批准人，批准记录 `confirm:<幂等键>`）；Walmart 只经统一 Walmart 网关（每店云函数 + 写入台账 + 审计表）访问，后端不读取任何 Walmart 凭证。

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
| GET | `/capabilities` | 登录 | `creation_enabled` / `preview_enabled` / `mode` / `reason` / `simulator`（本机模拟通道，只在 APP_ENV=local） |
| GET | `/creation-defaults?source_account_ref=` | create | WFS 设置 · 创建默认值，附默认预计到仓日期（今天 + 发货日偏移天数，北京时间） |
| POST | `/creation-probe?store_id=` | preview | 只读探测：用该店铺的通道查近 7 天货件，返回状态码和条数；再用一个不存在的单号查一次，要返回"查无此单"（8088 是 204，`lookup_not_found_ok=true`），首次提交前的查单靠它 |
| POST | `/allocation-preview` | create | 核对分箱（不变） |
| POST | `/creation-operations` | create | 确认创建：自动检查 + 占用箱子 + 生成单号，然后直接提交 Walmart（同一个幂等键重放返回原记录，不会再发一次）。`expected_delivery_at` 可不填，按创建默认值 |
| POST | `/creation-operations/{id}/approve` | create | 只给取消「待批准」之前留下的旧记录用：发出 |
| POST | `/creation-operations/{id}/reconcile` | reconcile | 立即用我方单号查一次 Walmart |
| POST | `/creation-operations/{id}/retry` | create | 仅失败的票：重新占箱 → 先查 Walmart → 没有才按同一单号重发 |
| POST | `/creation-operations/{id}/labels/retry` | label-retry | 补取箱唛 |
| POST | `/creation-operations/{id}/labels/{shipment_id}/print` | 登录 | 「打印箱唛」：返回 PDF（`application/octet-stream`，和下载箱唛一样），并给这个货件记一次打印（`labels[货件号].prints` 加 1，`printed_at` / `printed_by`，事件 `label_printed`）；不调用 Walmart |
| GET | `/rows?status=&show_shipped=&store_id=&keyword=&only_test=&completed_from=&completed_to=&page=&page_size=` | 登录 | 单列表（见下）|
| POST | `/simulator/pull` | reconcile | 只在本机模拟模式存在（别处 404）：标记所有提交中的票，每个账号立即跑一次「WFS 创建结果拉取」 |
| GET | `/creation-operations?order_id=` / `/{id}` | 登录 | 记录；每票含 `error_message`、`submissions`、`polls` / `max_polls` / `next_poll_at`、货件 `fc` |
| GET | `/creation-tickets?tab=submitting\|failed\|created&store_id=&keyword=&page=&page_size=` | 登录 | 待创建货件的 提交中 / 创建失败 / 已创建未发货 页签，一行一票 |
| GET | `/creation-ticket-counts?store_id=&keyword=` | 登录 | 三个页签的票数 |
| GET | `/store-creation-defaults` | 登录 | 创建默认值（只在待创建货件的抽屉里设置）：`common` = 「全部店铺通用」（每个来源账号一行，store_id = `*`），`items` = 每店一行；`level` = store（本店铺）/ common（沿用通用）/ account（旧账号行兜底）/ default |
| PUT | `/store-creation-defaults/{store_id}` | settings manage | 保存某店铺的创建默认值（运输方式、发货日偏移、托盘 / 混装箱数、承运人、ITS、退货地址），记入设置变更；`store_id` 为 `*` 时保存「全部店铺通用」（能看到多个来源账号时 body 带 `source_account_ref`） |

`/creation-defaults` 另收 `store_id`：店铺行 → 账号行 → 8088 默认值；创建弹窗据此带出，弹窗里改的值只用于那一次。
`/orders?arrangement=open` = 打包完成且还有箱子没建货件。`/orders`、`/creation-tickets`、`/creation-ticket-counts` 保留，页面已改用 `/rows`。

## 单列表 `GET /rows`（Rocky 2026-11-04 第 12–16 条 + 拆票）

一行 = 一个打包单 × 一个货件，`kind`：
- `pending`：还有可用箱子的打包单，一行（`pending` 字段是原来的待创建行，勾选后创建）；
- `shipment`：已提交的每一票。已创建的票每个 Walmart 货件一行（Walmart 把一票拆成多个货件时就是多行）；没有货件号的票（提交中、失败）一票一行。打包单号在几行里重复。

`status`（5 种，可多选，默认前 4 种）：`pending` 待创建 / `submitting` 提交中（含取消批准前留下的旧待批准记录）/ `failed` 创建失败 / `created` 已创建未发货 / `shipped` 已发货。`shipped` 只在 `show_shipped=true` 时返回。`counts` 给 5 种状态各自的行数（不受状态筛选影响）。

每行另有：`shipment_id`、`fc`、`label_state`、`print_count` / `printed_at` / `printed_by`、`shipping_code`（领星 SP 发货单号）、`detail`（提交中「已查询 x/10 次」、失败原因）、`ticket`（原来的一票一行内容，含单号）。

SP 发货单号：每个账号当前发布（`gov_wfs_board_publications.is_current`）的发货单批次 `shipping_run_id`，在 `ods_lingxing_wfs_shipping_lists.cargo_codes` 里按货件号反查；有发货单号 = 已发货，几票可以共用一张。本机模拟数据（操作快照带 `demo_seed`）另认 `result.simulated_shipping`（`DEMO-SP…`），真实数据不认。

排序：待创建行按打包完成时间，货件行按提交时间，合在一起最新的在前。日期筛选按打包完成日期。

## 本机模拟（只在 APP_ENV=local）

- `PMC_WFS_LOCAL_SIMULATOR=1` 打开本机模拟通道（`local_simulator.py`），只有 APP_ENV=local、库是 127.0.0.1:55432/szzsbj_dev、并且没设 `WFS_CREATION_MODE` 时才生效。别处设了这个变量：路由模块导入时报错（服务起不来），取网关时报错，绝不退回真实通道；有测试。
- 模拟通道不建网关、不读凭证、没有网络调用，行为和 8088 一样：先查单号（查无此单）→ 创建只返回货件号 → 回读给 FC `LAX2T` → 箱唛是本地生成的一页 PDF，印着 SIMULATED。退货地址邮编 `00000` = 拒绝，`99999` = 结果不明（进提交中，下一次拉取查到），其他 = 成功。
- 本机没有任务进程：模拟模式下请求建的任务中心运行直接在 API 进程里跑完，运行记录照常留在任务中心。
- 模拟数据：`scripts/seed_pmc_wfs_local_demo.py seed | clear`，只在本机运行。打包单号 `DEMO-01`～`DEMO-07`、`is_test` / `business_test`、操作人 `demo-seed:wfs-sim-20261104`；创建操作快照写 `demo_seed`；`clear` 只删这些（`clear` 会在本机库、本次事务里临时停掉两张审计事件表的只追加触发器，只删 DEMO 的事件，提交前恢复）。

## 任务中心「WFS 创建结果拉取」

提交 Walmart、每 3 分钟查结果、重试都由 数据中心 → 任务中心 的「WFS 创建结果拉取」执行（provider `walmart`，interface_key `wfsCreationResultPoll`，cron `*/3 * * * *`），WFS 没有自己的定时器或 Celery 任务。

- 每次运行处理该账号下：已确认待执行的票 → 提交；提交中且到了查询时间的票 → 用单号查一次；结果待核实的票 → 查一次；页面点了核实结果 / 补取箱唛的票 → 处理一次。每个操作一条运行明细。
- 确认创建、重试、核实结果、补取箱唛会立即建一次手动运行；任务没注册或被关掉时记一条 `waiting_task_center` 事件，等下一次定时运行。
- 注册：`PMC_WFS_CREATION_TASK_BOOTSTRAP_AUTHORIZED=true PMC_WFS_SOURCE_ACCOUNT_REF=<账号> python scripts/bootstrap_pmc_wfs_creation_task.py`（自动同步默认关，由管理员在任务中心打开）。

## 单号与调用顺序（对齐 8088 的 14 票真实创建，2026-10-14～16）

- 每个计划货件 = 一票 = 一个 Walmart inbound order。单号（`inbound_order_id` = Walmart `inboundOrderId` = 领星入库订单编号）格式 `PMC-<店铺码>-<YYYYMMDD>-<序号>`，日期按北京时间，同店同日序号递增（如 `PMC-HK2614-20261104-01`）；首次提交前分配，之后重试、查询都用它（迁移 0080）。
- 首次提交：① 先用单号查 Walmart，查无此单（204 / 404）才发；单号在 Walmart 已存在（不是我们发的，例如 8088 同一天建过）就顺延下一个序号再查，最多 5 次；查询本身失败则不发，记失败 `WFS_PRECHECK_FAILED`（不算提交次数，可重试，单号不变）。② POST 创建。③ 马上按单号回读一次：目的 FC（`fcName`）只在回读里有，创建响应里没有。④ 取箱唛。
- 回读没拿到 FC 时照样记成功，任务中心每 3 分钟再回读一次补 FC，最多 10 次。

## 状态

- `QUEUED` 已确认待执行 → `RUNNING` 提交中（页面上都算「提交中」）。
- Walmart 返回货件 → `SUCCEEDED`，随后取箱唛（箱数按 Walmart 返回的件数 / 箱规，单货件时按本票箱数；混装箱数取创建默认值）。
- Walmart 明确拒绝（4xx）或请求根本没发出 → `FAILED`，`error_message` 为原因，箱子释放。
- 超时、5xx、没有返回货件号 → 保持 `RUNNING`，每 3 分钟用单号查一次，最多 10 次；查到即成功，10 次仍查不到 → `FAILED`（`WFS_RESULT_TIMEOUT`），箱子释放。
- 操作汇总：全部成功 `SUCCEEDED`；有票提交中 `RUNNING`；部分成功其余失败 `PARTIAL`；全部失败 `FAILED`。

## 防重复

1. 前端每次提交带幂等 key；同 key 重放返回原记录，同 key 改内容拒绝。
2. 提交时按 key 和账号加库锁；箱子写入占用表（同一箱同版本只能被占一次）。
3. 只有点「确认创建」（或重试）才会调用 Walmart；线上还要管理员把 `WFS_CREATION_MODE` 设成 single / batch。
4. 写入台账以 `create:<单号>` 为键：上一次结果不明时拒绝再次 POST，只能先查；已成功的键永远不再 POST。
5. 提交中（有票 `RUNNING` / `QUEUED`）时重试接口返回 409 `WFS_SUBMITTING`。
6. 重试先用同一单号查 Walmart，查到就直接记成功；Walmart 端对同一 inboundOrderId 也不会建第二单。

## 服务器配置（只列名字）

- `WFS_CREATION_MODE`（新增）。
- 复用统一 Walmart 网关现有变量：店铺映射 `…_WALMART_SCF_STORE_ID_MAP`、`…_CVM_ROLE`、`…_TARGET_ROLE_ARN`、`…_PROTOCOL`；协议 1 时还需 `…_APPROVED_WRITE_KEYS` 含 `wfs_inbound_shipment_create, wfs_shipment_label, wfs_inbound_preview`，`…_APPROVED_READ_KEYS` 含 `inbound_shipments`；审计 outbox 目录 `…_WALMART_AUDIT_OUTBOX_DIR`。
- 每店云函数须以读写模式部署（`owner-approved-read-write`）。
- Celery worker 照常消费 `integration` 队列（任务中心的 `integration_sync.execute_sync_run` 执行本任务）。
