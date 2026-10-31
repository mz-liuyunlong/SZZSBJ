# 财务 · 现金流账户报表导入 数据源决策

- 调查日期：2026-10-31
- 调查人：Rocky 侧代码 AI（财务板块）
- 目标 method/path：`POST /api/finance/cashflow/imports`、`GET /api/finance/cashflow/imports`、`POST /api/finance/cashflow/imports/{import_id}/void`、`GET /api/finance/cashflow/lines`
- 业务用途：财务每周二 15:00 前把公司全部现金流账户（中行 ×3、深通村镇银座、派安盈 ×2、万里汇、PingPong）的原始导出文件一次性上传；系统按**文件内容**识别账户、解析成标准化流水、去重入库、留原件。它是「结算对账」（到账侧）与后续「现金状况」的唯一到账 / 流水来源。
- 接口总体状态：**READY_FOR_PRP**
- 是否包含 NEED_OWNER_DECISION：否
- 负责人批准状态：待确认（本文件由 Rocky 2026-10-31 18:06 确认后提交；技术负责人审阅后在本节记录批准）
- 关联证据：
  - 业务原型（Rocky 侧工作区，不在仓库）：财务 Demo v5.5.0 ⑥ 现金状况 / ⑨ 数据导入「现金流账户报表」（2026-10-29 起，`features/finance/drafts/bank_parsers.py`、`build_cash.py`、`fin_ingest_uploads.py`），10 月 7 份真实导出 → 160 行流水，财务已在用。
  - 业务决策：Rocky 2026-10-29 16:42（日记账改为财务每周导入原始导出）、2026-10-31 17:12（**派安盈 / PingPong / 万里汇一律文件导入，不接 PingPong API**）。
  - 仓库先例：`backend/app/modules/operation_plans/`（#227 文件导入：请求体 + `X-File-Name`、import_batches / import_rows、失败行导出）；`docs/runbooks/pmc-domestic-inbound-csv.md`（CSV 落地与 manifest 规范）。
  - 规则：`docs/delivery/backend-data-source-decision-gate.md`、`docs/data-sources/database-layering-standard.md`、`docs/data-sources/field-standardization-standard.md`、`docs/FINANCIAL_TIME_AND_CURRENCY_BOUNDARY_RULES.md`、`docs/SENSITIVE_DATA_AND_PERMISSION_RULES.md`、`docs/business-rules/permission-model.md`。

## 1. 旧系统与来源调查（强制前置）

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 旧系统没有现金流 / 日记账页面；此前公司用 Excel 日记账（9 本）+ 人工。Demo ⑥ / ⑨ 是唯一业务原型。不适用迁移。 |
| 旧 API | 无。不适用。 |
| 旧接口文件位置 | 无。不适用。 |
| 读取表 | 旧 MySQL 无相关表；新系统现无任何现金流 / 结算 / 回款表（2026-10-31 生产只读探测 NEWSYS-STATE-20261031：public schema 176 张表，无 `fin_` / `settlement` / `cashflow` 对象）。 |
| 表写入方 | 本决策新建：唯一写入方 = 财务用户通过本接口上传；系统解析写入；无其他进程写。 |
| cron / 脚本 / 外部 API | 无 cron。Demo 侧脚本（`fin_ingest_uploads.py` 同步到 Mac 再重建）仅为原型过渡，正式系统不依赖。不调用任何银行 / 平台 API。 |
| 人工写库入口 | 上传即人工入口；流水行本身不允许人工编辑（分类 / 备注 / 复核属于后续「现金状况」PRP，另行决策）。作废只允许整批作废（软删除 + 审计）。 |
| 外部平台重新获取可能性 | 可以：中行企业网银「交易明细」xls、深通村镇银座「交易明细查询列表」xlsx、派安盈 Transactions CSV、万里汇导出 xlsx、PingPong 账单明细 xlsx 都能按日期段重新导出；重复导出靠行指纹去重。 |
| 少量配置数据可行性 | 可行：账户主数据 10 条（见 §3 表 A），由 migration 种子写入，变更走审批后的维护接口（本期不做维护页，改动走 migration / 负责人授权脚本）。 |
| 短期策略 | 文件导入（本决策）。 |
| 长期策略 | 仍为文件导入：银行无开放 API；PingPong / 派安盈 / 万里汇 API 接入被 Rocky 明确否决（2026-10-31）。若未来改接 API，另立决策。 |

## 2. 数据集分类

| 数据集 | 层 | 对象（建议名） | 分类 | 权威来源 | 必要约束 |
|---|---|---|---|---|---|
| A 现金账户主数据 | L7 DIM | `dim_finance_cash_accounts` | `NEW_SYSTEM_OWNED` | 财务 / Rocky 确认的账户清单（§3 表 A） | migration 种子；字段：account_key、display_name、entity（法人主体）、currency_code、kind（对公 / 平台 / 对公外币）、provider（boc / shenzhen_rural_bank / payoneer / worldfirst / pingpong）、account_no_last4、identity_hint（识别用：账号 / 用户编号 / 子账户 Id，**只存识别所需、不存完整卡号以外的敏感项**）、is_active、effective_from。 |
| B 导入批次 | L1 Landing | `landing_finance_cashflow_imports` | `NEW_SYSTEM_OWNED` | 本接口 | 一次上传 = 一批；记录 uploader（principal）、上传时间、文件数、识别结果、状态（received / parsed / voided / failed）、request_id；`void` 只改状态并写审计，不删行。 |
| C 原始文件 | L2 RAW | `raw_finance_cashflow_files` | `ARCHIVE_ONLY` | 银行 / 平台导出原件 | 原件字节（bytea，默认方案；负责人可改为受控目录 + 路径）、sha256、size、原文件名、识别出的 account_key、表头声明区间（有则记）、解析器版本；append-only；同 sha256 重复上传返回已有记录不重存。不进入任何业务 API 响应。 |
| D 标准化流水 | L3 Standardized | `std_finance_cashflow_lines` | `NEW_SYSTEM_OWNED` | 由 C 经确定性解析得到 | 字段见 §4；`line_uid` 唯一（account_key + 指纹）；重复导入同一行 = 以最新文件为准（更新 raw_file_id 引用，不新增）；金额 Numeric(18,2) + currency_code；业务日期 + 来源时间 + 来源时区；对方户名 / 卡号尾号为敏感字段。 |
| E PingPong 非本主体店铺行 | L2 only | （留在 C 的原件里） | `ARCHIVE_ONLY` | 同 C | 只保留 PingPong 导出中用户编号 = 本公司专用户（Rocky 2026-10-29 19:53：其他主体店铺到账即归集，不入系统）的行进入 D；其余行不解析入 D，但原件完整留存，可回放。 |
| F 解析 / 去重 / 质量结果 | L12 Audit | `dq_run_finance_cashflow_import` 或复用 B 的 JSON 字段 | `NEW_SYSTEM_OWNED` | 解析器 | 每批：识别到的账户、行数、去重行数、余额链校验结果（期初 = 首行余额 − 金额、逐行连续）、表头区间 vs 实际首末笔、拒绝原因（PDF / 不认识的表头 / 未登记账号）。 |

没有 `READ_LEGACY_TEMPORARILY`、没有 `MIGRATE_ONCE`（旧 Excel 日记账 5–9 月按 Rocky 2026-10-29 决定不迁入）。

## 3. 账户与识别特征（表 A）

识别**只看文件内容**，不看文件名（财务原文件名随意）。特征来自 Demo `bank_parsers.detect` 在 7 份真实导出上的验证：

| account_key | 显示名 | 主体 | 币种 | provider | 识别特征（文件内） |
|---|---|---|---|---|---|
| `BOC_CNY` | 四颗洋葱 · 中行人民币户 | 四颗洋葱 | CNY | boc | xls / xlsx，表头含「交易类型」或「查询账号」，查询账号尾号 = 5951 |
| `BOC_USD` | 四颗洋葱 · 中行外汇户 | 四颗洋葱 | USD | boc | 同上文件内 USD 行（若单独导出则按账号 尾号 5951 + 币种 USD） |
| `ZSBJ_BOC` | 掌上便捷 · 中行对公 | 四颗洋葱（代管） | CNY | boc | 查询账号尾号 = 6815，CNY 行 |
| `ZSBJ_BOC_USD` | 掌上便捷 · 中行外币户 | 四颗洋葱（代管） | USD | boc | 查询账号尾号 = 6815 导出中的 USD 行（账号 尾号 1389） |
| `ZSBJ_YZ` | 掌上便捷 · 银座对公 | 四颗洋葱（代管） | CNY | shenzhen_rural_bank | xlsx「交易明细查询列表」/「对方账户名」，账号 尾号 0015 |
| `PAYONEER` | 派安盈 · 四颗洋葱 | 四颗洋葱 | USD | payoneer | CSV 首行 `Currency,Payout method,Transaction date…`，描述以 `Payment from Walmart` / `Card charge` / `Maintenance fee` 为主 |
| `PAYONEER_FH` | 派安盈 · 主账号（FurnitureHaven 归集） | 四颗洋葱 | USD | payoneer | 同格式，描述以 `STRIPE` / `connected account` 为主 |
| `WORLDFIRST` | 万里汇 | 四颗洋葱 | USD | worldfirst | xlsx 表头含「子账号昵称」「动账类型」 |
| `PINGPONG_MAIN_USD` / `PINGPONG_MAIN_CNH` | PingPong · 专用户 USD / CNH | 四颗洋葱 | USD / CNH | pingpong | xlsx 表头含「出账/入账」「流水号」，用户编号尾号 = 8366，按「账号Id」+ 币种分子账户 |
| `PINGPONG_<店铺账号后 6 位>` | PingPong · 店铺 Saiyu Artcave TECH（…877143） | 四颗洋葱 | USD | pingpong | 同上文件中本用户编号下的店铺账户行 |

PDF（回单 / 招行流水）一律拒绝并给出中文原因；招商银行账户不在范围（Rocky 2026-10-29）。

本仓库为 Public，文档只写账号 / 用户编号**尾号**；完整识别值放在 `dim_finance_cash_accounts` 的 migration 种子里由负责人在 PR 中审阅（种子值本身属 confidential，实现 PR 需按 `docs/SENSITIVE_DATA_AND_PERMISSION_RULES.md` 处理，必要时改为部署时注入）。

## 4. 标准化流水字段（表 D 契约要点）

| 字段 | 类型 / 规则 |
|---|---|
| `line_uid` | `sha1(account_key \| business_date \| source_time \| amount \| balance_after \| source_ref \| description)` 前 16 位；唯一索引 |
| `account_key` | 外键 → 表 A |
| `business_date` | date；银行 / PingPong / 万里汇为 Asia/Shanghai 的交易日期；派安盈 CSV 为 UTC 时间列，需同时保留 `source_time` + `source_timezone='UTC'` 并按 Asia/Shanghai 折算 `business_date`（口径在规则文档 §3 固定） |
| `source_time` | time / timestamptz（原值保留） |
| `amount` | Numeric(18,2)，入正出负 |
| `currency_code` | CNY / USD / CNH（CNH 不折算为 CNY） |
| `balance_after` | Numeric(18,2)，可空（派安盈部分行、PingPong 子账户按导出列） |
| `counterparty_name` | text，敏感字段（个人姓名）；字段权限控制返回 |
| `counterparty_account_last4` | 只存后 4 位；完整卡号、身份证号**不入库**（解析阶段剥离） |
| `description` / `memo` | 原文保留；连续 ≥16 位数字串在**展示层**脱敏为 `…` + 后 6 位（原文仍在 RAW） |
| `source_ref` | 银行流水号 / 报文号，存后 10 位 |
| `statement_row_no` | 文件内行号；配合 `file_row_order` 支持「严格按银行明细顺序」 |
| `raw_file_id` / `import_id` | 血缘 |
| `declared_range_from/to` | 文件表头声明的查询区间（中行有），无则空 |
| `parser_version` | 解析器版本号 |

不做的事：不分类、不挂审批单、不做复核状态、不折算人民币（这些属于「现金状况」PRP）。

## 5. 权限与敏感性

- 页面：`page:data_center:data_import:view`（既有）。本期不新增导航项。
- 功能：`action:data_center:data_import:finance_cashflow_upload`（高风险 = 否，但写审计）、`action:data_center:data_import:finance_cashflow_void`（高风险 = 是，需二次确认 + 审计）。
- 读取流水：`page:finance:settlement_reconciliation:view` 的读 API 复用本期的 `GET /lines`，字段权限 `field:finance:settlement_reconciliation:counterparty` 控制对方户名 / 尾号；未授权时字段不返回（不是返回空串）。
- 数据范围：按**法人主体 / 账户**而非店铺；data scope 资源 = `finance_cash_account`，角色默认 none → fail closed。
- 上传者限定：财务角色与超级管理员；运营角色不可见上传入口也不可调用。
- 原件（RAW）不通过任何 API 下载（本期）；需要回放时由负责人授权脚本处理。
- 日志 / 错误 / 测试 fixture 不得含真实户名、账号、金额明细；测试用合成文件。

## 6. 质量与控制总数

- 每批必须输出：识别账户、行数、新增 / 重复 / 拒绝行数、余额链是否连续、表头区间内无行的日期段（= 无交易，不报错）。
- 验收基线（来自 Demo 2026-10 真实导出，供实现 PR 做 control totals，文件不进 Git）：7 份文件 → 10 个账户 160 行（BOC_CNY 24、ZSBJ_BOC 23、ZSBJ_BOC_USD 2、ZSBJ_YZ 17、PAYONEER 29、PAYONEER_FH 34、WORLDFIRST 3、PINGPONG_MAIN_USD 16、PINGPONG_MAIN_CNH 8、PINGPONG_877143 4）；中行两户表头声明区间 2026-10-01 ~ 2026-10-28。
- 重复导入同一文件：新增 0、重复 = 全部；滚动导出（区间重叠）：只新增新行。

## 7. 退出条件 / 风险

- 不存在旧库依赖，无退出条件。
- 风险：银行导出模板改版 → 识别失败应整批拒绝并提示，不得部分入库；派安盈时区折算口径必须在规则文档固定；PingPong 用户编号变更需改表 A。
- 负责人可改的默认选择（不构成 NEED_OWNER_DECISION）：① 原件存 bytea 还是受控目录；② 上传入口放数据中心 → 数据导入（本决策）还是财务一级菜单（需改导航规范）。

## 负责人决定

（待技术负责人填写：批准 / 修改项 / 日期）
