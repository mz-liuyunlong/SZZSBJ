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

## 读时计算的口径

- 类别：整笔剔除 → X01；人工 > 规则 > 待分类。
- 配对：T02 类；15 天内、方向相反、不同账户；同币种差不超过 1 元，或跨币种按备注 USD 金额；再试一出多入（最多 3 笔）；同一平台多笔 USD 换一笔 CNH 按汇率 6.3~7.6 配，标「汇率区间配对待核」。
- 折人民币：CNY 原值；USD 用 `ref_product_pricing_rule_versions.usd_cny_rate` 当月生效的统一值（表按店存多行，取当月内最新生效的一行）；当月没有才为空；CNH 为空。不兜底。
- 剔除清单：按日期顺序在命中流水上按人民币扣；没有人民币金额的流水不扣；扣不完出异常。
- 异常类型：`余额不连续`、`内部转账未配对`、`剔除未命中`（页面显示「要剔除的款没找到」）；`对方账户不在日记账` 只是提示，不算异常。
