# 数据库架构规则

## 1. 总体架构

```text
旧系统 MySQL
  只读 legacy data source
  不改结构，不写入，不迁移 raw 大表

        ↓ 只读查询 / 增量同步 / ETL

新系统 PostgreSQL
  ├─ sys_*       系统层：用户、角色、权限、菜单、配置
  ├─ org_*       组织架构层：部门、小组、成员、上下级
  ├─ core_*      核心主数据：店铺、产品、SKU、负责人、供应商
  ├─ stg_*       暂存层：从旧库抽取后的过渡数据
  ├─ raw_*       新系统自己的原始导入/外部采集记录
  ├─ dim_*       维度层：店铺、产品、负责人、类目
  ├─ fact_*      事实层：销售、广告、库存、利润、退款
  ├─ mart_*      前端展示层：看板汇总、页面缓存
  ├─ biz_*       业务层：运营日志、计划、审批、清货
  ├─ event_*     事件层：异常、告警、任务结果
  ├─ ops_*       运维层：同步记录、失败记录、数据新鲜度
  ├─ audit_*     审计层：操作审计、权限审计、高危动作
  └─ ai_*        AI 层：任务、结果、Prompt、Token 成本
```

## 2. 第一阶段不要全量复制旧 raw 大表

新 PostgreSQL 可以有 `raw_*`，但第一阶段禁止把旧库 `raw_lingxing_api`、`raw_walmart_ads_csv` 等大 raw 表全量复制进新库。

第一阶段新库主要用于：

```text
系统配置
用户角色权限
组织架构
产品负责人归属
费用规则
SOP 元数据
AI 任务
审计日志
通知配置
任务状态
缓存汇总
```

## 3. 初始核心表

第一批建议：

```text
sys_user
sys_role
sys_permission
sys_user_role
sys_role_permission
sys_menu
sys_page_data_scope
sys_feature_flag
sys_integration_config
sys_secret
sys_secret_version

org_unit
org_user_membership
org_user_report_line

core_store
core_product
core_sku
core_product_owner
core_sku_mapping

biz_fee_rule
finance_period_lock

ops_data_freshness
ops_sync_run
ops_sync_error
ops_query_cache
ops_notification_channel
ops_notification_rule

audit_action_log
audit_permission_change_log
audit_secret_change_log

aio_task
ai_task_step
ai_prompt_template
ai_result
ai_usage_log
```

## 4. 账号权限

```text
legacy_readonly：旧 MySQL，只能 SELECT
skyc_v2_app：新 PostgreSQL 应用账号，只能 SELECT/INSERT/UPDATE/DELETE
skyc_v2_migrator：新 PostgreSQL 迁移账号，允许 DDL，但只在人工审核迁移时使用
```

## 5. 迁移规则

- 只允许 Alembic 管理新库结构。
- 不允许手工 SQL 直跑生产。
- Alembic migration 必须进入 PR。
- 生产迁移前必须备份和回滚方案。
- 已月结财务数据默认锁定。
