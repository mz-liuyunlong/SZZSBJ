# 字段统一清洗流程（0-18）

> Status: 规则在负责人合并后为 `approved`；具体 pipeline 均为 `planned`。
> Scope: 从来源证据到发布/隔离的字段处理顺序。
> Non-goals: 不实现任务、表、SQL、migration，也不替任何来源作接入决定。

每个实现 PRP 必须说明采用哪些步骤、物理产物在哪里以及为何可安全省略某个物理层。逻辑控制不得省略。第 0 步必须先于任何清洗。

本流程扩展 `docs/data-sources/field-standardization-standard.md` 的十二步标准：原标准继续约束字段字典和既有引用；新任务应引用本文件的 0-18 步，并将旧步骤按名称映射，不得仅按编号重解释。两个文件冲突时停止并交由负责人确认。

| step_number | step_name | purpose | input | output | required_metadata | examples | failure_handling | forbidden_patterns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | Raw Payload / File Capture | 在变换前保存可重放原始证据 | API payload、文件、表格快照、人工提交 envelope | 不可变 payload/file 与 raw record reference | `source_system`, `source_endpoint`, `source_file`, `source_row_number`, `raw_record_id`, `batch_id`, `run_id`, `hash`, `ingested_at` | candidate: 保存 CSV 文件及 hash | 捕获失败则整批 `reject`，不得继续发布 | 先清洗后保存；覆盖旧 payload；保存 secret |
| 1 | Source Field Capture | 按来源原名捕获字段与位置 | 第 0 步原始证据 | source-field map | 上述来源元数据、原字段名、路径/列号 | `itemId` 保持来源名记录 | 未知字段 `warn` 并记录；缺关键定位则 `quarantine` | 直接改成 canonical 名且丢原名 |
| 2 | Source Contract Validate | 校验 envelope、必需字段与版本 | source-field map、已登记 contract | contract validation result | contract/version、observed schema、validation error | API page 缺 pagination marker | 按规则 `reject` 或 `quarantine`，保留原始证据 | 自动接受破坏性 schema 变化 |
| 3 | Field Name Normalize | 映射到规范字段名 | 通过 contract 的来源字段 | 命名规范化记录 | source field、canonical field、mapping version | `itemId` → `item_id`（candidate） | 无映射时 `warn/quarantine`，不得猜测 | 同名异义合并；复制第二套字典 |
| 4 | Data Type Normalize | 转为声明类型且保留转换结果 | 命名规范化值 | typed value + parse status | source type、target type、parser version | 文本整数解析为 integer | 解析失败 `reject/quarantine`；原值可追溯 | 宽松强转；错误值变 0/false |
| 5 | Null Normalize | 统一明确的缺失表示 | typed/source value | canonical null 或有效值 | source null tokens、field rule version | `""` 是否为空由字段规则决定 | 模糊 token `warn`，关键字段可 `quarantine` | 把 0、`false`、`unknown` 一律转 null |
| 6 | Trim / Text Clean | 去除非语义空白和获批文本噪声 | 文本值 | cleaned text + change flag | cleaning rule/version、before hash | 去首尾空白，不改大小写 | 非法控制字符 `warn/quarantine` | 改大小写、翻译或删除有业务意义字符 |
| 7 | Encoding / Locale Normalize | 明确字符编码、语言与 locale | 文本/文件元数据 | UTF-8 或声明编码的文本 | source encoding、locale、language、decoder | CSV 编码转换并记录 | 无法解码则 `quarantine`，保留原字节引用 | 猜 locale 后静默改值 |
| 8 | Enum Normalize | 映射到统一参考代码 | 来源枚举值 | canonical code + source code | reference version、mapping status | platform code 映射到统一枚举 | 未知枚举 `warn/quarantine`，不得默认其他值 | 硬编码散落映射；覆盖来源值 |
| 9 | Unit Normalize | 统一重量、尺寸、数量等单位 | typed numeric + source unit | amount + canonical unit | source unit、target unit、conversion rule/version | lb → kg（仅获批规则） | 缺单位 `warn/quarantine`；不做猜测 | 只存数字不存单位；隐含转换 |
| 10 | Currency + FX Normalize | 统一金额表达并记录汇率证据 | 原金额、来源币种、业务日期 | canonical `amount`, `currency_code` 与 FX metadata | `amount`, `currency_code`, `precision`, `scale`, `rounding_rule`; 如换汇还需 `fx_rate`, `fx_date`, `fx_source`，可附加 `fx_rate_version` | USD 金额保持原币；转换另存证据 | 缺币种/规则则 `quarantine`；财务差异升级 owner | float；默认币种；覆盖原金额；取当前汇率改历史；canonical contract 使用 `currency`、`fx_rate_source` 或 `fx_rate_date` |
| 11 | Timezone + Business Date Normalize | 分离来源时间、业务日、摄取与处理时间 | 来源时间及来源时区 | UTC timestamp、业务日和时区元数据 | `source_time`, `source_timezone`, `business_date`, `ingested_at`, `processed_at`, rule version | Walmart 业务日按 America/Los_Angeles | 时区不明 `warn/quarantine`；不可猜中国时间 | 混用平台日、中国日、美国日、UTC；无时区 timestamp |
| 12 | Decimal / Precision Normalize | 按字段契约控制精度与舍入 | numeric/decimal text | 精确 Decimal 值 | precision、scale、rounding rule、source value reference | `numeric(18,4)` 规则 | 越界 `reject/quarantine`；舍入须记录 | float 中转；隐式截断；不同字段共用未知 scale |
| 13 | Identity Mapping | 解析内部实体与外部标识关系 | 标准化 identifier、source context | identity candidate/resolved mapping | platform、store、external ID、confidence、evidence、mapping version | `platform + store_id + item_id` listing identity | 冲突或低置信度进入 review/quarantine | SKU/MSKU 作全局唯一；自动覆盖人工确认 |
| 14 | Dedup / Idempotency | 防止分页、文件与任务重放重复 | 标准化记录、batch/run metadata | accepted duplicate status/idempotency result | idempotency key、hash、page/file/run、dedup rule version | 同一文件 hash 重传识别 | 冲突记录 `quarantine`；可重试不重复发布 | 只按时间去重；无证据删除；任务重跑重复写 |
| 15 | Business Derivation | 执行已批准且版本化的业务派生 | canonical input | derived fields + rule evidence | `rule_version`, inputs, effective dates, owner approval | candidate: 由明确规则生成分类 | 缺规则/输入则 `warn/quarantine`；不自动 fallback | 规则写死；覆盖来源事实；跨模块偷算财务 |
| 16 | Data Quality Check | 按字段、记录、批次校验质量 | 原值、规范值、派生值 | `pass/warn/reject/quarantine` 与 issue list | DQ rule/version、severity、counts、threshold、run ID | SKU 缺失可按批准规则 `warn` | 不合格数据保留证据并按状态路由 | 静默丢弃；只记成功数；用默认值掩盖错误 |
| 17 | Lineage Record | 记录来源、变换、目标的可追溯关系 | 全步骤 metadata 与 DQ result | lineage edges/manifest | source system/endpoint/file/table、raw record、transform rule versions、target dataset/field、run/batch ID | API 字段到 canonical 字段再到 response | lineage 写入失败则不得发布需要强血缘的数据 | 只记录表级“来自某库”；丢 raw/run/rule reference |
| 18 | Publish / Quarantine | 将合格数据发布到批准层，将问题数据隔离 | DQ 和 lineage 完整记录 | target-layer record 或 quarantine record | target layer/dataset、publish time、quarantine reason、retry/review status | `pass` 进入 Core；冲突 mapping 进入 quarantine | 发布失败可幂等重试；隔离须可调查 | 发布到未批准层；隔离无原因；reject 后销毁证据 |

金额 canonical output 只能使用 `amount`、`currency_code`、`precision`、`scale`、`rounding_rule`；涉及换汇时还必须使用 `fx_rate`、`fx_date`、`fx_source`。`currency`、`fx_rate_source`、`fx_rate_date` 只能作为来源字段、外部字段或旧字段别名，并通过 lineage 分别映射到 `currency_code`、`fx_source`、`fx_date`。`fx_rate_version` 可作为供应商、汇率表或规则版本元数据，但不能替代实际汇率值 `fx_rate`。金额处理禁止使用 float。

## 来源规则

1. 非领星来源默认必须完成第 0 步并遵守 `RAW_REQUIRED`；例外必须由 Source Decision 与负责人批准。
2. 领星来源必须逐接口记录 `RAW_CONFIRMED`、`RAW_PARTIAL`、`RAW_MISSING`、`RAW_NOT_APPLICABLE` 或 `NEEDS_RECHECK`，不得用“领星已有 RAW”作全局结论。
3. `source_system`、`source_endpoint`、`source_file`、`source_row_number`、`raw_record_id`、`batch_id`、`run_id`、`hash` 在适用时必须贯穿流程；缺失项必须有明确“不适用”理由。
4. 字段清洗不得改变业务含义；业务派生只能发生在第 15 步并带 `rule_version`。

## 最小发布门禁

- Contract、identity、idempotency、DQ 与 lineage 必须产生明确结果。
- DQ 状态只允许 `pass`、`warn`、`reject`、`quarantine`；发布哪些状态由数据集 PRP 指定。
- `reject` 和 `quarantine` 均不得静默丢失来源证据。
- Publish 必须声明目标层；Quarantine 必须声明原因、负责人、复核/重试路径和保留期。
