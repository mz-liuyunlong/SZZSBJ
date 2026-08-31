# Skill: API Contract Designer

## 用途

本 Skill 用于指导 AI 在开发前后端闭环前，先设计 API 契约。

## 必须读取

1. `docs/API_CONTRACT_RULES.md`
2. `docs/API_DESIGN_RULES.md`
3. `docs/ERROR_HANDLING_RULES.md`

## 输出格式

```md
## API 契约

### Endpoint

### Method

### Query 参数

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|

### Request Body

### Response

### Error

### 权限要求

### 是否写操作日志

### 是否触发 Celery
```

## 强制规则

1. 前后端实现前先确认契约。
2. 不允许每个接口自创响应结构。
3. 分页必须统一。
4. 错误必须统一。
