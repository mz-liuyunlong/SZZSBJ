# 国内仓本地同步任务

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
