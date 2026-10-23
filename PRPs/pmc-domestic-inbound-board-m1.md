# PRP：国内仓入库批次看板 M1 后端

日期：2026-10-20。状态：IMPLEMENTED_OFFLINE_VERIFIED；已在dev实现，未部署、未执行真实采集。

本文件替代此前以收货明细为主的草案。当前为 old-walmar-flie 工作区中的审阅件，目标归档为 SZZSBJ `PRPs/pmc-domestic-inbound-board-m1.md`。

## 1. Goal / Why

按交接文档建立“采购入库单 IB × SKU × 店铺批次”的独立后端链路，解释每笔入库及其批次余额。修正现有收货行 API 与用户业务粒度不一致的问题，先支持 CSV 验证，再通过明确发布动作供数据库查询。

## 2. 当前工程状态与执行边界

- 已只读核对目录：`C:/Users/treas/Desktop/work/SZZSBJ`。
- 分支 dev，基准 commit `46894605564da0ab0823dc0abe31ea12b32f4641`；调查时 `git status --short` 为空，只有此一个 worktree。
- 目标项目规则禁止 AI 自行创建/切换 worktree，禁止直接修改 dev。负责人须准备包含现有 pmc_domestic 前置代码的独立工作分支和 worktree；若从 main 开始，先确认相关依赖已合入，不能盲目依赖 dev 文件。
- 主执行角色：后端工程师（批准实施后）；本轮为架构师设计。使用项目 backend-module-designer 技能；不启用并行 agent 或生产操作技能。
- 当前请求授权准备后端实现方案；真实数据仍先文件输出，不执行业务库写入、生产迁移或部署。

## 3. Scope

In scope：官方 W1/W3 外部契约、分页采集、字段标准化、CSV+manifest 输出；RAW/ODS 接入设计；入库 mart 构建/发布代码；新增只读列表/统计/详情/来源追溯接口；隔离测试；迁移与文档。

Out of scope：前端改造、原 /batches 契约切换、生产库执行、旧系统运行依赖、浏览器会话采集作为运行方案、领星写操作、系统打包业务、发货完成率和 FIFO、ItemID 归属推断、定时任务启用。

交接文档完整批次页还依赖 A3a/A2/A1/P1/P2/P4/P6；本期仅基础入库与库存切片，不称完整复刻。后续补字段须分别确认来源和规则。

## 4. Navigation / Page / Permissions

页面已有 `/pmc/domestic-warehouse-board`，本期不改；页面不会因新接口存在自动切换来源。

GET 复用 `pmc:domestic-batch:read` 及现有页面权限映射和可信 source_account_ref scope。仓库 ID 只取允许清单；客户端 warehouse_id 筛选不能扩大权限。保留账号隔离并校验详情。

采集/发布使用现有治理任务入口，不新增匿名直通领星 HTTP 接口。动作权限、账号范围、审计沿用治理，不从 GET 路由触发同步。

## 5. Data Source

引用 [数据源决策](../docs/data-sources/decisions/pmc-domestic-inbound-board-decision.md)，状态 READY_FOR_PRP（M1 限定）。无运行时旧库查询，不复制旧架构。权威来源为领星；mart 只是查询模型；当前用户网页样本只作参考。

## 6. 拉取方式与文件输出

### Integration

复用 `app/integrations/lingxing/client.py`、Token Manager、签名、脱敏和白名单。增加 W3 的独立 endpoint contract 和采集方法，禁止把批次流水与库存流水共用不区分字段语义的 parser。

W1：POST `/erp/sc/routing/data/local_inventory/getBatchDetailList`，候选请求：

```json
{"offset":0,"length":400,"wids":"<已核实惠州仓库ID>","show_zero_stock":1}
```

W3：POST `/erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement`，候选请求：

```json
{"offset":0,"length":200,"wids":"<已核实惠州仓库ID>","start_date":"<开始业务日>","end_date":"<不包含的结束业务日>"}
```

W3 初次不默认过滤 sub_types，保留质检、撤销和其他变更用于对账；构建入库主记录只用已定义采购入库事件。W1 初次完整批次采集包括零库存；仓库字段/过滤效力先抽样核验。分页读取开放接口 code=0、data 数组、外层 total；不套用网页 code=1/data.list/wh_id。

### Collector / CLI

建议新增 `scripts/export_pmc_domestic_inbound_csv.py`，不 import 数据库 session，不调用现有落 ODS 的 handler；复用其契约/纯 parser 和已有只读客户端。显式参数：来源账号、仓库、开始/结束日、输出目录、页数上限；执行门禁按项目治理默认关闭，不伪造 production 环境。

输出独立批次目录：

```text
warehouse_statements.csv        库存流水，包含 statement_id 与有符号发生量
batch_details.csv              批次明细，包括源头和关联数组
inbound_board_preview.csv      同一纯构建器生成的入库看板预览
manifest.json                  来源时间、参数、覆盖范围、行数、哈希、失败及完整性
requests_log.jsonl             脱敏路径、分页、状态、request_id，无凭证
```

源响应脱敏留作可回放 JSONL（独立来源目录）；不导出 headers/sign/token/cookie。CSV UTF-8 BOM，ID 字符串，数组 JSON；null 与空文本采用明确记录的序列化契约，保留源 JSON 以无损回放。Excel 打开长 ID 需按文本导入。

空页早于 total、重复稳定身份内容冲突、总数变化、最大页数、超时或来源失败均标不完整；不得输出 completed=true，不覆盖上次成功目录，不发布数据库版本。每页按实际数量推进 offset，并核对总数及唯一身份；数量合计不能替代分页完整性校验。

真实请求配置尚未核实；首次运行先抽样，确认仓库和字段后再采完整范围。采集频率不由本文启用。

## 7. 逐表设计：M1 最小变更

| 表 | 动作 | 粒度与主要字段 | 约束/边界 |
|---|---|---|---|
| ods_lingxing_domestic_warehouses | 复用，不改结构 | 账号/仓库/run | 核实惠州 ID |
| ods_lingxing_domestic_batches | 复用，不改结构 | 原字段 + payload_json | 数组从已保留 payload 标准化；不强行扩充为收货主表 |
| ods_lingxing_domestic_inventory | 不改 | 仓库库存汇总 | M1 不作为批次余额真源 |
| ods_lingxing_domestic_inventory_events | 不改 | 现有批次流水 | 不混写 W3 库存流水、不借列塞不同语义 |
| ods_lingxing_domestic_warehouse_statements | 新增 | 账号、仓库、statement_id、order_sn、ref_order_sn、SKU/product_id、type/sub_type、有符号 product_total/good/bad/qc、opt_time 原文、payload_json、run/raw_ref/observed_at | append-only；raw_ref+ordinal 唯一；同 run 账号+statement_id 唯一；跨 run 保留版本 |
| mart_domestic_inbound_batch_board | 新增 | 账号、仓库、IB、SKU、归属店铺、publication_id、product_name、采购单集合、inbound_at_raw/源时区/UTC及业务日、入库量与 quantity_scope、余额/质量状态、batch_details JSONB、来源引用 | 每发布版本唯一账号+仓库+IB+SKU+归属键；父级总量和拆行量分开；未知字段可空 |
| gov_domestic_board_publications | 新增 | 账号、仓库、输入 W1/W3 run、覆盖时间、builder_version、status、is_current、quality_report、source_observed_at、published_at | 每账号/仓库最多一个 current 成功版本；单事务切换；旧版本可回退 |
| dwd_domestic_receipt_batch / _link | 不改 | 原收货模型 | 不删除、不重命名、不用它们承载 IB 行 |
| 收货 ODS/其他业务表 | 不改结构、不写业务数据 | 不适用 | 本期不采集收货，避免无必要耦合 |
| 公共 RAW/同步任务/血缘 | 复用结构 | 按既有治理运行 | 文件模式不写；获准数据库模式才写对应记录 |

新增外部 ID varchar(64)、账号 varchar(128)、SKU varchar(255)、时间 canonical timestamptz、原时间 varchar(32)、数量 integer、数组/来源引用 jsonb。对数量可能超 integer 的源值严格拒绝并报告，不截断。

ODS 与 publication 主键为 uuid。mart 以 `(publication_id, id)` 为复合主键：id 是账号、仓库、IB、SKU、标准归属键的规范 JSON 在固定 namespace 下生成的 UUIDv5，供 API 稳定引用；禁止简单拼接导致键碰撞。current publication 下同一逻辑 id 只有一行。不同版本相同 id 可共存；详情查询必须带服务端解析的当前版本和账号/仓库 scope。

meta.freshness_at 取本发布实际使用的 W1/W3 来源观测时间较早值，并另留各来源时间，避免最大更新时间掩盖较旧来源；source observed、provider update、published_at 三者不能混为一个字段。

mart 的 batch_details 是标准化组成明细，不整包复制 RAW；字段仅为批次号、店铺、数量、源头与关联单据、来源引用。省略单独 DWD 实体表是因为单来源+单查询模型，纯标准化/构建器仍明确承担清洗和语义层职责，血缘可回放；后续被多个模块消费时再评审复用模型。

索引：mart(publication_id, inbound_business_date, id)、mart(publication_id, sku)、statement(account, warehouse, opt_time)、statement(account, warehouse, order_sn, sku)；实际迁移需检查现有索引、规模和锁影响。store_id=0 规范为 unknown 归属键，不与真实店铺混并；在接口返回 null 并保留原值追溯。

新迁移编号以实施分支 head 为准，不修改 0047/0048 已应用迁移。新增业务约束与字段枚举须登记字段字典。

## 8. 核心业务构建规则

1. 校验账号/仓库与采集完整性，按稳定来源身份去重，禁止跨账号合并。
2. W3 2202 按 IB×SKU 建父级入库事实，保留事件与冲销；W1 按同账号/仓库/order_sn/SKU 关联现有批次。
3. W1 按唯一批次去重；店铺分组汇总余额。仅正向直接关联，不按 source_batch_no 自动把其他仓的调拨量加回原 IB。
4. 多店铺无可验证数量分配时，拆行入库量 null、scope=inbound_sku；单据 SKU 总量独立去重统计，不复制给各店铺相加。
5. 无批次行的 IB 仍保留，库存状态 unknown；只有完整来源明确返回余额=0 才显示 0，不计算已发货。
6. 窗口外采购批次补行标来源及历史不完整；批次时间只作 fallback 并展示 arrival_source。调拨 2401 等不混入采购入库主记录。
7. 质检未完成可发量 unknown；不执行旧代码“良品<=0则全部可发”。
8. 源时区未确认不生成 canonical 日期和在仓天数；已确认时请求日按 Asia/Taipei 计算；数据新鲜度仍用来源观测时间。
9. 不提供未经本期来源支持的业务状态、超时未发或完成率，available_capabilities 明确说明。

## 9. API Contract（新增，不切换旧接口）

### GET /api/pmc/domestic/inbound-batches

Query：page>=1，page_size=1..200，sort=inbound_date_desc（默认）/inbound_date_asc/balance_desc；warehouse_id、store_id、sku、inbound_order_sn、purchase_order_sn 各最多50项；inbound_from/to；search<=200；inventory_status=known/unknown。多值内部 OR、不同条件 AND；未知参数、非法范围 422。排序追加稳定 id，并定义 null 日期/余额排末。

统一 envelope：`success,data,error,meta,request_id`；data={items,total}。列表字段：

```text
id, source_account_ref, source_warehouse_id, warehouse_name,
inbound_order_sn, sku, product_name,
store_id, store_name, attribution_status,
purchase_order_sns[], inbound_at_raw, arrival_business_date,
arrival_source, arrival_date_status, days_in_warehouse,
total_inbound_qty, quantity_scope, balance_num, inventory_status,
batch_nos[], batch_details[], history_complete, publication_id
```

`attribution_status=known|unknown`；日期 known|unknown；inventory known|unknown；quantity_scope=store|inbound_sku|unknown。未归属 store_id=null；不编造 Walmart ItemID/GTIN。

meta：source=new_system_postgresql；source_objects=[mart_domestic_inbound_batch_board,gov_domestic_board_publications]；freshness_at、publication_id、coverage_start/end、as_of、available_capabilities、page/page_size/total。

没有成功发布与发布成功但确实0条：前者 meta.data_status=not_published、freshness_at=null；后者 data_status=ready 且有发布版本。空列表不能暗示采集已完成。

### GET /api/pmc/domestic/inbound-batches/summary

同业务筛选，不接受分页/排序。返回 board_row_count、inbound_order_count（IB去重）、sku_count、balance_qty（批次去重，仅known）、unknown_inventory_row_count、total_inbound_qty（父事实去重且只统计已知量）、unknown_inbound_qty_count、missing_arrival_date_count、as_of、publication_id。不能把 board 行数称为入库单张数。

### GET /api/pmc/domestic/inbound-batches/{id}

返回该行和批次组成，账号/仓库范围外 404。id 为稳定逻辑行标识，版本更新不应破坏现有行详情链接；查询指定发布版本由服务端当前指针选择，不任意暴露历史。

### GET /api/pmc/domestic/inbound-batches/{id}/trace

只返回本期已标准化的来源引用、入库事件与批次余额证据；不返回 RAW payload 或密钥，不推断发货分摊。未接通能力标 unknown/source_not_published，不造时间线。

错误：401认证、403权限/账号范围、404详情不可见、422校验、统一500（无SQL/连接串）。GET 不写审计业务记录、不调领星、不触发 Celery。

## 10. 后端分层及改动 allowlist

Route/Schema/Service/Repository：放在既有 pmc_domestic 内新增 inbound 专用文件，复用公共 envelope、权限和账号 scope；不改 receipt 类业务含义。

Integration：`app/integrations/lingxing/` 新增/扩充经审查的 W3 契约及只读 client 方法；W1 用已有契约。

Collector/Parser：`app/modules/integration_sync/` 新增 W3 parser 和纯采集分页服务；不要让 CSV 导出 import 触发 get_session_factory。

Builder/Publisher：`app/modules/pmc_domestic/`；先纯构建、后事务发布；组件复用同一业务逻辑生成 CSV 预览与 mart。

Celery：只编排受控采集/发布，默认没有周期 schedule。CLI sink=csv 与 sink=database 分离，数据库 sink 必须显式开启且校验目标环境，不假扮 production。

Model/Migration：本模块 models、model registry 按既有约定、`backend/alembic/versions/` 新迁移及测试。

Docs：API Markdown、数据源决策、PRP、字段字典、API文档登记、Data Interface Registry、帮助说明、CODEX_HANDOFF。仅必要位置挂接，不改其他模块业务。

## 11. 实施及验证顺序

1. 负责人批准本 PRP；准备独立 worktree/分支，核对前置 commit 和干净状态。
2. 在目标项目登记源决策及 registry candidate/approved，提交实现文件 allowlist。
3. 实现 W1/W3 契约、标准化、分页与纯构建，模拟数据通过后实现 CSV collector；不调用真实领星。
4. 实现新模型/迁移、事务发布、四个只读 API；仅使用隔离测试库。
5. 通过测试后交付；真实采集先 CSV、输出内容与数量验收另行执行；业务库发布和前端切换另行安排。

验证至少包括：signed 2202/2801、重复 statement_id、同SKU不同IB、多店铺数量不可分配、撤销与零余额、batch缺失、历史补行、非惠州/调拨排除、长ID与数组、分页缺页/总数变化、失败不发布、事务并发发布、CSV/数据库纯构建一致、401/403/404/422、筛选分页稳定、列表统计去重及无外呼、旧 /batches 回归兼容。

工具命令（实施后运行，不代表本轮已运行）：

```text
uv run ruff check <本次后端文件>
uv run pytest <本次 integration_sync 与 pmc_domestic 测试>
uv run alembic check  （仅明确隔离测试数据库）
```

## 12. 回滚

CSV 使用新目录并标完整性，不覆盖历史输出；代码能力默认关闭。数据库模式保留旧发布，单事务回退当前指针；旧收货 API 不受影响。新增表不自动 drop，生产未执行前无生产数据回滚事项。迁移恢复在隔离库演练后再审查，不声称自动零风险回滚。

## 13. Acceptance / 当前状态

- [x] 解读交接文档并纠正收货主粒度。
- [x] 用户确认新增 /inbound-batches，原接口暂不切换。
- [x] 补齐实际缺失的 W3 库存流水采集设计及三张新增表最小方案。
- [x] 明确先 CSV、数据库执行关闭、无页面改动。
- [x] 负责人批准实施，明确使用dev、不新建分支；现有三个前端改动保留。
- [x] 实现与离线测试通过；文档、registry、handoff同步。
- [ ] 获准真实采集完成并核验；数据库发布和前端切换不算本轮默认完成标准。

本轮交付后端实现与未执行的迁移文件；真实采集、数据库迁移/发布和前端切换仍未执行，不代表生产ready。


## 最新负责人指令与实际切片

2026-10-20：负责人明确要求在当前dev直接实现、不新建分支，覆盖本文先前worktree要求。当前已有三个前端修改不动。代码真实采集仍默认关闭；独立CSV配置不要求数据库连接；GET不触发同步。

实施细节：因无法证明“单一当前店铺”等于历史独占入库，本期total_inbound_qty保持null，额外返回parent_inbound_qty，summary按父级去重；quantity_scope=inbound_sku。pub仅存成功版本，失败由同步run/CSV manifest保留，不创建伪成功publication。元数据用publication_ids数组支持多可见账号。源时区未核实保持日期unknown。数据库业务发布使用独立CLI门禁，无自动执行。


## 实施验证记录（2026-10-20）

SZZSBJ实际目录回归：`tests/modules/pmc_domestic`、`tests/modules/integration_sync/test_lingxing_domestic_parser.py`、`tests/integrations/lingxing`，188 passed、3 skipped（未配置隔离PostgreSQL测试库）、1 warning。Ruff本次文件检查通过；前端`tsc --noEmit -p tsconfig.app.json`通过。新增表仅验证PostgreSQL DDL编译和SQLite内存读写，不等于已完成PostgreSQL迁移或并发锁实机验证。测试不调用领星，不连接业务数据库。三个原前端改动内容哈希保持一致。


## 前端与生产执行授权增量（2026-10-20）

负责人明确要求前端也实现以核对数据，并确认先完成页面和浏览器CSV预览；随后明确授权在SZZSBJ当前生产数据库建表、同步领星对应功能数据，继续dev、不建分支，先完成代码和数据库验证。上述指令覆盖此前本轮仅CSV、不切换页面/不写库的范围；不授权部署或重启服务。前端按独立inbound-batches契约接入，不改旧收货API。

组件复用与边界详见docs/frontend/domestic-warehouse-page.md，生产精确表范围、备份/恢复和版本见PRPs/pmc-domestic-inbound-production-execution.md。惠州仓ID通过当前账号仓库目录重新核实为16168。首次流水范围经负责人确认近90天：2026-07-23至2026-10-21（结束日不含）；余额取当前完整快照含零库存。源时区仍未独立核实，保留时间原值，标准化业务日未知，不能将文本强当UTC。

前端API分页与全局统计来自后端；CSV预览要求原始inbound_board_preview.csv和complete=true的manifest.json同批次、SHA256/行数/账号/仓库一致，仅内存解析，不上传、不写库、不存业务行到浏览器持久存储。上限20MiB/50000行，拒绝身份重复、数量冲突、未知格式。测试fixture不作为真实页面数据回退。

受控同步新增可选仓库范围：W1/W3请求wids、safe params、ODS入库前仓库复核，范围不匹配/缺total/提前短页拒绝成功。原未传仓库参数的调用兼容。


## 实际执行完成记录（2026-10-20，Asia/Shanghai）

最新负责人指令将首次流水从90天改成近30天，最终范围2026-09-21至2026-10-21（结束不含）；源时区由负责人明确确认为Asia/Shanghai。此处取代之前90天/时区未知的执行描述。

- 生产备份11:33完成，custom dump 3,194,306,808字节，SHA256 bf912d9f29ad14ed5eeea677658a371aa92837cf02412ed30c62fc0d6410bcbc，pg_restore目录校验通过。仅schema-only恢复已演练，不声称全量业务数据恢复已演练。
- 独立schema-only库使用专用角色演练0047→0049通过；演练库和专用角色随后已清理，无业务数据、无连接时才删除，没有强制断开连接，生产库和生产凭据未改。
- 11:49生产Alembic 0046→0047→0048→0049完成；三张新表创建成功，原收货DWD行数和角色授权数量不变。生产原来表存在但版本停0046，0047接管而非重建。
- 首次实际导入因公共gov_parse_jobs仅允许DWD而失败，保留failed run ad6e597e-0ac8-4285-b8ff-9de66c54b565及RAW；该批ODS页回滚，没有发布。修复国内仓ODS审计为run/work-item+完整DataLineage（parse_job_id=null），不改公共表约束、不冒充DWD；该修复有离线边界测试。
- 12:07批次快照run aafbbf09-e245-4056-a83a-232dd1d87dff成功1528行；流水run 3d7f1c80-183a-44da-a334-7758c764e02b成功1264行；共11个成功来源页，均限定惠州16168。接口/配置结束已关闭，无周期任务。
- 时区确认后使用上述同源ODS/RAW重新发布，未再次请求领星。当前publication 305a362a-dddb-4b84-98f2-bad1cd6d757c；1441展示行，1362个入库单，757个SKU，已知父级入库量24787件，批次余额4392件；1200组父IB×SKU历史入库量未知，日期缺失0。
- 源批次1528行中：2202采购入库1441、1601共49、1901共38，后两类不属于本看板采购入库范围。实际流水日期2026-09-21至2026-10-19，窗口外0；源码重建与当前mart全部payload一致，批次组成余额合计4392。
- 三张新表实际总行数：库存流水ODS1264、publication2、mart2882。后两者保留首次时区未知版本及确认时区版本；每账号/仓库当前版本只有1个，因此API总行数1441，不是2882。
- 同源CSV：warehouse_statements1264、batch_details1528、inbound_board_preview1441，清单complete=true；下载后用真实前端解析器核对SHA256/范围/计数/去重统计与数据库一致，日期及天数已可解析。业务文件不提交Git。
- 验证：后端194 passed、3 skipped（本地未配置隔离PG测试库），Ruff通过；前端Vitest8 passed、Playwright6 passed（含原打包页），TypeScript/ESLint通过；另外独立真实PG迁移演练通过。合成UI回归与真实业务源核对分别记录。
- 服务未部署/重启，代码未暂存/提交/push。当前本地8010是未开启reload的旧进程，新接口探测仍404；负责人已选择在原启动终端重启后端，实际生效与登录态HTTP200需复查。旧/batches仍读空收货表，不作为新看板入口。
