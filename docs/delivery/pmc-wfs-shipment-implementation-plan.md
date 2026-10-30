# PMC WFS 货件看板 · 开发实施计划

```text
状态：草案（待项目负责人确认 PRP / M1 范围）
前端预览：2026-10-23 已在 PMC 侧栏放七个建设中页面，数据为本地示例，未接接口
版本：2026-10-20
页面路径：/pmc/wfs（navigation key: pmc / wfs）
参考：PMC 交接文档 2026-10-19 §5.3；old-walmar-flie/features/pmc-wfs-shipment/
协作方式：方案与代码可在当前工作分支直接修改，不强制新建 feature 分支（以负责人最新指令为准）
```

## 1. 目标

在新系统 PMC 模块实现 **WFS 货件看板** 及上下游能力：从国内仓「打包完成」到 Walmart 货件创建/签收/上架的可视化、对账与（后期）受控写入。

Demo 对应：`old-walmar-flie` 中 `pmc-wfs-shipment`（Demo v14 流程：国内仓打包单 → 待发货打包单 → 系统货件写入 Walmart → WFS 货件看板）。

正式系统方向（与 demo 差异见交接文档 §1.9）：

- 拉数 → ODS/DWD/DWS → **FastAPI 只读/写 API** → React 页面（`PageShell`、权限 `permissionKey`）
- 审批与草稿：**PostgreSQL + 现有 approvals 扩展**，不沿用 demo JSONL + 口令
- 写 Walmart：**集成配置 + 高危权限 + 审计 + 执行器**，须单独 PRP 与书面授权

## 2. 不在本计划首版范围（Out of scope）

| 项 | 说明 |
|---|---|
| 探测货件列表 / 货件创建看板 | Demo 为前端模拟（交接 §5.3.1）；默认 **M1 不做**，若保留须单独 PRP |
| 物流页 `/pmc/logistics` | 独立页面，共享 A2/众壹，另开计划 |
| 自动补货 / PMC 总看板 | 依赖 WFS 读模型，后续 Epic |
| 生产环境自动执行 Walmart 写接口 | 须 M4 + 授权；禁止 AI 直连生产 |
| 复制 `old-walmar-flie` / `old-system` 代码 | 仅口径与金样例对账 |

## 3. Demo 页签与实施阶段映射

| Tab（Demo） | 业务 | 建议阶段 |
|---|---|---|
| 待发货打包单 | 打包完成 PK + 装箱，勾选建草稿 | **M2**（依赖国内仓打包 API） |
| 系统货件 · 写入 Walmart | 草稿审批 + 执行 create/箱唛 | **M3 审批** + **M4 写 Walmart** |
| 探测货件列表 | 模拟 inbound-preview | Out of scope（默认） |
| 货件创建看板 | 模拟创建/领星同步 | Out of scope（默认） |
| **WFS 货件看板** | A1 货件 + Walmart ②④ 到仓/Receipt | **M1** |
| **异常中心** | 前端规则（部分不持久化） | **M1 只读规则** → M2+ 可选落库 |
| 设置 | 渠道字典、阈值（demo 仅前端） | M1 只读字典 + 口径说明 |

页头全流程说明（Demo v14）：国内仓系统打包单（审批→装箱→完成）→ 待发货 → 草稿 → 批准 → 执行器 → 看板对账。

## 4. 核心业务口径（实施必须一致）

来源：交接文档 **5.3.2**、`build_from_daily.py`、demo `decisions.md`。

### 4.1 配对键

| 对象 | 键 | 说明 |
|---|---|---|
| 货件 | 领星 `cargo_code` = Walmart `shipmentId` | 清单只来自 A1；仅 Walmart 有的货件 demo 不进表（是否展示待定） |
| 商品行 | `(shipmentId, GTIN)` | 不按 SKU/MSKU 配 |
| 入库订单 | `in_bound_order_id` = 计划号 | 系统草稿与领星同步核对用（5.3.5 #1） |

### 4.2 指标以谁为准

| 指标 | 主数据源 |
|---|---|
| 货件状态 | 领星 A1 |
| 申报/Received（进度条） | 领星 |
| 签收（商品行） | Walmart ③（无则 demo 退回领星） |
| 上架 Receipt | Walmart ④ |
| 到仓实际 | 众壹「签收完成」与 Walmart `actualDeliveryDate` **取较早** |
| 可售日 | 最早 Receipt，否则到仓 + 缓冲（默认 10 天） |
| 商品标题 itemDesc | 领星 P4 `title`（非 Walmart ①） |

### 4.3 时区

- 数据日 / 页面 asof：`manifest.started_at` 前 10 位 → 正式系统用 **Asia/Taipei** 业务展示口径
- Walmart 拉数窗口：**America/Los_Angeles** 业务日（见 AGENTS.md、交接 §1.6）
- 领星 `to_*_time` 毫秒戳：demo 按 UTC 格式化 → 新系统须在 PRP 定展示策略

### 4.4 测试货

- Demo 部分统计含 `PMC-TEST-` 货件；`pmc_test_filter` 为不区分大小写且剔除 SP
- **PRP 须统一一种口径**，避免看板与采购/国内仓不一致

## 5. 新系统现状与缺口

| 能力 | 现状 | WFS 需要 |
|---|---|---|
| 导航 | `PMC → WFS` → `/pmc/wfs`，**无页面实现** | `WfsShipmentPage` |
| 权限 | 无 dedicated page key | 如 `pmc_wfs_board` + `pmc:wfs:read` 等 |
| 后端 | `warehouse_wfs` 仅 **WFS 费用异常 Case** | 新业务模块 **`pmc_wfs`**（推荐） |
| 领星 A1/A2/A4a | 无 PMC 专用 ODS/DWS | 同步任务 + DWD |
| Walmart ②③④ | 无 PMC 入库货件/流水 | 同步 + 守卫（无 Walmart / reuse stale） |
| 到仓/可售规则 | 无 | **`pmc_fulfillment_rules`**（与后续补货共用） |
| 国内仓 | 批次看板已有；**打包业务 API 未全接** | Tab「待发货」前置 |
| 货件草稿审批 | 无 | 扩展 approvals 或专用表 |
| 写 Walmart | 无 | M4 + 执行器（对标 demo `wfs_exec`） |

已具备可复用：**采购看板 DWS**、**国内仓批次 DWD**、Listing/产品维度、统一 API 信封与 IAM 框架。

## 6. 治理与文档交付物

每个阶段开发前（复杂功能门禁）：

1. **PRP 批准**：`PRPs/pmc-wfs-shipment-board.md`（可分 M1/M2… 子 PRP）
2. **接口数据源决策**：`docs/data-sources/decisions/pmc-wfs-shipment-board-decision.md`（须先于接口代码）
3. **分层与字段**：对照 `docs/data-sources/database-layering-standard.md`、字段标准化
4. **API 文档**：`docs/api/pmc-wfs-*.md` + OpenAPI
5. **页面规格**：`docs/page-specs/pmc-wfs-shipment-board.md`
6. **SOP**：`docs/sop/pmc/wfs-shipment-board.md` + `frontend/public/help/pmc-wfs-shipment.html`
7. **E2E**：每 `ready` 页至少 1 条 Playwright（`docs/delivery/e2e-playwright-standard.md`）

功能切片：一任务一页或一 API 模块；本计划按 **Phase** 拆 PR，可在同一分支连续提交。

## 7. 分阶段实施

### Phase 0 — 决策与契约（文档，约 1–2 周）

- [ ] 总 PRP 与 M1 范围签字（建议 M1 = 货件看板只读 + 只读异常）
- [ ] 数据源决策：A1、A2、A4a、P4/P6；Walmart inbound_shipments、items、inventory_log
- [ ] 指标字典 G1：到仓链、可售、异常阈值
- [ ] 与国内仓契约：PK、装箱 `lines`、`seg_in_use`、报关、测试单（键统一 **PK**，避免 demo OWS\| 旧键问题）
- [ ] 金样例：脱敏 daily（如 20261017）3 货件 + 1 条 PK 链路

### Phase 1 — 数据层（后端，无页面写操作）

| 编号 | 交付 |
|---|---|
| 1.1 | ODS：WFS 货件、SP 发货单、物流渠道/商；Walmart 三表等价结构 |
| 1.2 | DWD：货件头/行；SP 商品按 `cargo_code` 关联 |
| 1.3 | DWS：货件维度看板行；产品维度（可售日分段） |
| 1.4 | `arrival_rules` 逻辑服务化 + 单测；Walmart 守卫 |
| 1.5 | Celery 刷新任务；`data_asof` 元数据 |

验收：pytest + 与 demo JSON 子集字段 diff（不依赖生产 Walmart）。

### Phase 2 — M1 前端：WFS 货件看板（只读）

| 编号 | 交付 |
|---|---|
| 2.1 | API：`GET /api/v1/pmc/wfs/shipments`、`.../products`、`.../shipments/{id}`、`.../exceptions` |
| 2.2 | 前端：多 Tab 壳；**Tab5 货件看板**（货件/产品视图、详情抽屉）；Tab6 异常只读；Tab7 设置只读 |
| 2.3 | Tab1–4 占位「依赖 M2/M3」 |
| 2.4 | 权限注册 + PageShell 帮助入口 |
| 2.5 | Playwright 冒烟 |

### Phase 3 — M2：待发货打包单 Tab

**前置**：国内仓打包完成 / 装箱 / PK 后端 API（参见 `PRPs/pmc-domestic-packing-warehouse-frontend.md` 后续接口 PRP）。

- [ ] 合并 domestic 审批 + packing → `ready_to_ship` 列表 API
- [ ] 前端 Tab1：统计卡、店铺标签、可建货件校验（OWS/GTIN/装箱一致）
- [ ] 改装箱/换店铺仍在国内仓页；WFS 页仅刷新 state

### Phase 4 — M3：货件草稿与审批（不写 Walmart）

- [ ] 表：`pmc_wfs_draft`、`pmc_wfs_draft_event`（审计）
- [ ] API：由 PK 生成草稿、submit、approve/reject/withdraw
- [ ] 前端 Tab2：草稿列表与展开（执行结果可先空）
- [ ] 权限：`pmc:wfs:draft_submit`、`pmc:wfs:draft_approve`（高危）

### Phase 5 — M4：写 Walmart + 箱唛（独立 PRP + 书面授权）

- [ ] 集成配置（按店 credential，加密存储）
- [ ] 执行器：create → label；cancel/qty 可二期
- [ ] 结果回写 draft；箱唛下载 API
- [ ] 幂等、审计、单草稿单次执行；计划号与 A1 对账

### Phase 6 — 可选

- 探测/创建演示 Tab、物流页、运单号补写（demo 入口已隐藏）、众壹深度接入异常

## 8. 依赖顺序

```text
Phase 0 PRP / 数据源决策
        ↓
Phase 1 同步 + arrival_rules + DWS
        ↓
Phase 2 WFS 货件看板（只读）     ← 建议首个可演示里程碑
        ↓
国内仓打包 API 就绪
        ↓
Phase 3 待发货 Tab
        ↓
Phase 4 草稿审批
        ↓
Phase 5 写 Walmart（授权后）
```

与国内仓并行时：**优先统一装箱键为 PK**，并完成打包完成态，避免 demo 5.2.5 / 5.3.5 中「PK 键装箱在前端查不到」类问题。

## 9. 风险与 Demo 坑（须写入测试/PRP）

| # | 风险 | 处理 |
|---|---|---|
| 1 | 仅 A1 列表，Walmart 独有货件不可见 | 产品决定是否补「仅 Walmart」视图 |
| 2 | 执行后 exec 状态不刷新 | 定时同步或手动「刷新 Walmart 状态」 |
| 3 | UTC/北京混用 | 统一展示层时区策略 |
| 4 | 测试货口径不一致 | PRP 定一条并与 `pmc_test_filter` 对齐 |
| 5 | 无 Walmart 数据时构建失败 | 守卫 + 明确错误（对标 `NO_WALMART_DATA`） |
| 6 | 写操作无批准即执行 | 禁止；M4 必须审批链 + 执行器票据 |

## 10. 建议权限 Key（草案）

| 类型 | permissionKey（草案） |
|---|---|
| 页面 | `page:pmc:wfs_board:view` |
| 读 API | `pmc:wfs:read` |
| 提交草稿 | `pmc:wfs:draft_submit` |
| 批准草稿 | `pmc:wfs:draft_approve` |
| 执行写入（M4） | `pmc:wfs:exec`（高危，二次确认） |

角色名不写死，由超级管理员在页面配置。

## 11. 建议下一步

1. 负责人确认 **M1 = Phase 1 + Phase 2（货件看板只读）** 是否批准。
2. 创建并批准 `PRPs/pmc-wfs-shipment-board-m1.md`。
3. 完成 `docs/data-sources/decisions/pmc-wfs-shipment-board-decision.md`。
4. 从 `old-walmar-flie/.../build_from_daily.py` 提取纯函数清单，作为 Phase 1.4 单测规格（不提交 demo 源码）。

## 12. 参考文件索引

| 类型 | 路径 |
|---|---|
| 交接文档（外部） | `PMC交接文档_20261019.html` §5.3 |
| Demo 源码（外部） | `old-walmar-flie/features/pmc-wfs-shipment/` |
| 国内仓 packing PRP | `PRPs/pmc-domestic-packing-warehouse-frontend.md` |
| 采购 PRP（边界参考） | `PRPs/pmc-purchase-board.md` |
| 数据源决策门禁 | `docs/delivery/backend-data-source-decision-gate.md` |
| 前端导航 | `frontend/src/config/navigation.ts`（pmc / wfs） |

---

**变更记录**

| 日期 | 说明 |
|---|---|
| 2026-10-20 | 初稿：WFS 分阶段实施计划（替代误称 AFS 的自动补货方案） |
