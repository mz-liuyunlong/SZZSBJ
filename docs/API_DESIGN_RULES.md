# API 设计规则

## URL 命名

推荐 REST 风格：

```text
GET    /api/v1/products
GET    /api/v1/products/{id}
POST   /api/v1/products
PATCH  /api/v1/products/{id}
DELETE /api/v1/products/{id}

GET    /api/v1/ads/campaigns
GET    /api/v1/ads/search-terms
POST   /api/v1/ads/negative-keywords
```

禁止：

```text
/getProduct
/doAdThing
/testApi
/api1
/newData
```

## 分页规范

默认使用：

```text
page
page_size
```

响应结构建议：

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

如项目负责人另行确认统一响应格式，以确认后的规范为准。

## API Route 规则

API Route 只做：

- 接收请求
- 权限检查
- 参数校验
- 调用 Service
- 返回结果

不要在 Route 里写复杂 SQL、复杂业务判断或外部 API 细节。
