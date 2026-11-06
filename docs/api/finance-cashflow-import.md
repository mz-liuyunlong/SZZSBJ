# 财务日记账 API（流水导入与审核）

- 前缀：`/api/finance/cashflow`
- PRP：`PRPs/finance-journal-backend-v1.md`；导入规则：`docs/business-rules/finance-cashflow-import-rules.md`
- 响应：统一 `success/data/error/meta/request_id`。错误只返回安全文案，不带明细。
- 权限：全部接口只有超级管理员（`require_super_admin`）。未登录 401，其他账号 403。本期不新增权限点、数据范围或字段权限。
- 金额：`numeric(18,4)`，JSON 中是字符串；币种见同行 `currency_code`。

## 配置

| 变量 | 说明 |
|---|---|
| `MEDIA_STORAGE_ROOT` | 原件存放根目录，文件落在 `finance/cashflow/<sha 前两位>/<sha>.<扩展名>`。没配时上传返回 503，不写到别处。 |
| `FINANCE_CASHFLOW_MAX_UPLOAD_BYTES` | 单文件上限，默认 20 MB（20971520）。 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 同步审批单用的飞书应用，和后端其他飞书功能共用。 |
| `FINANCE_APPROVAL_CODES` | 四类审批定义编码，格式 `费用报销=…,付款申请=…,备用金申请=…,备用金核销=…`，真实值不进仓库。没配置或缺一类时同步失败，错误码 `SYNC_FEISHU_APPROVAL_CODES_NOT_CONFIGURED`。 |
| `FINANCE_APPROVAL_EXCLUDED_DEPARTMENT_IDS` | 逗号分隔的飞书部门 ID，这些部门的审批单不进报销闭环。 |

账户和带名字的分类规则不进仓库，上线时用 `backend/scripts/finance_cash_deploy_load.py` 导入。没导入账户时，上传被拒收并写明「没登记」。

## 接口

| 方法与路径 | 用途 | 说明 |
|---|---|---|
| `POST /imports` | 上传一个文件 | 请求体是文件字节；`X-File-Name`（URL 编码）；多文件用同一个 `X-Import-Id`（UUID）归入一批。文件内容不认识时仍返回 200，`file.status=rejected` 并带 `reject_reason`；同一文件已在未作废批次中时 `duplicate_of_file=true`，不新增。 |
| `GET /imports` | 批次列表 | `status`、`from`、`to`、`page`、`page_size`（最大 200） |
| `GET /imports/{import_id}` | 批次详情 | 每个文件的识别结果、行数、质量告警 |
| `POST /imports/{import_id}/void` | 整批作废 | body `{reason}`，必填。只出现在这批的流水标作废；也出现在别的未作废批次的，归属退回最近一个未作废批次。只属于这一批的流水里有已初审或已终审的，拒绝作废，什么都不改：409，错误码 `CASHFLOW_IMPORT_HAS_REVIEWED_LINES`，`details` 带 `count` 和 `line_ids`；要先退回这些流水的审核。 |
| `GET /accounts` | 账户 | 含流水条数、最近文件名、覆盖区间、来源（表头 / 首末笔）。不返回识别用的完整账号。 |
| `GET /categories` | 类别字典 | 26 个类别 |
| `GET /lines` | 日记账流水 | `account_key`、`from`、`to`、`page`、`page_size`（最大 2000）；日期倒序 |
| `GET /anomalies` | 异常 | 读时计算；有流水的带 `line_uid`，找不到流水的 `line_uid=null` |
| `POST /lines/{line_uid}/events` | 人工动作 | 见下 |

### 人工动作

body：`{kind, payload, reason, expected_version, idempotency_key}`。`expected_version` 必填，不带返回 422，不符返回 409；`idempotency_key` 已用过则不重复执行，返回 `replayed=true`。

| kind | payload / reason | 规则 |
|---|---|---|
| `review1_pass` | `payload.note` 可选 | 待初审（todo、rej1、rej2）→ ok1 |
| `review1_reject` | `reason` 必填 | 待初审 → rej1 |
| `review2_pass` | | ok1 → ok2 |
| `review2_reject` | `reason` 必填 | ok1 → rej2 |
| `set_category` | `payload.category_code`，空值表示退回规则 | X01 不能走这里 |
| `attach_ref` / `detach_ref` | `payload.ref`，12 位数字 | 手填审批单号 |
| `exclude` | `reason` 必填；`payload.amount` 可选（原币），不填即整笔 | 整笔剔除后生效类别为 X01 |
| `unexclude` | | 撤销剔除 |

已初审或已终审的流水，再改类别、单号或剔除，自动退回 todo，并多记一条 `auto_reset` 事件。阶段不允许返回 409；内容不合格返回 422；流水不存在或已作废返回 404。

### 错误码

错误统一放在 `error.code`，前端按 code 判断，`error.message` 只给人看。401 / 403 和请求参数校验（含不带 `expected_version`）沿用全局的 `UNAUTHORIZED`、`FORBIDDEN`、`VALIDATION_ERROR`。

| HTTP | code | 什么时候 |
|---|---|---|
| 404 | `CASHFLOW_IMPORT_NOT_FOUND` | 导入批次不存在（详情、作废） |
| 409 | `CASHFLOW_IMPORT_VOIDED` | 这一批已作废，不能再传文件或再作废 |
| 409 | `CASHFLOW_IMPORT_HAS_REVIEWED_LINES` | 作废被拦：这批有已审核的流水，`details` 带 `count`、`line_ids` |
| 422 | `CASHFLOW_VOID_REASON_REQUIRED` | 作废原因只有空格 |
| 404 | `CASHFLOW_LINE_NOT_FOUND` | 流水不存在或已作废 |
| 409 | `CASHFLOW_VERSION_CONFLICT` | `expected_version` 和当前版本不符，别人刚改过 |
| 409 | `CASHFLOW_STAGE_NOT_ALLOWED` | 当前审核阶段不允许这个动作（例如没初审就终审） |
| 422 / 409 | `CASHFLOW_INVALID_EVENT` | 内容不合格（缺原因、类别不存在、单号不是 12 位、剔除金额无效、不支持的 kind）返回 422；重复挂同一单号、摘不存在的单号、撤销没剔除的流水返回 409 |
| 409 | `CASHFLOW_IDEMPOTENCY_KEY_REUSED` | 幂等键已经用在别的操作上 |
| 503 | `CASHFLOW_STORAGE_NOT_CONFIGURED` | `MEDIA_STORAGE_ROOT` 没配 |
| 413 | `CASHFLOW_UPLOAD_TOO_LARGE` | 文件超过 `FINANCE_CASHFLOW_MAX_UPLOAD_BYTES` |
| 422 | `CASHFLOW_EMPTY_UPLOAD` | 上传内容为空 |

## 飞书审批单

| 方法与路径 | 用途 | 说明 |
|---|---|---|
| `GET /approvals` | 审批单列表 | 费用报销、付款申请、备用金申请、备用金核销；带已付流水和付款状态（已付 / 未付 / 部分已付 / 金额不符 / 金额缺失 / 待定 / 审批中 / 已取消）。一笔付款挂多张单时，按这笔的人民币和各单金额比例分，尾差给金额最大的那张；算不出来的单状态为待定，`paid[].amount_cny` 为空 |
| `GET /approvals/sync` | 最近一次同步的状态 | `status`：never / queued / running / succeeded / failed；失败时 `error_code` 带接口名、HTTP 状态和飞书错误码 |
| `POST /approvals/sync` | 手动同步 | 202；走任务中心的同步任务（接口 `financeApprovalInstances`），已有一次在跑就返回它，不重复开。没登记任务回 409 `CASHFLOW_APPROVAL_SYNC_NOT_CONFIGURED`；队列不可用回 503 `CASHFLOW_APPROVAL_SYNC_UNAVAILABLE` |

- 上线要跑一次 `FINANCE_APPROVAL_BOOTSTRAP_AUTHORIZED=true python backend/scripts/bootstrap_finance_approval_governance.py` 登记任务；定时默认关闭，以后在任务中心打开即可，手动和定时走同一个处理逻辑。
- 只取飞书只读接口；每次查最近 90 天，切成每段不超过 30 天。已结束超过 14 天且取过的单不再取详情。
- 申请人和审批记录里的处理人，读取时按系统员工表 `app_users.feishu_user_id` 换成姓名（优先 `feishu_name`，其次 `display_name`），匹配不到的显示编号；不调飞书通讯录接口。
- 只存账号尾号，不存完整账号；附件和截图只存元数据（来源、名称、是否图片），不存下载链接。

## 自动挂单

每次同步结束、以及流水导入后各跑一次；可重复执行。

1. 流水摘要或备注里写了审批单号（`20` 开头的 12 位数字，且是系统里有的、没取消的单）：直接挂。
2. 金额相等（差不超过 0.011）、都是人民币、流水日期在审批通过前 3 天到通过后 45 天内、收款人对得上，并且这笔流水只对得上这一张已同意的单、这张单也只对得上这一笔：自动挂，事件 `auto_attach_ref`（actor=system），流水带「自动匹配」标记。单子没写收款人时，唯一也算。
3. 其余放在流水的 `approval_candidates`，由财务选。审批中的单只进候选，不自动挂。
4. 已初审或终审的流水不动；财务手动摘掉过的「流水 + 单号」组合不再自动挂回去。

## 读时计算的口径

- 类别：整笔剔除 → X01；人工 > 规则 > 待分类。
- 配对：T02 类；15 天内、方向相反、不同账户；同币种差不超过 1 元，或跨币种按备注 USD 金额；再试一出多入（最多 3 笔）；同一平台多笔 USD 换一笔 CNH 按汇率 6.3~7.6 配，标「汇率区间配对待核」。
- 折人民币：CNY 原值；USD 用 `ref_product_pricing_rule_versions.usd_cny_rate` 当月生效的统一值（表按店存多行，取当月内最新生效的一行）；当月没有才为空；CNH 为空。不兜底。
- 剔除清单：按日期顺序在命中流水上按人民币扣；没有人民币金额的流水不扣；扣不完出异常。
- 异常的 `currency_code`：`amount` 的币种。`剔除未命中` 按人民币算，填 `CNY`；其他填这笔流水的币种。
- 异常类型：`余额不连续`、`内部转账未配对`、`剔除未命中`（页面显示「要剔除的款没找到」）；`对方账户不在日记账` 只是提示，不算异常。
