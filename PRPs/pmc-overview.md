# PRP：PMC 总看板（总览）一期只读上线

状态：`Approved`（Rocky 2026-11-03 批准，mz-liuyunlong 授权 Rocky 为 PRP 负责人；本地代码对齐 main，不合入 main）

负责人决定（2026-11-03 Rocky）：D1 同意；D2 = a；D3 = a（草稿以自动补货为准，20261102 为 87 张）；D4 = a；D5 = a（一期只读）；D6 = a（不显示 Walmart 列组）；D7 = a（先只读核实再复用）。5173 过渡：读 8088 20261102 快照并标「过渡」；8443 不得设置 `PMC_OVERVIEW_SNAPSHOT_FILE`（代码只在 APP_ENV = local / dev / test 读快照），接正式数据时按 `source_account` 过滤。共享文件补丁通过。

- 起草：PMC 总览代码 AI · 2026-11-03 · 需求方 Rocky（2026-11-03「WFS 物流、自动补货、总览这些板块都要上线」「按照 8088 的业务逻辑上线，按照 GitHub 的规定写代码」）
- 流程：本地 DEMO 工作区 `AGENTS.md` §1.1（8088 业务逻辑为准 → PRP 经刘云龙确认 → 5173 开发 → PR + CI → 审核 AI → Rocky 5173 验收合并 → 刘云龙发布 8443）；本仓库 `AGENTS.md` §11 / §11.1 / §11.2
- 数据源决策：`docs/data-sources/decisions/pmc-overview-decision.md`（总体 `BLOCKED_BY_OWNER_DECISION`，阻塞在上游；总看板自有部分 `READY_FOR_PRP`）
- 业务来源（需求以此为准，不入仓库代码）：本地 DEMO 工作区 `features/pmc-overview/`（`drafts/src/app.jsx` 的 `calcItem()` / `computeAll()` / `buildWorkbook()`、`drafts/build_from_daily.py`、`context/decisions.md` 第 1–38 条、`context/rocky-v1-plan-20260926.md`）
- 关联：`PRPs/pmc-purchase-group.md`（自动补货，总看板复用其计算结果）、`PRPs/pmc-wfs-logistics-group.md`（WFS 货件 / 发货单 / 到仓规则）、`PRPs/pmc-domestic-group-8088-alignment.md`（国内仓批次）

---

## 0. 需要负责人决定的事

| # | 事项 | 选项 | 建议 |
|---|---|---|---|
| D1 | 模块与表 | 新模块 `pmc_overview`，表见 §6.3 | 同意 |
| D2 | 与上游的关系 | a 总看板只读自动补货、WFS、采购、国内仓的结果，不重算；b 总看板自己再实现一遍（8088 的做法：页面里把补货算法又跑一遍） | a（Rocky V1 方案 §10「同一个指标只计算一次」）。代价：总看板上线排在补货计算任务、WFS 并分支之后 |
| D3 | 「本轮草稿」口径。**8088 自身两页不一致**：20261102 总看板判出 113 个草稿，其中 87 个有草稿号，另 26 个显示「CG261102-待发号」，自动补货页并没有发这 26 张 | a 总看板直接显示自动补货的结果（87 张，两页一致）；b 照 8088 总看板自己判断（113） | a。请 Rocky 确认（这是唯一会让 5173 与 8088 总看板数字不同的地方，对数表单列说明） |
| D4 | 海外仓扣减。8088 总看板扣海外仓（「海外仓可补」23 个，草稿量扣海外仓件数）；8088 自动补货页不扣（采购组 PRP 一期照此） | a 草稿量以自动补货为准（不扣），总看板照 8088 单独算并提示「海外仓可补 N 件」；b 两页都扣 | a（与 D3 一致；海外仓马上清空，是过渡状态，决策第 17 条） |
| D5 | 规则参数 | a 一期只读显示（版本、生效日）；b 页面可临时改、只在浏览器重算不保存（8088 做法）；c 可保存成新版本 | a。b 需要在前端再写一份规则引擎，与「只算一次」冲突；c 是写操作，放二期 |
| D6 | 「Walmart 数据」列组（20 列 + 4 个标签） | a 一期不做；b 一期接 `walmart_monitor` 商品监控投影 | a。8088 只有 HK2614 一家店、10-10 一批报表，之后没更新；等 Walmart 报表入库通路批准后单独做 |
| D7 | 两处数据落点待只读核实：惠州批次余额（国内仓在仓超期）、领星仓库库存明细（海外仓件数 / 仓库分布） | a 核实后复用已有表；b 没有则由对应板块补同步（领星接口逐个授权） | a，先核实再定；核实结果补进本 PRP |

---

## 1. Goal

在 PMC 下新增「总看板」页面（`/pmc/overview`），照 8088：一个 ItemID 一行，汇总采购、国内仓、在途、WFS、销量；用 12 张统计卡和标签提示已断货、断货风险、库存过剩 / 严重过剩、滞销、供应链异常、执行异常、海外仓可补、超期未上架、缺默认箱规；点行看详情；下载 Excel（5 页，替代运营数据表）。只看、不操作。

## 2. Why

- Rocky V1 方案（2026-09-26）：总看板是 PMC 的「监控屏」，看全局 → 发现问题 → 给出提示；运营判断进运营日志，业务操作回各模块。
- 8088 已按周跑了 10 余期（最新 20261102），业务规则经 Rocky 逐条确认（决策 1–38 条），需要搬到正式系统。

## 3. Scope

### In scope（一期，只读）

- [ ] A 总看板规则引擎（纯函数）：移植 8088 `calcItem()` 中总看板自有的判断 + `computeAll()`（海外仓分配、提示、分类、主要问题、统计卡），输入是自动补货的每 ItemID 计算结果
- [ ] B 每期计算任务（手动触发，默认 disabled，不改调度）：读上游结果 → 写 `ai_pmc_overview_items` → 发布读模型
- [ ] C 只读 API（§7）
- [ ] D 前端 `/pmc/overview`：统计卡、筛选、ItemID 主表、详情抽屉、仓库分布页签、规则页签（只读）
- [ ] E Excel 下载：汇总 / ItemID 总看板明细 / 店铺×SKU 明细 / 仓库分布 / 说明；可选「全部」「当前筛选」
- [ ] F 本地对数：同一数据日（建议 20261102）5173 与 8088 逐项对比，附差异表
- [ ] 文档：`docs/api/pmc-overview-api.md`、`docs/sop/pmc/overview.md`、帮助页 `frontend/public/help/pmc-overview.html`

### Out of scope（一期不做）

- [ ] 任何业务操作（审批草稿、建货件、处理物流）；运营建议
- [ ] 运营日志、PMC 统一事件接口、异常责任与绩效（决策第 15 / 16 / 25 条：以后再讨论）
- [ ] 「Walmart 数据」列组（D6）
- [ ] 规则参数在页面修改（D5）
- [ ] 新增任何外部数据同步；领星 / Walmart / 众壹真实调用；开启定时
- [ ] 导航 / 路由 / 权限目录 / `main.py` / `model_registry.py` 注册（共享文件，交 PMC 总负责 AI 排队）

## 4. Navigation / Page

- PMC 二级菜单最前面加「总看板」，路由 `/pmc/overview`，状态 `testing`，`readOnly: true`（由总负责 AI 改 `navigation.ts` / `routes.tsx`）。
- 现有「仓库 › PMC看板」（`/warehouse/pmc-dashboard`）是旧导航占位，与本页无关，不动。

## 5. Permissions

- 接口权限 `pmc:overview:read`；页面可见 `page:pmc:overview:view`（由总负责 AI 加到权限目录）。
- 只读，无写权限键。

## 6. Data Source

决策文件：`docs/data-sources/decisions/pmc-overview-decision.md`（数据集 O1–O16）。

### 6.1 总看板规则（以 8088 代码为准）

**范围与粒度**：一个 ItemID 一行，多店铺合并（决策第 2 条）。纳入 = 补货结果里的全部 ItemID（在售 PUBLISHED 的 WFS Listing + SYSTEM PROBLEM 的 WFS Listing（标「Listing 异常」，第 31 条）+ 不在售但链路仍有库存）。归档暂不判断（第 25 条：等 Listing 管理）。

**从自动补货复用（不重算，D2）**：日销（最近 30 个有货日 ÷ 天数，回看 90 天）、有货日（期初 WFS 可售 ≥ 5）、断货天数、尾货、互斥供应各段与预计可售日、提前期、断货时间线（能卖到 / 下一批可售 / 断几天 / 恢复日）、建议量与单次封顶、草稿号与补货状态（D3）、产品标签、Listing 状态、未归属件数。

**总看板自有判断**（参数默认值 = 8088 `build_from_daily.py` 的 `P`）：

| 规则 | 8088 口径 |
|---|---|
| 库存问题最低件数 | 有效供应 < `minSupplyIssue`（10）的 ItemID 不提示库存类问题（过剩 / 滞销 / 超期未上架 / 查验 / 无轨迹 / 国内仓超期 / 近 90 天无库存）；断货、采购单据超时、缺箱规照常提示（第 28 条） |
| 覆盖天数 / 过剩 | 有库存天数 ≥ `salesMinDays`（14）且日销 > 0 才算：覆盖 = 有效供应 ÷ 日销，> `over1`（120）库存过剩，> `over2`（150）严重过剩；不含海外仓（第 4 / 18 条） |
| 滞销 | 供应达标 + 有库存天数 ≥ 14 + 日销 0 + 仍有库存 |
| 已断货 | 日销 > 0 且 WFS 可售 < `instockMin`（5）；提示「已断货 N 天」（第 29 / 33 条） |
| 断货风险 | 有能卖到日期，且（断货窗口 > 0 天，或之后无来货且能卖到 ≤ 提前期）；已断货的不再算风险 |
| 供应链异常 | 已发货货件预计可售日（到仓 + 上架缓冲 10 天）已过 →「已过预计可售日未上架」；其中无物流轨迹且不是海外仓发出 →「超期无物流轨迹」；被查验；采购单下单天数 > 近 5 单交期（无样本用 `s3Fallback` 7 天）→「采购已下单未到货超期」；已发过货仍无默认箱规 →「缺默认箱规」 |
| 执行异常 | 采购计划待审批 > `s1Days`（2）天；待采购 > `s2Days`（7）天；采购单待下单 > 7 天；惠州批次在仓 > `domesticDays`（7）天、可用 + 锁定合计 ≥ `domesticMinQty`（10）件（第 7 / 14 条） |
| 海外仓可补 | 海外仓按 SKU，不分摊；同 SKU 的 ItemID 按能卖到日期从早到晚（同日按建议量大的先）依次分 min(剩余, 建议量)（第 12 / 19 / 20 条）；D4 = a 时只做提示，不改草稿量 |
| 近 90 天无库存 / 有库存天数不足 | 90 天无一天有货且供应达标 →「近 90 天无库存」；有库存天数 < 30 →「有库存天数 N 天」 |
| 主要问题 / 排序 | 见决策 §3 |

### 6.2 下载 Excel（照 8088 `buildWorkbook()`）

1. 汇总：店铺 × 各段（运营数据表口径，段与段可重叠，不跨段相加）+ 合计
2. ItemID 总看板明细：32 列（ItemID、SKU、MSKU、品名、店铺、负责人、主要问题、全部提示、各段、有效供应、日销、有库存天数、断货天数、能卖到、下一批可售、预计断货天数、覆盖天数、过剩判断、补货状态、草稿号、建议量、扣海外仓、国内采购量、海外仓同 SKU 件数、国内仓超 7 天件数、最长在仓天数、默认箱规）；D6 = a 时不含 Walmart 20 列
3. 店铺 × SKU 明细：运营数据表 v4 口径（移植 `agg_pmc_ops.py`，O10）
4. 仓库分布
5. 说明：口径、当前参数与规则版本、数据日

### 6.3 表（D1，命名按现有 DWS / AI / mart 习惯）

| 层 | 表 | 内容 | 写入方 |
|---|---|---|---|
| 规则 | `pmc_overview_rule_versions` | 总看板 10 个参数 + 版本 + 生效日 | 迁移种子（= 8088 默认值） |
| AI / 计算 | `ai_pmc_overview_runs` | 每期每次计算：数据日、补货期次、规则版本、起止、状态、各项计数（只追加） | 计算任务 |
| AI / 计算 | `ai_pmc_overview_items` | 期 × ItemID：提示列表、分类、主要问题、覆盖天数、过剩判断、海外仓分配、国内仓超期件数 / 最长天数、规则版本 | 计算任务（同期重算覆盖本期本行） |
| DWS | `dws_pmc_overview_store_sku` | 期 × 店铺 × SKU：运营数据表 v4 各段（O10） | 计算任务 |
| mart | `mart_pmc_overview_board` | 主表读模型（补货结果 + 总看板判断合并成一行） | 发布器 |
| mart | `mart_pmc_overview_warehouses` | 仓库分布读模型 | 发布器 |

只写计算层与读模型；不改 RAW / ODS，不覆盖人工记录，不删历史。

## 7. API Contract（一期，全部 GET，前缀 `/api/pmc/overview`，权限 `pmc:overview:read`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/summary` | 12 张统计卡计数 + 正常数 / 草稿数 / Listing 异常数；数据日、计算时间、规则版本、补货期次 |
| GET | `/items` | 主表：`store_id`、`owner`、`cats`（多选，全部命中）、`keyword`（ItemID / SKU / MSKU / 品名 / 草稿号）、`only_issue`（默认 true）、排序、分页（50 / 100 / 200 / 500） |
| GET | `/items/{item_id}` | 详情：店铺分布、断货时间线、供应链批次（互斥）、惠州批次在仓天数、异常与提示、补货公式与状态 |
| GET | `/filter-options` | 店铺、负责人、问题类型 |
| GET | `/warehouses` | 仓库分布 |
| GET | `/unattributed` | 未归属到 ItemID 的件数与原因、海外仓总件数、海外仓发出的发货单数 |
| GET | `/rules` | 当前规则版本与参数（含自动补货共用参数的只读引用） |
| GET | `/export` | Excel 下载，`scope=all|filtered` + 主表同样的筛选参数（实现前核对仓库现有导出做法，前端已有 xlsx 依赖） |

统一 envelope、`response_model`、错误码；读模型未就绪返回 503 `PMC_OVERVIEW_NOT_READY`；route 里不调外部接口。

## 8. UI Requirements（照 8088 `app.jsx`，外框同 5173）

- 标题区：数据日 · 来源 · 规则版本；「下载 Excel ▾」（全部 / 当前筛选）。
- 统计卡 12 张，可点筛选：ItemID 总数（副：正常 / 草稿 / Listing 异常）、已断货、断货风险、供应链异常、执行异常、海外仓可补、库存过剩、严重过剩、滞销、近 90 天无库存（副：有库存不足 30 天）、超期未上架、缺默认箱规。
- 筛选：店铺、负责人、问题类型（多选）、关键词、只看有问题的（默认开）、重置。
- 主表列：ItemID（`WalmartItemLink`）、SKU / 品名、MSKU、店铺（+N 店，悬停看各店销量 / 可售 / 在途）、负责人、主要问题（标签 + 说明）、采购未到、国内仓 可用 / 锁定、已发货未可售、已到·收货中、WFS 可售、全链路供应、日销、有库存天数、断货天数、能卖到、下一批可售、预计断货天数、覆盖天数、补货状态、全部提示。已断货 / 断货风险行标红。
- 表底：未归属到 ItemID 一行 + 海外仓说明。
- 详情抽屉：店铺分布、断货时间线、供应链批次（已过可售日标红、查验标签）、国内仓批次在仓天数、异常与提示、补货（公式、扣海外仓、国内采购量、草稿号与状态）、运营日志（显示「未接入」）。
- 仓库分布页签；规则页签（参数只读 + 口径表）。
- 每个推算值标来源（真实 / 推算 / 待接入）；未接入的数据集写「待接入」，不造示例（R-6）。
- 用系统现成组件与样式，不写死颜色字体；样式类名以 `.pmc-overview-` 开头。

## 9. SOP / API Docs

- 新增 `docs/api/pmc-overview-api.md`、`docs/sop/pmc/overview.md`（每期：上游同步 → 补货计算 → 总看板计算 → 发布 → 页面数据日更新）、`frontend/public/help/pmc-overview.html`
- 数据中心接口文档由总负责 AI 统一加

## 10. Implementation Plan（分 PR，每个 PR 独立可回滚）

1. **PR-A 规则引擎**（不依赖上游，PRP 批准即可做）：`pmc_overview/calculations.py` 纯函数 + 单测；用 8088 20261102 `demo-data.json` 做金样对数（只用已拉下的文件，本地脚本运行，真实数据不进仓库，仓库里只放脱敏小样例）。
2. **PR-B 表与计算任务**：迁移（§6.3）+ 计算任务（手动触发、默认 disabled）+ 发布器；等补货 PR-C、WFS 并分支落地后接入。
3. **PR-C 只读 API + 文档**。
4. **PR-D 前端页面**（导航 / 路由 / 权限键由总负责 AI 同步加）。
5. **PR-E 运营数据表口径**：移植 `agg_pmc_ops.py` v4 → `dws_pmc_overview_store_sku`；Excel 汇总 / 店铺×SKU 明细两页。

每步：从最新 main 建 `ai/YYYYMMDD-task`；跑 lint / test / build / `scripts/check-rule-pack.sh` / `git diff --check`；本地检查通过即合进 `pmc/local-preview` 并给 Rocky「5173 改动清单」（R-8）。

### 允许路径（开发单）

`backend/app/modules/pmc_overview/`（新）、`backend/tests/modules/pmc_overview/`（新）、`backend/alembic/versions/<本组新迁移>`、`backend/scripts/*pmc_overview*`（新）、`frontend/src/pages/pmc/overview/`（新）、`frontend/e2e/pmc-overview-*.spec.ts`（新）、`docs/api/pmc-overview-api.md`、`docs/sop/pmc/overview.md`、`frontend/public/help/pmc-overview.html`、本 PRP 与决策文件。

### 禁止路径

共享文件（`navigation.ts`、`pmcNavigation.test.ts`、`e2e/pmc-navigation.spec.ts`、`routes.tsx`、`pmcPlaceholderPages.test.tsx`、`main.py`、`model_registry.py`、`alembic/env.py`、alembic merge 迁移、`permission_catalog_v2.py`、`lingxing/client.py`、`integration_sync/catalog.py`、`execution.py`、数据中心接口文档）；其他板块模块（`pmc_replenishment/`、`pmc_purchase/`、`pmc_domestic/`、`pmc_wfs/`、`pmc_logistics/`、`warehouse_wfs/`）只读引用、不改；`old-system/`；凭证与 `.env`；服务器与定时任务；`main` 分支。

## 11. Validation Gates

```bash
# backend
cd backend && uv run ruff check . && uv run pytest tests/modules/pmc_overview
# frontend
cd frontend && npm run lint && npx vitest run src/pages/pmc/overview && npm run build
# repo
scripts/check-rule-pack.sh && git diff --check
```

对数（5173 vs 8088，数据日 20261102；数据只用已拉下 daily 或 RAW 回放灌本地库）。8088 基准（`app.jsx` 默认参数在本地重算，不含 Walmart 列组标签）：

| 项 | 8088 |
|---|---|
| ItemID 总数 | 1,531 |
| Listing 异常 | 8 |
| 已断货 | 179 |
| 断货风险 | 117 |
| 供应链异常 | 117 |
| 执行异常 | 35 |
| 海外仓可补 | 23 |
| 库存过剩 / 严重过剩 | 41 / 172 |
| 滞销 | 7 |
| 近 90 天无库存 / 有库存不足 30 天 | 363 / 197 |
| 超期未上架 | 35 |
| 缺默认箱规 | 74 |
| 正常 | 188 |
| 本轮草稿 | 113（其中有草稿号 87；D3 = a 时 5173 应为 87） |
| 未归属（采购计划 / 采购单 / 待下单 / 国内仓 / 已发货） | 4,980 / 578 / 20 / 20 / 25 件 |
| 海外仓总件数 | 13,698 |

逐 ItemID 比对：主要问题、全部提示、各段件数、有效供应、覆盖天数、过剩判断、海外仓分配——差 0；有差异逐条列表说明原因（多半是上游数据集未接入）。

## 12. Forbidden Actions

- 不调领星 / Walmart / 众壹真实接口；不读凭证；不碰服务器；不改定时任务
- 不重算上游指标（日销、供应、时间线、建议量、草稿号）；不改其他板块代码
- 计算不写 RAW / ODS，不覆盖人工记录，不删历史
- 不改共享文件；不推 main、不自行合并

## 13. Rollback Plan

- 新模块新表、只读：回退 = 关闭导航项 + downgrade 迁移（表无外部依赖、无人工数据）。
- 计算任务默认 disabled，不改调度。

## 14. Acceptance Checklist

- [ ] D1–D7 已决定，结果写回本 PRP
- [ ] PR-A 金样对数 20261102 全部差 0（D3 / D4 的已知差异单列）
- [ ] 5173 页面 12 张卡、主表、详情、仓库分布、规则页、Excel 5 页与 8088 同日逐项对比，附差异表
- [ ] 未接入的数据集在页面写明「待接入」，没有示例数据
- [ ] lint / test / build / rule-pack / diff-check 全绿，CI 全绿
- [ ] Rocky 在 5173 验收
