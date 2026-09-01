# 数据库账号权限规划

## 1. 账号分层

| 账号 | 数据库 | 权限 | 用途 |
|---|---|---|---|
| legacy_readonly | 旧 MySQL | SELECT only | 旧库只读查询 |
| skyc_v2_app | 新 PostgreSQL | SELECT/INSERT/UPDATE/DELETE | 应用运行 |
| skyc_v2_migrator | 新 PostgreSQL | DDL | Alembic 迁移 |
| skyc_v2_readonly | 新 PostgreSQL | SELECT only | 报表/排查 |

## 2. 禁止事项

```text
应用账号不允许 DROP / ALTER
readonly 账号不允许写入
migrator 账号不用于日常 API
生产连接串不进 Git
```

## 3. 迁移流程

```text
生成 Alembic migration
本地测试
staging 测试
人工审核
备份
production 执行
验证
记录发布日志
```
