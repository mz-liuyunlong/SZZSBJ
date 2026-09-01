# 旧库只读接入方案

## 1. 原则

```text
旧 MySQL 是 legacy data source
只读，不写，不迁移，不重启，不改结构
```

## 2. 访问账号

必须使用只读账号：

```text
SELECT only
禁止 INSERT / UPDATE / DELETE / ALTER / DROP / CREATE / TRUNCATE
```

## 3. 查询规则

```text
禁止 SELECT * 扫描大表
禁止无条件读取 response_json 大字段
必须分页
必须限制日期范围
必须记录 source_tables
必须返回数据新鲜度
```

## 4. 后端目录

```text
backend/app/db/legacy_mysql.py
backend/app/modules/*/repositories/legacy_*.py
```

## 5. API meta

所有旧库接口必须返回：

```json
{
  "source": "legacy_mysql",
  "source_tables": ["fact_sales_daily"],
  "freshness": {
    "latest_business_date": "2026-09-01"
  }
}
```

## 6. 禁止第一阶段复制大 raw 表

旧库 raw 大表可只读分析，不要第一阶段全量复制到 PostgreSQL。
