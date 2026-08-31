# API 契约规则

## 文件用途

本文件用于约束前后端在开发一个页面前，必须先约定 API 契约，避免前端和后端字段不一致。

## API 契约必须包含

1. API 路径。
2. HTTP 方法。
3. Query 参数。
4. Request Body。
5. Response 字段。
6. 分页结构。
7. 错误结构。
8. 权限要求。
9. 是否触发 Celery 任务。
10. 是否写操作日志。

## 模板

```md
# API Contract: 广告活动列表

## Endpoint

GET /api/v1/ads/campaigns

## Query

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| store_id | string | 否 | 店铺 ID |
| status | string | 否 | 活动状态 |
| page | number | 是 | 页码，从 1 开始 |
| page_size | number | 是 | 每页数量 |

## Response

```json
{
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  },
  "message": "ok"
}
```
```

AI 开发页面前必须先输出 API 契约草案。用户确认后再写前后端代码。
