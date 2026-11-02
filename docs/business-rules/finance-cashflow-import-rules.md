# 财务 · 现金流账户报表导入规则 V1

- Status: Draft（随 PRP `finance-cashflow-statement-import-v1` 一起审）
- Source Decision: `docs/data-sources/decisions/finance-cashflow-statement-import-decision.md`
- 来源：业务原型（Rocky 侧财务 Demo v5.3.0 ~ v5.5.0，2026-10-29 ~ 10-31 与财务与财务主管逐条确认）。本文只定口径，不定实现。

## 1. 节奏与责任

- 财务每周二 15:00 前把**全部**现金流账户的原始导出一次性上传（一次可多文件）；系统不看文件名，按内容认账户。
- 文件覆盖区间以**文件表头声明的查询区间**为准（中行「查询时间范围」），没有表头的按文件内首末两笔；区间内没有行 = 该段无交易，不报错、不追问。
- 滚动导出允许重叠；重复行按指纹去重，不重复入库。
- 作废只允许整批作废（软删除 + 审计），不允许改单行。

## 2. 识别规则（按内容，顺序）

1. 文件头 `%PDF` → 拒绝：「PDF 不是流水导出：中行请导『交易明细』xls；招商银行不接」。
2. xlsx（zip）：共享字符串 / 工作表文本（含 HTML 实体解码）中
   - 含「子账号昵称」且「动账类型」→ 万里汇；
   - 含「出账/入账」且「流水号」→ PingPong（再按用户编号 / 账号Id 拆子账户）；
   - 含「交易明细查询列表」或「对方账户名」→ 深通村镇银座，须含账号 尾号 0015，否则拒绝「账号没登记」；
   - 含「查询账号[Inquirer account]」且明细表头含「交易类型[Transaction Type]」→ 中行，按查询账号尾号 6815 / 5951 归户；USD 行单列外币户（`ZSBJ_BOC_USD` / `BOC_USD`）；
   - xlsx 解压后总大小 > 50 MB 或条目数 > 200 → 拒绝「文件异常（解压超限）」；
   - 其余 → 拒绝「表头不认识（支持：万里汇 / PingPong / 中行交易明细 / 银座交易明细）」。
3. xls（OLE，`D0 CF 11 E0`）：按账号字符串（含 UTF-16LE）归中行两户，否则拒绝。
4. CSV 首行 `Currency,Payout method,Transaction date` → 派安盈；按描述特征计数分四颗洋葱户（Payment from Walmart / Card charge / Maintenance fee）与主账号（STRIPE / connected account）：计数多者归户；两类都为 0 或**两类相等 → 拒绝该文件**「派安盈账户无法判定，请人工指定」。
5. 其他 → 拒绝「不是 xlsx / xls / Payoneer CSV」。

## 3. 解析口径

| 来源 | 日期 / 时间 | 金额方向 | 余额 | 对方 | 备注 |
|---|---|---|---|---|---|
| 中行 xls | 交易日期 + 交易时间（Asia/Shanghai） | 「往账」或金额为负 = 出 | 「账户余额」列 | 出账取收款人名称，入账取付款人名称 | 用途 / 交易附言 / 摘要合并；USD 行归外币户 |
| 银座 xlsx | 交易日期 + 时间（Asia/Shanghai） | 借 / 贷列 | 余额列 | 对方账户名 | 摘要 |
| 派安盈 CSV | Transaction date + time + Time zone 列（UTC）；`business_date` = 折算到 Asia/Shanghai 的日期；原值与时区保留 | Credit / Debit | Running balance | 从 Description 解析（示例 `Payment to 某银行 (0000)` 取银行 + 卡尾号） | Description 原文 |
| 万里汇 xlsx | 交易时间（Asia/Shanghai） | 动账类型 | 主账户行带余额 | 对方 | 子账号昵称 |
| PingPong xlsx | 交易时间（Asia/Shanghai） | 出账 / 入账 | 该子账户交易后余额 | 对方 / 业务类型 | 只保留用户编号 = 本公司专用户的行；「专用账户入账」拆成两行：回款全额（余额 = 实际 + 手续费）与「归集手续费」（余额 = 实际），手续费按同订单号的其他主体归集出账额对出 |

- `line_uid = sha1(account_key | business_date | source_time(UTC) | amount | balance_after | source_ref 全值 | description 脱敏前原文 | dup_ordinal)[:16]`，`dup_ordinal` = 同一文件内同键出现序号；指纹用全值 / 原文（只在 RAW 里），入库字段是后 10 位 / 脱敏后。同 uid 再次出现 → 不新增，`last_import_id / last_raw_file_id` 指向最新文件。
- 时间：`source_time` 存 timestamptz（UTC）+ `source_timezone`；**财务流水业务日 `business_date` 统一按 Asia/Shanghai**（见 §7）。
- 边界案例（实现 PR 必须有对应测试）：
  | 案例 | 预期 |
  |---|---|
  | 同一文件内同秒、同金额、同描述、同余额两笔 | 两行都入库，`dup_ordinal` = 1 / 2，uid 不同 |
  | 滚动导出区间重叠（上周文件含 10-01~10-28，本周文件含 10-15~11-04） | 重叠行 uid 相同 → 不新增，`last_*` 改指本周文件；只新增 10-29 之后的行；覆盖区间取并集 |
  | 作废最新批 | 只出现在该批的行标 `voided_at`（不删、不参与任何汇总）；也出现在更早未作废批的行归属回退到那一批，`last_*` 改回；再次上传同文件 → 新批、行恢复 |
- 金额 `numeric(18,4)`，入正出负；文件中的数字按字符串转 `Decimal`，不经 float；币种随账户（CNH 不等于 CNY，不折算）。
- 精度：存储与汇总、余额链比较一律按 `Decimal` 精确计算，不做中间舍入；余额链按 0.0001 精确相等判断；只在展示层保留 2 位（ROUND_HALF_UP）。导出原值超过 4 位小数 → 该文件拒绝「金额精度超出」，不截断。
- 文件内顺序：各家导出方向不一（中行 / PingPong 旧→新，派安盈 / 银座 新→旧），按每个账户的整体方向把行号归一成时间正序号 `file_row_order`，页面按 日期↓ 时间↓ 序号↓ 排，手续费紧跟对应那笔。
- 余额链：有余额列的账户，期初 = 首行余额 − 首行金额；逐行校验「上一行余额 + 本行金额 = 本行余额」，断链记质量结果，不拒绝入库（PingPong 子账户不做链校验）。

## 4. 脱敏（解析阶段，进入 L3 之前）

- 身份证号：不入库（匹配 18 位身份证模式的片段整体丢弃）。
- 银行卡 / 账号：只保留后 4 位；描述里连续 ≥16 位数字串替换为 `…` + 末 4 位（与卡号尾号口径一致）。
- 邮箱（PingPong / 派安盈子账户）：保留前 3 字符 + `…@`。
- 流水号 / 报文号：存后 10 位。
- 原件（RAW）不脱敏、不对外。
- 对方户名（个人）：入库，但为字段权限控制项。

## 5. 质量与拒绝

- 原子性：**按文件原子**——一个文件内全有或全无（识别失败、解析报错、校验不过 → 该文件整体拒绝并给原因）；同一批里的其他文件互不影响、照常入库；返回每文件结果。
- 表头声明区间早于首笔 / 晚于末笔 → 正常（无交易）；首笔早于声明区间 → 质量告警（导出与声明不符）。
- 同 sha256 文件重复上传 → 返回既有记录，不重存、不重解析。
- 账户主数据变更（新账户、用户编号变）→ 走 migration / 负责人授权脚本，不在页面改。

## 6. 不在本规则范围

分类（类别编码）、挂审批单、拆分 / 剔除、初审 / 二审、折人民币、公司口径剔除净额、资产负债表——这些在 Demo ⑥ / ⑩ 已有口径，等「现金状况」是否进正式菜单由负责人决定后另立规则与 PRP。

## 7. 时间口径例外登记

- `docs/business-rules/time-money-metric-rules.md` 规定 Walmart 销售 / 广告业务日按 America/Los_Angeles 归属。**财务流水不是 Walmart 业务数据**：银行与收款平台的交易日以中国账期为准，因此本模块 `business_date` 统一 = **Asia/Shanghai**，在此登记为该规则的例外（适用范围：`std_finance_cashflow_lines` 及其下游现金 / 对账口径）。
- 存储：`source_time` timestamptz（UTC）+ `source_timezone` + `source_time_raw`；展示按仓库默认展示时区；与 Walmart 结算期次（America/Los_Angeles）对账时按各自口径显示日期，不互相折算。
