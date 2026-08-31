# 后端模块清单

## 文件用途

本文件用于记录本项目计划使用和已经实现的后端通用模块。

后端不使用“组件”这个概念，应使用 Route / Schema / Service / Repository / Model / Task / Integration 分层。

## 初始通用模块规划

| 模块 | 建议目录 | 用途 | 备注 |
|---|---|---|---|
| API Response | `backend/app/core/responses.py` | 统一响应结构 | 不允许每个接口自创格式 |
| Error Handling | `backend/app/core/errors.py` | 统一异常和错误码 | 前端可识别 |
| Config | `backend/app/core/config.py` | 配置读取 | 不写死密钥 |
| Logging | `backend/app/core/logging.py` | 日志配置 | 不输出敏感信息 |
| Security | `backend/app/core/security.py` | 鉴权与权限基础 | 敏感接口必须校验 |
| Pagination | `backend/app/schemas/pagination.py` | 分页请求和响应 | page / page_size |
| Task Model | `backend/app/models/task.py` | 统一后台任务表 | Celery 状态承接 |
| Audit Log | `backend/app/models/audit_log.py` | 操作日志 | 敏感写操作必须记录 |
| LLM Adapter | `backend/app/integrations/llm/` | 模型调用封装 | 默认 OpenAI SDK |
| External Client Base | `backend/app/integrations/base.py` | 第三方 API 基类 | 超时、重试、错误转换 |

## AI 使用规则

AI 新增后端模块时必须：

1. 先检查是否已有可复用模块。
2. 遵守 Route / Schema / Service / Repository / Model 分层。
3. 不在 Route 中写复杂业务。
4. 不在 Service 中写大量裸 SQL。
5. 不在 Repository 中写页面展示逻辑。
6. 不在 Celery Task 中堆复杂业务逻辑。

新增通用后端模块后，AI 必须更新本文件。
