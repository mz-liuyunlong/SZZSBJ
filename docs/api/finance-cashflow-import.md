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
| `GET /fx-rates` | 领星美元月汇率，只读 | 新月份在前；领星没给汇率的月份 `my_rate` 为空 |
| `GET /fx-rates/sync` | 最近一次同步汇率的状态 | `never` / `queued` / `running` / `succeeded` / `failed`，失败带 `error_code` |
| `POST /fx-rates/sync` | 手动同步汇率 | 走任务中心的同步任务，已在跑就不重复开；没打开返回 409，队列不可用返回 503 |
| `GET /lines` | 日记账流水 | `account_key`、`from`、`to`、`page`、`page_size`（最大 2000）；日期倒序。`description` / `memo` 是银行原文，`manual_description` / `manual_memo` 是人工改过的（没改为 null）；`parts` 是拆分行 `[{amount, category_code}]`（没拆为 null） |
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
| `review1_undo` | | 撤销初审：ok1 / rej1 → todo。只有最近一次做初审（通过或不通过）的人能撤，别人撤返回 403 `CASHFLOW_NOT_FIRST_REVIEWER` |
| `review2_undo` | | 撤销终审：ok2 / rej2 → ok1 |
| `set_text` | `payload.description` / `payload.memo`，至少一个；空字符串或 null 表示恢复银行原文；每项最多 500 字 | 只改显示，银行原文不动，分类规则照原文算；不退回审核 |
| `split` | `payload.amounts`：2 到 20 个正数，合计等于流水金额绝对值 | 拆分后各行类别为空，再逐行选；再拆一次会整体替换 |
| `set_part_category` | `payload.index`（从 0 起）、`payload.category_code`（空值表示清掉） | 给拆分行选类别；X01 不能选 |
| `set_part_text` | `payload.index`（从 0 起）、`payload.description` / `payload.memo`，至少一个；空字符串或 null 表示清掉（沿用整笔的）；每项最多 500 字 | 改拆分行自己的摘要 / 备注；只改显示，不退回审核 |
| `unsplit` | | 取消拆分（确认过的手续费行一起取消） |
| `confirm_fee` | `payload.fee_amount`（正数）；`payload.fee_layer` 可选，默认 `fee`；`payload.transfer_category` 可选（没拆过时转账行的类别）；`payload.alert_type` 可选，只记录 | 确认记为手续费：没拆过的拆成转账行（金额 − 手续费）+ 手续费行（F01，带 `fee_layer`）；拆过的从最大的非手续费行里扣。同一 `fee_layer` 只能确认一次；手续费不能大于等于被扣的那行。按拆分处理，已审过的退回 todo |
| `pair` | `payload.pair_id`（1~40 字） | 人工配对：同一配对号的几笔算同一笔内部转账（每笔各发一次）。不改金额类别，不退回审核；已终审（ok2）的拒绝 |
| `unpair` | `reason` 必填 | 取消人工配对，原因记在操作记录里；已终审的要先撤销终审 |

已初审或已终审的流水，再改类别、单号、剔除或拆分，自动退回 todo，并多记一条 `auto_reset` 事件。阶段不允许返回 409；内容不合格返回 422；流水不存在或已作废返回 404。

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
| 422 / 409 | `CASHFLOW_INVALID_EVENT` | 内容不合格（缺原因、类别不存在、单号不是 12 位、剔除金额无效、不支持的 kind）返回 422；重复挂同一单号、摘不存在的单号、撤销没剔除的流水、已拆分的流水改整笔类别、没拆分就选拆分行类别 / 取消拆分返回 409 |
| 403 | `CASHFLOW_NOT_FIRST_REVIEWER` | 撤销初审的人不是当时做初审的人 |
| 409 | `CASHFLOW_IDEMPOTENCY_KEY_REUSED` | 幂等键已经用在别的操作上 |
| 503 | `CASHFLOW_STORAGE_NOT_CONFIGURED` | `MEDIA_STORAGE_ROOT` 没配 |
| 413 | `CASHFLOW_UPLOAD_TOO_LARGE` | 文件超过 `FINANCE_CASHFLOW_MAX_UPLOAD_BYTES` |
| 422 | `CASHFLOW_EMPTY_UPLOAD` | 上传内容为空 |

## 飞书审批单

| 方法与路径 | 用途 | 说明 |
|---|---|---|
| `GET /approvals` | 审批单列表 | 费用报销、付款申请、备用金申请、备用金核销；带已付流水和付款状态（已付 / 未付 / 部分已付 / 金额不符 / 金额缺失 / 审批中 / 已取消） |
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
- 人工配对优先：同一 `manual_pair` 的几笔直接配上（不看类别），一出一进且同币种有差额的出「转账到账差额」异常。
- 配对：T02 类；15 天内、方向相反、不同账户；同币种差不超过 1 元，或跨币种按备注 USD 金额；再试一出多入（最多 3 笔）；同一平台多笔 USD 换一笔 CNH 按汇率 6.3~7.6 配，标「汇率区间配对待核」。还没配上的再按带差额配：付出那笔的对方尾号 = 收到那笔账户的尾号（或反过来），5 天内，同币种，到账 ≤ 扣款，差额不超过 0.5% 且不超过 50 USD / 300 CNY（CNH 同 CNY）；配上后差额大于 0.01 的在付出那笔上出「转账到账差额」异常（`amount` = 差额）。比较用的金额：拆过手续费的按非手续费行合计，所以确认手续费后不再提示。
- 规则剔除：规则命中 X01（目前是「归集-万里汇主账号」，即万里汇子账号归集到主账号那笔）视为整笔剔除，`auto_exclude_reason`=「已在主账号记录」，标「已剔除」；人工选别的类别就撤销。主账号那笔「归集-万里汇子账号」按规则记 T03。
- 折人民币：CNY 原值；USD 用领星月汇率 `fact_lingxing_fx_rate.my_rate` 业务日所在月的值；当月没有才为空，不兜底；CNH 按 1:1（rocky 2026-11-05）。
- 剔除清单：按日期顺序在命中流水上按人民币扣；没有人民币金额的流水不扣；扣不完出异常。
- 异常的 `currency_code`：`amount` 的币种。`剔除未命中` 按人民币算，填 `CNY`；其他填这笔流水的币种。
- 异常类型：`余额不连续`、`内部转账未配对`、`转账到账差额`、`剔除未命中`（页面显示「要剔除的款没找到」）；`对方账户不在日记账` 只是提示，不算异常。

## 第三轮补充（rocky 11-05）

- 接口里的 `currency_code` 仍是 CNY、CNH、USD 等代码；页面显示时 CNY、CNH 写「人民币」，USD 写「美元」；导出的 Excel 币种列保留代码。

- `GET /lines` 多返回 `manual_pair`、`auto_exclude_reason`；`parts[]` 多返回 `fee_layer`（有值 = 手续费行）。
- 邮箱不再打码（派安盈子账号靠完整邮箱区分）。证件号仍去掉、16 位以上长数字仍只留尾 4 位。解析版本升到 `finance_cashflow/2`：同一个文件再导一次（或导入包含已有流水的文件），已有流水的对方 / 摘要 / 备注按新解析刷新，不新增流水；人工改的摘要 / 备注另存，不受影响。
- 迁移 `20261105_0080_finance_journal_round3`：加 `manual_finance_cash_line_state.manual_pair`；规则「Transfer from connected account」从 T02 改为 T03（seed 规则 90 只保留「资金归集至专用账户」→ T02，新增 89 → T03）；新增「代发收费」→ F01、「归集-万里汇主账号」→ X01、「归集-万里汇子账号」→ T03。已有人工配对时拒绝降级。

## 派安盈月结补充（rocky 11-05）

每周照旧导派安盈交易报告（老格式，只有美元）。月底派安盈才给的月结明细 CSV（表头以 `Transaction Date,Transaction Time,Time Zone,Transaction ID` 开头，带 `Transfer Amount` / `Transfer Amount Currency`）也走 `POST /imports`，但**不新增流水**：

- 识别：和交易报告同一套「卖家户 / 归集户」判断；只收 `Completed` 行；明细存 `std_finance_payoneer_statement_rows`（迁移 `20261105_0081_finance_payoneer_statement`）。返回的 `rows_new=0`，读到多少行写在 `warnings` 里。作废这一批，补上的数就跟着撤掉。
- 对账（读时算）：只看提现（`Payment to …`）。同账户、金额分毫不差、交易时间相差 2 分钟内；没有交易时间的按业务日前后一天。对上唯一一笔才补；同一交易号重复导入、内容一样只算一次。
- 折人民币：到账币种是 CNY 的，用派安盈写的人民币（汇率 = 人民币 ÷ 美元，四位小数）；到账是美元或没写的，照旧用当月统一汇率；提现还没对上月结单的**留空，不预估**。`GET /lines` 多返回 `fx_rate`、`fx_source`（`payoneer` / `lingxing` / `pending` / 空）。
- 配对：对上月结单的提现，按派安盈写的到账金额和币种去配（人民币提现按实际人民币配国内账户入账）。
- 新异常类型：`派安盈提现到账差额`（扣款比派安盈写的到账多，同币种；`amount` = 差额，交给「确认记为手续费」按钮，fee_layer = `payoneer`）、`缺派安盈实际汇率`（月份已结束还没导月结单，或月结单里没有这笔）、`月结单有、流水没有`、`月结单匹配到多笔`、`月结单前后不一致`。
