# Backend AGENTS.md

本文件适用于 `backend/` 下所有后端开发。

## 技术栈

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- Redis
- Celery
- LLM Provider Adapter，默认 OpenAI Python SDK

## 分层

```text
API Route
↓
Schema
↓
Service
↓
Repository
↓
Model
```

## 规则

1. API Route 保持薄。
2. 业务逻辑放 Service。
3. 数据库访问放 Repository。
4. 数据表定义放 Model。
5. 请求和响应放 Schema。
6. 外部 API 客户端放 Integration。
7. 后台任务使用 Celery。
8. Celery Task 只做任务编排，不堆复杂业务。
9. 数据库结构变更必须使用 Alembic。
10. 不允许记录密钥到日志。
11. 不允许从 `old-system/` import 代码。

开发后端模块前，先读取 `skills/backend-module-designer/SKILL.md`。
