# PMC 采购看板 Page Specification


## 1. Document Status

```text
Status: Draft
Owner Approval Required: Yes
Implementation Allowed: No until PRPs/pmc-purchase-board.md is Approved
```

关联 PRP：`PRPs/pmc-purchase-board.md`。关联 Demo：`features/pmc-purchase/drafts/demo-v1.html`（v1.4）。

## 2. Page Positioning

```text
一级导航：PMC
页面名称：采购看板
页面路径：/pmc/purchase-board
navigation key：pmc_purchase_board
页面状态：planned
用户角色：全员可看；中台 / 采购 / 管理员可人工修正
```

## 3. Visual Reference

Demo v1.4（Artifact / `drafts/demo-v1.html`）：PageShell 页卡 → 工具栏 → 7 张统计卡 → ReportTable → 详情 Modal。全部使用 Ant Design 5 组件与仓库既有封装。

## 4. 数据来源

只读 `dws_purchase_board`、`dws_purchase_sku_cycle`、`dws_purchase_pending`；店铺名来自 `dim_lingxing_stores`；ItemID/MSKU/GTIN/发货方式来自 `dim_walmart_listings`；负责人/标签/分类来自产品管理。前端不查 RAW/ODS。

## 5. 筛选条件

| 位置 | 控件 | 取值 |
|---|---|---|
| 主工具栏 | 负责人 Select（多选） | 产品管理负责人（唯一来源；不含采购单 principal） |
| 主工具栏 | 店铺 Select（多选） | dim_lingxing_stores |
| 主工具栏 | 状态 Select（多选） | 待下单 / 已下单未到货 / 部分到货 / 已逾期 / 已到货 / 已作废（与表格"状态"列同一套） |
| 主工具栏 | ConnectedSearch | 类型 SKU / ItemID / GTIN / MSKU；支持批量粘贴 |
| 主工具栏 | 下单时间 RangePicker | order_date |
| 更多筛选 | ItemID 归属 | 已归属(备注) / 已归属(人工) / 待追溯 / 待处理 |
| 更多筛选 | 产品标签、分类、单价区间、采购量区间 | 产品管理 / 采购单 |
| 待办 | 采购单号（Rocky 说做再做） | — |

## 6. 表格字段

采购单号 · SKU / 产品 · 店铺 · ItemID 归属（`WalmartItemLink`）· GTIN · 负责人 · 下单日期 · 采购量（本行分配量）· 收货进度（已收 / 采购量，%）· 到仓日期 · 采购交期（天；<2 显示并标"已剔除"）· 实际采购交期（SKU 级；悬浮近 5 条：单号 / 下单日 / 到仓日 / 天数 / 剔除）· 审批周期（天）· 状态（含 WFS 待转换标记）· 逾期 · 金额（CNY）。单价、计划号可在列配置中打开。支持 RuntimeColumnConfigDrawer。

## 7. 统计卡（7 张）

待到货采购单、逾期未到货、待采购超时、平均采购交期（大号为 90 天平均，副标题为中位数和样本单数）、本月采购金额、交期不稳定 SKU、ItemID 待处理。

点击一张卡片会带 `summary_filter` 重新请求列表，工具栏筛选保留，汇总数字不跟着变。再点一次取消，列表恢复。未转单计划不在看板行里，待采购超时卡片只筛出已超时的待下单采购单。

## 8. 操作与弹窗

- 行点击 → 详情 Modal：单头、明细 × ItemID 拆分、收货记录、计划链、交期样本。
- ItemID 修正 Modal（override 权限）：选择该店铺 SKU 对应候选 ItemID 或手输 11 位；原因必填。
- 交期修正 Modal（override 权限）：剔除/恢复某单、修正某单到仓日期、设置整体基准值；原因必填。
- 无导出、无推送。

## 9. API 契约

见 PRP §7（7.1–7.5）。

## 10. 权限要求

`pmc.purchase.view` / `pmc.purchase.override` / `pmc.purchase.rule.manage`。

## 11. 验收标准

- 筛选"状态"与表格"状态"取值一致；批量搜索 ≥100 个 SKU 不卡顿（分页服务端）。
- ItemID 全部为链接、新标签打开。
- 交期样本悬浮最多 5 条，剔除样本灰显。
- 人工修正后列表与卡片即时刷新且有审计记录。
- Playwright：筛选、批量搜索、详情、两个 Modal（mock API）。
