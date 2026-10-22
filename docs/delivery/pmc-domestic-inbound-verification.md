# 国内仓交付与审查边界

负责人要求在dev实现并保留现有前端改动，不创建新分支或自动提交。当前目录合并展示多个切片的未提交文件，不能整体暂存成混合PR。后续按以下边界逐项审查：

1. 前端：国内仓页面、客户端/hooks/types、CSV内存预览、组件、Vitest/E2E、SOP；复用Shared且不新增依赖。
2. 后端：独立入库API、纯构建/收集/发布、W3契约/解析及W1/W3仓库限定；旧收货API不变，CSV不要求数据库配置。
3. 数据库：0049三表create-only，前置0047接管/0048确认的生产执行、备份与恢复、治理元数据和首次导入记录；不混入业务页面PR。

已执行的生产动作由负责人明确授权，过程证据与回滚边界见PRPs/pmc-domestic-inbound-production-execution.md。跨切片必须保持契约兼容，部署/合并是独立动作。未修改旧系统、密钥、角色授权、生产服务配置和无关WFS计划；无自动Git暂存/提交/push。


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

只使用 backend/.env 中本地 APP_ENV=local、127.0.0.1:55432/LOCAL_DATABASE_NAME；URL驱动/host/port/db/query与连接后的数据库身份均核对，指纹9caf2d76b6ec467c，0049已存在，不新增迁移。项目仍dev，保留其他并发改动，未提交推送。没有修改.env/原有密钥/权限/用户/会话，没有部署或重启服务。

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

负责人明确授权把生产用户数据导入本地以恢复登录，并确认目标为LOCAL_DATABASE_NAME而非ISOLATED_TEST_DATABASE_NAME。本轮只读连接生产：default_transaction_read_only=on、REPEATABLE READ、transaction_read_only=on；核对原生产身份指纹1029699bdbcf02fc。生产未写入、未改配置、未重启。仅七表IAM快照经已验证SSH在进程内存传输，用户资料/密码哈希未写源dump、日志、聊天或Git；未复制生产会话、重置令牌、生产审计。

本地目标127.0.0.1:55432/LOCAL_DATABASE_NAME/public，导入前用户与会话均0；先完整custom-format本地备份并核验pg_restore目录，备份1354412字节、SHA256 c118d59d67c564af730106302d9f0e5ed83740ee1196a56fbde0109fbd7fbc51。单事务导入、保留用户ID及全部原字段、原密码哈希、启停/超级管理员标记；角色ID冲突则拒绝；角色授权和范围按源精确替换而非并集合并，不扩大已有生产授权；用户序列校准。源数据和导入后哈希/用户字段/授权逐项内存比对一致，不输出值。

结果：app_users29（启用28、超级管理员1）；app_roles6；app_user_roles29；app_role_permissions112；app_role_data_scopes5；app_user_data_scopes0；app_permissions本地160，源159，保留本地额外1条权限定义但不自动授权。会话未迁移，导入后0，用户需重新登录，原生产用户名/密码校验数据保留。国内仓MART仍1454，不改其它业务数据；.env、认证逻辑、数据库结构均未改；仍dev、未提交推送。

Navicat只读核对脚本：docs/delivery/local-iam-import-verification.sql，5条查询已在本地只读事务实际执行通过，检查目标、11张表计数、用户角色、启用/管理员数量、当前发布1454。脚本不查询密码哈希/Token；app_sessions在正常登录后自然增长不应固定为0。没有使用未知生产明文密码做实际登录验证，不声称已验证某个真人的原密码登录200。

详细安全证据存Codex artifact local-iam-import-20261020/import-evidence.json，仅计数/范围/校验结论，无密码哈希或用户资料。后续只在本地正常重新登录；不要因为本轮读取授权继续写生产或迁移生产会话。


> 占位名称说明：`LOCAL_DATABASE_NAME` 与 `ISOLATED_TEST_DATABASE_NAME` 分别表示负责人已批准的本地开发库和隔离测试库；执行前必须与获批本地配置中的实际数据库名逐字核对，并同时核对环境、host、port及连接后数据库身份。占位名称不是可直接执行的数据库名，也不授权其他本地库或生产库。历史数量、指纹及备份哈希保持原记录。
