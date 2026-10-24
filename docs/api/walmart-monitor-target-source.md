# Walmart 监控目标来源 API

## 接口名称

Walmart 监控目标分页查询。

## 契约

| 项目 | 内容 |
|---|---|
| URL | `/api/integrations/walmart-monitor/targets` |
| Method | `GET` |
| 认证 | 独立 machine Bearer Token；配置项 `WALMART_MONITOR_TARGETS_TOKEN` |
| permissionKey | `integrations:walmart-monitor:read` |
| 数据权限 | 专用只读 machine principal 可读取当前 Listing MART；不向普通用户会话开放 |
| 数据来源 | `mart_listing_management_current`；用 `listing_archive_states` 排除已归档 Listing |
| sourceTables | `mart_listing_management_current`、`listing_archive_states` |
| 是否只读 | 是 |
| 是否审计 | 使用既有 request ID、认证失败与服务日志；不记录 Token 或商品字段值 |
| 是否高危 | 否；不会写库、触发同步或调用外部 API |

## 查询参数

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|
| `page` | integer | `1` | `>= 1` | 页码 |
| `page_size` | integer | `200` | `1..500` | 每页数量 |

## 返回字段

统一返回格式：`{ success, data, error, meta, request_id }`。

`data.items[]` 只包含下列获批字段：

| 字段 | 类型 | 来源 / 说明 |
|---|---|---|
| `source_account_ref` | string | 稳定业务键之一 |
| `store_id` | string | 稳定业务键之一 |
| `item_id` | string | 稳定业务键之一 |
| `store_name` | string/null | Listing MART 店铺名称 |
| `sku` | string/null | `local_sku` |
| `msku` | string/null | Listing MART MSKU |
| `owner` | string/null | `owner_ref` |
| `product_name` | string/null | `local_name`，不以页面标题替代 |
| `product_category` | string/null | Listing 来源类目 `category` |
| `wfs_inventory` | decimal/null | `wfs_available_quantity`；未知时为 `null`，不会因此取消监控资格 |
| `monitoring_eligible` | boolean | V1 固定为 `true`；为后续资格规则预留 |

`data` 还包含 `total`、`page`、`page_size`。`meta` 包含固定来源说明、`source_tables` 与可空的 `latest_calculated_at`。

只返回未归档 Listing：存在 `listing_archive_states.is_archived=true` 且 `listing_id` 指向当前 MART 行的商品，不计入 `total`，也不进入分页。未创建归档状态或已恢复为 `false` 的商品保留。稳定分页顺序为：`source_account_ref + store_id + item_id`。

## 示例

请求：

```http
GET /api/integrations/walmart-monitor/targets?page=1&page_size=200
Authorization: Bearer <machine-token>
```

响应结构示例使用合成值：

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "source_account_ref": "synthetic-account",
        "store_id": "synthetic-store",
        "item_id": "synthetic-item",
        "store_name": "Synthetic Store",
        "sku": "SYNTHETIC-SKU",
        "msku": "SYNTHETIC-MSKU",
        "owner": "synthetic-owner",
        "product_name": "Synthetic product",
        "product_category": "Synthetic > Category",
        "wfs_inventory": null,
        "monitoring_eligible": true
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 200
  },
  "error": null,
  "meta": {
    "source": "listing_management",
    "source_tables": ["mart_listing_management_current", "listing_archive_states"],
    "latest_calculated_at": null
  },
  "request_id": "synthetic-request-id"
}
```

## 错误码

| HTTP | 含义 |
|---:|---|
| `401` | 缺少、格式错误或不匹配的 machine token；配置缺失时也 fail closed |
| `403` | principal 不具备 `integrations:walmart-monitor:read` |
| `422` | 分页参数不合法 |
| `500` | 未处理的服务错误；响应不得包含 Token、SQL 或商品字段值 |

## 数据边界与回滚

- 接口读取新系统当前 Listing MART，不读取 `old-system/`，不调用 Lingxing、Walmart 或 Decodo。
- `product_category` 是商品来源类目；监控页面实际观察到的类目应写入统一 RAW 事件，两者语义不同。
- 当前没有持久化资格规则；V1 仅对未归档 Listing 返回 `monitoring_eligible=true`。后续其他资格筛选必须另开任务。
- 回滚只需移除 router 注册和专用认证路径，或不配置 Token 使接口 fail closed；没有数据库 migration。
