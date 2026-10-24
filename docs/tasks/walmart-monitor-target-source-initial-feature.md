# Walmart Monitor Target Source — Initial Feature

## FEATURE

提供只读机器接口，让独立 Walmart 监控程序分页读取当前 Listing 监控目标。接口返回稳定业务键、来源描述、类目、可空 WFS 库存和显式监控资格，不写业务数据。

## BUSINESS RULES

- 稳定业务键：`source_account_ref + store_id + item_id`。
- 当前全部 Listing 具备监控资格，`monitoring_eligible=true`；保留字段供未来独立规则变更。
- `product_category` 来自 Listing MART 的 `category`。
- `wfs_inventory` 来自 `wfs_available_quantity`，缺失时返回 `null`，不伪造为零。
- 接口只读现有 MART，不实时调用 Lingxing、Walmart 或 Decodo。

## NAVIGATION

无页面；机器到机器接口。

## PERMISSION

```text
permissionKey: integrations:walmart-monitor:read
actions: read current monitoring targets
data scope: dedicated machine principal, all current Listing MART rows
field permissions: only the approved target contract
high-risk actions: none; endpoint is read-only
```

## DATA SOURCE

```text
old-system reference: no
legacy MySQL readonly tables: none
new PostgreSQL tables: none
external APIs: none at request time
read model: mart_listing_management_current
```

## API REQUIREMENTS

`GET /api/integrations/walmart-monitor/targets?page=1&page_size=200`；统一 envelope；专用 bearer token；严格分页；OpenAPI 和 Markdown 文档齐全。

## TESTS

认证/权限、分页、字段映射、类目、可空库存、固定资格、空结果、只读事务边界及无外部 API 单元/API 测试。

## FORBIDDEN

不新增表或 Alembic；不写生产数据库；不调用外部 API；不修改 `old-system/**`；不触发同步；不部署或重启服务；不输出真实业务数据或密钥。

## ACCEPTANCE

监控程序现有 product-source client 可直接读取并解析；API 仅查询 Listing MART；所有离线测试和 rule-pack 通过。
