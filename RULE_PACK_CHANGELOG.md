# Rule Pack Changelog

## v2.0 - 2026-09-01

### Added

- PostgreSQL 最终数据库决策
- Python 3.13 / Node 24 LTS / npm / uv 最终工程选型
- API 返回格式 `{ success, data, error, meta, request_id }`
- 数据中心 > API文档 页面规则
- 页面右上角 `?` 帮助入口规则
- SOP / 公司 SOP 目录规则
- 动态角色权限，不硬编码 roleName
- 每个页面独立数据权限
- 组织架构、小组长、组员、直属关系规则
- 产品负责人归属和 owner_type 规则
- 店铺佣金、汇率、费用规则版本化
- 月结锁账和历史重算规则
- AI Token、飞书 Webhook、外部密钥集成配置规则
- 不新增第二套后台管理系统规则
- P0 / P1 / P2 阶段优先级
- 第一批 30 个 Codex 任务
- 前端 navigation.ts 模板
- 后端 response / permission 模板
- Alembic 初始 migration 草稿

### Changed

- `AGENTS.md` 重写为 v2 总规则。
- `AI_DAILY_RULES.md` 重写为 v2 日常入口。
- `README_AI_RULES.md` 更新为 v2 使用说明。
- `docs/TECH_STACK.md` 从待确认改为最终选型。
- `docs/PERMISSION_AND_AUDIT_RULES.md` 更新为动态权限模型。
- `RULE_PACK_FILE_INDEX.md` 更新 v2 文件索引。

### Removed from output zip

- `.git/`
- `__MACOSX/`
- `.DS_Store`
- AppleDouble `._*` 文件

### Important

v2 新文件优先于旧 docs。旧 docs 保留为细节参考，但如果发生冲突，以 v2 新文件为准。
