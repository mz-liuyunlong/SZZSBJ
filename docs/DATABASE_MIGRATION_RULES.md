# Database Migration Rules

## Required Rules

- PostgreSQL schema 只通过 Alembic migration 变更；禁止手工修改生产结构。
- 每个 migration 必须属于已批准数据库 PRP，包含目的、影响对象、锁/性能风险、upgrade、downgrade 或不可逆说明、数据备份/恢复和验证。
- Autogenerate 只生成候选 diff，必须人工逐行 Review。
- Migration 文件不得包含 secret、真实生产标识或无关格式化。
- 生产执行与代码合并是两次授权；AI 不得自动升级/降级生产。
- 数据回填、历史重算、破坏性 DDL、重命名或删除必须独立计划并有停机/在线策略。
- 测试只能使用明确隔离的 test DB，不得 fallback 到开发或生产。

## Stop Conditions

目标环境不明、权限过大、无回滚/恢复、查询/锁风险未知、包含业务口径变更或需要 root 权限时停止。

## Checklist

- [ ] PRP、owner approval、精确 revision 和环境确认。
- [ ] 前后 schema、数据影响和兼容窗口已说明。
- [ ] 测试、备份/恢复、观察和回滚步骤可执行。
- [ ] Registry/catalog 按新增对象更新。
