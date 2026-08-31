# 后端模块清单

## 文件用途

本文件用于记录本项目计划使用和已经实现的后端通用模块。

后端不使用“组件”这个概念，应使用 Route / Schema / Service / Repository / Model / Task / Integration 分层。

## 初始通用模块规划

| 模块 | 建议目录 | 用途 |
|---|---|---|
| API Response | `backend/app/core/responses.py` | 统一响应结构 |
| Error Handling | `backend/app/core/errors.py` | 统一异常和错误码 |
| Config | `backend/app/core/config.py` | 配置读取 |
| Logging | `backend/app/core/logging.py` | 日志配置 |
| Security | `backend/app/core/security.py` | 鉴权与权限基础 |
| Pagination | `backend/app/schemas/pagination.py` | 分页请求和响应 |
| Task Model | `backend/app/models/task.py` | 统一后台任务表 |
| Audit Log | `backend/app/models/audit_log.py` | 操作日志 |
| LLM Adapter | `backend/app/integrations/llm/` | 模型调用封装 |
| External Client Base | `backend/app/integrations/base.py` | 第三方 API 基类 |

新增通用后端模块后，AI 必须更新本文件。
