# 后端架构规则

## 1. 固定技术栈

```text
Python 3.13 + uv + FastAPI + Pydantic + SQLAlchemy 2 + Alembic + Redis + Celery
```

## 2. 推荐目录

```text
backend/
├─ app/
│  ├─ main.py
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ response.py
│  │  ├─ security.py
│  │  ├─ permissions.py
│  │  ├─ data_scope.py
│  │  ├─ logging.py
│  │  └─ secrets.py
│  ├─ db/
│  │  ├─ postgres.py
│  │  ├─ legacy_mysql.py
│  │  └─ session.py
│  ├─ modules/
│  │  ├─ auth/
│  │  ├─ dashboard/
│  │  ├─ products/
│  │  ├─ sales/
│  │  ├─ ads/
│  │  ├─ aftersales/
│  │  ├─ warehouse/
│  │  ├─ finance/
│  │  ├─ operations/
│  │  ├─ purchase/
│  │  ├─ ai_center/
│  │  ├─ data_center/
│  │  ├─ statistics/
│  │  └─ settings/
│  ├─ workers/
│  ├─ integrations/
│  └─ utils/
├─ alembic/
├─ tests/
├─ pyproject.toml
└─ uv.lock
```

## 3. 分层规则

```text
route       只负责接收请求、权限声明、调用 service、返回响应
schema      Pydantic request / response
service     业务规则、流程编排、权限后的业务判断
repository  数据库查询与写入
model       SQLAlchemy table model
task        Celery 后台任务
integration 外部 API / AI / 飞书 / Webhook 客户端
```

禁止把 SQL、业务计算、权限判断全部堆在 route 文件。

## 4. 旧库访问规则

- 旧库 MySQL 只能放在 `db/legacy_mysql.py` 和 legacy repository 中读取。
- 旧库账号必须只读。
- 禁止写旧库。
- 禁止旧库迁移。
- 禁止无条件扫描旧库 raw 大表。
- 旧库接口必须在 API meta 中返回 `source: legacy_mysql` 和 `source_tables`。

## 5. 新库写入规则

- 新 PostgreSQL 写入必须走 SQLAlchemy repository。
- 表结构变更必须走 Alembic。
- 生产迁移必须人工审核。
- app 账号不允许 DROP / ALTER。
- migration 账号只在迁移流程中使用。

## 6. 后台任务规则

以下任务必须走 Celery，不能阻塞 API：

```text
导入
导出
同步
历史重算
AI 任务
批量处理
飞书通知批量发送
大数据报表生成
```

所有 Celery 任务必须：

```text
有 task_id
幂等
可重试但有限制
记录 started_at / finished_at / failed_reason
写入 ops_sync_run / ai_task / ops_export_task 等任务表
```
