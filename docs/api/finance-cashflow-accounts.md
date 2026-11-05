# 资金流水 · 账户管理和手工录入

都在 `/api/finance/cashflow` 下面，和日记账一样只有超级管理员能用，不新增权限点，也不改表结构（不加迁移）。

## 账户管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/accounts/admin` | 账户列表。识别值只说填了哪几项（`identity_fields`），不返回内容；附 `line_count` |
| POST | `/accounts` | 新增。`account_key` 由后端生成：`平台前缀_币种_尾号`，重名加 `_2` |
| PATCH | `/accounts/{account_key}` | 修改 / 停用 / 启用。`identity` 不传 = 不改；传了整组替换 |

规则：

- 平台（`provider`）：`boc`、`shenzhen_rural_bank`、`cmb`、`payoneer`、`worldfirst`、`pingpong`、`manual`（手工录入，不导入文件）。
- 币种只能是 CNY、USD、CNH；手工账户只能是 CNY，新增和修改都拦（422）。
- 识别值按平台：中行 `inquiry_account`（币种自动带上）；银座 / 招行 `account_no`（完整账号）；派安盈 `feature`（seller / collector）；PingPong `user_no` + `main`，或 `user_no` + `account_id`；万里汇、手工不用。
- 同一份流水不能认成两个启用中的账户：撞了返回 409。
- 已有流水的账户不能改平台和币种（409），没有删除接口，只能停用。停用后导入不再认它，已有流水照常显示。
- 尾号不填就从账号取后 4 位。

错误码：`CASHFLOW_ACCOUNT_REJECTED`（422 填写不合格 / 409 冲突或已有流水）、`CASHFLOW_ACCOUNT_NOT_FOUND`（404）。

注意：账户管理上线后，不要再用上线导入脚本（`deploy_load`）重跑账户部分，否则会把页面上改过的名称等覆盖回文件里的值。

## 手工录入

`POST /manual-lines`，请求：`account_key`、`business_date`、`direction`（in / out）、`amount`（正数，最多 2 位小数）、`description`（必填）、`counterparty_name`、`memo`、`category_code`（可空，空就按规则分类）、`idempotency_key`（重复提交只录一次）。

- 币种跟账户走（rocky 2026-11-05）：页面先选人民币或美元（默认人民币），再选这个币种的账户；人民币默认选名字叫「现金」的。手工账户（现金）只记人民币，其他币种返回 422。现金账户上线时用 `backend/scripts/finance_cash_ensure_cash_account.py --apply` 补一次，不含账号，可重复执行。
- 任何启用中的账户都能录：现金这种手工账户，或者银行 / 平台流水里没有的那笔（比如另外扣的手续费，类别选 F01）。
- 每录一笔，后台记成一次导入：一个批次 + 一个名为「手工录入」的虚拟文件（`provider = manual`，不存原件），流水进 `std_finance_cashflow_lines`，`source_ref = 手工`，事件表记一条 `manual_create`（谁、什么时候录的）。所以分类、初审终审、剔除、配对、导出都照常走。
- 录错了用剔除；还没审核的也可以在导入记录里作废这一批。
- 日期不能晚于今天；停用的账户不能录。
- 手工账户（`provider = manual`）没有银行余额：`GET /lines` 返回时按日期、同日录入顺序从第一笔往下累计，剔除的部分不算。期初就录一笔「期初余额」。银行账户上手工录的那笔不填余额，不影响银行余额连续性检查。

错误码：`CASHFLOW_MANUAL_LINE_REJECTED`（422）、`CASHFLOW_ACCOUNT_NOT_FOUND`（404）。

## 招商银行流水 PDF

导入支持招商银行「交易流水」PDF（一网通 / 掌上生活申请的流水证明，pypdf 抽文字，不做 OCR）。

- PDF 里账号只露前 4 后 4 位，按这 8 位 + 每行的币种认账户；没登记就整份拒收并给出尾号。
- 对手信息折行的接回上一笔；每页表头、页码、最后的「温馨提示」都跳过。
- 没有时间和流水号；同一天按 PDF 里的先后顺序，余额链照常检查。
- 招行以外的 PDF 仍然拒收。
