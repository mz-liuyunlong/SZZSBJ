# PRP：PMC C 组（WFS · 物流）第一期只读上线

状态：`Draft — 待项目负责人 mz-liuyunlong 确认`（PRP 不等于批准开发，见 `AGENTS.md` §11）
起草：PMC C 组 WFS·物流组 代码 AI，2026-11-02
请求人：Rocky（2026-11-02「可以开始」）
流程依据：`NEW SZZSBJ/AGENTS.md` §1.1（PMC 九步流程）、本仓库 `AGENTS.md` §11 / §11.1 / §11.2 / §14–§16
需求来源：8088 DEMO 源码（`features/pmc-wfs-shipment/drafts/`、`features/pmc-logistics/drafts/`、共用规则 `features/tools/ops_report/arrival_rules.py`），业务口径以 8088 为准
负责人分工：`NEW SZZSBJ/PMC_OWNERS.md`（PMC-02 物流、PMC-06 WFS 待发货、PMC-07 WFS 货件看板 / 异常中心）

> 本组范围：WFS 待发货打包单、WFS 货件看板（组长，含 WFS 共用前端框架 `WfsFrame` / `WfsQueryPage` / `WfsTable`）、WFS 异常中心、物流。
> **不在本组**：WFS 设置（归 D 组设置 AI）。本 PRP 只引用设置项的默认值，不做设置页。

---

## 0. 七项（§1.1 第 1 步，报 PMC 总负责 AI 核对后放行）

| 项 | 内容 |
|---|---|
| **任务类型** | 本次：文档（PRP + 接口数据源决策）。确认后：前端页面 + 只读 API + 读模型计算 + 迁移（仅合并头 / 读模型字段）。 |
| **允许路径** | `backend/app/modules/pmc_wfs/`（`creation_*`、`gateway.py` 不改逻辑）；`backend/app/modules/pmc_logistics/`（新增）；`backend/app/modules/integration_sync/handlers/lingxing_pmc_wfs_board_sync.py`、`parsers/lingxing_wfs_board.py`、`pmc_wfs_catalog.py`；`backend/scripts/*pmc_wfs*`、新增 `backend/scripts/replay_pmc_wfs_daily.py`；`backend/alembic/versions/` 本组新迁移；`backend/tests/modules/pmc_wfs/`、`pmc_logistics/`；`frontend/src/pages/pmc/wfs/`（除 `WfsSupportPages` 设置页）、`frontend/src/pages/pmc/logistics/`（新增）；`frontend/e2e/wfs-*`、`logistics-*`；`docs/api/pmc-wfs-*`、`pmc-logistics-*`；`docs/sop/pmc-wfs-*`、`pmc-logistics-*`；`docs/data-sources/decisions/pmc-wfs-*`、`pmc-logistics-*`；`frontend/public/help/pmc-wfs*.html`、`pmc-logistics.html`；`PRPs/pmc-wfs-*`、`pmc-logistics-*`。 |
| **禁止路径** | 共享文件（`PMC_OWNERS.md` §4：`navigation.ts`、`routes.tsx`、`main.py`、`model_registry.py`、`alembic/env.py`、`permission_catalog_v2.py`、`lingxing/client.py`、`integration_sync/catalog.py`、`execution.py`、`pmcWfsApiDocs.ts`）——只能报总负责 AI 排队改；`pmc_domestic/`（`warehouse_service.py` 分支里 +7 行须与 PMC-05 协调）；`warehouse_wfs/`（仓库 › WFS 费用异常，不属 PMC）；`integrations/walmart/`（统一网关，归 Walmart 写入单）；WFS 设置页（D 组）；`old-system/`；`.env`、调度配置、生产库。 |
| **docs** | 8088 源码（见文首）；`features/pmc-wfs-shipment/context/decisions.md`（10-10 异常规则定稿第 1–8 条）；`features/pmc-logistics/context/decisions.md`、`carrier-api-zhongyi.md`；`features/pmc-handover/chapters/71_wfs_board_datasource_design.md`、`75_wfs_exception_rules_design.md`；本仓库 `docs/delivery/backend-data-source-decision-gate.md`、`docs/data-sources/database-layering-standard.md`、`field-standardization-standard.md`；分支 `pmc/wfs-v2-20261029` 上的 4 份 WFS 数据源决策与 3 份 API 文档。 |
| **Skill** | 不使用外部 Skill。 |
| **计划** | 见 §10：A 等 #282 合入 → B 货件看板补 8088 口径 → C 异常中心规则引擎 → D 待发货只读化 → E 物流总览（领星段）→ F 众壹 / Walmart 段（待决策后）。 |
| **风险** | 见 §12：#282 体量大、共享文件冲突、Walmart / 众壹数据无入库通路、写入路由已注册（网关关闭）、本地不能调真实接口需回放数据。 |

---

## 1. Goal

把 8088 DEMO 里已经在用的 WFS 与物流四个页面，**以只读方式**搬进正式系统 5173 → 8443，业务口径与 8088 同一天数据逐项一致；“生成货件 / 写 Walmart”等写入功能全部放第二期。

## 2. Why

8088 DEMO 已能完成约 60 分的日常工作（Rocky 2026-11-02），但它是静态 HTML + 每周拉数 + 审批服务，不能多人登录、没有权限、数据不在正式库。分支 `pmc/wfs-v2-20261029` 已做了大量正式代码，但口径与 8088 有差距（看板没有到仓/可售规则、异常中心规则引擎是空壳、待发货带写入）。本 PRP 把两者对齐，给出最快的合规上线路径。

## 3. Scope

### In scope（第一期，只读）

| 编号 | 页面 | 第一期内容（以 8088 为准） |
|---|---|---|
| PMC-06 | WFS › 待发货打包单 `/pmc/wfs/pending-packing` | 只列国内仓“打包完成”的系统打包单（PK）；按 8088 `packRows` 给每行状态：可建货件 / 已在草稿 / 未关联 OWS / 未装箱 / 未点打包完成 / 缺 GTIN 或店铺 / 装箱合计≠打包单数量 / 已作废；店铺筛选、关键字（PK / SKU / ItemID / GTIN / OWS / MSKU）、按店铺汇总（可建张数 / 箱数 / 件数 / 已占用）；行详情显示装箱段（箱数 × 每箱件数 × 尺寸 × 重量）。**不显示“生成货件草稿”按钮**。 |
| PMC-07 | WFS › WFS 货件看板 `/pmc/wfs/board` | 货件维度 + 产品维度两视图；8088 `COLS` 列（默认列见 §8）；8088 `enrich` 派生字段：实际发货基准（SP 发货量优先，否则申报）、差异、到仓日（实际 / 预计，带来源）、可售日（首批上架或到仓 + 10 天）、到货桶（已过 / 15 / 30 / 60 / >60 天）、ITS 推算（FC 代码 T 结尾）、产品负责人（货件内全部 SKU 负责人）、测试货件标记（`PMC-TEST-` 计划号，不计入统计和异常）；详情抽屉（产品明细：发货 / 已收 / 破损 / 正常 / 异常件数）。 |
| PMC-07 | WFS › 异常中心 `/pmc/wfs/exceptions` | 按 Rocky 2026-10-10 定稿规则自动算异常（§6.3），一个货件一行、多种情况并列；类型卡片计数、筛选（类型 / 处理状态 / 店铺 / 负责人 / 严重度 / 关键字）、详情抽屉。处理状态 / 负责人 / 处理记录见决策点 **D-3**。 |
| PMC-02 | 物流 `/pmc/logistics` | 8088 物流页中**保留在物流**的两块：①物流总览（一行一张 SP 发货单：发货单 + 运单号、阶段、物流商 / 渠道 / 地区、箱数、计费重、发货 / 开船 / 到港 / 到货时间（预计 / 实际）、合同时效剩余、展开为货件 × 产品明细）；②异常与提醒（合同超时 · 可索赔、即将超时、物流已签收 WFS 未收货、渠道与目的地区不符、实际费用未录入、预计到港缺失、运单号缺失）。**到货预测 / 可售日已按 10-10 决定挪到 WFS 页**，物流页不再做；“众壹接口面板”不进正式系统（属调试面板，ARCHIVE_ONLY）。 |

### Out of scope

- 第二期：箱规写回领星、生成货件草稿、探测（inbound-preview）、建货件 + 取箱唛、取消 / 改数量 / 补运单号、换箱规、换店铺 / 作废 PK（全部是 Walmart 或国内仓写入）；分支 `pmc/wfs-creation-walmart` 的 3 个提交整体留到第二期。
- WFS 设置页（D 组）。第一期阈值用 8088 当前值作为**版本化常量**（`rule_version=WFS-RULES-20261010`），D 组设置表上线后改为读配置。
- 通知（钉钉 / 飞书 / 企业微信）、申诉 / 复议数据（等 Walmart Dispute 数据）、POD。
- 开启任何定时同步、生产迁移执行、权限授予——均须单独票据 + Rocky 书面批准（§1.1 末段）。

## 4. Navigation / Page

导航与路由分支里已有（`navigation.ts` 298–316 行、`routes.tsx` `pmc_wfs_*` → `WfsFrontendPage`），由总负责 AI 合并共享文件。第一期状态建议：待发货 `testing, readOnly: true`；货件看板 `testing`；异常中心 `testing`；设置 `disabled`（D 组接手前不显示可写表单）；物流从 `ComingSoonPage` 切到新页面 `testing`。main 现有的“系统货件（写入 Walmart）”菜单保持 `disabled`，第二期再开。

## 5. Permissions

- 复用 `page:pmc:wfs:view`（四个 WFS 页）；物流新增 `page:pmc:logistics:view`（共享文件 `permission_catalog_v2.py`，由总负责 AI 改）。
- 数据范围：沿用分支已实现的“来源账号 + 店铺”范围校验。
- 第一期不新增任何 `action:*` 写权限；若 D-3 选“带人工处理”，新增 `action:pmc:wfs:exception-handle`。

## 6. Data Source

### 6.1 《接口数据源决策》（§11.1，先于接口）

拟新增决策文件 `docs/data-sources/decisions/pmc-wfs-logistics-phase1-decision.md`，引用并部分替代分支上 4 份 WFS 决策（M1 / M2 时期的“领星履约段不读取”“规则引擎 STUB”结论由本决策更新）。

| # | 数据集 | 分类 | 权威 / 新系统存放 | 现状 |
|---|---|---|---|---|
| S1 | 领星 WFS 货件 + 货件商品（`queryWFSCargoPage`，LX-C95DBD64F2A9） | REBUILD_SYNC | `ods_lingxing_wfs_cargos` / `_cargo_goods` → `mart_wfs_shipment_board` | 分支已有 handler/parser/ODS/MART/发布器；手工一次性运行，无定时 |
| S2 | 领星 SP 发货单（`queryShippingListPage`，LX-C99E2D00C76D）：发货 / 开船 / 到港 / 到货、物流商 / 渠道 ID、运单号、费用、箱数 | REBUILD_SYNC | `ods_lingxing_wfs_shipping_lists` | 分支已有；物流页复用同一张 ODS，不另建 |
| S3 | 领星物流商 / 渠道字典（LX-725F26FDC523 头程物流商、LX-E95A3442D310 头程物流渠道列表） | REBUILD_SYNC | 新增 `ods_lingxing_logistics_providers` / `_channels` → `dim_logistics_channels` | 官方清单已登记为 OFFICIAL_VERIFIED；正式系统未接；需新增 2 个 handler |
| S4 | Walmart 在线商品（store × MSKU → ItemID / GTIN / 标题） | REBUILD_SYNC（复用） | `dim_walmart_listings` | main 已有 |
| S5 | 产品负责人（按 SKU，多人） | REBUILD_SYNC（复用） | 采购 / 国内仓已在用的负责人来源（`pmc_domestic/board_owners.py` 同口径） | main 已有，复用同一函数，不另建 |
| S6 | 国内仓系统打包单、装箱行、打包完成、作废 | NEW_SYSTEM_OWNED（上游国内仓） | `ops_domestic_packing_orders` / `_box_sets` / `_box_lines` | main 已有；WFS 只读，不改国内仓数据 |
| S7 | WFS 草稿 / 箱段占用 / 创建记录 | NEW_SYSTEM_OWNED | 分支 `ops_wfs_creation_*`、0072 草稿表 | 第一期只读（用于“已在草稿”状态）；写入第二期 |
| S8 | 众壹物流（运单详情 + 轨迹：签收完成、开船、到港、派送预约、计费重） | REBUILD_SYNC（新集成） | 拟 `raw_carrier_zhongyi_*` → `ods_carrier_zhongyi_orders` / `_tracks` | **NEED_OWNER_DECISION**：新外部集成；凭证目前只在 Mac `.secrets/logistics/6995/`；无按日期列表接口，须以 S2 运单号驱动 |
| S9 | Walmart v3 入库数据（采集已在跑，2026-11-02 已有店铺拉完）（inbound-shipments：签收日 `actualDeliveryDate`；inbound-shipment-items：逐 GTIN 收货 / 破损；inventory-log Receipt：首批 / 末批上架） | REBUILD_SYNC（新入库） | 拟 `raw_walmart_wfs_*` → `ods_walmart_wfs_inbound_shipments` / `_items` / `_receipts` | **NEED_OWNER_DECISION**：见 §6.2 |
| S10 | 异常案件处理（状态 / 负责人 / 记录） | NEW_SYSTEM_OWNED | 分支 `ops_wfs_exception_cases`、`evt_wfs_exception_*` | 分支已有；是否第一期开放见 D-3 |
| S11 | 8088 demo JSON、审批服务 `/pmc-api/wfs/state`、众壹接口面板 | ARCHIVE_ONLY | — | 只作对数参照，不进在线接口 |

**接口总体状态：** 全量为 `BLOCKED_BY_OWNER_DECISION`（S8、S9）。**拆分后**：S1–S7、S10、S11 已可执行，**“第一期 a（只用领星 + 本系统数据）”为 `READY_FOR_PRP`**；S8 / S9 决定后再做“第一期 b”。

### 6.2 Walmart v3 数据入库通路（现状与待确认）

已核实（main `a7239e98`→`3c62ae2a`）：
- main 的 `walmart_remote` 模块（#275 / #279–#281）能按店铺排队、经一店一服务器采集 `wfs_inventory`、`inbound_shipments`、`inbound_shipment_items`、`inventory_log`（`remote_dispatch.ALLOWED_KEYS`），结果是**校验过的 CSV 文件**，落在 `SZZSBJ_WALMART_REMOTE_ARCHIVE_ROOT/daily/`；任务表只有 `walmart_remote_jobs`（状态、文件数）。
- **没有任何代码把这些 CSV 写进 PostgreSQL**（全库无 `raw_walmart_wfs*` / `ods_walmart_*inbound*` 表）；`walmart_monitor` 的 RAW 表是商品监控，不含入库数据。
- 开关 `SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED` 默认关；读 key 还需 `SZZSBJ_WALMART_APPROVED_READ_KEYS` 加 `inbound_shipments,inbound_shipment_items`（`INTEGRATION.md` 136 行，10-31 实测未批）。

**2026-11-02 更新（Rocky）**：Walmart 一店一服务器采集正在跑，已有店铺拉完（部署 AI 回执显示 HK2612 / HK2613 / HK2614 成功），其余店铺进行中。也就是说 **Walmart 原始数据已经有了，缺的只是“文件 → 数据库”这一步**。

待负责人 / Rocky 确认（**D-1**）：
- 方案 A（推荐，第一期内完成）：新增 RAW 入库任务，只读采集已校验的 CSV（服务器上是 `archive_root/daily/<run>/<store>/`，本地 5173 用 `features/pmc-wfs-shipment/data/daily/<日期>/walmart/<store_id>/` 同一份文件回放），按文件 checksum 幂等落 `raw_walmart_wfs_*`，解析成 ODS；看板 / 异常从 ODS 取签收日、Receipt、逐 GTIN 收货与破损。**不新增任何 Walmart 调用**；采集本身仍按红线逐次批准。拉完几家店就入几家，未拉到的店铺页面显示“该店铺 Walmart 数据未接入”（与 8088 一致）。
- 方案 B（兜底）：A 来不及时先不接 Walmart，相关列显示“暂无 Walmart 数据”，不推算、不造示例；依赖 Walmart 签收日的异常先停用并在页面写明。
- 建议：按 A 做（数据已在路上，本地可直接回放对数）；若 8443 上线时服务器入库任务还没批准，先以 B 状态上线，入库批准后无需改页面即可补齐。

### 6.4 发货单 / 出库 / 打包单归属规则（8088 `build_from_daily.py` + `arrival_rules.py`）

| 问题 | 8088 规则（照搬） |
|---|---|
| SP 发货单属于哪个货件 | SP 的 `shipping_goods` 每一行带 `cargo_code`，**按行归属**到货件；一个货件可挂多张 SP（领星货件 `shipping_list_codes`），一张 SP 可装多个货件 |
| 货件的实际发货量 | 只取 `cargo_code` = 本货件的 SP 商品行 `shipments_num` 求和；SP 上没有 → 领星货件 `shipments_num`；仍为 0 → 用申报量 `declare_num` 作基准（标“按申报”） |
| 货件是否已发货 | 有任一状态“已发货”的 SP；或没有任何 SP 关联且状态不是“待补发货信息”（外部 / 海外仓直发货件） |
| 实际发货时间 / 实际出库时间 | 发货 = SP `delivery_time`；出库 = SP `actual_delivery_time`（8088 标“待核实”，默认隐藏列） |
| 到仓日 | 到仓按 SP 整柜算；货件到仓 = 其已发货 SP 的实际到仓与货件自己的 Walmart 签收取**最早**；都没有实际 → 各已发货 SP 的预计到仓取**最晚** |
| 物流费用 | SP 级（运输费 + 其他费），不拆到货件；头程分摊只在商品行 = `per_first_let_cost × 发货量` |
| 打包单（PK）→ 货件 | 本系统建的货件按创建记录关联 PK；领星侧外部创建（无 SP、2026-08-01 后创建、未取消）标“外部创建 · 待关联” |
| PK ↔ OWS 对账 | **不恢复**（Rocky 2026-11-02） |
| 物流页一行 | 一行 = 一张 SP；多个运单号合并一行并标“n 单合并”；运单号缺失单独提示 |

### 6.5 Rocky 2026-11-02 补充口径

- **操作人不写死**：8088 里“只有吴贤玲能提交 / Rocky 能批准”的姓名白名单不搬；正式系统一律按权限（8443 权限设置）控制。
- **待发货超时提醒**：打包完成后满 **3 天** 还没生成货件 → 待发货页标红并进提醒；阈值可在设置里改（设置页归 D 组，第一期先用常量 3，配置项名 `wfs.pending_packing_overdue_days`）。
- **箱规写回领星**：要做（领星产品箱规，名称按日期如“11月2日箱规”），属领星写入，放第二期并单独出票、Rocky 批准。

### 6.3 业务规则（以 8088 为准）

**到仓 / 可售（`arrival_rules.py`，Rocky 2026-09-25，物流 / WFS / 运营数据表共用；移植成后端纯函数 + 单测，不改算法）**
- 到仓日（按 SP 整柜）：实际 = 众壹“签收完成”与 Walmart `actualDeliveryDate` 取早；否则预计链：众壹“预计…派送入仓” › 实际到港 + 到港→到货周期 › 实际开船 + 航程 + 周期 › 预计到港 + 周期 › 领星 `arrival_time` › 发货日 + 地区兜底（美西 50 / 美中 60 / 美东 80）。地区按 FC 所在州（`REGION` 表）。
- 可售日（货件 × SKU）：有 Receipt → 首批上架日（实际）；否则到仓日 + `BUFFER_DAYS=10`。
- 到货桶：可售日 − 数据日：<0 已过未上架 / 0–15 / 16–30 / 31–60 / >60 / 无预计日期。
- 第一期 a 没有 S8 / S9 时，链条从“预计到港 + 周期”开始，来源标签如实写出（“领星预计到港 + 周期”等）。

**WFS 异常（`buildExceptions`，Rocky 2026-10-10 定稿；测试货件不进异常）**

| 类型 | 判定 | 阈值（第一期常量） | 第一期 a 可用 |
|---|---|---|---|
| 已关闭短少 | 状态 CLOSED，且有 SKU 异常件数 > `diffTol` | diffTol=10；≥25 件为高 | ✅ |
| 预计到仓已过未签收 | 在途、到仓日非实际、已过 ≥ `etaOverdue` 天 | 7（≥21 高） | ✅ |
| 货代已签收 · WFS 未收货 | 无 Walmart 签收、货代签收 ≥ N 天、Received=0 | 3 | ⛔ 需 S8 |
| 沃尔玛签收 · 未开始上架 | Walmart 签收 ≥ N 天、无 Receipt、Received=0，且有超差 SKU | 10 | ⛔ 需 S9 |
| 收货长期未完成 | 自签收 ≥ N 天未收完，且有超差 SKU | 15 | ⛔ 需 S9 |
| 创建后长期未发货 | 待补发货信息 ≥ N 天 | 7 | ✅ |
| 申诉期内未处理 / 临近期限 / 已过期 | CLOSED + 有真实 Walmart 签收日 + 超差；D+10～D+50 | disputeUrgent=5 | ⛔ 需 S9 |

一个货件同一时间只报一条阶段异常（第 8 条）；完成收货 = CLOSED 或 实际接收 ≥ 实际发货；超收不算异常；实际发货为空不参与短少；产品行：正常 = min(领星已收, 发货) − 破损，异常 = 发货 − 正常。

**物流异常（`features/pmc-logistics`，10-10 边界：物流只管到货代签收）**：合同时效对所有物流商统一 35 / 42 / 48 天（自然日，提货次日起算），超时索赔 0.5 元/KG/天；“Walmart 签收滞后于物流到货”已废止；“Walmart 已收货但物流未显示派送”降为“物流数据缺失”提示。合同时效、渠道周期在第一期为常量，D 组设置上线后读配置。

## 7. API Contract（第一期只读）

| 模块 | 方法 / 路径 | 状态 |
|---|---|---|
| 待发货 | GET `/api/pmc/wfs/pending-packing/orders`、`/summary`、`/orders/{ident}`、新增 `/by-store` | 分支已有前三个；补 8088 行状态枚举与按店铺汇总 |
| 待发货 | POST `/drafts`；创建 `/capabilities`、`/optional-previews`、审批等 | #282 已在 `main.py` 注册 `creation_router`（挂在 `/api/pmc/wfs/pending-packing`）。写不出去：网关是 `DisabledGateway`（调用即 503 `WFS_EXECUTION_DISABLED`），`guard_write` 只放行本地 / 测试库，创建须人工书面批准后才派发。一期是否摘掉该路由由刘云龙定（D-2） |
| 货件看板 | GET `/api/pmc/wfs/shipment-board/shipments`、`/products`、`/shipments/{row_id}`、`/summary`、`/filter-options` | 分支已有；补 §6.3 派生字段（`eta`、`eta_source`、`sellable_date`、`sellable_real`、`arrival_bucket`、`its_inferred`、`owners`、`is_test`、产品行 `normal_units` / `abnormal_units`）；产品维度改为到货桶数量 |
| 异常中心 | GET `/api/pmc/wfs/exception-center/cases`、`/summary`、新增 `/cases/{code}` | 分支已有；规则引擎从 STUB 改为 §6.3 实算，`rule_version=WFS-RULES-20261010` |
| 物流 | GET `/api/pmc/logistics/shipping-lists`、`/shipping-lists/{code}`、`/alerts`、`/summary`、`/filter-options` | 新增 |

统一 envelope、`response_model`、错误码、权限键、数据范围、OpenAPI、Markdown 文档、数据中心 API 文档页（§15）。读模型未就绪返回 503 `*_SCHEMA_NOT_READY`（沿用分支做法）。

## 8. UI Requirements

- 复用分支 `WfsFrame` / `WfsQueryPage` / `WfsTable`（WFS 共用框架，组长维护）；物流页用仓库标准 `PageShell` + `ReportTableShell` + `ConnectedSearch`。
- 货件看板默认列（8088 `def:true`）：店铺、Shipment ID、产品负责人、状态、货件类型、打包单·来源、SKU 数、Item 数、实际发货、Received、Receiving 进度、Walmart FC（地区）、到仓日（实际 / 预计）、可售日、Walmart 开始收货 / 完成、实际发货时间、物流商、物流渠道、SP 发货单、异常数；其余列在列设置里。
- 每个推算值旁标来源标签（真实 / 推算 / 计划），与 8088 一致；无数据显示“—”或“暂无 Walmart 数据”，**不显示示例值**（8088 的 D0 示例 `eta+2` 不搬）。
- 页面中文；右上角帮助入口（分支已有 `pmc-wfs.html`、`pmc-wfs-pending-packing.html`，新增 `pmc-logistics.html`）。

## 9. SOP / API Docs

分支已有 `docs/sop/pmc-wfs-*.md` 三份、`docs/api/pmc-wfs-*.md` 三份，按第一期口径更新；新增物流 SOP / API 文档；更新 `DATA_INTERFACE_REGISTRY.md`、`BACKEND_MODULE_CATALOG.md`（共享文档，冲突时总负责 AI 排队）。

## 10. Implementation Plan

**#282 现状（2026-11-03 核对）**
- PR #282（`pmc/wfs-v2-20261029`）head `ab61bd8`，已把 main `a156640` 合进分支，**尚未合入 main**。
- 分支迁移 0068–0075：`0068_wfs_creation`、`0068_walmart_remote_jobs`、`0069_wfs_exception_center`、`0069_walmart_gateway_ledger`、`0070_merge_wfs_walmart_remote`、`0070_ai_skill_soft_delete`、`0071_wfs_lingxing_board`、`0071_independent_skill_library`、`0072_wfs_pending_drafts`、`0073_wfs_creation_manual_approval`、`0074_merge_wfs_walmart_gateway`、`0075_merge_wfs_skill_lib`；单一头 `20261102_0075_merge_wfs_skill_lib`。
- 写入相关现状：`creation_router` 已在 `main.py` 注册；网关 `DisabledGateway`（`get_creation_gateway()` 只返回它，任何创建都 503 `WFS_EXECUTION_DISABLED`）；`guard_write` 只放行 `APP_ENV=local`（且必须是本机 `szzsbj_dev:55432`）或 `test`（库名 `wfs_v2_test_*`）；创建要有人工书面批准记录（`approval_ref` + `approved_by` + `approved_at`）才派发。
- 本组第一期代码已开 Draft PR #302（head `8046849`，基于 #282 分支，新增迁移 `20261103_0076_wfs_source_files`）；#282 合入 main 后 #302 改 base 为 main。
- `pmc/wfs-creation-walmart`（Walmart 建货件适配器、店铺 WFS 设置、负责人默认值）**第一期不并**；其中“店铺设置”交 D 组评估。
- `pmc_domestic/warehouse_service.py`（+7 行）与 PMC-05 仓库打包 AI 对一下再合。

**步骤**
- A. 等 #282 合入 main（由刘云龙审核合并，本组不改 #282 分支）；合入后 #302 改 base 为 main，CI 绿（lint / test / build / `scripts/check-rule-pack.sh` / `git diff --check`）。
- B. 货件看板：移植 `arrival_rules` 为 `pmc_wfs/arrival_rules.py`（纯函数 + 用 8088 同日数据做金样测试）；发布器写入派生字段；产品维度改到货桶；负责人、ITS、测试标记。
- C. 异常中心：规则引擎实算（§6.3 可用的 4 条），去重键沿用分支 `source_account_ref + store_id + shipment_id + rule_family + item_key`；不可用规则在页面列“待接入 Walmart / 众壹数据”。
- D. 待发货：按 `packRows` 补行状态 / 按店铺汇总；写入入口按 D-2 处理。
- E. 物流：新建 `pmc_logistics` 只读模块（读 S2 + S3），物流总览 + 异常与提醒（第一期 a 可用：合同超时 / 即将超时（以领星实际发货、到货时间）、实际费用未录入、预计到港缺失、运单号缺失、渠道与目的地区不符）。
- F. Walmart CSV → RAW 入库（S9，D-1 方案 A，本地用 daily 回放）；补齐依赖 Walmart 的 3 类异常。
- G. 众壹集成（S8，D-5 决定后）；补齐“货代已签收 · WFS 未收货”。

**本地数据（§1.1 第 4 步，不在 Mac 调真实接口）**：分支的 `run_pmc_wfs_board_once.py` 会真实调领星，Mac 上不能用。新增 `backend/scripts/replay_pmc_wfs_daily.py`：读 `features/pmc-wfs-shipment/data/daily/<日期>/lingxing/*.csv`（与 8088 同一份），按 RAW 回放写本地 ODS → 发布 MART。5173 与 8088 用同一天数据逐项对比，附差异表（货件数、状态分布、每张货件发货 / 已收 / 到仓日 / 可售日 / 桶、异常类型计数）。

## 11. Validation Gates

```bash
# backend
cd backend && ruff check . && ruff format --check . && pytest tests/modules/pmc_wfs tests/modules/pmc_logistics tests/db/test_alembic_scaffold.py
# frontend
cd frontend && npm run lint && npm run test -- pmc && npm run build
# rule pack / diff
scripts/check-rule-pack.sh && git diff --check
# e2e（本地真实后端 + 回放数据；与 route mock 测试分开记录）
npx playwright test e2e/wfs-v2-live.spec.ts e2e/logistics-live.spec.ts
```

金样测试：`arrival_rules` 与 `buildExceptions` 用 8088 同日输入 → 输出与 `demo-data-daily.json` / 页面结果一致（差异须逐条解释）。

## 12. Forbidden Actions / 风险

- 不调用领星 / Walmart / 众壹真实接口；不读凭证；不开定时同步；不执行生产迁移；不推 main、不自行合并。
- **生产写入风险**：#282 的 `creation_router` 已注册，但网关是 `DisabledGateway`（任何创建都 503），`guard_write` 在生产环境直接拒绝（`WFS_LOCAL_ONLY`），创建还须人工书面批准，三道关都在代码里，没有可误开的环境变量开关。要接真实 Walmart 写入，必须另行审核替换网关（第二期）。一期是否连路由一起摘掉由刘云龙定（D-2）；8443 预检票（`features/pmc-launch-8443/precheck-ticket-20261102.md`）补一项：确认 `get_creation_gateway()` 返回的仍是 `DisabledGateway`。
- 分支体量大：审核按模块分段（看板 / 异常 / 待发货 / 物流）给审核 AI。
- 共享文件（导航、路由、main.py、权限目录、model_registry、alembic env）只由总负责 AI 改。
- 数据新鲜度：第一期 a 的领星数据靠手工一次性运行；上线后“多久刷新一次”需 Rocky 单独批准定时同步（D-4）。

## 13. Rollback Plan

前端：导航状态改 `disabled` 即下线。后端：只读接口，回滚 = 回退合并提交；0074、0075 为空合并迁移，可安全 downgrade；0076 表空时可 downgrade；分支已有迁移有“表里有数据拒绝 downgrade”保护，生产以向前修复为主。异常案件数据保留不删。

## 14. Acceptance Checklist

- [ ] 5173 四个页面与 8088 同日数据对数差异表全部解释清楚
- [ ] 第一期页面上没有任何写 Walmart / 领星的按钮或接口
- [ ] CI 全绿；审核 AI 通过；Rocky 在 5173 验收
- [ ] API 文档 / SOP / 帮助页 / 数据中心接口文档更新
- [ ] 发布单交刘云龙（提交、迁移 0068–0075（#282）+ 0076（#302）、冒烟步骤、回滚）

---

## 15. 请负责人确认的决策点

| # | 问题 | 建议 |
|---|---|---|
| D-1 | Walmart v3 数据怎么进库（§6.2；数据已在采集） | 按 A：读已校验 CSV 落 RAW，不新增任何 Walmart 调用；服务器入库未批准前以 B 状态上线 |
| D-2 | #282 里的写入代码（草稿 / 创建 / 网关）第一期怎么处理 | 现状：路由已注册，但网关 `DisabledGateway`、`guard_write` 只放本地 / 测试库、创建须人工书面批准，生产写不出去。建议保持现状随 #282 合入；是否再把 `creation_router` 从 `main.py` 摘掉由刘云龙定 |
| D-3 | 异常中心第一期是否开放“处理状态 / 负责人 / 处理记录”（只写本系统，不碰外部） | 开放（8088 已在用，分支已实现）；若坚持纯只读则隐藏处理按钮 |
| D-4 | 第一期领星数据刷新方式 | 上线时先手工一次性运行；定时同步另出票据由 Rocky 批准 |
| D-5 | 众壹物流集成（S8）是否立项、凭证放哪台服务器 | 立项为第一期 b；凭证按部署规范放服务器环境变量，由刘云龙决定位置 |
| D-6 | 物流页“到货预测”是否确定不做（10-10 已挪到 WFS 页） | 确认不做，避免两处口径 |
