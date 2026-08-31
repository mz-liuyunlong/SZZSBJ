# Skill: Backend Module Designer

## 用途

本 Skill 用于指导 AI 在开发后端功能前，先设计 Route / Schema / Service / Repository / Model 的分层方案。

## 必须读取

1. `docs/BACKEND_MODULE_CATALOG.md`
2. `docs/API_DESIGN_RULES.md`
3. `docs/API_CONTRACT_RULES.md`
4. `docs/DATABASE_RULES.md`

## 输出格式

```md
## 后端模块设计方案

### API Route

### Pydantic Schema

### Service

### Repository

### Model / Migration

### Integration

### Celery Task

### 权限与操作日志

### 测试方案
```

## 强制规则

1. Route 保持薄。
2. Service 写业务。
3. Repository 写数据访问。
4. Task 只做任务编排。
5. 外部 API 放入 integrations。
6. 不在 Route 中写复杂 SQL。
