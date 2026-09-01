# PostgreSQL 初始 Schema 规划

## 1. 第一批表

### 系统权限

```text
sys_user
sys_role
sys_permission
sys_user_role
sys_role_permission
sys_menu
sys_page_data_scope
sys_feature_flag
```

### 组织与负责人

```text
org_unit
org_user_membership
org_user_report_line
core_product_owner
```

### 主数据

```text
core_store
core_product
core_sku
core_sku_mapping
core_store_mapping
```

### 费用规则

```text
biz_fee_rule
finance_period_lock
finance_recalculate_batch
finance_recalculate_diff
```

### 集成配置

```text
sys_integration_config
sys_secret
sys_secret_version
ops_notification_channel
ops_notification_rule
sys_ai_provider_config
sys_ai_model_config
```

### 任务与审计

```text
ops_sync_run
ops_sync_error
ops_data_freshness
ops_query_cache
ops_api_log
ops_error_log
ops_export_task
ops_import_batch
ops_import_row_error
audit_action_log
audit_permission_change_log
audit_secret_change_log
```

### AI

```text
ai_task
ai_task_step
ai_prompt_template
ai_result
ai_usage_log
ai_human_review
```

## 2. 字段约定

每张业务表建议包含：

```text
id uuid primary key
created_at timestamptz
updated_at timestamptz
created_by uuid nullable
updated_by uuid nullable
is_active boolean
```

重要业务表不要物理删除，使用：

```text
deleted_at timestamptz nullable
deleted_by uuid nullable
```

## 3. 金额字段

```text
numeric(18,4)
currency_code varchar(3)
fx_rate numeric(18,8)
fx_date date
fx_source varchar
```

## 4. 配置字段

复杂配置使用 PostgreSQL `jsonb`，但必须有 schema 文档和测试。
