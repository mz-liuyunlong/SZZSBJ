# 惠州仓入库/批次数据：先采集 CSV

本入口不连接数据库，不需要DATABASE_URL，也不要求APP_ENV=production。复用现有Token Manager和查询签名客户端，使用独立的文件采集配置模型；不会绕过真实请求开关。

先在领星核实当前账号下惠州仓库ID、所需时间窗及源时间时区。不要把WFS虚拟仓28030当惠州仓；旧项目16168也须重新核实。浏览器登录会话不替代开放接口App凭据。

## 1. 文件采集配置

凭据由既有安全运行环境提供，不输入聊天、不写命令参数、不提交.env：

```text
LINGXING_APP_ID
LINGXING_APP_SECRET
LINGXING_BASE_URL=https://openapi.lingxing.com （可省略默认）
LINGXING_ENABLE_TOKEN_REQUESTS=true
LINGXING_ENABLE_REAL_CALLS=true
PMC_DOMESTIC_CSV_EXPORT_AUTHORIZED=true
```

默认所有真实请求开关关闭。使用方自行在获准环境设置，不在本次代码变更中修改真实配置。

在backend运行（尖括号内容由负责人替换）：

```text
uv run python scripts/export_pmc_domestic_inbound_csv.py --source-account <来源账号引用> --warehouse-id <惠州仓库ID> --start 2026-09-01 --end 2026-10-21 --output <新的采集目录>
```

以上日期仅为示例，不代表首次采集窗口已获确认。end不包含；代码按30天拆分W3窗口，W1请求包含零库存。源时区确认后可加 `--source-timezone Asia/Shanghai`，未确认就省略，业务日保持未知。支持 `--max-pages` 全局页数上限。

采集只允许官方HTTPS origin，不允许把App凭据发送到网页接口或任意代理地址。IP白名单、App接口权限由已有领星配置管理。

## 2. 输出与验收

- warehouse_statements.csv：W3库存流水，保留statement_id和正负数量。
- batch_details.csv：W1批次明细，数组以JSON完整保留。
- inbound_board_preview.csv：相同纯构建器的IB×SKU×归属预览。
- source_pages.jsonl：脱敏来源响应和分页参数，可回放；仍为业务数据，按项目数据访问范围保存，不能提交Git。
- requests_log.jsonl：脱敏请求路径、分页和结果，不含凭据。
- manifest.json：complete、来源窗口/账号/仓库、来源时间、各CSV行数及SHA256、失败代码。

CSV使用UTF-8 BOM；null为 `\N`，源字符串开头反斜杠双写；数组保留JSON。ID按文本导入，不能让Excel自动转换18位ID；精确源类型以JSONL为准。

目录必须不存在；失败保留complete=false的manifest和已收到的来源页，不覆盖上一次成功结果。缺页、总数变化、重复身份冲突、仓库不符、超出页数或源失败都不可作为完整结果入库。空结果也必须有成功来源页和完整性证据。

CSV成功只表示文件采集/预览完成，不会自动填充 `/inbound-batches`。本次开发没有运行真实采集。

## 3. 可选的数据库路径（本轮不执行）

数据库路径仍走现有集成治理：先在明确数据库迁移0049；`bootstrap_pmc_domestic_governance.py`登记元数据默认关闭；新增domesticWarehouseStatement与原domesticBatchDetailList均须显式启用并限定账号。使用原 `run_pmc_domestic_once.py` 选interface_key，可逐个有界窗口运行；此入口保留原环境/审批门禁。不要把文件命令改成production环境来绕过配置。

W1现在显式包含零库存并记录于safe params；旧的未包含零库存run不能发布本看板。W3用新的独立ODS表，不写入原批次流水表。任务编排复用既有integration_sync Celery执行器，无新增周期任务。

发布入口单独要求 `PMC_DOMESTIC_INBOUND_DB_PUBLISH_AUTHORIZED=true`，使用目标环境已配置的数据库；无领星调用：

```text
uv run python scripts/publish_pmc_domestic_inbound.py --source-account <账号> --warehouse-id <惠州ID> --batch-run-id <W1成功run UUID> --statement-run-id <W3成功run UUID> --source-timezone <已确认时区>
```

多个W3窗口重复传 `--statement-run-id`；只接受同账号成功来源run，校验接口、零库存快照证据与连续窗口。缺配置、来源失败或gap时拒绝发布。发布事务保存旧版并切换当前指针，GET只读mart。

生产迁移/回填、真实DB发布、部署、权限授予不由此runbook自动授权。任何线上动作须单独核对目标和维护窗口。


## 页面核对与生产执行增量

国内仓批次页面已接入新API，CSV预览选择原始inbound_board_preview.csv与manifest.json；两者先经过完整性、SHA256、行数、账号/仓库与业务字段校验。仅浏览器内存读取，退出/刷新不保留，不向服务器上传，不写数据库。库表未就绪可先文件核对。

2026-10-20负责人另行授权生产迁移/首次同步，精确范围及实际执行状态见PRPs/pmc-domestic-inbound-production-execution.md。同步入口现在支持PMC_DOMESTIC_WAREHOUSE_ID，仅W1/W3；必须显式限制惠州仓，源请求和safe params记录wids，返回其他仓库时失败，不发布。原未限定仓库的旧run不应用于本次执行。


实际首次执行采用30天窗口2026-09-21至2026-10-21（不含）。时区已确认Asia/Shanghai。新表/导入/发布已执行，代码部署和后端重启不包含在内。ODS审计复用run/work-item和DataLineage，gov_parse_jobs的DWD-only契约保持不变。建议后续同步继续显式指定仓库、窗口、环境、授权与来源run，不沿用本次一次性授权。

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


> 占位名称说明：`LOCAL_DATABASE_NAME` 与 `ISOLATED_TEST_DATABASE_NAME` 分别表示负责人已批准的本地开发库和隔离测试库；执行前必须与获批本地配置中的实际数据库名逐字核对，并同时核对环境、host、port及连接后数据库身份。占位名称不是可直接执行的数据库名，也不授权其他本地库或生产库。历史数量、指纹及备份哈希保持原记录。
