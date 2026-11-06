# PRP：财务 · 日记账后端 V1（PR-A）

- 状态：已批准（rocky 2026-11-04），分支 `fin/journal-backend`，PR #312。
- 数据源决策：`docs/data-sources/decisions/finance-cashflow-statement-import-decision.md`，结论：文件导入，`NEW_SYSTEM_OWNED`。
- 底稿：`PRPs/finance-cashflow-statement-import-v1.md`（#289）+ 从 PR-E 草稿（`_deploy_tmp/tickets/20261102_fin-pre-docs/`）挑出的部分 + rocky 2026-11-04 的决定。
- 前后端分开提：后端（模块、迁移、脚本、测试、配置、依赖、文档）一个 PR；前端接接口的改动等 #305 这轮修改合进工作区后，作为 #305 的后续提交。

## 1. 目标

财务在日记账上导入流水，系统去重入库并自动分类、配对内部转账；管理员在页面上改类别、手填审批单号、剔除、初审、终审；日记账显示异常。

## 2. 范围

做：
1. 流水导入、去重、作废（照 #289 的规则，变更见第 3 节）。
2. 分类：26 个类别 + 现行规则，作固定种子；行上可改类别。优先级：人工 > 规则 > 待分类。
3. 内部转账配对：照 Demo 现行算法，T02 类参与。
4. 挂审批单：只手填单号。
5. 剔除：行上剔除；剔除清单只用脚本写入。
6. 初审、终审。
7. 异常：余额不连续、内部转账未配对、要剔除的款没找到。「审批单无付款流水」只留类型，没有数据。
8. 折人民币。

不做：飞书表和同步、审批单自动挂单（这两项已由 finance-journal-approvals-v1 覆盖）、拆分（拆分已由 finance-journal-approvals-v1 覆盖）、结账锁月、规则版本化和规则维护页、导出、账户总览、备货资金、Demo 历史迁移、PDF、新权限点、角色、数据范围、字段权限、工资打码。

## 3. 相对 #289 的变更（rocky 已定）

| 项目 | #289 原写法 | 本 PRP |
|---|---|---|
| 入口 | 数据中心 → 数据导入 | 日记账「流水导入」抽屉 |
| 原件 | 建议存数据库 bytea | 存 `MEDIA_STORAGE_ROOT/finance/cashflow/` 下，表里只记路径和 sha256 |
| 大小上限 | 10 MB | 20 MB，写进配置 |
| .xls | 待定 | 加 xlrd |
| 文件类型 | xls、xlsx、csv | 不变；PDF 拒收 |
| 权限 | 多个新权限点和数据范围 | 全部接口只有超级管理员（`require_super_admin`） |
| 表 | 5 张 | 加第 6 张 `std_finance_cashflow_line_occurrences`，否则作废后退不回去 |
| 重复文件 | 同 sha256 直接返回已有记录 | 只在未作废批次内算重复，否则作废后不能重传 |

代码不写死路径；`MEDIA_STORAGE_ROOT` 没配时上传返回错误，不落到别处。

账户：银行账号不进仓库（rocky 2026-11-04 定），尾号和哈希也不放。迁移不写账户种子，账户上线时由部署AI导入；测试用编造的假账号。没导入时，上传会被拒收并提示账户没登记。平台出现没登记的店铺账户，整个文件拒收并写明原因。

预研定下要带走的解析口径：重复表头行、汇总页脚行跳过并记质量告警；表头声明了区间的就读出来；个别平台的余额链只告警。

## 4. 数据表

新建模块 `backend/app/modules/finance_cashflow/`，一个 Alembic 迁移，接最新单一 head。

导入（6 张）：`dim_finance_cash_accounts`、`landing_finance_cashflow_imports`、`raw_finance_cashflow_files`、`std_finance_cashflow_lines`、`std_finance_cashflow_line_occurrences`、`dq_run_finance_cashflow_import`。

日记账（5 张）：
- `dim_finance_cash_categories`：类别编码、大类、名称、是否内部类、是否剔除类。
- `cfg_finance_cash_classify_rules`：规则类型（对方户名 / 摘要备注）、匹配式、目标类别、顺序。只有种子，无维护接口。
- `evt_finance_cash_line_reviews`：人工动作事件，只追加。字段：line_uid、kind、payload、reason、操作人、时间、request_id、幂等键。
- `manual_finance_cash_line_state`：每行的人工当前状态：人工类别、手填单号、剔除金额和原因、审核阶段、原因、版本号。规则类别、配对号、剔除清单命中、异常都在读取时算，不落表，所以规则或流水一变，结果自然跟着变。
- `manual_finance_cash_exclusions`：剔除清单：审批单号，或「日期 + 账户 + 摘要关键词」；人民币金额、原因、登记人、登记日。只由脚本 `backend/scripts/finance_cash_deploy_load.py` 写入。

金额 `numeric(18,4)`，全程 Decimal，不经 float；业务日按 Asia/Shanghai（同 #289）。

时区：业务时区 Asia/Shanghai。业务日、月份和页面上显示的时间都按这个时区；入库的时间戳带时区存。

## 5. 接口（前缀 `/api/finance/cashflow`，统一 envelope）

- `POST /imports`（文件放请求体，`X-File-Name`、`X-Import-Id`）；`GET /imports`；`GET /imports/{id}`；`POST /imports/{id}/void`（必填原因）。
- `GET /accounts`：账户，含各账户最近一次导入和覆盖区间。
- `GET /categories`。
- `GET /lines?account_key&from&to&page&page_size`：日记账字段 + 类别和来源 + 单号 + 配对号 + 剔除金额 + 审核阶段和原因 + 折人民币。
- `GET /anomalies`：读时计算；有流水的带 line_uid，找不到流水的单列。
- `POST /lines/{line_uid}/events`：`{kind, payload, reason, expected_version, idempotency_key}`。

错误：401、403；404；409（状态不允许、版本过期、作废被拦）；413（超 20 MB）；422（参数，含不带 `expected_version`）。除 401、403 和参数校验外，都带固定错误码 `CASHFLOW_*`，对照表见 `docs/api/finance-cashflow-import.md`。文件类型不认识时不算错误：返回 200，`status=rejected`，带 `reject_reason`。

## 6. 规则

**审核阶段**：todo（待初审）、rej1（初审不通过）、ok1（待终审）、rej2（终审驳回）、ok2（已终审）。
- 初审：todo、rej1、rej2 可做；通过到 ok1；不通过到 rej1，仍算待初审，必填原因。
- 终审：只有 ok1 可做；通过到 ok2，不通过到 rej2，必填原因。其他状态返回 409。
- 同一个超级管理员可以做初审和终审。
- 已初审或已终审的流水，再改类别、挂或撤单号、剔除或撤销，自动退回 todo，记一条 `auto_reset` 事件。
- 差额说明要有审批单金额才能比，飞书同步前不触发。

**分类**：新导入或规则重跑只影响没被人工改过的流水。类别选 X01 不能走改类别，必须走剔除。

**配对**：相差不超过 15 天、方向相反、不同账户；同币种差不超过 1 元，或跨币种按备注里的 USD 金额相等；再试一出多入（最多 3 笔）；同一平台多笔 USD 换一笔 CNH 按汇率 6.3~7.6 标「待核」。读取时算。配对变化不触发退回。USD 换 CNH 这一轮 Demo 因账户改名已不生效，这里按本 PRP 恢复，配出来的都标待核。

**作废导入**（rocky 2026-11-04 定）：只属于这一批的流水里有已初审或已终审的，拒绝作废，什么都不改，返回 409 和错误码 `CASHFLOW_IMPORT_HAS_REVIEWED_LINES`，带数量和 line_id 列表；要先退回审核。同时出现在别的未作废批次的流水，作废时只退归属，不拦。

**剔除**：
- 行上剔除：整笔或部分金额（原币），必填原因，二次确认；可撤销。整笔剔除后生效类别为 X01。已剔除卡 = 有剔除金额的流水。
- 剔除清单：按日期顺序在命中流水上按人民币扣，扣完为止，只算不写行状态之外的东西。扣不完或没命中，出异常「要剔除的款没找到」。按审批单号登记的靠手填单号命中。
- 清单只能扣有人民币金额的流水；没有汇率的外币流水不扣。
- 剔除不改银行余额。

**折人民币**：CNY 等于原值；USD 用 `ref_product_pricing_rule_versions.usd_cny_rate` 业务日当月生效值，全公司统一一个值（表按店存多行，取当月内最新生效的那一行）；当月没有才为空，页面显示「—」；CNH 也空。不兜底。

**异常**：
- 余额不连续：账户有余额列时，本笔余额 − 本笔金额，在该账户找不到相同余额（差 0.01 内），就算漏行。做不了余额链的平台子账户不算。
- 内部转账未配对：生效类别是内部类且没配上。
- 要剔除的款没找到：见上。

## 7. 前端

- 新增接口层，日记账改读接口；账户总览、备货资金不动。
- **5174 上没有后端**：开发环境继续读 Demo 数据，正式构建走接口。切换只看一个环境变量 `VITE_FINANCE_CASH_SOURCE`：`demo` 读 Demo，`api` 读接口；不设时开发环境默认 `demo`，正式构建默认 `api`。这样 rocky 在 5174 看到的不变。
- 只解锁上传、剔除、类别下拉、关联审批单，改「本地预览」类提示。样式布局不动。
- 剔除要原因和二次确认，用现有驳回弹窗同样的写法，只加这一个弹窗；清单没有弹窗。
- 抽屉里的交表说明写死在前端，账户覆盖读接口。导入历史和作废这次没有界面，接口先留着。

## 8. 测试

合成样本，不含真实户名、账号、金额。覆盖：5 种格式识别和解析、拒收、去重、重叠导出、同文件重复行、作废回退和重传、20 MB、原件落盘、审核状态流转、自动退回、幂等和版本冲突、分类优先级、配对、两种剔除、三类异常、折人民币有无汇率、权限（非超管 403）、迁移 up / down。

门禁：`ruff check`、`ruff format --check`、`pytest backend/tests/modules/finance_cashflow`、`alembic check`、`tsc`、`eslint`。数据库测试只用 `APP_ENV=test` + `TEST_DATABASE_URL`。

## 9. 红线

不连生产库和 8010 / PMC 的库；不调外部接口；不部署；不提交、不推送；真实流水不进测试、日志和文档。

## 10. 回滚

代码 revert；迁移 down 删新表（有数据时拒绝，防误删）；原件目录不自动删。

## 11. 文件数

预计超过 20 个文件。理由：rocky 已定一个 PR 覆盖流水导入和日记账，解析器、迁移、接口和测试不能安全拆开；回滚边界是整个模块和这一个迁移。前端改动单独提。

## 12. 上线

1. 分类规则里带平台、服务商、机构、银行、供应商、对方单位名字的部分不进仓库（rocky 2026-11-04 定），所有按对方户名的规则也一样。迁移只放 26 个类别和不带名字的关键词规则，其余上线时由部署AI导入，顺序号不变。账户、带名字的规则、剔除清单都用同一个脚本 `backend/scripts/finance_cash_deploy_load.py`，读一个不进仓库的 JSON 文件写入。没导入时，这些流水显示待分类。
2. 真实效果上线后才能测，第一次上线要带上「上线后要验证的点」。
