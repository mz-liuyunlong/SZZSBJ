# CODEX_HANDOFF — SZZSBJ 关键词 V1.1 规则 + 建表交付

> 2026-10-24 开发更新：下文保留为**历史交接**，不能作为当前分支的完成状态。当前源码有带证据短语的分类、0057 独立规则审批、内部五表和官方模板拒绝式适配；原有关键词页面已恢复，本地工作流尚未接通后端持久化。详情和真实测试见 [`docs/architecture/KEYWORD_V11_ONE_SHOT_STATUS.md`](docs/architecture/KEYWORD_V11_ONE_SHOT_STATUS.md)。D01–D08 尚未获真实批准，外部采集授权/当前官方模板尚缺，整体仍为 **NO-GO**。分支已推送到 Draft PR，未合并、未上线。

## 范围和状态

- 已完成：原规则/审查稿对照、规则裁决表、21 张第一阶段新增表 ORM、静态 PostgreSQL DDL、Alembic 迁移草案、源数据保护触发器、规则保守判定模块、单元/元数据测试、两组补丁。
- **未完成/不得误报：** 未访问 Mac 工作树实时版本、未读取 `backend/app/modules/decodo/*` 等所有 untracked 源码、未在用户真实项目环境做 build、未连接/改动生产 PostgreSQL、未执行 Alembic 迁移、未实现 API/对象存储/前端绑定/完整 25 类型自动判断/5 表正式导出/真实广告创建。
- 原始文档仍是旧版锁定规则；新规则文档标注为**审查基线/待批准**。不要直接覆盖旧原文，不可把建议当作用户已确认的正式变更。

## 第一批应该进入 PR 的安全修改

1. **确认本地状态，保留全部已有工作**：`git status --short --branch`。严禁 `git reset --hard`、自动删 `.bak`、提交整个 worktree；禁止写 `old-system/**`。
2. 验证 Decodo 本地未跟踪迁移 `backend/alembic/versions/20261022_0048_decodo_config_usage.py` 的 `revision/down_revision`，并检查 `alembic heads`。本包 `20261023_0055_keyword_planning_core.py` 目前针对 GitHub main 的 `20261022_0054_merge_walmart_identity_and_domestic_packing`；**如果两者同为 head 必须先处理迁移图，不得绕过**。
3. 复制 `backend/app/modules/keyword_planning` 模型和规则底座、`backend/tests/modules/keyword_planning` 测试到对应目录；将 migration 草案拷入本地前先验证版本依赖。
4. `git apply --check` 两个补丁后再决定是否合并；本包 `0001` 在用户上传 `git diff origin/main` 的已跟踪快照上已试通过。若本地随后继续改过对应文件，不应强制应用或覆盖新代码。
5. `backend/alembic/env.py` 注册新模型；运行 `pytest`、`ruff`、`mypy`、导入/元数据检查，随后在**经过独立授权的隔离 PostgreSQL** 进行迁移和读写事务验收。禁止连接本机生产隧道误写生产库。
6. 跟踪独立 Issue 完成规则发布/后端校验 API/文件对象存储/API 实采快照/关键词分析与 5 表输出；完成审查前不得启用任何正式平台上传或自动广告创建操作。

## 已上传差异明确发现的现有代码问题

| 文件/功能 | 现状问题 | 处理 |
|---|---|---|
| `frontend/src/features/keyword-planning/model.ts` | `isAsin()` 只检查非空，非法词可算合法 ASIN | `0001` 补丁严格检查 10 位字母数字；后端同样校验 |
| `frontend/src/pages/ai-center/keyword-launch/KeywordLaunchPage.tsx` | Walmart `confirmWalmartFacts()` 失败路径仍会 `setProductConfirmation`，存在假确认 | `0001` 补丁改失败为锁定；最终仍要后端严查 Item ID/权限 |
| `frontend/src/features/keyword-planning/importWorkbook.ts` | 在 Map 解析阶段对关键词去重，未保留完整原始行 | 不做小补丁蒙混；迁移后由后端先保存原始二进制/行，再独立为分析生成去重候选 |
| `frontend/src/features/keyword-planning/store.ts` | `analyze` 以新分析结果替换整个 SKU 的当前 entries；人工词库状态可能消失 | 改为后端持久库 + 追加 analysis run，永不覆盖 `biz_sku_keyword`，页面 Zustand 只做 UI 缓存 |
| `frontend/src/features/keyword-planning/model.ts` | 有简化本地近似评分，且 P0→P1/P2、Broad 规则不完整 | 替换为服务器已发布版本算法；当前 `rule_gates.py` 为安全底座，未知分数禁止编造 |
| `frontend/src/pages/ai-center/keyword-launch/KeywordLaunchPage.tsx` | 导出是本地五表初筛，不能声称 Walmart 官方 Bulk 模板 | 正式输出必须由后端生成/核验模板版本且显式二次授权 |
| `frontend/src/pages/ads/keyword-library/KeywordLibraryPage.tsx` | 来源仅 `'excel' | 'manual'`，未来不能表达同词多来源 | 用 `biz_kw_source_event` 事件记录，正式词库始终一条 |
| 本地 `backend/app/modules/decodo/` | 只有文件名而没有上传内容 | 必须读取路由/服务/解析/SQLite 测试代码，核实 verified 判据和数据库写入边界 |
| 本地 `20261022_0048_decodo_config_usage.py` | 未跟踪、真实 revision 未知 | 先审查并处理 Alembic 多头/冲突，再接本次 migration |

## 规则实现现有可用部分

`rule_gates.py` 已支持：严格 ASIN、保守关键词标准化、Item ID/10 项事实/额外风险核对、四项金额与日期校验、25 类型枚举、九页面承接证据检查、六分量边界、硬风险/品牌隔离、base vs allocation grade、P0 5/P1 10/P2 30、Exact 20、Broad 5+15、14 项稳定排序、正式导出授权门。

**尚未实现**：从真实 Walmart/ASIN/Excel 文本自动识别 25 主类型、真正的语义根归一化、九状态证据解析、分量量化证据生成、数据缺失的正式业务分值方案、预算合理性与最新平台模板、可读的 10–30 字逐词词质说明、后端 Excel 5 Sheet 导出、来源 API 同步。不可让前端假装这些已完成。

## 当前分支必须修的非业务基础安全问题

`backend/app/core/auth.py` 和 `backend/app/core/local_scoped_writes.py` 的两组 Decodo 本地测试白名单要求特别检查。即使代码注释称“SQLite-only”，也必须验证实际数据连接来源不会复用 PostgreSQL 隧道；不要因为 `APP_ENV=local` 就信任外部请求与前端声明的 `source_account_ref`。

## 建议的分步 PR 和验收

| PR | 范围 | 验收门槛 |
|---|---|---|
| PR-1 | 产品/ASIN/Excel/规则的**安全基础契约**，前端 fail-closed 小补丁 | 缺失事实、API 失败、非法 ASIN 均不能确认；不能生成真实广告 |
| PR-2 | Core ORM+Alembic+RBAC+对象存储原件导入 | 21 张表、唯一性/历史不可变/账户隔离、原文件重复上传保留、ASIN 50+ URL |
| PR-3 | 后端完整分类、页面证据和评分算法，规则发布 | 25 类型及九页面状态黄金样例全通过；所有分项有来源、无不确定分数“伪完成” |
| PR-4 | Exact/Broad 配额与统一分析结果、11 列前端 | 同一 run 稳定重现，历史分析不覆盖词库，人工补词状态保留 |
| PR-5 | 五表导出、官方模板校验、确认/审计 | 11 列 UI ≠ 14 列 01；5 表内容来自同一个 run；无授权不得正式输出 |
| PR-6（后续） | 搜索词入库与真实广告同步/执行 | 自动入库有版本和否决记录；自动创建广告具备店铺隔离、幂等和平台对账 |

## 立即执行的 QA（只读）

```bash
# 在你本机 SZZSBJ 项目根目录（不要在生产服务器运行）
git status --short --branch
rg '^(revision|down_revision)\s*=' backend/alembic/versions/20261022_0048_decodo_config_usage.py
cd backend
alembic heads       # 只检查迁移图，不执行 upgrade
pytest -q tests/modules/keyword_planning
python -m compileall -q app/modules/keyword_planning
```

`alembic heads` 可能依赖项目环境配置；如果要求连接生产数据库，先停止并只检查迁移脚本的 revisions。

## 2026-10-23 本交付 QA

- Python 规则测试、ORM metadata 结构测试：21 项已通过（隔离 QA stub 使用与真实项目相同的 Base 命名约定，未连接数据库）。
- 21 张新增表 PostgreSQL DDL 已由 SQLAlchemy 生成并与静态迁移冻结；没有实际 PostgreSQL 运行验证。
- 前端安全补丁已在上传的差异快照上通过 `git apply --check`；尚未应用到用户本机。
