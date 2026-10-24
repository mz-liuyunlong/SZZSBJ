# Walmart Keyword V1.1 增量交付 — 2026-10-24

## 来源和运行边界

本增量建立在 2026-10-23 已安装的安全规则引擎、21 表迁移、只读 API、`analysis_execution.py`、Excel 导入、五表内部导出和 `keywordPlanningV11Api.ts` 之上。

本次只修改两个既有文件 `backend/app/modules/keyword_planning/router.py` 和 `frontend/src/api/keywordPlanningV11Api.ts`，其它文件全部新增。**不覆盖** `main.py`、迁移文件、`runtime_rules.py`、旧系统、已有页面、stash 或未提交的其它文件。

## 新增的 API

- `GET /api/v1/keyword-planning/preflight`：按账户、商品、Walmart Item ID、事实快照、上传文件、规则版本只读校验真实来源，返回可否创建复核批次、评分缺口、Top40 复核数量；**永远不伪称正式广告文件已授权**。
- `GET /api/v1/keyword-planning/rulesets`：账户范围内和全局评分规则集查询，禁止预览身份。
- `GET /api/v1/keyword-planning/rulesets/{rule_set_id}/versions`：按账户范围查询历史版本，不返回规则配置原文或隐私详情。
- `POST /api/v1/keyword-planning/rulesets`：拥有来源账户权限的超管可创建**禁用**的账户专属规则集，默认被 `KEYWORD_V11_WRITE_ENABLED` 关闭。
- `POST /api/v1/keyword-planning/rulesets/{rule_set_id}/drafts`：创建非执行草稿，所有 D01–D08 初始为 `pending`。拒绝负数、布尔配额、缺乏来源证明的品牌、过大的配额和跨账户规则集。并发版本生成采用父规则行 `FOR UPDATE` 和唯一约束。
- `POST /api/v1/keyword-planning/rules/{version_id}/retire`：仅超管显式操作本人账户规则；冻结旧配置的情况下，允许 `published → retired`（需此前已经验收的 0055 修复）。
- `POST /api/v1/keyword-planning/rules/{version_id}/publish`：业务审核**默认阻断**，返回 `INDEPENDENT_D01_D08_APPROVAL_REQUIRED`；不接受浏览器自填审批编号作为批准证据。待设计并验收双人审批/不可变审批证据链后才能开放。

## 前端组件

`frontend/src/features/keyword-planning/components/KeywordV11LiveConsole.tsx`

为 Ant Design v5 React 组件，集中展示商品/账户/快照标识、原件上传、前置核验、分析批次、逐词结果、内部 Excel 下载、规则集与草稿限额。所有页面均调用 SZZSBJ `backendRequest` / `backendDownload`，不用浏览器 Mock 分数，也不提供官方上传按钮。

**集成差异说明：**用户 Mac 上现有的三个页面有未提交修改，当前工作环境没有这些精确内容。本交付**不自动改写**它们。可在准确核对页面后挂载 `<KeywordV11LiveConsole />`；需要保留现有导航和设计。没有挂载前，不得宣称前端完整联调。

## PostgreSQL 实测（独立临时容器）

额外新增 `test_analysis_pg_isolated_v11.py`，必须显式设置 `RUN_KW_ANALYSIS_PG_SANDBOX=1`。它验证临时 PostgreSQL 上真实 DDL、已确认商品事实、冻结规则、原始 Excel 行、一次入库、重复请求幂等，以及重用相同请求键但修改输入时拦截。使用 Docker 绑定随机 **127.0.0.1** 端口，拒绝远程 Docker Context、5432 和 15432、无宿主机挂载，并自动销毁命名临时容器。注意：测试创建的是专用临时库，不是正式执行 Alembic 历史迁移。

## 源码验收

作者隔离环境中已有 **64 passed, 1 skipped**（基础规则/Excel/本次治理与预检子集），新增的治理与预检单测 **21 passed**。受运行环境所限，真实数据库写入测试、完整 HTTP 鉴权、AntD 页面构建均**未在作者环境运行**，不得把已安装或静态编译等同于验收通过。

已知 Mac 上的上一轮完整回归：`110 passed, 1 skipped`。安装本补丁后请重新执行完整回归。

## Mac 安装（只执行一次）

1. 将同名 `.patch` 保存至 `~/Downloads/`。
2. 运行：

```bash
REPO="/Users/sakura/Desktop/YC-System/SZZSBJ-worktrees/frontend/SZZSBJ-frontend-acceptance"
PATCH="$HOME/Downloads/SZZSBJ_V11_governance_live_20261024.patch"
if [ ! -f "$PATCH" ]; then
  echo "STOP: 补丁尚未下载至 Downloads"
elif git -C "$REPO" apply --check "$PATCH"; then
  git -C "$REPO" apply "$PATCH" && echo "PASS: 补丁安装成功"
else
  echo "STOP: Git 补丁冲突，未修改"
fi
```

3. 验收（当前工作树有 Python 3.13 和后端虚拟环境）：

```bash
cd "/Users/sakura/Desktop/YC-System/SZZSBJ-worktrees/frontend/SZZSBJ-frontend-acceptance/backend"
.venv/bin/python -m pytest -q tests/modules/keyword_planning tests/modules/decodo
.venv/bin/python -m compileall -q app/modules/keyword_planning
.venv/bin/python -m ruff check app/modules/keyword_planning/governance_routes.py app/modules/keyword_planning/rule_governance.py app/modules/keyword_planning/preflight_routes.py app/modules/keyword_planning/analysis_preflight.py
cd ../frontend && npm run build && npm run lint
cd .. && git diff --check && git diff --cached --check
```

4. 仅在确认 Docker Desktop 的本地 `desktop-linux` Context 后，才可额外执行临时数据库测试：

```bash
cd "/Users/sakura/Desktop/YC-System/SZZSBJ-worktrees/frontend/SZZSBJ-frontend-acceptance/backend"
RUN_KW_ANALYSIS_PG_SANDBOX=1 .venv/bin/python -m pytest -q -s -rs tests/modules/keyword_planning/test_analysis_pg_isolated_v11.py
```

## 剩余审批/外部条件（不可伪称已完成）

- D01–D08 的正式业务签署、25 类关键词独立语义判定标准与黄金样例、六维评分中的缺失数据策略；此版本仍把无依据的分类和数据分数设为待审核。
- Walmart Item ID、Amazon ASIN、实际页面抓取的外部适配器及真实凭证授权。**不会**利用 Amazon PPC 冒充 Walmart 建议价。
- Walmart 现行官方 Bulk 模板及字段校验、具体店铺授权和二次确认；当前仅内部五 Sheet，绝不宣称是官方上传版。
- 最新三页面现存本地源码整合、完整 GitHub/本机前后端联调、生产授权与部署。

不得执行生产迁移、广告创建、正式发布、提交代码或 push。
