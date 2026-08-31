# 日志规则

## 文件用途

本文件用于约束后端、Celery、外部 API、LLM 调用中的日志记录方式。

## 日志应包含

- request_id
- task_id
- user_id / operator_id，如适用
- store_id，如适用
- source_platform，如适用
- action
- status
- duration_ms
- error_code

## 禁止记录

- API Key
- Token
- Cookie
- Session
- 密码
- SSH 私钥
- 完整外部 API 请求头
- 大量原始业务数据

## Celery 日志

任务日志必须能追踪任务开始、结束、失败、重试、进度和错误摘要。
