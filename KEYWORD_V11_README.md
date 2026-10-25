# SZZSBJ 关键词规则 V1.1 与数据库建表交付包

**本包不包含用户 Mac 的未跟踪文件。当前为可审查的迁移和开发交付，不代表数据库已经部署建好。**

## 建设结果

- 从旧版 49 章规则与 10 月 23 日审查稿整理出统一规则、冲突裁决项、当前/未来业务边界。
- **第一阶段 21 张新表**：SQLAlchemy 2.0 模型 + PostgreSQL SQL + Alembic 草案，复用现有 `products`/`product_platform_listings`。另有 12 张未来广告业务表只在设计中，不会本次提前创建。
- 源文件和行、ASIN 全部图片 URL、Walmart 页面快照、商品事实、关键词来源、规则版本、逐词评分、运行/导出历史、自动入库评估及运营决策记录的持久化结构。
- 保守规则底座（`rule_gates.py`）以及 21 项测试；前端两个阻断安全问题的小补丁。
- **尚未发布的算法规则和平台模板**明确列出待审批项，不会擅自把数据缺失变成具体分数/真实出价。

## 文件导航

| 文件 | 用途 |
|---|---|
| `docs/architecture/WALMART_KEYWORD_V11_RULES.md` | 规则重构、Rule ID、硬约束、未裁决清单 |
| `docs/architecture/KEYWORD_SCHEMA_DATA_DICTIONARY.md` | 21 张新增表的用途、约束及 12 张未来表 |
| `docs/architecture/KEYWORD_CORE_SCHEMA.sql` | 第一阶段 21 张表的静态 PostgreSQL DDL（**仅审查，不要直连生产执行**） |
| `backend/app/modules/keyword_planning/models.py` | PostgreSQL SQLAlchemy 实体模型 |
| `backend/app/modules/keyword_planning/rule_gates.py` | 不造假的后端规则基础校验及名额分配 |
| `backend/alembic/versions/20261023_0055_keyword_planning_core.py` | 基于 GitHub main 0054 的静态建表迁移草案；自带历史不可变触发器 |
| `backend/tests/modules/keyword_planning/` | 必填/安全/评分上界/配额/元数据的测试 |
| `patches/0001_frontend_fail_closed_from_uploaded_diff.patch` | ASIN 校验 + Walmart API 失败不再错误确认 |
| `patches/0002_alembic_register_keyword_models.patch` | 为真实仓库 Alembic 登记模型 |
| `CODEX_HANDOFF.md` | 接入本地工作树的安全步骤、真实缺口与后续开发 PR 建议 |
| `qa/` | 隔离运行用的测试辅助文件/模拟 FK 根，不进入用户生产代码 |

## 安全接入（先核验，不自动覆盖本机）

1. 从本包复制 `backend/app/modules/keyword_planning/`、`backend/tests/modules/keyword_planning/` 和文档到用户的独立开发 worktree；**不要复制 `qa/` 到正式 backend/app**。
2. 先读 `CODEX_HANDOFF.md` 和 `20261022_0048_decodo_config_usage.py`，核对 `alembic heads`。本包迁移当前 `down_revision` 是主线 `20261022_0054_merge_walmart_identity_and_domestic_packing`，不知道本地尚未跟踪的 Decodo 迁移真正依赖链，**不得直接 upgrade**。
3. 对两个补丁先 `git apply --check`，如果本地代码已有不同变化，手动比对，禁止强制覆写。
4. 集成后在授权的隔离 PostgreSQL 测试数据库测试迁移和全部操作，确认成功后才能申请生产审批。**本包没有执行任何数据库迁移。**
5. 新规则文档待业务批准后才发布；UI/Excel/广告仍需通过实际 API 和模板验证，不能将此包视为已接通所有业务。

## 测试情况

- `21 passed`：规则安全校验及 ORM 元数据结构检查，在 Python/SQLAlchemy 隔离环境完成。
- Python 模块 `py_compile` 和 SQLAlchemy PostgreSQL `CreateTable/CreateIndex` 编译通过。
- 前端补丁在上传的差异快照上通过 `git apply --check`，**未覆盖你本机代码**。
- 未运行实际 PostgreSQL 建表、实际文件上传、官方 Walmart Bulk 文件生成或广告 API 写入。
