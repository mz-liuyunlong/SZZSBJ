# PRP：财务 · 日记账第三轮 V1

- 状态：已批准（rocky 2026-11-05）。分支 `fin/journal-round3`，PR #320。
- 单功能规则豁免：rocky 2026-11-05 书面同意保持一个 PR。这个 PR 里有多块功能，按下面的回滚边界分别处理。
- 数据源决策：`docs/data-sources/decisions/finance-cashflow-statement-import-decision.md`「招商银行个人流水 PDF、派安盈月结单」；派安盈提现汇率见 `docs/data-sources/decisions/lingxing-fx-rate-source-decision.md`「例外：派安盈提现」。
- 接口说明：`docs/api/finance-cashflow-import.md`、`docs/api/finance-cashflow-accounts.md`。
- 前置：`PRPs/finance-journal-backend-v1.md`、`PRPs/finance-journal-approvals-v1.md`、`PRPs/lingxing-fx-rate-v1.md`。迁移接在 0079 后面：0080、0081。

## 1. 目标

财务用日记账做完一个月的账：配对更好找，手续费差额能确认，页面上能管账户、能补录流水，招行个人账户和派安盈月结单也能导入。

## 2. 范围和回滚边界

| 功能 | 做什么 | 回滚边界 |
|---|---|---|
| 配对搜索 | 配对弹窗可按账户、金额、摘要、备注、对方、日期搜索；输入关键词后不限日期 | 只改前端，回退代码即可 |
| 拆分写备注 | 拆分行显示在父行下面，备注列写上拆分说明（拆成几行、各多少、什么类别） | 只改前端显示，拆分数据还在 `manual_finance_cash_line_state.parts`；回退代码不丢数据 |
| 拆分行可编辑 | 拆分行显示账户和对方，可改摘要、备注 | 同上 |
| 取消配对必填原因 | 取消配对不写原因就拒绝，原因记在事件表 | 回退代码后不再强制，已有事件保留 |
| 人工配对 | `manual_finance_cash_line_state.manual_pair`，同组几笔直接配上 | 迁移 0080 回退时，已有人工配对就拒绝，要先取消配对 |
| 万里汇自动剔除 | 规则命中「归集-万里汇主账号」记 X01，视为整笔剔除；财务选别的类别就撤销 | 规则是种子数据，改规则即可；读时计算，不改流水 |
| 带差额自动配对 | 5 天内、差额不超过 0.5%，且不超过币种上限（USD 50、CNY 300、CNH 300）；付出方的对方尾号要等于到账账户尾号；差额进「转账到账差额」异常，可确认记为手续费 | 读时计算，回退代码即恢复；已确认的手续费用「取消拆分」撤销 |
| 邮箱不打码 | rocky 2026-11-05 定：派安盈子账号靠完整邮箱区分。证件号仍去掉，16 位以上长数字仍只留尾 4 位 | 解析版本 `finance_cashflow/2`，重新导入按新解析刷新；回退后要重新导入才会再打码 |
| 账户管理 | 页面新增、修改、停用账户；识别值只写不读；没有删除 | 不加迁移。回退代码后账户数据保留。上线后不要再用 `deploy_load` 重跑账户部分 |
| 手工录入流水 | 现金账户或流水里没有的那笔，记成一次手工导入；先选人民币或美元，人民币默认「现金」；现金只记人民币 | 不加迁移。录错用剔除，没审核的可作废这一批 |
| 招行个人流水 PDF | 只接招商银行「交易流水」，pypdf 抽文字，不做 OCR | 导入作废回退；回退代码后这种文件重新被拒收，已入库流水保留 |
| 派安盈月结补充 | 月结 CSV 只补提现的实际到账，不新增流水；差额和缺月结单进异常 | 作废这一批，补上的数就撤掉。迁移 0081 回退时，有明细就拒绝 |
| 派安盈提现按实际汇率 | 引用汇率决策文件的「例外：派安盈提现」；到账是人民币的按派安盈的数，没对上月结单的留空，不预估 | 读时计算，回退代码后恢复领星汇率 |

页面上币种一律写中文（rocky 2026-11-05）：CNY、CNH、RMB 写「人民币」，USD 写「美元」。只改显示，存的币种代码不变；导出的 Excel 币种列保留代码（CNY、CNH、USD），方便对账。CNH 按 1:1 折人民币（rocky 2026-11-05）；备注里的长数字保持打码。

不做：结账锁月、规则维护页、导出、账户总览和备货资金接正式数据、定时开启。

## 3. 存储

- 迁移 `20261105_0080_finance_journal_round3`：加 `manual_finance_cash_line_state.manual_pair`，调整分类规则种子。
- 迁移 `20261105_0081_finance_payoneer_statement`：新建 `std_finance_payoneer_statement_rows`。
- 账户管理和手工录入不加迁移。

## 4. 接口（前缀 `/api/finance/cashflow`）

`GET /accounts/admin`、`POST /accounts`、`PATCH /accounts/{account_key}`、`POST /manual-lines`；`POST /imports` 多接招行 PDF 和派安盈月结 CSV；`GET /lines` 多返回 `manual_pair`、`auto_exclude_reason`、`fx_rate`、`fx_source`。

## 5. 权限

全部 `require_super_admin`，不新增权限点。

## 6. 上线

按 #316、#317、#319、#318、#320 的顺序合并后跑迁移，head 应是 `20261105_0081_finance_payoneer_statement`。不要重跑 `deploy_load` 的账户部分。

## 7. 验收

合成数据测试覆盖上面每块功能：`tests/modules/finance_cashflow`、`tests/db/test_alembic_scaffold.py`，前端 `src/pages/finance`。真实账号、户名、金额不进测试和文档。
