# 国内仓前端交接

日期：2026-10-19；主执行角色：前端工程师。
用户明确授权直接在dev实现，不创建分支；无提交、推送、部署授权。

## 后续任务：打包单（仓库）结构

用户已选择“只做页面结构，不做示例交互”。已启用packing页签，增加5个页面专属文件、结构浏览器测试；仅保存筛选/分页/列宽界面设置，无打包示例订单、模拟装箱、业务保存或完成状态。
新增打包页不发出业务API请求，操作入口禁用。批次查询Hook增加enabled边界，打包页激活时不请求批次数据。
TypeScript、ESLint、6项既有Vitest与5项结构/批次Playwright回归通过；额外分页可见性断言后2项结构验收再次通过，最终截图已查看。构建通过（主包体积提示仍在）。
详见docs/frontend/domestic-packing-warehouse-structure.md；该任务没有改变之前批次页面的只读数据边界，没有实现打包后端。以下原交接中的“打包未实现”特指真实业务，不再表示页签结构未开放。

## Task / Workspace

仓库 C:/Users/treas/Desktop/work/SZZSBJ；dev；任务开始基线986f355bf8f4acc3e894dfbf3abc81d636570888；worktree为当前仓库；PR未创建。
开始时已有.gitignore、后端/权限/迁移代码、docs/data-registry/DATA_INTERFACE_REGISTRY.md、docs/frontend/PAGE_REGISTRY.md及表设计文件改动；本任务未编辑这些已有改动。

## Implemented

单个国内仓批次页面，复用采购看板使用的共享搜索/表格/分页/列宽/列设置/统计组件；独立类型、API客户端和Query hooks。
只消费工作区已有只读batches/summary/trace路由；不修改后端。列表筛选、排序、分页和详情可接入该契约，尚未验证真实环境部署。
收货单日期用于到仓日，缺失保持未知。缺少的产品、ItemID、负责人、装箱/出库指标显示未接入，不填假数据。
增加客户端契约测试、PMC占位测试调整、合成数据浏览器验收和可新标签打开的静态SOP。

## Files changed

- 本目录：页面、CSS、类型、API、hooks、四个页面专属组件、客户端测试、本文。
- frontend/src/router/routes.tsx：渲染现有国内仓导航路径。
- frontend/src/config/navigation.ts：本页testing/来源与既有后端权限元数据。
- frontend/src/pages/pmc/pmcPlaceholderPages.test.tsx：保留WFS/物流占位断言。
- frontend/e2e/domestic-warehouse.spec.ts、frontend/public/help/domestic-warehouse.html。
- PRPs/pmc-domestic-warehouse-frontend.md、docs/frontend/domestic-warehouse-page.md。

## Validation

执行本地TypeScript、目标ESLint、Vitest客户端/导航以及Playwright。使用node直接执行项目已有CLI，因为当前PATH没有npm；没有安装/升级依赖。
默认Playwright Chromium缺失，本地以PLAYWRIGHT_CHANNEL=msedge使用已安装Edge；CI未设置该变量仍用默认Chromium。
早期测试失败涉及fixture envelope类型、测试拦截误匹配/src/api模块、图标可访问名称和排序下拉定位；均作为本任务修复，不修改共享组件。
最终结果：TypeScript通过；目标ESLint通过；Vitest两个文件共6项通过；Playwright三项通过（本机Edge，合成数据）；Vite生产构建通过。构建提示主包体积超过500kB，此任务不做无关的全站打包重构。
命令：node node_modules/typescript/bin/tsc -b；node node_modules/eslint/bin/eslint.js <本任务文件>；node node_modules/vitest/vitest.mjs run <客户端测试> <PMC占位测试>；node node_modules/@playwright/test/cli.js test e2e/domestic-warehouse.spec.ts --workers=1；node node_modules/vite/bin/vite.js build。
已查看稳定状态下截图，确认桌面表格可读、横向滚动限制在表格内部；窄屏包含性由浏览器断言覆盖。没有宣称真实业务数据联调通过。

## Context / docs checked

AGENTS、frontend/AGENTS、UI规则/组件目录/设计规范、采购看板实际代码、pmc_domestic当前schema/router、Ant Design 5.29.3官方Table/Tabs、TanStack Query v5取消请求文档。
使用项目内 skills/react-component-architect/SKILL.md 完成组件拆分；未新增外部Skill依赖。

## Risks / Explicitly not implemented

无数据库、.env、真实业务API、旧系统、依赖或迁移修改。既有权限体系未变；客户端不能替代后端数据权限。
打包、审批、对账未实现，仅待开放页签；通知与导出不在范围。未完整接入的指标不可宣称国内仓业务已上线。
来源观察时间由接口meta展示，不等于全系统统一快照版本；未来跨指标一致性需后端契约支持。
注册总表任务开始已有改动，本次以独立页面实施记录保存消费契约，后续合并评审需核对总表最终版本，不覆盖他人记录。

## Rollback / Next step

仅撤销本清单，保留既有采购、后端及.gitignore改动；无业务数据需要回滚。不创建/删除worktree、不提交推送。
下一步联合验证后端已部署契约和账号权限，再逐项接入缺少的字段；保持testing。

## 后续页面调整（2026-10-19）

打包单（仓库）按用户确认仅完成页面结构，无示例交互、打包业务请求或真实写操作；实施记录见 docs/frontend/domestic-packing-warehouse-structure.md。
批次筛选按截图改为两行：店铺、负责人、六种业务状态、类型搜索/批量入口/蓝色搜索按钮、收货单日期、更多筛选；第二行重置、统计显隐、列设置、禁用导出。
业务状态后端尚不支持，选择时阻止查询并清空结果，明确提示未接入；不发送虚构参数。关联状态和排序移入更多筛选。SKU、采购单、收货单支持最多50项去重精确查询，入库单使用综合匹配。负责人和ItemID/GTIN/MSKU禁用，店铺暂按ID输入。
ConnectedSearch与CommittedSearch新增可选searchButtonText/batchPlacement，原消费者默认样式和顺序不变；新增共享组件测试与目录登记。
最终回归通过：4个Vitest文件16项（含采购看板）；2个Playwright文件6项（含打包结构）；TypeScript、目标ESLint、git diff --check及生产构建。已查看最终1920px筛选区截图；构建仍提示既有大包警告，Vitest有jsdom伪元素样式未实现提示，均未导致失败。
无后端、数据库、权限模型、旧系统或.env修改；保留其他未提交改动，不提交、不推送。

## 店铺与当前负责人下拉增量（2026-10-19，覆盖上文对应待接入项）

负责人已明确确认“同意补齐后端，按当前产品负责人”。数据源决策为 docs/data-sources/decisions/pmc-domestic-filter-options-decision.md，施工图为 PRPs/pmc-domestic-filter-options.md。继续dev，不提交/推送；保留其他工作区改动。

### Done / Files changed

- backend/app/modules/pmc_domestic/{schemas,repository,service,router,registry}.py：GET filter-options、稳定ID/UID选项、列表/统计共同owner_uid筛选。沿用现有权限与账号范围，不依赖Listing权限，不读旧库/ODS/RAW。
- frontend本目录类型、API、Query hook、DomesticWarehousePage及DomesticToolbar：ReportFacetSelect搜索、多选确认、清除/重置、50项限制、加载失败重试、用户范围缓存；打包页不发选项请求。
- 后端test_read_service/test_router、前端客户端测试与两份国内仓E2E；API文档目录增加PMC真实契约及对应目录测试；nav来源登记扩充。
- 正式决策/PRP、.planning/current、API Markdown、数据接口与页面登记、SOP、页面实施文档和本文。未更改新表/迁移、外部集成、权限策略或他人的其他代码。

### Commands / Tests

使用现有node直接运行CLI，未安装依赖。pytest tests/modules/pmc_domestic -q -p no:cacheprovider（SQLite内存合成数据）13项通过；Vitest客户端/共享搜索/PMC导航/API目录4个文件13项通过；Playwright批次6项+打包结构2项通过；新增多选流程截图再次单项通过。TypeScript、目标ESLint、目标ruff、5个后端文件mypy及Vite构建通过。构建仍有既有大包提示。选项错误测试按失败开关模拟，适应开发模式取消/重新挂载请求；窄屏检查等待Drawer关闭动画后再测，不以固定sleep遮盖问题。

### Context / docs checked

项目规则、数据分层与字段标准、现有采购/Listing和实际国内仓契约。使用项目内skills/backend-module-designer/SKILL.md与skills/react-component-architect/SKILL.md分层；未引入外部Skill依赖。核对SQLAlchemy 2.0 Select/group_by/having、FastAPI query parameter model官方文档；本地实际类型检查验证安装版本。

### Risk / Acceptance / Next step

可见批次店铺跨平台覆盖，名称缺失/歧义展示ID；当前负责人通过同账号+SKU唯一active身份匹配，同名不同UID不合并，歧义/缺失不猜。列表和统计同条件，不用当前页凑选项或统计。行内负责人展示仍无契约，六种业务状态仍待后端支持，保持testing。
无真实数据库/生产连接、.env、外部API、业务写入、迁移或部署；仅测试创建SQLite内存库。新接口继承现有权限，无新增角色/授权策略。无业务数据回滚；撤销本切片明确增量即可，不撤销国内仓已有其他代码。
下一步在获准的测试环境验证已有五张表及数据新鲜度、账号范围与实际查询计划；本任务不运行真实同步或连接生产环境。


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


## 2026-10-20 国内仓打包单审批本地M1

来源决策READY_FOR_PRP及负责人本轮授权；四表OPS发号/订单/分配+EVT事件，0050接本地0049，保留已有迁移及业务资料。候选来自当前入库MART×符合条件Listing；builder v2把既有ODS良品/锁定证明规范化到MART payload，本地重新发布保留旧版，当前1454行。GET不查ODS、不调用外部。8个API见pmc-domestic-packing-approval-api.md；POST独立动作权限，可信账号隔离、幂等/并发库存/统一北京日发号/不可变事件。前端真实列表、审批弹窗、筛选/重试/分页及历史审计已接通。所有写入仅本地验证is_test=true，生产写保护；原采购与IAM保留，未自动授权角色。AD/manual/OWS/装箱/六态为后续切片。验证与逐表记录：docs/delivery/pmc-domestic-packing-approval-verification.md。继续dev，未新建分支/提交/推送/部署。

最终本地验证：待审44（阻断6），3通过/1驳回、3分配/4事件；当前入库1454、历史总2908。57后端通过/3跳过、6前端单测、真实本地E2E1项及UI契约2项均通过；临时验证服务已停。详细交付与逐表影响见docs/delivery/pmc-domestic-packing-approval-verification.md。
