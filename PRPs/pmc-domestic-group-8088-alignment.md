# 国内仓组 PRP：批次看板 / 打包单审批 / 打包单（仓库）对齐 8088

- 日期：2026-11-02 · 作者：PMC B 国内仓组 代码 AI · 申请人：Rocky
- 状态：**Draft，待项目负责人刘云龙确认；未批准开发**（AGENTS.md §11；本地 DEMO 工作区 AGENTS.md §1.1 第 2 步）
- 数据源决策：`docs/data-sources/decisions/pmc-domestic-group-8088-alignment-decision.md`，总体 **BLOCKED_BY_OWNER_DECISION**，只剩 D1-a / D1-b 两处待刘云龙确认（Rocky 2026-11-02 已定 D2–D5，见决策 §3.2）。**A 期**不依赖这两处，确认 PRP 后即可开发；**B1 期**（发货 / 出库归属，按 8088 规则）等 D1-a / D1-b 确认；**B2 期**（箱规写回领星）另需受控写票据。
- 基线：`origin/main` 3c62ae2a（2026-11-02）。说明：本机 `git fetch` 经代理返回 403，未能确认 GitHub 上是否有更新的提交，开发前须重新拉取最新 main。
- 需求来源：8088 DEMO —— `features/pmc-domestic-warehouse/drafts/demo-v7.html`（页面代码）、`drafts/build_from_daily.py`（计算）、`features/pmc-replenishment/review_server/server.py`（审批 / 装箱事件服务）、`features/pmc-v2-app/src/pages/domestic/*`（8088 新版批次看板）、`rules/business-rules.md` v11、`context/decisions.md`。

## 0. 七项（§1.1 第 1 步）

| 项 | 内容 |
|---|---|
| 任务类型 | 既有页面功能补齐（前端 + 后端读接口字段扩展；A 期不新增表、不新增迁移、不新增外部同步） |
| 允许路径 | `backend/app/modules/pmc_domestic/**`（PMC-03/04/05 三块）、`backend/tests/modules/pmc_domestic/**`、`frontend/src/pages/pmc/domestic-warehouse/**`、`frontend/e2e/domestic-*.spec.ts`、`frontend/public/help/domestic-warehouse.html`、`docs/api/pmc-domestic-*.md`、本 PRP 与决策文件 |
| 禁止路径 | PMC_OWNERS §4 共享文件（navigation.ts、routes.tsx、main.py、model_registry.py、alembic/env.py 与任何新迁移、permission_catalog_v2.py、lingxing/client.py、integration_sync/*、数据中心接口文档）；`pmc_wfs/**`；`old-system/**`；`.env` / `.secrets/` |
| docs | 本 PRP；决策文件；更新 `docs/api/pmc-domestic-*-api.md`、帮助页；`docs/delivery/` 验证记录 |
| Skill | 项目内 backend-module-designer、react-component-architect（仅辅助分层）；不启用外部部署 Skill |
| 计划 | 见 §6（A1 批次看板 → A2 仓库页 → A3 审批页 → 自检对数；B1 发货归属；B2 箱规写回） |
| 风险 | 见 §8；重点 R1 打包审批在生产的放行（guard_local / 口令配置；操作人不限定，按权限设置） |

共享文件冲突核对：A 期不碰 §4 共享文件。`warehouse_service.py` 在 WFS 分支 `pmc/wfs-v2-20261029`（+7 行）与 `pmc/wfs-creation-walmart`（+4 行）被改过，A2 若改此文件须与 PMC-06 排队（建议 A2 只改 schema / repository / 前端，service 改动等 WFS 合入后再做）。

## 1. Goal

正式系统（5173 → 8443）三个国内仓页签的业务内容、列、筛选、统计卡与动作与 8088 一致；8088 没有、正式系统已有的严格校验（来源账号隔离、幂等、库存上限、不可变审计）保留不退。

## 2. Why

仓库与中台（吴贤玲）目前在 8088 上审批、装箱。正式系统三个页签已上线（testing）但批次看板的业务状态 / 统计口径与 8088 不同（正式版是数据质量统计卡、状态"待接入"），仓库页缺打包天数、延迟备注等，审批页的系统打包单管理（已决定不恢复）。对齐后才能把日常操作从 8088 切到 8443。

## 3. 8088 基线与正式系统差异

### 3.1 批次看板（PMC-03）

| 8088 内容 | 正式系统（origin/main） | 差异 / 处理 |
|---|---|---|
| 行 = 入库单 × SKU × 店铺批次 | 相同（MART） | 无 |
| 8 张卡：在库入库单、平均在仓天数、待打包（领星单已建）、已打包待发、超时未发（>7 天且完成率<90%）、近 7 天发出、平均出仓周期（90 天）、ItemID 待归属；卡片可点击筛选 | 数据质量卡：入库单数、展示行数、SKU 数、已知入库总量、已知批次余额、余额未知、入库量未知、到仓日期未知 **A 期**换成 8088 卡：在库（余额>0）、平均在仓天数、待打包、已打包待发、ItemID 待归属 5 张；"超时未发 / 近 7 天发出 / 平均出仓周期"3 张 B1 期接入。数据质量卡移到"更多"或详情提示，不删（铁律：不删原功能） |
| 列：到仓日期、入库单、采购单、SKU、产品、店铺、ItemID（唯一/多/待归属，按货件标记）、GTIN、负责人、在仓天数（超时标红）、**延迟备注**、**打包天数**（>3 天标红）、发货完成率、状态、**打包单（PK）**、领星打包单（OWS）、发货单、发出日期、出仓周期 | 有到仓日期～在仓天数、余额；无后 9 列 | **A 期**补：延迟备注、打包天数、打包单（PK，可多张）、状态（先出系统可判定的"待打包 / 已打包待发"）。**B1 期**：发货单、发出日期、出仓周期、发货完成率、其余状态。领星打包单（OWS）列不做（D2 不恢复关联） |
| 状态筛选 6 项（在库 / 待打包 / 已打包待发 / 超时未发 / 已发出 / 非发货出库） | 下拉存在，6 项禁用"待接入" | A 期启用"待打包""已打包待发"；B1 期启用其余四项 |
| 搜索类型 SKU / 入库单 / 采购单 / ItemID / GTIN / MSKU + 批量搜索 | SKU / 采购单 / 入库单 | A 期补 ItemID / GTIN / MSKU（MART 已有 identity 数组，可检索） |
| 更多筛选：在仓天数 ≥、ItemID 归属（唯一 / 多 / 待归属） | 仓库 ID、余额状态、排序 | A 期补两项，保留现有 |
| 详情：事件时间线（入库 → 审批 PK → 装箱完成 → 发货单） | 有详情 / trace | A 期补前三步（系统事实），发货步 B1 期 |

### 3.2 打包单审批（PMC-04，组长审批）

| 8088 内容 | 正式系统 | 差异 / 处理 |
|---|---|---|
| 待审批列表：PK 占位、入库单、采购单、到货情况（采购/已到/未到、部分到货、分批第 k/n 批）、SKU、GTIN（随 ItemID）、ItemID、MSKU、店铺、备货数量、是否报关（采购备注带出，可改）、发货仓 → 收货仓、生成日期、待审批天数（≥1 天标红"次日 10:00 已通报"）、状态 | 基本齐（到货、分批、报关、修改、手工、超时、待补资料） | A 期补"发货仓 → 收货仓"列与"次日 10:00 已通报"提示文案；正式系统多出的"待补资料 / 计划比例建议"保留 |
| 操作：修改（数量 / 店铺 / ItemID / 收货仓 / 原因）、审批通过（口令）、驳回（必填原因） | 有（PUT draft、approve、reject，均口令） | 无 |
| 手工添加打包单 | 有（manual，独立权限） | 无 |
| 全流程测试单勾选、补录、「系统打包单」段（填 OWS 号、两向关联、作废、差异确认、标为测试） | M2 已删除 | 不做（Rocky 2026-11-02：PK 与 OWS 关联对账不恢复） |
| 已审批历史：PK、OWS、入库单、SKU、GTIN、ItemID、店铺、数量、生成日期、审批人、审批时间、**当前状态（待仓库打包 / 已打包待发 / 已发出）** | 历史有审批审计，状态只到 通过 / 作废 / 驳回 | A 期补"当前状态"（待仓库打包 / 已打包待发 来自系统；已发出 B1 期） |
| 审批人只能吴贤玲（`DOM_NAMES`） | 登录 + `packing-approve` 动作权限 + 口令，不限姓名 | 不改（Rocky：不限定，8443 用权限设置管）。A3 顺带删掉前端从不触发的 `OPERATOR_NOT_ALLOWED` 吴贤玲提示 |

### 3.3 打包单（仓库）（PMC-05）

| 8088 内容 | 正式系统 | 差异 / 处理 |
|---|---|---|
| 只列已审批未发出；默认只看"待打包"；筛选：店铺、打包状态（待打包 / 已打包待发 / 打包超时 / 箱规待写领星 / 已写 / 写入失败）、关键字、审批日期 | 店铺、待打包 / 已打包待发、关键字、审批日期 | A 期补"打包超时"（阈值读设置）；箱规三项 B2 期 |
| 列：审批日期、打包单、到仓日期、入库单、采购单、SKU、店铺、ItemID、OWS、打包数量、批次余额、装箱数据（多行箱规、合计≠数量需原因）、状态、**打包天数**、**在仓天数**、**延迟备注**（写/更新）、GTIN、是否报关（可改）、单品包装 / 毛重（缺资料完成时必填）、产品标签 PDF、操作（填装箱 / 改装箱 / 打包完成） | 装箱、完成、报关、单品包装、超发 / 补入库、改装箱已有；延迟备注有接口与弹窗 | A 期补：打包天数、在仓天数两列，延迟备注列（显示最新一条 + 历史悬浮，接已有 notes 接口）。标签 PDF 按已提交的 `pmc-packing-gtin-label.md` 另审。OWS 列不做 |
| 写操作需口令（与审批同一口令） | 只有登录 + 动作权限，不验口令 | 不加（按权限设置管，Rocky 2026-11-02） |
| 打包完成后写领星"更多箱规"（整箱 `M月D日箱规`、尾箱 `M月D日箱规尾箱`；默认箱规不动；每 SKU 只留最近 6 条系统条目；部署 AI 跑 boxspec_exec） | 有 lx_spec 字段，不写 | 要写（Rocky 已定）。A 期显示状态；**B2 期**在正式系统实现写入任务，按领星受控写红线逐单 / 逐批票据批准后才开 |

### 3.4 发货 / 出库归属（B1 期口径）

照 8088 `build_from_daily.py`，全文见决策文件 §3.1：6501 发货单出库按单净额（撤销回冲抵消、作废不算），旧流程 4107 同计；4201 / 4106 算非发货出库、带原因、不计完成率；同 SKU 按到仓日期先进先出冲减到各入库行；可发 = 质检良品；累计达可发 90% 的那张发货单日期 = 发出日期，出仓周期 = 发出日期 − 到仓日期；超时 = 在仓 > 7 天且完成率 < 90%；已发出货物的店铺 / ItemID 以 WFS 货件去向为准。实现：新增派生事实（出库事件 + 分配），由发布器在入库发布时同版本投影进 MART，接口只读 MART。需刘云龙确认 D1-a（不接 SP 列表接口，发出日期用流水时间）和 D1-b（允许跨店铺先进先出，结果标"估算"）。B1 期如需新表 / 迁移，另附结构说明交云龙，不在 A 期做。

### 3.5 8088 有但本 PRP 不做

- 双轨对账页签（不恢复）；通知设置页签（8088 只是界面、推送全关，移到系统级通知框架另立项）。
- 8088 新版 README 里列的"ItemID 搜索改目标 / 拆单多 PK / 批量审批"：8088 本身还没做（"server.py 需增量改"），按"8088 为准"原则，等 8088 定稿后再补。

## 4. Permissions

不新增权限键。沿用 `page:pmc:domestic-warehouse-board:view`、`action:...:packing-approve / packing-reject / packing-manual-create / packing-boxes-save / packing-done / packing-customs / packing-note / packing-rebox / packing-unpacked-dispose / packing-supplement-ib / packing-supplement-sync`（0052 / 0053 已注册）。授权给谁由 D3 决定，代码不自动授予角色。

## 5. API Contract（A 期，只加字段，不改既有语义）

| 接口 | 新增字段 / 参数 |
|---|---|
| GET `/api/pmc/domestic/inbound-batches`、`/{id}` | `packing_refs[]`（pk、status=approved/packed、approved_at、packed_at、qty）、`packing_stage`（approved / packed / null）、`packing_days`、`packing_days_over`、`delay_note`（latest：cat、text、who、at；count）；查询参数 `packing_stage`、`min_age_days`、`identity_status`、`search_type` 增加 item_id / gtin / msku |
| GET `/inbound-batches/summary` | `in_stock_rows`、`avg_age_days`、`max_age_days`、`approved_rows`、`approved_units`、`packed_rows`、`identity_unresolved_rows`；原数据质量字段保留 |
| GET `/packing-warehouse/orders` | `packing_days`、`packing_days_over`、`days_in_warehouse`、`delay_note`；参数 `status=late` |
| 阈值来源 | 打包天数阈值从 D 组设置 AI 提供的读设置接口读取（键名双方约定，建议 `pmc.domestic.packing_days_limit`，默认 3）；本模块不建设置表、不写设置 |
| GET `/packing-approval/orders` | `current_stage`（待仓库打包 / 已打包待发） |

`meta.source` / `source_tables` 照现有约定；打包相关字段读 ops/evt 表（同库事务读，不进 MART，避免发布版本与实时事件错位；如负责人要求进 MART，改为发布时投影）。错误码沿用。

## 6. Implementation Plan（A 期）

1. A1 批次看板：repository 关联 PK 分配与最新延迟备注 → schema / summary 扩展 → 前端卡片、列、筛选、详情时间线；单测 + Vitest + E2E。
2. A2 仓库页：打包天数 / 在仓天数 / 延迟备注列与"打包超时"筛选（尽量不改 `warehouse_service.py`，见 §0）。
3. A3 审批页：收货仓列、已通报提示、历史"当前状态"。
4. 自检对数（§1.1 第 4 步）：用已拉下的 daily 数据 / RAW 回放灌本地库，5173 与 8088 同日数据逐项对比卡片数、行数、打包天数，附差异表；不在 Mac 调真实接口。
5. 分支 `ai/YYYYMMDD-pmc-domestic-8088-a`，lint / test / build / `scripts/check-rule-pack.sh` / `git diff --check`，开 PR 等 CI。

B1 期（D1-a / D1-b 确认后）：发出事件与先进先出分配、六状态、发货列、3 张统计卡。
B2 期（受控写票据获批后）：打包完成后写领星"更多箱规"，写入状态回显到仓库页。

## 7. Validation Gates

```bash
cd frontend && npm run lint && npm run typecheck && npm run test && npm run build && npm run test:e2e -- domestic
cd backend && uv run ruff check . && uv run pytest tests/modules/pmc_domestic && uv run alembic check
scripts/check-rule-pack.sh && git diff --check
```

验收：同一天数据 5173 与 8088 卡片数 / 行数一致或差异有解释；三页签无回归（既有 pytest / Vitest / E2E 全过）。

## 8. 风险

- **R1 打包审批（及仓库写）在生产的放行 —— 需刘云龙确认后才能在 8443 实际使用**
  1. `guard_local()` → `database_write_allowed()`：生产环境要求 `DATABASE_URL` **不带任何查询参数**（`url.query` 非空即拒绝，返回 403 `LOCAL_DATABASE_ONLY`）。若生产连接串带 `?sslmode=...` 等，审批 / 手工 / 装箱全部写不进。需部署侧核实（代码 AI 不读 .env）。
  2. 口令：生产须配置 `PMC_DOMESTIC_PASSCODE_SHA256`（64 位小写 hex），否则审批 503 `PASSCODE_UNSET`；限流依赖 `CELERY_BROKER_URL` 为 redis，否则 503。
  3. 操作人：按 Rocky 决定不限定姓名，生产上谁有 `packing-approve` / 仓库动作权限谁就能操作，所以上线前要在权限设置里只给该给的人授权（代码不自动授予）。
  4. 仓库页写操作不验口令（8088 要），按决定不补，同样靠权限设置把关。
  5. 生产订单 `is_test=false`（正式单），本地 / 测试为验证单；上线即真实占用批次余额。
  6. 迁移 0051–0053 是本地历史，M2 PRP 已写明"上线前单独整理生产迁移方案，从生产实际版本验证"；生产迁移与备份须单独票据、Rocky 书面批准（§1.1 不在 5173 验收范围）。
- R2 批次看板关联系统 PK 后，8088 与正式系统两套审批并行期间数据不互通（8088 jsonl 不导入），两边"待打包 / 已打包"会不一致，切换前要定迁移或切换日。
- R3 `warehouse_service.py` 与 WFS 分支冲突（§0）。
- R4 打包天数阈值依赖 D 组设置接口；设置接口未上线前用默认 3 天。超时 7 天 / 90% 仍是常量。
- R6 B1 跨店铺先进先出是估算，可能与实际出货批次不一致（8088 同样如此）；页面需标"估算"。
- R7 B2 写领星属于外部写入，红线要求逐单 / 逐批批准；写失败只记录、下次再试，不阻塞打包完成。
- R5 本机无法 fetch GitHub，基线可能落后。

## 9. Forbidden Actions

不改生产、不部署、不读凭证、不调领星 / Walmart、A / B1 期不写领星箱规（B2 期票据批准后才写）、A 期不新增迁移、不改共享文件、不推 main、不自行合并；未获刘云龙确认前不开发。
