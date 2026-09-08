# 后端模块清单

## 文件用途

本文件用于记录本项目计划使用和已经实现的后端通用模块。

后端不使用“组件”这个概念，应使用 Route / Schema / Service / Repository / Model / Task / Integration 分层。

## 初始通用模块规划

| 模块 | 建议目录 | 用途 |
|---|---|---|
| Backend API Foundation | `backend/app/core/` | 请求关联、响应契约、异常、认证、权限与资源级数据范围 |
| Config | `backend/app/core/config.py` | 配置读取 |
| Logging | `backend/app/core/logging.py` | 日志配置 |
| Pagination | `backend/app/schemas/pagination.py` | 分页请求和响应 |
| Task Model | `backend/app/models/task.py` | 统一后台任务表 |
| Audit Log | `backend/app/models/audit_log.py` | 操作日志 |
| LLM Adapter | `backend/app/integrations/llm/` | 模型调用封装 |
| External Client Base | `backend/app/integrations/base.py` | 第三方 API 基类 |

新增通用后端模块后，AI 必须更新本文件。

## Backend API Foundation

| 项目 | 内容 |
|---|---|
| Module name | Backend API Foundation |
| Module key | `backend-api-foundation` |
| Purpose | 提供 request ID、统一响应和错误、默认关闭认证、权限入口及资源级 store scope |
| Owned backend files | `backend/app/core/api.py`, `backend/app/core/auth.py`, `backend/app/core/permissions.py`, `backend/app/core/data_scope.py` |
| Application entrypoint | `backend/app/main.py` |
| Tests | `backend/tests/core/test_backend_api_foundation.py`, `backend/tests/test_health.py` |
| Public endpoint | 仅 `/health`；无需认证、权限或 data scope，只返回安全存活状态 |
| Protected default | 其他业务路由默认需要可信 Principal；无可信认证时 fail closed |
| Dependencies | 仅使用现有 FastAPI、Pydantic 与 Python 标准库；无数据库、无外部 API |
| Not in scope | 产品 API、legacy MySQL、PyMySQL、ORM、migration、mart/read model、frontend |
