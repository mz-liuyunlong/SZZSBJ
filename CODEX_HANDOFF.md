# 当前任务交接：打包单审批（2026-10-28）

后续字段纠错：负责人已授权修复 quantity_receive 语义。当前打包审批已到取采购明细 ODS payload_json.quantity_entry，未到取 quantity_receive；缺失保留未知，不按差值补值。此次只修改到货投影／纯函数、合成用例和文档，未运行测试、未操作数据库、未修改表结构。工作区其他审批编辑、0062迁移等改动不属于此次修复，保留不动。

负责人确认在当前 develop 修改 WFS 准入、计划比例数量预填、采购到货计数及分批筛选；代码已修改。随后要求“暂时不要测试”，现仅补齐文档；不继续测试，不标 ready。

详细记录：[打包审批交接](docs/delivery/pmc-packing-approval-allocation-arrival-handoff-20261028.md)；接口：[当前字段契约](docs/api/pmc-domestic-packing-approval-allocation-arrival-api.md)。没有新物理表／字段／迁移，没有真实数据库操作、外部采集、分支创建、Git提交推送或部署。

暂停前 scoped 后端 46 passed / 19 skipped、前端审批目录 13 passed。新增 E2E 首轮失败在 Select 点击定位，已修正但未重跑；原结构场景2项通过。真实数据联调未执行。不要把旧交接中的全量测试、生产采集或授权套用到本轮。

# 打包审批草稿 CI 修复（2026-10-28）

负责人授权继续 develop，同步测试文档、修复失败项、提交推送并重跑全量 CI；不新建分支、不合并 main、不部署或迁移生产。基准 b190a61，工作区开始时干净。

本轮只修三个文件的格式、保存按钮测试和历史 0054 表清单测试；新增隔离 PostgreSQL 的 0062 升级/草稿事务验收及前端保存不审批的浏览器契约。迁移文件、业务规则和 approve 入口保持原实现。详见 `docs/delivery/pmc-packing-approval-allocation-arrival-handoff-20261028.md` 本轮章节，远端最终结果以修复提交对应的 Actions 为准。

已执行：代码修复 e010518 的 CI 40642011374 全部 10 项通过；后端 1802 passed / 121 skipped，前端 308 passed，Playwright 28 passed / 7 skipped，独立 PostgreSQL 16 专项 59 passed / 0 skipped。文档收尾只补实际证据，不更改代码或迁移。生产升级、部署和 PR 合并均未执行。

# Develop CI 修复交接（2026-10-27）

本轮基准 aa7637b，负责人授权复用 develop、提交和推送、创建 develop → main 草稿 PR。禁止合并、部署或生产数据库操作。

修复内容：局部 Ruff 格式和导入排序、React 组件模块导出及 hooks 依赖、文档占位名称；develop push 加入现有 CI。采购备注和国内仓草稿号的表结构检查复用 Session 事务连接，避免单连接池中意外回滚。历史 Gate 3 测试合并已有 0055 加列结果再对照当前 ORM；不修改历史迁移语义或 revision ID。

本地已运行：前端 lint、TypeScript/Vite 构建通过，Vitest 68 文件 / 304 tests passed；后端 Ruff lint/format 通过，采购覆盖、迁移对照和备注回归 15 passed，规则检查通过。首次 Windows 全量后端为 1769 passed / 13 failed / 118 skipped：4 项真实问题已修复，9 项涉及 POSIX 文件权限，保留断言等待 Linux CI。远端结果须以本轮提交对应的实际 Actions 记录为准，不能将本地结果替代远端验收。

# 最新交接：待发货打包单（2026-10-23，dev_wfs 合入）

已批准本地开发完成。具体范围、数据保护、验证和后续限制见 `docs/delivery/pmc-wfs-pending-packing-handoff.md`。本地待发货0张、待装箱4张；真实流程已通过隔离PostgreSQL与浏览器模拟接口验证，未往现有业务表灌样例。审批/Walmart/箱唛/取消改量仍属下一阶段。

以下为历史交接：

# 国内仓入库批次看板 M1 交接

日期：2026-10-20。目标分支：dev（用户明确要求，不创建新分支/worktree）。基准46894605564da0ab0823dc0abe31ea12b32f4641。

范围：新增入库单口径的四个GET；保留原收货/batches。W1/W3采集及CSV、独立库存流水ODS、入库mart、成功发布版本、发布CLI、文档和模拟测试。真实外部调用、真实库迁移/同步、页面切换未执行。

原目录已有三个未提交前端改动：docs/frontend/domestic-warehouse-page.md、frontend/public/help/domestic-warehouse.html、frontend/src/pages/pmc/domestic-warehouse/DomesticWarehousePage.tsx；本任务不修改它们。

治理：用户最新指令覆盖“必须新worktree”的本任务要求；不修改Git分支、不暂存/commit/push，不改.env、密钥、旧系统、生产配置或其他业务表。API文档目录仅补元数据，不修改页面业务。

待运行：按明确账号、仓库、窗口和安全配置进行领星CSV抽样及全量采集；经过文件验收后，另行安排数据库迁移/同步/发布和页面切换。

验证结果及运行限制见同次交付报告；代码通过模拟测试不代表已取得领星真实数据或线上接口已有数据。


离线验证（2026-10-20）：SZZSBJ目录188 passed、3 skipped（隔离PostgreSQL未配置）、1 warning；本次后端文件Ruff通过；前端TypeScript检查通过。仅做PostgreSQL DDL编译、SQLite内存与模拟来源测试，未执行真实PostgreSQL迁移或并发锁验证。安装时核验原三个前端文件哈希一致。没有commit/push。


2026-10-20后续：负责人已授权前端接入和CSV预览，且明确生产库建表/导入、dev继续开发。此前“不改三个前端文件”和“本轮不写库/不切换页面”的边界由新授权覆盖，但保留既有去除对账页签与打包结构；WFS实施计划等其他任务文件不碰。前端8项Vitest、4项批次E2E与2项打包回归通过；后端含仓库范围修复192 passed/3 skipped。生产目标已连接核实，惠州ID16168；独立角色/测试库已演练0047→0049成功。生产备份生成中，建表/导入尚未执行。精确计划见PRPs/pmc-domestic-inbound-production-execution.md，执行后须更新记录。


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

## 2026-10-20 入库批次下拉衔接验收

用户本轮明确要求店铺/负责人/状态调用接口，随后确认截图六状态，并明确“没有，按交接文档补做后端数据方案”。店铺/当前负责人增量已实现；状态数据建设仍是候选方案，未建表/同步，不得宣称六种业务状态筛选已经可用。沿用 dev，不建新分支、不提交推送，保留既有打包和刷新UI调整。

- API：GET /api/pmc/domestic/inbound-batches/filter-options；warehouse_id重复<=50；stores/owners真实稳定ID和UID，options覆盖当前版本所有行，不受当前页影响。旧收货filter-options保持原契约。
- list/summary：owner_uid重复<=50，按当前产品负责人，account+SKU唯一active身份；EXISTS，不复制数量。共享filter_sources.py保留原收货逻辑。meta追加DIM/DWD依赖，不冒充来源同时快照。
- 前端：feature API/hook/类型、DomesticToolbar复用ReportFacetSelect；搜索、多选确认/清除、应用回第一页，loading、独立error/retry；缓存含用户和仓库；打包页不加载选项，切回批次后才加载。六状态从接口返回disabled/reason，下拉可展开查看，不能提交伪业务状态筛选。
- 文档：数据源决策、PRP、API、数据中心目录、registry、SOP/help、前端说明已更新。状态方案 PRPs/pmc-domestic-business-status.md 逐表写明候选变更/影响；旧版SP接口被项目标DO_NOT_USE、出库关联/FIFO边界、分母/历史覆盖需确认；不从零库存或OWS默认箱规猜状态。

实际验证：国内仓pytest **38 passed, 3 skipped, 1 warning**（无独立PG配置的3项迁移演练测试跳过，本轮未接真实PG）；Vitest两文件 **9 passed**；Edge Playwright批次+打包 **6 passed**，最终状态展开可见增补用例 **1 passed**；tsc --noEmit、scoped ESLint、Ruff和git diff --check通过。用例覆盖账号隔离、仓库、旧发布、第一页外选项、同名UID、身份歧义、店铺名冲突、列表统计交集、路由权限/422和失败重试。测试全合成，不依赖生产/真实领星。

本地匿名探测：localhost:5173/api/pmc/domestic/inbound-batches/filter-options 与列表均 **401**，没有此前404；这仅说明匿名访问的鉴权结果，不证明登录态真实数据验证完成。尚需在用户已登录页面核对真实选项/筛选。未重启任何用户后端或生产服务。

安全边界：本轮无DB连接/写入、无schema/migration变更、无.env/密钥变更、无领星真实调用、无权限模型变化、无旧系统修改、无提交/推送/部署。只读参考旧业务文档，未复制旧架构。项目内 backend-module-designer/react-component-architect 辅助；未用外部部署Skill。

命令：backend .venv/Scripts/python.exe -m pytest tests/modules/pmc_domestic -q --disable-warnings -p no:cacheprovider（basetemp在任务artifact目录）；frontend vitest run domesticWarehouseApi.test.ts domesticInboundPreview.test.ts；tsc --noEmit -p tsconfig.app.json；scoped ESLint/Ruff；PLAYWRIGHT_CHANNEL=msedge playwright test e2e/domestic-warehouse.spec.ts e2e/domestic-packing-structure.spec.ts。官方核对 SQLAlchemy2 Select.exists/group_by/having（docs.sqlalchemy.org/en/20/core/selectable.html）及 AntD Select（ant.design/components/select/）；沿用已安装API，无依赖升级。

下一步：用户登录态核对新选项与list/summary；状态数据方案确认后，先解决SP契约禁用和归属/分母，再独立实施数据基础，不能未经批准执行候选新表或真实同步。

## 2026-10-20 本地数据库重新采集与发布（最新环境指令）

负责人明确“当前项目连接的是本地数据库……重新拉取一遍30日，存到本地数据库，不要再动生产数据库”，补充“完善下表数据，我需要批次看板接口能查询到数据”，并授权本次任务全部执行不再询问。此指令覆盖之前的生产目标讨论；旧生产执行记录仅为审计，不可复用为新生产操作授权。

### 实际范围与安全边界

只使用 backend/.env 中本地 APP_ENV=local、127.0.0.1:55432/szzsbj_dev；URL驱动/host/port/db/query与连接后的数据库身份均核对，指纹9caf2d76b6ec467c，0049已存在，不新增迁移。项目仍dev，保留其他并发改动，未提交推送。没有修改.env/原有密钥/权限/用户/会话，没有部署或重启服务。

本地没有领星App凭据，文件采集在已有服务器凭据所在环境单独执行：仅加载LINGXING白名单变量，不加载生产DATABASE_URL；阻止PostgreSQL驱动import，网络DNS仅准openapi.lingxing.com:443。仅W1/W3，仓库惠州16168，2026-09-21（含）至2026-10-21（不含），源时区Asia/Shanghai，W1当前全量含零库存。读取服务器凭据不等于连接生产库；本轮**没有连接或修改生产数据库**，没有修改生产配置/服务。新采集不是复制上午生产库或复用旧CSV。

11页成功源响应，manifest/CSV/source_pages/压缩包逐项SHA256验证后下载至本地。源捕获时间2026-10-20 17:43（北京时间）。压缩包SHA256 348093ffa493eb8e3221260b7b9fe021b772c8468dd0028453e4eaa98709cd4a；业务原始文件和本地备份均归档在Codex artifact目录，不进Git。

### 表写入与结果

| 表 | 本次数据 | 说明 |
|---|---:|---|
| ods_lingxing_domestic_warehouse_statements | 1296 | 近30天流水 |
| ods_lingxing_domestic_batches | 1541 | 当前完整批次快照（必要输入，不只有三张表） |
| gov_domestic_board_publications | 1 | 当前发布2a185fd5-f4b5-47d2-a93d-3c2e78446f08 |
| mart_domestic_inbound_batch_board | 1454 | 当前版本全部展示行 |

前置本地custom-format备份473351字节，SHA256 bde7cfe48d2fd95a86885939acc60b226a52f8334106b02018cd90f38ba984f9，pg_restore --list核验通过。没有恢复/覆盖现有表。

复用国内仓handler的file-backed replay注入、Parser、RAW blob/ref、run/work-item和DataLineage导入，不把APP_ENV伪装为production，不降低现有production-only网络同步门禁。必要的五组本地接口/同步配置/保留策略由既有bootstrap登记，默认关闭；仅导入期间受控启用两项并最终关闭，没有定时任务。两条成功本地run：W1 6a814612-9198-4c70-987d-c588b60450b1；W3 34c8ac16-aa9e-4a3d-9362-f70d27c1d388。原收货DWD与/batches不改，不填虚构收货明细。

核对：1454展示行、1375入库单、758 SKU，批次余额5420件、已知父级入库量26365件，1200组父级历史入库量未知，到仓日期缺失0；当前版本1个。入库日期北京时间已处理。所有当前MART源字段与新捕获重建一致；首个严格比较发现4行inbound_events数组顺序不同（数据库读取同时间戳记录顺序不保证），独立校验按证据项排序后全部字段一致；没有重复导入或另建发布掩盖差异。首次核验诊断保留于artifact，最终completed以独立核验为依据。

### API 验证及未完成的登录前提

真实本地DB、只读事务的TestClient路由联调，使用明确标注的synthetic principal/scope依赖注入：列表HTTP200、total1454、首屏50；summary/options/detail/trace均HTTP200，店铺筛选与统计交集一致。店铺选项9个；负责人0个，因为本地尚无产品负责人主数据，不在本任务新增同步。

运行中8011和Vite5173的匿名请求均401。**本地app_users=0、app_sessions=0**，真实浏览器登录态尚不能验证，不能把上述TestClient200宣称为运行服务已登录HTTP200。本任务未创建管理员、伪造运行服务Token或放宽认证；登录初始化需要独立处理。业务数据已具备，新接口查询路径：`/api/pmc/domestic/inbound-batches?page=1&page_size=50&sort=inbound_date_desc`；旧`/batches`仍为收货明细，不返回本次入库MART。

### 执行与交接

实际运行：local-only preflight、独立Lingxing file capture、scp下载及hash验证、pg_dump本地备份/目录核验、两项file-backed RAW→ODS导入和MART发布、独立全字段/summary/trace核对、真实本地DB路由联调。应用代码未修改，无需重复已有38/9/6合成回归；本次验证不是生产测试，也不声称已做浏览器登录验收。来源/入库/版本血缘保留。源文件和备份路径见本地artifact的local-import-evidence.json及capture-safety.json。

下一步仅需本地登录初始化后核对运行服务；负责人主数据和六状态数据源仍按各自范围推进，不应因本次导入自动上线定时、扩大历史窗口或再次访问生产库。

## 2026-10-20 本地用户导入完成（取代“本地用户为0”的旧状态）

负责人明确授权把生产用户数据导入本地以恢复登录，并确认目标为szzsbj_dev而非szzsbj_test。本轮只读连接生产：default_transaction_read_only=on、REPEATABLE READ、transaction_read_only=on；核对原生产身份指纹1029699bdbcf02fc。生产未写入、未改配置、未重启。仅七表IAM快照经已验证SSH在进程内存传输，用户资料/密码哈希未写源dump、日志、聊天或Git；未复制生产会话、重置令牌、生产审计。

本地目标127.0.0.1:55432/szzsbj_dev/public，导入前用户与会话均0；先完整custom-format本地备份并核验pg_restore目录，备份1354412字节、SHA256 c118d59d67c564af730106302d9f0e5ed83740ee1196a56fbde0109fbd7fbc51。单事务导入、保留用户ID及全部原字段、原密码哈希、启停/超级管理员标记；角色ID冲突则拒绝；角色授权和范围按源精确替换而非并集合并，不扩大已有生产授权；用户序列校准。源数据和导入后哈希/用户字段/授权逐项内存比对一致，不输出值。

结果：app_users29（启用28、超级管理员1）；app_roles6；app_user_roles29；app_role_permissions112；app_role_data_scopes5；app_user_data_scopes0；app_permissions本地160，源159，保留本地额外1条权限定义但不自动授权。会话未迁移，导入后0，用户需重新登录，原生产用户名/密码校验数据保留。国内仓MART仍1454，不改其它业务数据；.env、认证逻辑、数据库结构均未改；仍dev、未提交推送。

Navicat只读核对脚本：docs/delivery/local-iam-import-verification.sql，5条查询已在本地只读事务实际执行通过，检查目标、11张表计数、用户角色、启用/管理员数量、当前发布1454。脚本不查询密码哈希/Token；app_sessions在正常登录后自然增长不应固定为0。没有使用未知生产明文密码做实际登录验证，不声称已验证某个真人的原密码登录200。

详细安全证据存Codex artifact local-iam-import-20261020/import-evidence.json，仅计数/范围/校验结论，无密码哈希或用户资料。后续只在本地正常重新登录；不要因为本轮读取授权继续写生产或迁移生产会话。


## 2026-10-20 采购看板本地数据已导入

负责人授权全量采购看板依赖复制到local 127.0.0.1:55432/szzsbj_dev/public。源生产只读，未重新采集领星；采购来源最新观察时间10-17 18:00:43，不能把10-20本地重算时间视为采集时间。27张非空来源表及完整FK父记录、每条相关记录最新血缘已导入，人工覆盖源为0。核心结果：DWD计划1119/采购单784/明细867，DWS看板867/周期652/重算后待处理711；店铺9、Listing3223、SKU当前资料1435、产品1301。接口只读真实本地DB合成鉴权联调200：看板867、待采购计划196、负责人17；店铺/负责人筛选和带收货详情通过，匿名401，真人浏览器登录态未代替验证。原国内仓1454/用户29保留，所有本地同步/定时/外呼关闭。没有改schema/env/认证/生产或部署。执行与逐表清单：PRPs/pmc-purchase-local-data-execution.md；Navicat：docs/delivery/local-purchase-import-verification.sql，7查询已实跑。仍dev、未提交推送。


## 2026-10-20 国内仓打包单审批本地M1

来源决策READY_FOR_PRP及负责人本轮授权；四表OPS发号/订单/分配+EVT事件，0050接本地0049，保留已有迁移及业务资料。候选来自当前入库MART×符合条件Listing；builder v2把既有ODS良品/锁定证明规范化到MART payload，本地重新发布保留旧版，当前1454行。GET不查ODS、不调用外部。8个API见pmc-domestic-packing-approval-api.md；POST独立动作权限，可信账号隔离、幂等/并发库存/统一北京日发号/不可变事件。前端真实列表、审批弹窗、筛选/重试/分页及历史审计已接通。所有写入仅本地验证is_test=true，生产写保护；原采购与IAM保留，未自动授权角色。AD/manual/OWS/装箱/六态为后续切片。验证与逐表记录：docs/delivery/pmc-domestic-packing-approval-verification.md。继续dev，未新建分支/提交/推送/部署。

最终本地验证：待审44（阻断6），3通过/1驳回、3分配/4事件；当前入库1454、历史总2908。57后端通过/3跳过、6前端单测、真实本地E2E1项及UI契约2项均通过；临时验证服务已停。详细交付与逐表影响见docs/delivery/pmc-domestic-packing-approval-verification.md。

## 国内仓打包审批M2：最终手工流程（2026-10-21）

2026-10-21，当前dev，本地127.0.0.1:55432/szzsbj_dev。最终范围是手工添加打包单与审批前同SKU商品身份修改；系统打包单管理已按负责人要求删除。没有生产访问、提交、推送或部署。

流程：先选择当前批次看板的入库单×SKU，再选择同账号同SKU的有效Listing目标店铺/ItemID；GTIN/MSKU跟随Listing，不能自由修改SKU。填写数量、报关、收货仓备注和原因后，仅保存待审批申请，不发PK、不分配库存。通过审批时重新核对当前来源和Listing指纹、库存上限，并在单事务中发PK、分配原来源库存和写不可变审计；驳回需要原因。多个手工申请共用原入库库存池，可分批审批但不可超量。

跨店铺以当前批次看板入库单为依据，保存原始和目标快照，不要求不存在的领星审批/转移单，不修改领星库存归属。缺少报关信息默认不报关并标记default；人工选择标记manual。未知到货数量保持未知。全部审批仍受local-only/is_test保护，不创建领星OWS或调用WFS。

手工新增需独立packing-manual-create动作权限；页面只读权限不能提交。既有approve/reject动作和来源账号隔离继续生效，不自动授予角色或用户权限。

本轮本地历史：0051已执行，保留其迁移历史；0052接0051，已在全库备份并检查pg_restore目录后仅应用本地。0052确认OWS关联表为空后删除，停用3条系统管理动作定义；新增ops_domestic_packing_manual_requests，保存来源复合外键、来源/目标快照、数量、报关、备注、原因、操作者、请求JSON/哈希、账号幂等键和UTC提交时间。原发号/审批/分配/事件四表沿用；orders的原快照与最终身份字段用于审批，0051剩余兼容字段不代表存在系统管理功能。

负责人最新要求：后续本地开发不再自动新增或执行迁移编号。本次不增加0053，不回退现有0051/0052。未来结构调整记录SQL及影响；上线前必须单独整理最终生产迁移方案，从生产实际版本验证，不把本地迁移历史直接当作发布批准。当前代码依赖新表/字段，不能只部署代码。现有local-only审批保护也不代表生产写入已开放。

前缀 /api/pmc/domestic/packing-approval，复用标准success/data/error/meta/request_id响应。

|方法/路径|用途/参数|权限与校验|
|---|---|---|
|GET /manual/sources|入库单×SKU来源，keyword/page/page_size及既有PackingQuery筛选|页面读+来源账号；当前发布惠州仓；余额含本地分配扣减|
|GET /manual/{board_id}/options|source_account_ref，返回来源指纹与同SKUListing身份及listing_version|页面读+来源账号；不跨账号|
|POST /manual|source_account_ref、warehouse_id=16168、board_id、source_version、target_store_id、target_item_id、listing_version、qty、customs、rwh、reason、idempotency_key|manual-create+local guard；同SKU/当前有效Listing/可用量/原因；响应id和pending|
|GET /pending/{candidate_id}/edit-options|source_account_ref，读取候选与目标身份|适用于自动候选或手工申请|
|GET /pending、/pending/summary|沿用现有列表及统计，追加origin=manual待审行|手工来源变化时阻断，成功审批后退出待审|
|POST /pending/{candidate_id}/approve、/reject|沿用既有命令，approve扩展目标店铺/ItemID、listing_version、edit_reason|独立approve/reject；单事务幂等、并发库存、审计|

其余历史及事件接口保持。/packs及/orders/{id}/link、/void、/test-flag已删除。来源、Listing、库存或状态变化返回冲突而非假成功。完整原接口契约见pmc-domestic-packing-approval-api.md；具体模型以packing_schemas.py为准。

验收证据：docs/delivery/pmc-domestic-packing-approval-m2-verification.md。

## 2026-10-21 报关与操作列最终调整

下拉仅有“报关”和“不报关”，列表、手工添加、审批弹窗一致，没有可选“默认规则”。初次显示服务端自动结果，未修改时内部命令仍为default，并非前端第三个选项；用户选择后命令declare/skip，结果标记manual，随审批保存，列表暂存不直接写库。

优先产品purchase_remark（当前DWD产品快照所指原始成功响应，按商品ID精确匹配）。字段存在但为空视为无明确备注，默认false；字段不可用时回退同账号同SKU当前DWD所指ODS采购计划/采购明细item_purchase_remark/remark/plan_remark。否定词优先。采购兜底最新明确不报关优先，否则任一历史当前单据明确报关则报关，否则默认false。单据只读取DWD当前版本所指ODS，不能累加同一单据历史旧版本；拆分采购行去重。

既有MART payload新增customs_proof：value(bool)、source(default/product_remark/purchase_remark)、rule(domestic.customs.v1)、field、remark(最多500字)、ref(来源RAW引用或ODS记录UUID)、observed_at。Candidate映射customs_default、customs_default_src与customs_proof，来源证据进入candidate_version；default命令由后端取当前自动结果，人工选择记manual。订单现有customs_value/customs_src及JSON快照/不可变事件保存审批结果，不覆盖历史。旧无证据快照兼容默认false，不追写历史审批。

数据整理在既有发布流程完成，正常业务GET不访问RAW/ODS、不调用领星；CSV不带该新增数据库备注证据，不能声称CSV和本次备注富化字段相同。未改库存、商品身份和到仓日期。

本地备份后重建当前1454行发布版本，其中155行产品采购备注判定报关，1299行默认不报关；旧发布版本保留，MART历史总4362。迁移仍0052，无新表/字段/约束、无0053，历史4审批/3分配/4事件和用户29保留。

操作列“修改”普通按钮、“审批通过”蓝色主按钮、“驳回”普通按钮，统一间距和最小280px列宽（兼容已有窄列设置），权限/业务阻断逻辑不变。当前仅进行本地本模块验证，不进行全局测试；全局回归待用户后续功能全部完成后统一安排。

最终本地结果：60项本模块后端检查通过（含原入库发布兼容；现有Pydantic测试1个弃用提示），3项Playwright页面验收通过；相关前端ESLint通过，双选项实现阶段TS检查通过。本轮不是全局测试。一次与临时回滚E2E事务并行的后端运行出现2项发号锁等待超时；停止临时事务后单独重跑60项全部通过，未修改业务锁逻辑。

只读本地真实数据库、合成鉴权路由核对：pending HTTP200/44行（4 product_remark报关、40 default不报关）；inbound HTTP200/1454行。最终4审批/3分配/4事件、0手工申请/0合成MART、用户29。GOV3发布版本/MART历史4362，旧版保留；数据库版本仍0052。临时8012与4173验证服务已停止。普通用户实际登录态和全局回归不由合成鉴权验收替代，待后续功能全部开发完统一测试。没有提交推送、生产连接或生产修改。


## 2026-10-22 国内仓 0054 迁移安全补充验收（dev）

负责人本轮明确授权直接在 dev 修复剩余问题、不新建分支、不新增 0055，并确认旧版没有 extra 建表逻辑的 0054 从未执行。开始工作区干净，base c76208c。未提交、推送、合并或连接生产数据库。

补齐 ODS/0053/0054 的完整结构接管校验（列类型/长度/非空/默认值、PK/UQ、FK schema/动作/验证状态、CHECK、有序有效索引），ODS 部分缺表拒绝接管；0053 五表冻结建表参数 AST 对照不变。0054 保留双父依赖与 extra 建表，并拒绝危险删表降级。测试仅创建随机专用库且只销毁本进程拥有的库；CI 扩充 ODS/安全/静态链测试并拒绝跳过。

最终真实 PostgreSQL 14.24 验收：56 passed、0 failed/errors/skipped，170.39s。24 项链/业务 + 14 项 ODS + 13 项静态链/迁移环境 + 5 项库保护。空库和带合成 ODS/DWD/当前发布/MART 的真实 0049 均到 0054；旧表逐行快照不变、20 表存在且 ORM 可查、实际库存/额外分配/仓库列表通过、0052 非空 OWS 历史阻断、漂移与同事务 DDL 回滚通过。所有一次性测试数据库已销毁，独立测试实例已停止。全后端 Ruff lint/format 532 文件通过，app.main 导入通过；新 helper 定向 mypy（follow-imports=skip）通过，不代表全项目 mypy。

全部 62 个完整 revision：一根、一 head（20261022_0054_merge_walmart_identity_and_domestic_packing），无重复、缺失父节点、孤立或循环；国内仓 0047–0049 文件 Blob 与开始 HEAD 一致，未改历史 ID/版本表。完整文件清单、依赖链、20 表正式来源、命令、风险和生产申请前置项见 docs/delivery/domestic-chain-0054-validation.md。

待负责人审核后自行决定提交/推送与 PR #242；本轮未发布修改，不能声称 GitHub PostgreSQL 16 已验证。生产实时版本/结构及 staging 已执行 0047–0049 Blob 尚未核实。若有非空 OWS 历史保持原版本，先审查业务归档/迁移方案，禁止清空/stamp 绕过。0054 仍是建议目标，不执行任何生产迁移或部署。

## 2026-10-27 PR #260 Listing 监控 RAW 投影与预览修复

负责人批准在现有 PR #260 分支中完成 Listing 计算修复与监控 RAW 消费。实现保持一个统一 RAW 事件模型：`raw_walmart_monitor_events` 经过不可变 L3 观察表 `std_walmart_monitor_listing_observations`，再投影为 L9 当前态 `mart_walmart_monitor_listing_current`。Listing 查询仅按 `source_account_ref + store_id + item_id` 覆盖标题、划线价、在售价、类目、购物车状态、Walmart 卖家、是否被跟卖、评分、评论数和品牌；监控值为空时回退原 Listing 值，显式 `false` 和 `0` 不会被当作空值。监控来源、图片、错误码、RAW 事件标识与原始类目不进入页面响应。

一个页面结果对应多个稳定目标身份时会在同一事务内逐目标投影。最终失败事件保留 L3 证据，但不会覆盖最后一次成功的 L9 当前态。受控历史回放脚本默认回滚，生产提交还需要显式开关与确认令牌；本任务未执行数据库迁移、RAW 回放、同步、外部 API、部署或生产访问。

PR #260 原有预览同时修复：批处理固定使用同一规则版本、UUID keyset 分页、所有排除生命周期清除等级候选、监控日观察作为生命周期证据，以及 Celery 调度 advisory lock 在物理连接上跨提交保持。财务证据完整性仍会阻止正式等级发布；本切片不启用正式发布或生产调度。

验证：定向后端 `53 passed`；合入最新 main 后完整后端 `1825 passed, 127 skipped`；完整前端单 worker `61 files / 292 tests`、lint 和 build 通过（lint 保留 main 既有 1 条 Hook warning）；Ruff `659 files` format/lint、应用导入、回放 CLI help、Alembic 单 head `20261028_0066_walmart_monitor_listing_projection`、离线迁移检查、rule-pack 与 PR 净差异检查通过。集中 mypy 仍被仓库既有 repository/service 类型债务阻断，新增监控投影文件没有直接报告的新错误。所有验证使用合成数据，没有输出或提交商品标识、账号、Token 或 RAW payload。
