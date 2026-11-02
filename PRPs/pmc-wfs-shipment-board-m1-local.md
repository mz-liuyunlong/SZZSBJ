# PRP：WFS 货件看板 M1（本地）

批准：2026-10-29 负责人对话授权（Q1–Q16）。  
决策：`docs/data-sources/decisions/pmc-wfs-shipment-board-decision.md`

## 交付

- `GET /api/pmc/wfs/shipment-board/shipments`
- `GET /api/pmc/wfs/shipment-board/shipments/{row_id}`
- `GET /api/pmc/wfs/shipment-board/summary`
- `GET /api/pmc/wfs/shipment-board/filter-options`
- 前端货件 Tab 接 API；产品 Tab Empty 占位；详情抽屉四块（创建/标签/PK/领星占位）
- pytest + Vitest；不 commit（任务约定）

## 非范围

领星同步、产品维度聚合、标签下载、异常案件链接、统计卡点击筛选。
