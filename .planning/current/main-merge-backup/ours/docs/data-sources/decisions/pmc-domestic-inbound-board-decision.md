# 国内仓入库批次看板 M1：数据源决策

调查日期：2026-10-20（Asia/Shanghai）。主执行角色：架构师。

状态：READY_FOR_PRP，仅适用于本文限定的 M1；PRP 尚待负责人批准。此状态不是代码实施、真实采集或数据库写入授权。

存放说明：本文为当前工作区内可审阅交付；目标归档路径为 本项目 `docs/data-sources/decisions/pmc-domestic-inbound-board-decision.md`，本次实施同步归档到该项目。

## 1. 已确认需求与限制

- 只做国内仓的“批次看板”后端，主粒度为来源账号 + 仓库 + 采购入库单 IB + SKU + 店铺批次归属。
- 用户确认新增 `/api/pmc/domestic/inbound-batches`，后续再切换前端；原收货明细 `/batches` 不变。
- 仅惠州仓库。仓库 ID 通过当前来源账号的仓库清单核实；不直接使用旧系统常量或样本中的 WFS 虚拟仓 ID。
- 最近确认的真实数据运行方式是先导 CSV，不写本地或线上业务数据库。实现可包含模型、迁移和数据库发布能力，但真实执行不默认开启。
- 本期解决入库事实、批次余额、来源追溯、分页列表、基础统计；发货完成率、打包状态和跨店铺 FIFO 不在本期实现或伪装为已实现。

## 2. 证据

1. 用户文件：`C:/Users/treas/Desktop/工作文件/PMC交接文档_20261019.html`，第 5.2.1、5.2.2、5.2.5 节；第 2.1.17、2.1.19 节。
2. 文档明确主表为采购入库单 IB × SKU × 店铺批次；库存流水 2202 建行，批次明细补余额；旧构建实际不读收货单或 inventoryDetails。
3. 本地旧项目对应 `features/pmc-domestic-warehouse/drafts/build_from_daily.py`，仅作为业务证据，不作为新系统运行依赖或直接复制来源。
4. 本项目 `backend/app/modules/pmc_domestic/{models,publisher,schemas,router}.py`：现 `/batches` 为收货行；不能通过仅换字段名称改为入库事实。
5. 本项目 `backend/app/modules/integration_sync/pmc_domestic_catalog.py`：已有仓库、库存、批次、批次流水四个来源；缺少库存流水（新）的对应国内仓采集流程。
6. 官方批次明细：https://apidoc.lingxing.com/new/api-docs/Warehouse/GetBatchDetailList/
7. 官方库存流水：https://apidoc.lingxing.com/new/api-docs/Warehouse/WarehouseStatementNew/
8. 本项目 官方接口索引：库存流水（新）ID `LX-F0CE5B7F589B`，批次明细 ID `LX-1181D4F827FB`；索引登记不代表外呼已启用。
9. 用户提供网页 `/api/batch_detail/list` 单条样本：code=1，data.list，wh_id=28030/WFS虚拟仓，调拨入库 2401，收货和采购关联数组为空；不是惠州采购入库验收样本。

## 3. 强制来源调查

| 项目 | 结论 |
|---|---|
| 旧页面 | 国内仓 / 批次看板，静态快照主体 + 操作事件接口 |
| 旧 API | 原始数据由领星开放接口批处理采集；不是浏览器实时列表 API |
| 旧文件 | 旧构建脚本、daily_pull/run.py；只读参考 |
| 新系统读取表 | 原接口读收货 DWD；新增入库接口拟读独立 mart，不读 RAW/ODS |
| 新写入方 | 受控采集器 → RAW/ODS；发布 Service → 入库 mart |
| 调度 | 2026-10-24 起，同步任务页保存的 cron 可以执行这五项国内仓采集。流水类未带日期时按上海日期取最近 90 天。一次性脚本仍要求定时关闭。 |
| 人工写库 | 不新增；不以手工 SQL 拼造真实业务数据 |
| 外部重新获取 | 官方开放接口可重新采集；复用 Token/签名客户端 |
| 少量配置 | 账号、仓库允许清单、时间窗、源时区；不能用配置代替库存事实 |
| 短期 | 实现离线契约和 CSV 输出路径，真实采集单独按配置执行 |
| 长期 | 同一标准化流程发布 PostgreSQL mart，页面通过后端只读查询 |

## 4. 数据集分类

| 字段组 | 分类 | 权威来源 | M1 使用 |
|---|---|---|---|
| 仓库身份 | REBUILD_SYNC | 已登记 warehouse 开放接口 | 核实惠州 ID；配置固定后每行再次校验 |
| 入库事实/采购关联 | REBUILD_SYNC | wareHouseCenterStatement | 2202 的 IB、SKU、发生时间、ref_order_sn 和有符号数量 |
| 库存批次与余额 | REBUILD_SYNC | getBatchDetailList | 批次身份、店铺、余额、源头与关联单据数组 |
| 负责人/产品描述 | REBUILD_SYNC | 既有产品 DWD、批次品名 | 有唯一同账号身份时复用；歧义返回未知 |
| 发布版本/质量结果 | NEW_SYSTEM_OWNED | 本模块发布器 | 记录来源 run、时间、规则版本和当前成功发布 |
| 网页 batch_detail/list 样本 | ARCHIVE_ONLY | 用户提供的单条响应 | 字段对照与离线测试参考，不冒充全量开放接口结果 |
| 旧 CSV/旧代码 | ARCHIVE_ONLY | 交接材料 | 业务解释和对账参考，不作运行兜底 |

M1 不包含 NEED_OWNER_DECISION 数据集：无法证明的店铺数量分摊、日期、发货、打包、ItemID 不参与推断。未来接入这些指标需单独数据源决策，不能沿用本状态。

## 5. 核心字段与语义

| 对外字段 | 来源 | 处理 |
|---|---|---|
| inbound_order_sn / sku | W3 order_sn / sku | 账号、仓库一起隔离，不截取单号推断业务类型 |
| purchase_order_sns | W3 ref_order_sn、W1 purchase_order_sns | 保留完整集合和各自来源，不任取第一个作为唯一关联 |
| inbound_at_raw / arrival_source | W3 2202 opt_time | 正常行取最早有效入库事件；冲销后仍保留事件供追溯 |
| arrival_business_date | opt_time + 核实的源时区 | UTC 存储/Asia/Taipei 业务日；源时区未核实则 null 并标原因，不默认 UTC |
| total_inbound_qty | W3 2202 product_qc_num，0 时使用 product_total | 保留符号累计，与总量交叉核验；无变化证据/字段冲突时 unknown，不将 null 当 0 |
| available_qty | W3 2801 良品事件 | M1 不默认“未质检=全部良品”；质量过程不完整时 null |
| balance_num | W1 balance_num | 同一完整快照中按唯一批次去重后求和；缺批次不是零 |
| store_id | W1 store_id | 0/空为未归属；不同真实店铺拆行，未知余额保留未知归属行 |
| batch_nos / batch_details | W1 batch_no 等 | 保留批次级余额和 lineage，防止聚合后无法对数 |
| source_observed_at / publication_id | 采集元数据/发布器 | 与来源 update_time 区分；元数据不可称为来源业务更新时间 |

仅当入库数量具备店铺级直接来源证据时，才能给拆分店铺行填 total_inbound_qty。入库总量仅到 IB×SKU 时保留在父级事实：拆行 qty=null、quantity_scope=inbound_sku；summary 从父级去重汇总，禁止每店铺复制整单数量。实现可在 mart 里存父级证据字段，但不能将它当店铺行可累加数量。

90 天窗口外可从 W1 采购入库批次补行，标 source_kind=batch_backfill 和 history_complete=false。total 是批次源字段，不自动当完整历史入库量；余额可确知、历史入库量仍可未知。调拨、退货等不强行转为采购 IB。

## 6. 不照搬交接文档中的临时逻辑

- 不把余额清零直接判为已发货。
- 不按 SKU+数量猜测 OWS 关联；不生成临时 PK 作为真实单号。
- 不跨店铺做未经批准的 FIFO；批次库存余额不反推已发件数。
- 不将 good_num 当历史可发量，也不默认未检为全良品。
- 不继承静态快照日当“今天”；在仓天数使用请求时业务日，并同时展示来源新鲜度。
- 不返回名为“完整旧版看板”的八项统计；M1 只公布有来源支持的基础统计及能力范围。

## 7. 运行前核对（不阻塞 mock 实现，阻止无配置真实执行）

- 目标账号、惠州仓库 ID、源时区、明确采集开始/结束日期、输出目录必须配置并校验。
- W1 wids 字段表与官方示例的 wid 拼写存在差异，契约测试按字段表，首次抽样核实后才允许全量；不能用多仓返回冒充筛选成功。
- W3 start_date 包含，end_date 不包含；按业务日分 30 天窗口；“明天”用源业务时区计算，不使用 UTC 日期截断。
- 外部大整数 ID 保持字符串；signed numeric 文本显式解析；数组保留 JSON；日期和精度不静默截断。
- Token/App 凭据使用现有配置/Token Manager；不导出浏览器 Cookie，不索取聊天中的密码。
- 当前采集样本不证明生产账号凭据已配置、不证明全量拉取成功。

## 8. 批准边界

本决策允许形成 M1 PRP 候选。接口契约和新表仍须负责人确认 PRP，实际代码在负责人准备的独立 worktree 中实现。真实数据输出先 CSV；数据库发布、生产迁移、服务部署另行明确，不自动继承先前生产讨论。


## 本次实施授权记录

负责人确认新增 /inbound-batches 后，明确要求“就在当前dev分支实现，不要新建分支”。本次据此在dev实现M1，保留已有三个前端改动；不自动授权真实领星调用、数据库写入或部署。原收货主粒度调查不再作为本接口施工图。
