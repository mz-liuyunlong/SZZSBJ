# API 文档目录

每个模块一个 Markdown API 文档：

```text
dashboard.md
products.md
sales.md
ads.md
warehouse.md
finance.md
data-center.md
ai-center.md
settings.md
```

每个接口必须包含：接口名称、URL、Method、权限、数据权限、请求参数、返回字段、错误码、数据来源、sourceTables、是否只读、是否审计、是否高危、示例。

后端接口没有对应 API 文档，不允许标记完成。

已登记模块文档：

- `product-management-backend-mvp.md`
- `integration-sync-governance-sku-detail-v1.md`
- `pmc-purchase-api.md`（PMC 采购看板只读 API，Gate 3）
- `walmart-monitor-integration.md`（Walmart Monitor 统一 RAW 事件接收；无 RAW 读取或 Listing 写入）
- `walmart-monitor-target-source.md`（Walmart 监控目标只读来源接口）
- `pmc-domestic-batch-board-api.md`（PMC 国内仓批次看板只读 API）
- `keyword-planning-v11.md`（关键词 V1.1 本地开发契约；未部署、未开放正式投放）
