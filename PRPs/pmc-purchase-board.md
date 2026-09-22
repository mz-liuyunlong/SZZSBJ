# PRP：PMC-PURCHASE-1 采购看板（采购计划 / 采购单 / 收货单只读同步 + 看板）


状态：`Approved`（负责人 mz-liuyunlong 2026-09-18 批准进入 PRP / Gate 2 开发，方案 A。**批准范围仅为开发；不授权生产真实调用、生产回填、生产调度、生产迁移或任何领星写接口，生产执行另行书面授权**）

关联数据源决策：`docs/data-sources/decisions/pmc-purchase-board-decision.md`（状态 `READY_FOR_PRP`；收货单接口 `LX-4B9473A2D2E1` 已按例外流程重评为 `READY_FOR_PRP`，PRP planning only）

关联证据：`docs/integrations/lingxing-pmc-purchase-endpoint-evidence.md`；契约快照 `docs/integrations/lingxing/contracts/purchase-lx-03b82747b50a.md`、`purchase-lx-d332f931885e.md`、`warehouse-receipt-lx-4b9473a2d2e1.md`

业务规则：`docs/business-rules/pmc-purchase-rules.md`（v4）

Demo：`features/pmc-purchase/drafts/demo-v1.html`（antd 5 UMD，真实探测数据脱敏；仅供验收对照，不入仓库代码）

## 1. Goal

把领星采购计划、采购单（含明细）、收货单（含明细）三个只读接口同步进新系统，分层到 DWS，提供 PMC 采购看板：每张采购单的状态（待下单 / 已下单未到货 / 部分到货 / 已到货 / 已作废 / 逾期）、进度率、采购交期、审批周期、金额，按店铺 + ItemID 可追溯；SKU 级实际采购交期（近 5 有效样本）；ItemID 待处理、WFS 待转换、逾期与交期不稳定清单。

## 2. Why

PMC 目标是提单、提利润、降人力：采购是补货链路第一段，采购交期是后续自动补货、自动建计划、自动建 WFS 货件的基础参数；ItemID 归属与采购金额是财务单品成本的输入。旧系统只有飞书提醒且逻辑混乱，无法追溯。

## 3. Scope

### In scope

- [x] Gate 1（docs-only，#113 + 批准 PR）：数据源决策、证据、3 份契约快照、契约清单行更新（含收货单重评）、PRP、页面规格、业务规则副本
- [ ] Gate 2：3 个 `integration_sync` handler/parser、ODS 5 张表、质量检查、Celery 任务（默认 disabled）、12 个月回填 runner（手动）
- [ ] Gate 3：DWD 3 张、DWS 3 张、`manual_*` 1 张（交期修正；ItemID 人工指定不建，负责人 2026-09-21 决定）、规则表 1 张、4 个只读 API + 1 个人工覆盖 API
- [ ] Gate 4：前端 `/pmc/purchase-board` 页面（PageShell + ReportTableShell + ConnectedSearch + 详情 Modal + ItemID/交期修正 Modal）
- [ ] 跨模块最小改动（负责人 2026-09-18 已同意，各带条件）：`dim_walmart_listings.fulfillment_type` 列 + Listing 管理展示（**单独最小 PR，走 Alembic，不手改生产库，不影响现有 Listing 链路**）；`WalmartItemLink` 共享组件（**全系统唯一共享组件，先查 main 是否已有，采购看板 / Listing / 产品详情直接调用，不允许各页面自拼 URL**）；产品详情"采购交期"改读 `dws_purchase_sku_cycle`（**放 Gate 4 或 DWS 完成后，前端只经后端 BFF/DWS 读取，DWS 未完成前不接页面**）

### Out of scope

- [ ] 任何领星写接口（createPurchasePlan、备货单、变更单）
- [ ] WFS 货件同步；ItemID 发货追溯已由打包单回填替代（负责人 2026-09-21）
- [ ] 通知推送（提醒、月报）——正式上线后另做
- [ ] 成本核算、汇率换算、退换货、辅料/组合品、尾数报警
- [ ] 生产领星调用、生产库写入、生产调度开启（另行书面授权）

## 4. Navigation / Page

```text
一级导航：PMC
二级导航：采购看板
页面路径：/pmc/purchase-board
navigation key：pmc_purchase_board
页面状态：planned
```

## 5. Permissions

```text
page permissionKey: pmc.purchase.view（全员可看）
action permissionKeys: pmc.purchase.override（ItemID 指定、交期修正、样本剔除/恢复）; pmc.purchase.rule.manage（阈值规则）
data scope resource: 无行级限制（全店铺可见）
field permissions: 金额列对无 finance 范围角色仍可见（Rocky 决定全员可看；负责人可否决）
high-risk actions: manual 覆盖写入需二次确认 + 原因必填 + 审计
```

## 6. Data Source

```text
data source decision file:
- docs/data-sources/decisions/pmc-purchase-board-decision.md

decision status:
- READY_FOR_PRP（负责人已批准，2026-09-18；生产执行未授权）

dataset classifications:
- 采购计划 / 采购单 / 收货单：REBUILD_SYNC
- 店铺、Walmart 在线商品、产品负责人/标签/分类：EXISTING_NEW_SYSTEM_DATA
- 阈值规则：NEW_SYSTEM_OWNED_VERSIONED_RULE
- 交期修正：NEW_SYSTEM_OWNED（manual_*）；ItemID 归属由国内仓打包单回填（`from_packing_slip`），不做人工指定
- ItemID 打包单回填：依赖国内仓模块打包单表（业务流 AI 定义），就绪前显示 `pending_packing_slip`

contains NEED_OWNER_DECISION:
- no（原单项已由负责人决定；ItemID 发货追溯本期明确不接入，不构成待决事项）

owner approval status:
- Approved（mz-liuyunlong，2026-09-18，方案 A；开发批准，非生产授权）

short-term strategy:
- 三接口 90 天增量 + 12 个月一次性回填；复用 DATA-PAGES-1 DIM

long-term strategy:
- PMC 后续板块补齐发货追溯与写接口

legacy exit criteria:
- 不适用（不读旧库）

old-system reference: yes（只读探测证据）
legacy MySQL readonly tables: 无
new PostgreSQL tables:
- ods_lingxing_purchase_plan / ods_lingxing_purchase_order / ods_lingxing_purchase_order_item / ods_lingxing_receipt_order / ods_lingxing_receipt_order_item
- dwd_purchase_plan / dwd_purchase_order / dwd_purchase_order_line_item
- manual_purchase_cycle_override / rule_purchase_thresholds（`manual_purchase_item_itemid_override` 不建，见 §7.5）
cache / mart tables:
- dws_purchase_board / dws_purchase_sku_cycle / dws_purchase_pending
sensitive or critical domains: 财务（采购金额）/ 成本（输入）
```

## 7. API Contract

> 路径规范（负责人 mz-liuyunlong 2026-09-21）：Gate 3 采购模块 API 使用 `/api/pmc/purchase/...`，不引入
> `/api/v1/` 前缀，与仓库现有 `/api/data-pages/`、`/api/listings/` 等路由风格保持一致。`auth.py` 的只读
> 预览前缀只覆盖本模块的 GET 只读接口；7.5 的人工覆盖 POST 不进入只读预览权限，按单独权限处理。


### 7.1 看板列表

```text
method: GET
path: /api/pmc/purchase/board
request schema: page, page_size, owner_uid[], store_id[], status[](s2|s3|s4|over|s9|s0), search_type(sku|item_id|gtin|msku) + search_values[], item_id_source[], order_date_from/to, product_tag[], category_id[], price_min/max, qty_min/max, sort
response schema: items[{purchase_order_sn, status, stage_code, overdue_days, store{id,name}, sku, product_name, gtin, item_ids[{item_id,msku,source}], owner{uid,name}, quantity_total, quantity_receive, progress_pct, order_date, arrival_date, purchase_cycle_days, approval_cycle_days, sku_cycle{value_days,sample_count,unstable,source}, unit_price, amount_total, currency_code, plan_sns[], wfs_not_ready}], total
error codes: 400 VALIDATION, 403 FORBIDDEN
meta.source: dws_purchase_board
meta.source_tables: dws_purchase_board, dws_purchase_sku_cycle, dim_lingxing_stores, dim_walmart_listings
request_id: yes
```

### 7.2 汇总卡片 `GET /api/pmc/purchase/board/summary` → 7 张卡（待下单 / 待下单逾期 / 已下单未到货 / 下单逾期 / 部分到货 / ItemID 待处理 / 交期不稳定 SKU），同筛选参数。

### 7.3 详情 `GET /api/pmc/purchase/orders/{order_sn}` → 单头 + 明细 × ItemID 拆分 + 收货记录 + 计划链 + 交期样本（近 5 条：单号、下单日、到仓日、天数、是否剔除）。

### 7.4 SKU 交期 `GET /api/pmc/purchase/sku-cycles?sku=` → 有效样本、剔除样本、人工基准、不稳定标记。

### 7.5 人工覆盖（`pmc.purchase.override`）

```text
POST /api/pmc/purchase/sku-cycles/{sku}/overrides                     body: kind(exclude|restore|arrival_date|baseline), purchase_order_sn?, value?, reason
```
写入 `manual_*`，记录 before/after/operator/reason，触发 DWS 局部刷新。

> 负责人决定（2026-09-21，`docs/data-sources/decisions/pmc-purchase-board-decision.md` 补充决策）：**不建设** ItemID 人工指定接口
> （原 `POST .../items/{item_row_id}/item-id`）与 `manual_purchase_item_itemid_override`。采购单明细缺失 ItemID 时由国内仓打包单
> 反向回填（`from_packing_slip`），就绪前显示 `pending_packing_slip`；DWS 保留来源字段、来源单号/打包单号、匹配时间、匹配状态。

## 8. UI Requirements

```text
layout: PageShell → 工具栏（负责人 Select / 店铺 Select / 状态 Select / SKU-ItemID-GTIN-MSKU ConnectedSearch 含批量 / 下单时间 RangePicker / 更多筛选 Drawer：ItemID 归属、产品标签、分类、单价、采购量 / ResetButton / 显示统计）→ 7 张统计卡 → ReportTableShell
table columns: 采购单号 | 状态(含逾期天数) | 店铺 | SKU | 产品名 | GTIN | ItemID(链接) | 负责人 | 进度(收货/采购) | 下单日期 | 到仓日期 | 采购交期 | 审批周期 | 实际采购交期(悬浮近 5 条) | 单价 | 金额 | 计划号
filters: 见 layout；"状态"筛选与表格"状态"列同一套取值
actions: 行点击 → 详情 Modal；详情内 ItemID 修正 Modal、交期修正 Modal（override 权限）；RuntimeColumnConfigDrawer
empty state / loading state / error state: 复用 ReportTableShell 约定
helpUrl: /help/pmc/purchase-board
```

- 组件仅 Ant Design + ProComponents + 仓库既有封装；样式沿 `ProductManagementPage.css` 模式；不自创表格/筛选样式。
- ItemID 全站渲染为 `WalmartItemLink`（系统级规则待负责人批准）。
- 采购交期 <2 天显示 0/1 天 + 灰字"已剔除"。

## 9. SOP / API Docs

- [x] Markdown API doc required（Gate 3）
- [x] OpenAPI metadata required（Gate 3）
- [x] SOP help page required（Gate 4：ITEMID 备注规范、人工修正流程）
- [x] PageShell help entry required

## 10. Implementation Plan

```text
Task 1（Gate 1，已完成）：docs-only —— 决策 / 证据 / 契约 ×3 / 清单行更新 / PRP / 页面规格 / 业务规则副本。负责人已决定 DO_NOT_USE 重评（方案 A）与 3 项跨模块事项（均同意，附条件）。
Gate 2 起后端必须复用 `backend/app/modules/integration_sync/`（catalog / execution / importer / repository / router / scheduler / service / tasks / handlers / parsers），不新造同步框架，不绕过 `gov_integration_*`、`ods_api_raw_blobs` / `ods_api_raw_request_refs`、`gov_data_lineage`；Gate 4 前端必须复用 PageShell / ReportTableShell / ConnectedSearch / ResetButton / RuntimeColumnConfigDrawer / cells.tsx 及 shared/*（负责人 2026-09-18 要求）。
Task 2（Gate 2）：backend/app/integrations/lingxing/pmc_purchase_contracts.py（3 端点、offset/length、页长 500、purchaseOrderList 无 total）；3 个 handler/parser 接入 integration_sync；Alembic：5 张 ODS；质量检查（明细合计=单头、收货归属率、店铺 ID 一致）；Celery 任务默认 disabled；回填 runner 手动。
Task 3（Gate 3）：Alembic：DWD ×3、DWS ×3、manual ×1、rule ×1；刷新服务（归属优先级 from_system_plan > from_plan_remark > from_packing_slip > unresolved、合并单按计划比例拆分、打包单按数量比例拆分、50% 到仓、交期与剔除、近 5 样本与基准、不稳定判定、wfs_not_ready）；API 7.1–7.5（7.5 仅 SKU 交期覆盖）；权限 3 个 key；OpenAPI + Markdown 文档。
Task 4（Gate 4）：frontend 页面与两个 Modal；WalmartItemLink（若批准）；Playwright 用例；SOP 页。
Task 5：生产授权单独申请（真实调用 + 回填 + 调度），流程同 REAL-DATA-1。
```

## 11. Validation Gates

```bash
# Gate 1（docs-only）
git diff --name-only origin/main | grep -vE '^(docs/|PRPs/)' && echo "非文档改动，拒绝" || echo ok
npx markdownlint docs/data-sources/decisions/pmc-purchase-board-decision.md PRPs/pmc-purchase-board.md
python3 - <<'EOF'
import csv;rows=list(csv.DictReader(open('docs/integrations/lingxing/API_CONTRACT_INVENTORY.csv',encoding='utf-8')))
print({r['interface_key']:r['contract_status'] for r in rows if r['interface_key'] in('LX-03B82747B50A','LX-D332F931885E','LX-4B9473A2D2E1')})
EOF

# Gate 2–4（沿用仓库标准）
cd frontend && npm run lint && npm run typecheck && npm run test && npm run build && npm run test:e2e
cd backend && uv run ruff check . && uv run pytest && uv run alembic check
```

验收标准（Gate 1）：三份契约字段数与 normalized CSV 行数一致（10/47、8/102、10/47）；决策文件含 §3.1 前置表、§7 分类表、§8 血缘表、最终建议与负责人决定块；PRP 含 §4 required fields 全部项；未触碰 `backend/ frontend/ old-system/`。

## 12. Forbidden Actions

```text
不修改 old-system
不连接生产数据库
不修改 .env
不调用真实外部 API（含新系统内任何领星请求）
不部署
不重启服务
不在 Gate 1 PR 内改 backend/ frontend/ 或 official_verified_interfaces.csv
不实现任何推送
```

## 13. Rollback Plan

### 文档 PR 回滚
revert 单个 docs-only commit；契约清单行恢复原状态。

### 代码实现 PR 回滚（Gate 2–4）
按 Gate 独立 PR、独立 Alembic revision，可逐级 downgrade；ODS/DWD/DWS 表可 drop 重建；`manual_*` 表数据不删除（人工记录），回滚只停用 API。

### 数据回滚
同步任务默认 disabled；回填 runner 带 run_id，可按 run_id 清理 RAW/ODS。

## 14. Acceptance Checklist

- [ ] 页面 / API 完成
- [ ] 权限生效（3 个 key）
- [ ] 数据权限生效（不适用：全店铺可见）
- [ ] API 文档完成
- [ ] SOP 完成
- [ ] 测试通过
- [ ] Playwright 通过
- [ ] CODEX_HANDOFF 更新
- [ ] Gate 1：负责人在决策文件"负责人决定"块签字；契约清单行更新合入
