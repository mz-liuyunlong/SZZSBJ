# 后台任务开发规则

## 文件用途

本文件用于约束 AI 在未来新增后台任务时的开发方式。

本项目固定使用 Redis + Celery 作为后台任务方案。AI 不允许自行引入第二套后台任务系统。

## 什么情况必须用 Celery

以下场景不得直接在 FastAPI 请求里同步执行：预计执行超过 3 秒的任务、批量同步平台数据、批量调用外部 API、批量调用 AI 模型、大文件导入、大报表生成、批量图片生成或处理、需要失败重试的任务、需要后台持续执行的任务。

## 标准流程

```text
FastAPI 接收请求
↓
创建任务记录
↓
投递 Celery
↓
Celery Worker 执行
↓
更新任务进度和状态
↓
前端轮询任务状态
↓
任务完成后读取结果
```

## 统一任务状态

```text
pending
running
succeeded
failed
cancelled
partial_success
```

## 任务表建议字段

```text
id
task_type
status
progress
total
success_count
failed_count
error_message
result_path
created_by
created_at
started_at
finished_at
```

## Celery 任务必须说明

任务用途、输入参数、输出结果、是否幂等、重试策略、会修改哪些表、是否调用外部 API、是否可能产生费用、失败后用户应该看到什么、是否允许重复执行。

Celery Task 只做任务编排，不要把复杂业务逻辑写满 Task。
