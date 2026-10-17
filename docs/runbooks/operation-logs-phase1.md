# 运营日志第一阶段：旧历史导入 + 新系统人工编辑

> Draft PR #227 依赖 PR #226 的 RBAC 0042 迁移。仅代码审查，不代表生产授权。

## 迁移链与版本核对

已确认 GitHub `main` 唯一链头是 `20261016_0041_wfs_rbac_actions`。
未合并的 #226 新增 `20261017_0042_rbac_backfill`，因此本 PR 创建
`20261017_0043_operation_logs`，其 `down_revision` 必须严格为
`20261017_0042_rbac_backfill`。

- #227 当前 **以 #226 的分支为 base**，差异仅运营日志代码。
- 合并顺序：先 #226，再重新核对 #227 的 Alembic `heads`。
- 不允许在 #226 未合并到主线时直接将 #227 合并进 main。
- 现有 WFS migration smoke 升级到固定的 0036/0037，而非任意 head；
  本模块 migration 仍须在**隔离 PostgreSQL 16**上完成真实升级/结构验证。
- 不自动执行 `alembic upgrade head`，不写旧 MySQL，不改镜像定时脚本。

## 两类日志的数据归属（重要）

| 内容 | 历史来源 | 正式存储 | 后续写入 |
| --- | --- | --- | --- |
| 系统运营事件 | `legacy_mirror.event_ops_action_log` | `ops_system_operation_events` | Celery 增量同步 + 每日对账 |
| 旧人工运营日志 | `legacy_mirror.biz_product_operation_log` | `ops_manual_operation_logs`，`source_kind=legacy` | 首次导入后只读；不持续覆盖 |
| 新人工日志 | 无旧系统依赖 | `ops_manual_operation_logs`，`source_kind=manual` | 运营直接在新系统编辑、保存、提交 |
| 词/广快捷链接 | 无旧系统依赖 | `ops_operation_log_links` | 新系统可写 |

新人工日志必须以 `source_account_ref + 业务日 + store_id + item_id + msku`
确定唯一键；旧镜像 ID 不作为人工新记录的 ID。旧历史保留，不被新编辑删除。
一条新人工记录可以覆盖展示旧日志，但旧原文仍保存在历史表中。

## 生产安全：默认不可写

首次导入必须先读取新库镜像并核对以下预检：

```bash
cd backend
uv run alembic heads
uv run python scripts/sync_legacy_operation_logs.py --batch-size 250
```

仅输出安全计数：system_scanned、manual_scanned、unresolved、affected。
`--commit` 必须另外加 `--acknowledge-db-write` 和环境开关
`OPERATION_LOG_DB_WRITE_AUTHORIZED=true`，生产必须再设置
`PRODUCTION_LOG_IMPORT_AUTHORIZED=true`；没有书面授权不要执行。

先完成历史导入并验证数量、异常账户以及幂等性，再**单独授权**设置
`OPERATION_LOG_HISTORICAL_IMPORT_VERIFIED=true` 和
`OPERATION_LOG_MIRROR_SYNC_ENABLED=true`，启用 Celery Beat/Worker：

- 每 10 分钟 `operation_logs.mirror_incremental`，只读取镜像系统事件；
- 每天 UTC 03:00 `operation_logs.mirror_reconcile` 全量差异对账；
- 实际新鲜度不能高于旧 MySQL → `legacy_mirror` 的现有任务频率；
- 写入门禁不满足时任务返回 disabled，不连接旧系统、不写历史镜像。

## 权限、读写接口

- `GET /api/operations/logs/rows?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`：
  登录用户在授权 account 范围内取得运营日志列表/版本号/系统事件；
  当前对跨度与单次结果大小设上限，避免全店铺多日笛卡尔积。
- `GET /api/operations/logs`：只读系统事件/当日人工日志及历史。
- `PUT /api/operations/logs/manual/batch`：批量事务提交（每次最多 200 条），
  每行以 revision 乐观锁防覆盖；一批中任一错误整批回滚。
- `PUT /api/operations/logs/links`：词/广快捷链接保存。
- 查看要求页面访问权限；写入要求独立的
  `action:operations:log:edit`，不是运营计划写入权限。
- 账号无法唯一解析的旧日志保留未归属状态，禁止对外展示。
- 不允许用 Item ID 单独关联跨账号或跨店铺日志。
- 旧快照事件不是精确操作审计，禁止伪造操作人或真正点击的时间。

## UI 与数据范围

保留原“运营 → 运营日志”编辑页面，去掉模拟表数据。表格单行保存、
批量填写、草稿保存、提交全部都请求新系统 API。
当前“系统事件生成草稿”仅从正式事件结果生成，不用假时间和假操作人。

限制：页面当前最多查询连续 31 个业务日 / 5000 行，超过时返回 422
而非悄悄截断；历史范围、多店铺批量查询需要下一轮服务端分页优化。
此 PR 仍是 **Draft**，应待全面测试后才可合并。

## 必须验收

1. 比较镜像两表行数、正式表行数、最小最大 ID、日期覆盖范围；
   镜像仍同步时允许给出一致性截点。
2. 同一历史数据重复导入：原文不被改写，不产生新重复记录。
3. 旧事件发生修正或迟到：增量窗口以及每日完整对账能更新系统事件。
4. 多来源账号同店铺 ID、多个 MSKU、无归属 Item：不得越权。
5. 历史旧人工日志只读；新运营写入不调用旧系统，也不修改镜像。
6. 草稿、提交、单行、多行、乐观锁冲突、批次回滚、工作类型。
7. 运营日志与每日销售的关联展示：同业务日同账号同店铺商品一致。
8. GitHub rule-pack、前端 lint/typecheck/test/build、后端 Ruff/pytest/import，
   隔离 PostgreSQL WFS smoke 和新增 0043 migration smoke 全部通过。

此 PR 不执行任何生产迁移、回填、定时任务启用或部署。


## 日志按登录用户隔离（PR #227 补充）

管理员身份基于 app_users.is_super_admin 或数据库 app_roles 的 admin 授权；普通用户登录后以 app_users 的 ID 进行新日志归属校验。非管理员只能查看其实际负责商品以及由其建立的日志记录；即使持有店铺 source_account 数据权限也不能读取其他运营的日志。商品负责人字符串必须唯一匹配 app_users.username / display_name / feishu_name，发生重名、无负责人或历史孤立记录时拒绝推测，仅管理员可见。服务端逐项拦截详情、列表、写入、链接入口；预览令牌不可访问正式日志数据。

人工新增日志 owner_user_id 是后端从 Token 派生而非前端指定；已有日志归属其他用户时拒绝修改。历史 legacy 记录保持原始内容且 owner_user_id 为空，不依据导入时间冒名绑定。正式数据库权限验收必须包括两名用户具有相同店铺权限但互不能读取/编辑日志的用例。
