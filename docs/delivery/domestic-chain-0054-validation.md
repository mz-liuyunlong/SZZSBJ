# 国内仓迁移 0054 补充修复与验收（2026-10-22）

## 结论与边界

此前修复基于 `dev` 的 `c76208c275ffd09a92618f463a22b622fde228ad`；本次合并前文档复核重新确认，本地与 PR #242 的最新提交均为 `7c0a1f4b0c36d616f4ad312f200deaf484eb8595`，开始时工作区干净。负责人明确授权在 `dev` 修改、不新建分支、不新增 0055，并确认旧版不包含额外分配表创建逻辑的 0054 从未执行。

真实独立 PostgreSQL **14.24** 最终验收：**56 passed、0 failed、0 errors、0 skipped，170.39 秒**。其中数据库迁移/业务测试 24 项、ODS 接管测试 14 项、版本链/迁移环境静态测试 13 项、测试库安全测试 5 项。全后端 Ruff 检查通过，532 个 Python 文件格式检查通过。

代码与独立测试库的自动化验收已通过；最新 GitHub 全量 CI 证据见下节。本次只更新验收文档和 PR 正文，没有改动迁移或业务代码，也没有重跑整套数据库测试。真实登录业务验收、分支保护及生产核对分别记录，不将 CI 通过等同于获准合并或生产升级。没有连接生产数据库，没有读取生产业务明细，没有生产升级、降级、stamp、部署或服务重启。

最终目标仍为 `20261022_0054_merge_walmart_identity_and_domestic_packing`。

## 最新 GitHub CI（当前有效）

重新读取 Actions 与任务日志后确认：最新提交 `7c0a1f4b0c36d616f4ad312f200deaf484eb8595` 的 PR run `39762292250`、push run `39762285931` 均为 completed / success；每轮 **10 个任务通过、0 失败、0 任务跳过**。PR checks rollup 另含两个成功的预览部署状态，不能将其计作数据库测试。

| 验证组 | 最新 PR run 实际结果 | 解释 |
|---|---|---|
| 国内仓 PostgreSQL 16.15 | 56 passed，0 failed，0 skipped，115.08 秒 | 包含真实空库和已有 0049 合成数据升级；JUnit 零跳过门禁通过。 |
| 后端全量 | 1410 passed，0 failed，114 skipped，1 warning，115.02 秒 | 普通任务的 opt-in 测试仍有跳过；不能宣称这些业务路径均实际执行。 |
| 前端 Vitest | 51 个文件、258 项通过，0 失败 | 包含国内仓接口与组件契约测试。 |
| 前端 Playwright | 14 passed、6 skipped，0 failed | 六项为需要本地测试桥接的 live 用例，见页面验收边界。 |
| 其他任务 | 规则、IAM、Walmart identity、PMC 0043、WFS、审批、操作日志均通过 | 前端 lint/类型检查/build 与后端 Ruff 也通过。 |

不同任务会重复收集部分用例，以上数量不相加当作唯一测试总数。数据库数据全部为合成数据，不是生产订单或实际业务验证。

历史记录：旧提交 `dd45223` 的 run `39761275789` 曾为 9 通过、1 规则失败，原因是本报告四行包含规则禁止的项目专用文字。修复已随当前提交发布，最新 rule-pack-check 已通过；这是**已修复历史问题**，不再列作当前失败或“等待提交”。

0054 的职责明确为：**合并两个父分支，并创建或严格接管额外库存分配表**；它包含 DDL，不能描述为空合并迁移。最终完整 ID 见下方版本链，不新增 0055。

## 修改文件清单

| 文件 | 原因与修改 | 影响范围 |
|---|---|---|
| `backend/app/db/domestic_schema_contract.py` | 新增国内仓专用严格接管校验：列类型/长度/非空/默认值、PK、联合 UQ、FK 目标 schema/列顺序/更新与删除规则、约束验证与延迟状态、CHECK 和有序索引及有效状态。 | 仅国内仓迁移接管。使用会话临时空表让 PostgreSQL 解析 CHECK；不修补业务表、不删业务行。 |
| `backend/app/db/domestic_ods_adopt.py` | 四张 ODS 要么全无而创建，要么完整存在且全部校验；部分缺表拒绝接管，不再按名称自动补索引。保留时间时区和 varchar 长度检查。 | 未来运行原 ODS 接管的环境；已执行 0047 的环境不会因修改 helper 而重跑。 |
| `backend/alembic/versions/20261022_0053_domestic_packing_production_compat.py` | 将已有仓库表的字段/主键检查补为完整校验。通过同一份冻结建表参数执行创建或校验，避免两份定义漂移。 | 保留 revision、父依赖和五表建表参数；未改变字段及业务约束。AST 比对确认五个 CREATE TABLE 参数与修复前一致。 |
| `backend/alembic/versions/20261022_0054_merge_walmart_identity_and_domestic_packing.py` | 保留原有额外分配表创建与双父依赖，使用完整校验替换不完整检查。降级改为拒绝自动删除，要求经过验证的备份恢复。 | 额外分配表；不再存在先计数后删表的竞争窗口，也不会误删被接管的空表。 |
| `backend/tests/db/domestic_postgresql_support.py` | 独立测试库创建/销毁工具。显式 opt-in、APP_ENV=test、专用本地 CI 用户/主库、随机库名、CREATE 不覆盖、仅删除本进程创建的库。 | 测试工具；不再读取 DATABASE_URL/PGPASSWORD 回退目标或清理固定同名库。 |
| `backend/tests/db/test_domestic_database_safety.py` | 拒绝非测试环境、业务库、远程目标、缺配置和其他进程所有的库。 | 无实际数据库连接的保护测试。 |
| `backend/tests/db/test_domestic_chain_postgresql.py` | 补齐真实空库和 0049 路径、20 表实际 ORM 查询、逐行旧数据快照、升级日志/幂等、已存在且有合成数据的额外分配表、结构漂移、事务回滚、库存与仓库列表读写、OWS 非空阻断和降级保护。 | 只使用随机一次性 PostgreSQL 库、合成数据；移除手改测试 alembic_version 的做法。 |
| `backend/tests/modules/pmc_domestic/test_domestic_ods_adopt.py` | 专用一次性库；补齐 PK/FK/UQ/CHECK、NOT VALID、非空、索引顺序/缺失、部分缺表的反例。配置错误不再被笼统捕获后 skip。 | 真实 PostgreSQL ODS 接管。 |
| `backend/tests/db/test_alembic_scaffold.py` | 增加完整 revision ID 去重、单 head、单根、全图可遍历检查。 | 静态迁移图；不连接数据库。 |
| `.github/workflows/ci.yml` | PostgreSQL 16 独立任务加入 ODS、安全、静态链测试，输出 JUnit，并拒绝零用例或任意 skip。 | 最新提交已由 GitHub PostgreSQL 16.15 实跑通过；不调整生产部署。 |
| `.planning/current/task_plan.md` | 记录当前 dev 授权、0054 未执行确认和验收进度；旧分支记录保留为历史。 | 本地工作计划，不需随代码提交。 |
| `docs/tasks/TASK_REGISTRY.md` | 登记本轮任务、授权范围及测试证据。 | 项目交接。 |
| `CODEX_HANDOFF.md` | 追加本轮结论、测试结果和生产前置事项。 | 项目交接，保留此前内容。 |
| `docs/delivery/domestic-chain-0054-validation.md` | 本报告。 | 审查与验收证据。 |

没有新增 API、权限、业务模型或业务规则，没有修改 `old-system/**`、`.env`、依赖或生产配置。

## Alembic 完整版本链

下表使用完整 ID，表中短号只用于解释。

| revision | down_revision |
|---|---|
| `20261019_0046_operation_logs` | `20261019_0045_approval_scope` |
| `20261020_0047_walmart_order_identity_guard` | `20261019_0046_operation_logs` |
| `20261019_0047_domestic_warehouse_ods` | `20261019_0046_operation_logs` |
| `20261019_0048_domestic_warehouse_dwd_and_permission` | `20261019_0047_domestic_warehouse_ods` |
| `20261020_0049_domestic_inbound_board` | `20261019_0048_domestic_warehouse_dwd_and_permission` |
| `20261020_0050_domestic_packing_approval` | `20261020_0049_domestic_inbound_board` |
| `20261021_0051_domestic_packing_lifecycle` | `20261020_0050_domestic_packing_approval` |
| `20261021_0052_domestic_packing_manual` | `20261021_0051_domestic_packing_lifecycle` |
| `20261022_0053_domestic_packing_production_compat` | `20261021_0052_domestic_packing_manual` |
| `20261022_0054_merge_walmart_identity_and_domestic_packing` | (`20261020_0047_walmart_order_identity_guard`, `20261022_0053_domestic_packing_production_compat`) |

静态检查覆盖仓库全部 **62** 个 revision：一个根、一个 head，无重复完整 ID、缺失父节点、孤立节点或循环。0054 必须等两条父分支完成。0049→head 测试实际捕获六次升级：Walmart 0047、国内仓 0050、0051、0052、0053 和 0054；不强制两条独立分支的相互先后顺序。确认未重跑国内仓 0047、0048、0049。第二次 upgrade head 没有升级日志，版本仍只有一行 0054。

本轮没有修改任何历史 revision/down_revision，也没有 stamp 或直接更新测试/生产 alembic_version。版本表仅由 Alembic 正常维护。

## 国内仓全部 20 张表的正式来源

| 表 | 正式创建或接管迁移 | 实际验收 |
|---|---|---|
| `ods_lingxing_domestic_warehouses` | 国内仓 0047，全新创建/完整旧表接管 | 存在；ORM 全列查询通过 |
| `ods_lingxing_domestic_inventory` | 国内仓 0047 | 存在；ORM 全列查询通过 |
| `ods_lingxing_domestic_batches` | 国内仓 0047 | 存在；ORM 全列查询通过 |
| `ods_lingxing_domestic_inventory_events` | 国内仓 0047 | 存在；ORM 全列查询通过 |
| `dwd_domestic_receipt_batch` | 国内仓 0048 | 存在；ORM 全列查询通过 |
| `dwd_domestic_receipt_batch_link` | 国内仓 0048 | 存在；ORM 全列查询通过 |
| `ods_lingxing_domestic_warehouse_statements` | 国内仓 0049 | 存在；ORM 全列查询通过 |
| `gov_domestic_board_publications` | 国内仓 0049 | 存在；ORM 全列查询通过 |
| `mart_domestic_inbound_batch_board` | 国内仓 0049 | 存在；ORM 全列查询通过 |
| `ops_domestic_pk_sequences` | 国内仓 0050 | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_orders` | 国内仓 0050，0051/0053 调整已有约束 | 存在；ORM 全列查询及合成写入通过 |
| `ops_domestic_packing_allocations` | 国内仓 0050 | 存在；ORM 全列查询及库存占用通过 |
| `evt_domestic_packing_events` | 国内仓 0050，0053 调整事件种类 CHECK | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_manual_requests` | 国内仓 0052 | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_box_sets` | 国内仓 0053 | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_box_lines` | 国内仓 0053 | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_notes` | 国内仓 0053 | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_variance_cases` | 国内仓 0053 | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_notification_outbox` | 国内仓 0053 | 存在；ORM 全列查询通过 |
| `ops_domestic_packing_extra_allocations` | 现有 0054 | 存在；完整结构校验、实际分配与读取通过 |

以上基于真实 Alembic base→head 和 0049→head 后的 PostgreSQL 系统目录，并执行全部 20 个 ORM Table 的全列查询；测试不会调用 metadata.create_all 代替正式迁移。用于“已有表接管”反例的表来自现有迁移冻结 DDL，不通过手改版本表伪造迁移状态。

`ops_domestic_packing_ows_links` 是 0051 的历史临时关联表，0052 仅在为空时删除，不计入最终 20 表。

额外分配表的完整契约：UUID 主键 id；所有九个字段非空；order_id 外键指向 public 打包订单；账号 varchar(128)、仓库 varchar(64)、SKU varchar(255)；publication_id/board_id 联合外键指向 public 入库看板版本和行；两组 FK 均 ON DELETE RESTRICT、ON UPDATE NO ACTION、即时且已验证；唯一键 `(order_id, source_board_id)`；`qty integer CHECK(qty>0)`；created_at 为 timestamptz。普通 btree 索引 `ix_packing_extra_source` 列顺序是 `(source_account_ref, warehouse_id, source_board_id)`，必须 valid/ready/live。字段不额外接受未声明的 server default、identity 或 generated 表达式。

## 实际 PostgreSQL 测试

环境：Windows、Python 3.13、PostgreSQL **14.24**，SQLAlchemy **2.0.52**、Alembic **1.19.1**、psycopg **3.3.5**。使用全新 initdb 数据目录，回环地址随机端口 54323，专用用户和主库 `domestic_chain_ci`。每个测试用例创建随机名的一次性数据库；不会连接既有开发库、生产库或服务实例。只使用合成账号、SKU、订单和发布数据。

实际执行（backend 目录，环境变量 APP_ENV=test、DOMESTIC_CHAIN_DB_TESTS=1，TEST_DATABASE_URL 指向上述新实例）：

```powershell
$evidence = "$env:USERPROFILE/.codex/visualizations/2026/10/19/01a15238-e1bb-79f1-9cb5-b712d3bd78d5/domestic-audit-5f9df714"
./.venv/Scripts/python.exe -X utf8 -m pytest -q tests/db/test_domestic_chain_postgresql.py tests/db/test_domestic_database_safety.py tests/modules/pmc_domestic/test_domestic_ods_adopt.py tests/db/test_alembic_scaffold.py -p no:cacheprovider --basetemp="$evidence/pytest-acceptance" --junitxml="$evidence/postgresql-results.xml"
./.venv/Scripts/python.exe -X utf8 -m alembic heads
./.venv/Scripts/ruff.exe check .
./.venv/Scripts/ruff.exe format --check .
./.venv/Scripts/python.exe -X utf8 -c "import app.main"
./.venv/Scripts/python.exe -X utf8 -m mypy app/db/domestic_schema_contract.py --follow-imports=skip --ignore-missing-imports
```

最后一项仅为新校验器的定向类型检查，不代表全项目 mypy。

| 场景/测试组 | 关键实际断言 | 结果 |
|---|---|---|
| 全新数据库 | base→0054；单版本行；20 表存在且全列 ORM 可查；完整 extra 结构；第二次升级无动作；实际库存、额外分配和仓库列表读取。 | 通过 |
| 模拟生产 0049 | 真实升级到完整国内仓 0049 ID 后插入 ODS、DWD、DWD 关联、当前 publication 与 MART 合成行；升级前后九张 0049 已有表逐行 JSON 快照完全一致，当前发布指针不变；六次后续升级且不重跑原 0047–0049；再次升级无动作；实际业务读写。 | 通过 |
| 已有仓库表 | 真实 0052 上创建五张冻结 DDL 表，正确结构可接管；字段、联合唯一、CHECK、FK 缺失和 NOT VALID 均拒绝；0053 失败后旧事件 CHECK 等全部约束与版本回滚。 | 6 项通过 |
| 已有 extra 表 | 结构正确且已有合成分配记录时保留数据；非空、默认值、无时区时间、UQ/CHECK/FK 缺失、NOT VALID、延迟外键、错误删除规则、跨 schema 外键、索引缺失/错误顺序/真实失败并发建索引残留均拒绝。 | 14 项通过 |
| 0054 失败事务 | 失败后仍停在 0053；同事务内 Walmart identity 列也回滚；测试预置数据保持不变。 | 通过 |
| 0052 非空历史 | 真实 0051 写入合成 OWS 历史记录，升级被 OWS_LINK_HISTORY_PRESENT_DO_NOT_DROP 阻断；历史记录/版本保持原样，没有创建空 manual_requests 掩盖问题。 | 通过 |
| 降级保护 | 已成功接管含数据 extra 表后请求隔离库降级，明确拒绝；head 和数据不变。 | 通过 |
| 库存及仓库列表 | 可用量 10，基础占用 3，额外分配 2 后剩余 5；仓库列表能读取该额外分配；超量分配被拒绝。 | 两条主路径及已有表场景通过 |
| ODS 接管 | 手工 SQL 参考结构和新建结构均能复验；类型、长度、PK/FK/UQ/CHECK、非空、未验证约束、索引顺序/缺失、部分缺表均拒绝。 | 14 项通过 |
| 静态及测试库保护 | 62 revision 完整图；保护非测试/业务/远程目标、缺配置、其他进程所有的库。 | 18 项通过 |

总计 **56 通过、0 失败、0 错误、0 跳过**。结束后查询本次集群剩余的一次性测试数据库为 **0**，本次独立测试实例已停止，确认 postmaster.pid 不再存在。首轮测试中发现的 numeric 类型格式化和测试断言问题均修复，以上为最终完整复跑结果，不是把失败用例排除后的结果。

独立 GitHub CI 仍使用 PostgreSQL 16，运行上述四个测试文件并检查 JUnit 不得含 skip。缺少必需测试配置会失败；没有数据库不能被描述为验收通过。

## 历史文件与生产状态

国内仓 0047–0049 文件未修改，工作区 Git Blob 与本轮开始的 HEAD 完全一致：

| 文件 | Git Blob |
|---|---|
| `20261019_0047_domestic_warehouse_ods.py` | `7699c9664f5012c3e1fc9c9331603091bc42c360` |
| `20261019_0048_domestic_warehouse_dwd_and_permission.py` | `d2e26b48c4ead4e90e1c18ae9d4cc7286c130b30` |
| `20261020_0049_domestic_inbound_board.py` | `3e26ecd854ba7a9e189e98562af9aaea49b8da98` |

本轮未能核实此前授权的服务器 staging 目录（`domestic-inbound-20261020-1115`）的已执行文件 Blob，也未查询生产实时版本。上述哈希只证明当前仓库历史文件未被本轮改写，不能证明它们与生产实际文件一致。此前生产 0049 仅是历史背景，不能当作当前状态。

## 风险与恢复

1. **0052 删除历史关联表**：非空即阻断，测试证明记录和事务不受损。遇到此错误保持当前版本，先由负责人决定旧关系的业务归档/迁移方案；不能清空数据或 stamp 绕过。没有另行批准的方案不继续升级。
2. **迁移中途失败**：本项目 PostgreSQL Alembic 使用事务 DDL。本次反例验证版本、先前同事务 DDL 和数据回滚。应先查失败原因，不手动改 alembic_version。备份恢复需在隔离环境完成恢复演练后，另行批准生产操作。
3. **不可自动逆向删除**：0052/0053 已要求备份恢复；0054 也改为相同边界，避免删除被接管表。数据已写入后不提供自动删表降级捷径。
4. **已有迁移不会重跑**：0053 的新校验仅作用于将来执行；如数据库已执行 0053，不能声称重跑 head 会重新审计旧五表。升级申请仍需只读比对实际表结构和版本。负责人已确认旧 0054 未执行；若事实变化，应停止本方案并重新评审修复路径，不能补 stamp 或改 ID。
5. **严格接管可能阻断历史手工结构**：缺索引、额外/失配约束等会拒绝，不自动修复。先调查差异，不临时放宽验证。CHECK 验证需要数据库 TEMP 权限，接管检查持有 SHARE 表锁至事务结束；生产申请应确认角色权限及维护窗口。
6. **版本差异及 CI**：本地验收为 PostgreSQL 14.24，最新 GitHub PostgreSQL 16.15 及其他 CI 任务也已通过。后续若提交新文档，新的提交仍须通过适用 CI；不能把当前提交的通过记录冒充未来提交的结果。未对生产数据规模、迁移耗时、并发压力或本机之外的生产结构作保证。

## 最终验收建议

- 代码/独立 PostgreSQL 验收：通过。当前只有一个 Alembic head，推荐完整 revision 为 `20261022_0054_merge_walmart_identity_and_domestic_packing`，不新增 0055。
- PR #242：**有条件合并**。当前代码提交的全量 CI 已绿，但 GitHub 仍为 MERGEABLE / BLOCKED；须由负责人确认规则集下的合并资格、范围门禁及人工业务验收或明确延期。生产历史文件核对属于独立升级前置，不以其未完成推断代码测试失败。
- 数据丢失/覆盖：本次合成数据升级及失败回滚没有发生丢失或覆盖；非空 OWS 会安全停止。尚不能据此对未知生产结构作无条件保证。
- 生产升级：本轮不批准、不执行。可据本报告准备单独申请，但须补实时只读版本/结构、0047–0049 服务器 Blob 对照、非空 OWS 检查、备份恢复演练、数据库角色 TEMP 权限、维护窗口和最终 CI 证据后，由负责人批准。

官方依据：FK/唯一/CHECK 的定义参照 [SQLAlchemy 2.0 Constraints](https://docs.sqlalchemy.org/en/20/core/constraints.html)；约束验证/延迟与外键动作字段参照 [PostgreSQL pg_constraint](https://www.postgresql.org/docs/16/catalog-pg-constraint.html)；索引 valid/ready/live 判定参照 [PostgreSQL pg_index](https://www.postgresql.org/docs/16/catalog-pg-index.html)。沿用项目锁定库版本，没有升级依赖。


## 本次合并前验收的补充结论

### 页面与业务：自动化和人工分开

本次未提供可用的真实测试登录态/测试账号，未启用任何已有本地业务库写入桥接。以下是最新 CI、测试代码与权限/查询实现的复核，不是本轮新做了一次真实登录页面操作。

| 页面或业务 | 已核实证据 | 当前结论 |
|---|---|---|
| `/pmc/domestic/batches` | inbound API 读取当前 publication，按可信账号范围过滤；合成浏览器测试覆盖列表、筛选、版本缺失/已发布空集、错误、trace/help。 | 自动化契约通过；真实测试账号读取当前发布版本与跨账号拒绝仍待人工验收。 |
| `/pmc/domestic/packing-approval` | 独立动作 permissionKey + source-account scope；前端只读权限与错误场景、组件/接口测试通过。 | 自动化契约通过；实际审批/驳回、是否报关与同一 PK 跨页联调待人工验收。 |
| `/pmc/domestic/packing-warehouse` | 列表实际 ORM 读取及额外分配在 56 项专项中执行；前端空/错/只读契约通过。 | 自动化通过的范围有限；装箱、完成、备注、少装、超发的完整登录流程待人工验收。 |
| 库存占用 | 专项实测总量 10、基础占用 3、额外 2、剩余 5，超量拒绝；代码读取当前发布、基础未释放分配与 extra 占用。 | 该合成数据库场景通过；不能替代完整并发审批/完成压力验收。 |

当前 Playwright 六项 live 跳过：审批 1、手工申请 1、仓库 2、超发 2；它们分别要求 PACKING_LIVE_E2E、PACKING_WAREHOUSE_E2E 或 PACKING_OVERPACK_E2E 及本地桥接。后端 PACKING_LOCAL_INTEGRATION 的完整审批/仓库/并发业务用例也未由本轮开启。本次不改 skip、不虚构通过、不使用生产写操作补验收。

### PR 规则、评审与旧 PR

- PR #242 为 OPEN、非 draft，dev → main，代码无合并冲突（MERGEABLE），但 mergeStateStatus 为 **BLOCKED**。
- 官方 review submissions 为 0，未解决 review threads 为 0（已检查分页，hasNextPage=false）；请求审核人尚未完成审查，不能写成“已批准”。
- main 使用 active ruleset，传统 branchProtectionRule 为 null。实际规则含：只允许 squash、review thread 必须解决、普通 required approval count=0、未归属改动可能要求额外批准，并限制 update。当前账号只有 WRITE，无 admin/maintain；规则集返回的 bypass_actors 为 null，不能据此宣称满足或可以绕过全部规则。具体 BLOCKED 原因需负责人在 GitHub merge 区核对，本轮不改规则。
- 完整 PR diff 为 268 文件，包含国内仓前后端/迁移，也累积采购看板与治理/计划文件。按 scope gate 需要负责人说明整体合并与原子回滚边界或安排拆分；本轮未证明所有旧改动无法安全拆分，不把 CI 全绿当作范围批准。
- 旧 PR #234 仍 OPEN、CONFLICTING/DIRTY，不关闭。其 14 个文件中 13 个路径出现在 #242 diff，不能因此推断内容完全覆盖：两分支已经 diverged，#242 相对旧分支 ahead 27 / behind 6。旧 0047 Blob 为 `058bfbdae8fdc0a08a94092d61bf14fb2f2bd682`，与本 PR/已知历史 `7699c9664f5012c3e1fc9c9331603091bc42c360` 不同；不应重复合并覆盖历史脚本。旧 PR 独有的 PR 正文草稿也不能当成新实现缺表的证据。负责人须按实际差异处置旧 PR。

### 生产只读核对：尚未执行，提供负责人命令

本轮没有现成、已确认授权的生产只读连接，也未登录服务器、读取连接密钥或申请更高权限。生产实时版本、全部版本行、服务器实际执行 0047–0049 Blob、是否已执行 0050–0054、是否执行过旧版 0054 **均未重新确认**；此前 0049 只是历史值。当前仓库三份 Blob 与已知历史值一致，但不能代替服务器文件对照。

以下由负责人在**现有授权的服务器 shell**执行；STAGING_ROOT 仅指此前指定的 staging 目录，不另建目录、不覆盖文件。目录结构若不同/文件缺失，报告实际情况，不猜测或自动拷贝：

```bash
: "${STAGING_ROOT:?use the already-authorized staging directory}"
for name in \
  20261019_0047_domestic_warehouse_ods.py \
  20261019_0048_domestic_warehouse_dwd_and_permission.py \
  20261020_0049_domestic_inbound_board.py
do
  file="$STAGING_ROOT/backend/alembic/versions/$name"
  test -f "$file" || { printf 'MISSING: %s\n' "$file"; exit 1; }
  printf '%s ' "$name"
  git hash-object --no-filters -- "$file"
  grep -nE '^(revision|down_revision)([[:space:]:=]|$)' "$file"
done
```

这条 hash-object 没有 -w，只计算 Blob，不写 Git 对象或文件。输出逐项对照上方三个历史 Blob，并检查文件 revision/down_revision；差异保留原文件，提交负责人分析。

数据库只使用**现成已授权的只读 PGSERVICE**，不新建 service/连接配置，不把密码贴到终端、PR 或文档；未配置则停止。下面 SQL 不含任何升级或业务写入：

```bash
: "${PGSERVICE:?use an existing authorized read-only service}"
export PGSERVICE
psql -X -w -v ON_ERROR_STOP=1 <<'SQL'
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';
SHOW transaction_read_only;
SELECT current_database(), current_user;
SELECT version_num FROM public.alembic_version ORDER BY version_num;
SELECT to_regclass('public.ops_domestic_packing_extra_allocations') IS NOT NULL
       AS extra_table_exists;
ROLLBACK;
SQL
```

判读：单行完整国内仓 0049 才与原先基线相符；多行需核对全部已执行分支，不手工改版本。若已有 0050–0053，重新审查现场结构/部署历史；若已有 0054，必须同时核对**实际执行时**的 0054 发布制品，不能只凭当前文件或 extra 表存在就断言为新版。0054 版本下缺 extra 表是高风险异常；确认执行过旧版 0054 时立即暂停本方案，不依赖改文件重跑。

### 剩余事项及两个独立结论

- P0：未发现当前代码/CI 的新 P0；生产若确认已执行旧版 0054 或历史文件不一致，应按潜在 P0 停止升级路径。当前是未核实风险，不冒充已发生事故。
- P1：GitHub BLOCKED 规则资格、268 文件范围说明、真实测试登录业务验收/并发场景，需负责人处理或明确延期；生产实时版本/历史文件/恢复演练尚未完成，阻断生产执行。
- P2：旧 #234 仍开放且内容分叉，需负责人决定后续处置，避免重复合并；本轮只读核查。历史 CI 文案已修正。
- **PR #242 是否具备代码合并条件？技术自动化通过，建议有条件合并；目前仍有 GitHub 保护门禁和上述负责人验收事项，不能直接标记为无条件可合并。**
- **生产是否具备升级到 0054 的条件？尚未具备可执行条件，也未获得升级授权。可以准备独立申请，但必须先补齐现场只读证据、备份恢复验证和维护窗口，由负责人另行批准。**
