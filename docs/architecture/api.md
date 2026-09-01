# API 架构与契约规则

## 1. 统一返回格式

成功：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": {
    "pagination": null,
    "source": "legacy_mysql",
    "source_tables": [],
    "freshness": null,
    "warnings": []
  },
  "request_id": "req_xxx"
}
```

失败：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数错误",
    "details": {}
  },
  "meta": null,
  "request_id": "req_xxx"
}
```

## 2. 每个 API 必须声明

```text
summary
description
tags
response_model
required permissionKey
required data scope
source
source_tables
readonly
audit_required
high_risk
error_codes
```

## 3. OpenAPI metadata

FastAPI route 必须通过 `openapi_extra` 补充业务元信息：

```python
openapi_extra={
    "x-page": "销售 > 每日销售",
    "x-permission": "sales.daily_sales.view",
    "x-data-scope": ["store", "owner", "sku"],
    "x-source": "legacy_mysql",
    "x-source-tables": ["fact_sales_daily", "dim_product"],
    "x-readonly": True,
    "x-audit-required": False,
    "x-high-risk": False,
}
```

## 4. 分页规范

请求参数：

```text
page=1
page_size=20
sort_by=created_at
sort_order=desc
keyword=
filters={}
```

返回：

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  }
}
```

规则：

```text
默认 page_size = 20
最大 page_size = 200
导出不能复用普通列表接口
大表必须强制分页
旧库 raw 表禁止无条件分页扫描
```

## 5. 错误码

常用错误码：

```text
VALIDATION_ERROR
UNAUTHORIZED
FORBIDDEN
NOT_FOUND
CONFLICT
LEGACY_DB_READ_FAILED
NEW_DB_WRITE_FAILED
AI_TASK_FAILED
EXPORT_FAILED
IMPORT_FAILED
FEE_RULE_MISSING
DATA_SCOPE_DENIED
INTERNAL_ERROR
```

前端不能解析后端错误字符串，只能根据 `error.code` 判断。
