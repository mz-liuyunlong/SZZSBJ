# 来源注册与 RAW 策略

> Status: 规则在负责人合并后为 `approved`；来源条目和 RAW 实现均为 `planned` 或 `candidate`。
> Scope: 新来源接入前的登记、决策、原始证据与重放边界。
> Non-goals: 不确认任何外部接口可用，不授权凭据、连接、同步或建表。

## 来源类型目录

| source_type | 默认 raw_policy | 特别约束 | 示例状态 |
| --- | --- | --- | --- |
| Lingxing API | 逐接口决定 | 不能作全平台结论；逐 endpoint 核验已有 RAW 的完整性 | candidate |
| Walmart API | RAW_REQUIRED | 保存 payload、endpoint、分页、run/batch、hash | candidate |
| Amazon API | RAW_REQUIRED | 同上，须单独 Source Decision | candidate |
| TEMU API | RAW_REQUIRED | 同上，须单独 Source Decision | candidate |
| Walmart Ads CSV | RAW_REQUIRED | 保留原文件、表头、行号、上传元数据、hash | candidate |
| Walmart Connect Invoice | RAW_REQUIRED | 财务敏感；同时应用财务对账规则 | candidate |
| SEM CSV | RAW_REQUIRED | 保留文件版本和导出期间 | candidate |
| WFS 文件 | RAW_REQUIRED | 费用/仓储相关时必须负责人确认 | candidate |
| 飞书表格 | RAW_REQUIRED | 保存原始快照/行定位，不把当前表格当永久权威 | candidate |
| Excel / CSV 导入 | RAW_REQUIRED | 原文件与逐行定位必须可追溯 | candidate |
| 人工录入 | RAW_REQUIRED | 以不可变提交 envelope + before/after audit 作为原始证据；例外需批准 | candidate |
| 旧系统 MySQL | RAW_REQUIRED | 读取结果是 `legacy_reference`/过渡来源；旧 cleaned/derived 不能冒充 RAW | legacy_reference |
| 公司文档 / SOP | RAW_REQUIRED | 保存文档原件、版本、状态、owner、权限、hash | candidate |
| AI 输入材料 | RAW_REQUIRED | 保存允许留存的输入引用与 retrieval 来源；不得保存 secret | candidate |

## RAW 状态

| raw_status | 含义 | 是否允许继续 |
| --- | --- | --- |
| `RAW_REQUIRED` | 已决定必须建立原始证据，尚未证明完成 | 仅可做设计/PRP，不得声称已落地 |
| `RAW_CONFIRMED` | 对指定来源/接口/版本已有完整可追溯 RAW 证据 | 可按获批 PRP 继续，不代表数据已权威 |
| `RAW_PARTIAL` | 只覆盖部分字段、时间、分页、错误或版本 | 缺口关闭前不得用于依赖完整性的发布 |
| `RAW_MISSING` | 应有 RAW 但不存在或无法证明 | 阻塞发布，需补采或 owner 决策 |
| `RAW_NOT_APPLICABLE` | 经 Source Decision 证明无 RAW 必要 | 必须写明理由、替代证据、风险与批准人 |
| `NEEDS_RECHECK` | 当前证据不足、过期或相互冲突 | 视为未确认，不能提升为 `RAW_CONFIRMED` |

## Source Registry 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `source_key` | 是 | 稳定、小写、唯一的来源键；不得包含凭据 |
| `source_name` | 是 | 可读名称 |
| `source_type` | 是 | 上述来源类型或经 PRP 批准的新类型 |
| `owner` | 是 | 对来源合法性、契约与停用负责的角色 |
| `authority_level` | 是 | `candidate`、`legacy_reference` 或已批准字段级权威说明 |
| `raw_policy` | 是 | `RAW_REQUIRED` 或获批例外策略 |
| `raw_status` | 是 | 上述 RAW 状态，按接口/文件类别记录 |
| `connection_type` | 是 | API、file、readonly DB、manual、document 等；不写连接串 |
| `access_method` | 是 | 获批访问方式和最小权限说明；不写 secret |
| `sync_cadence` | 是 | batch/周期/on-demand/manual；未知写 `NEEDS_RECHECK` |
| `retention_policy` | 是 | 原始证据与元数据留存/删除策略 |
| `sensitive_level` | 是 | public/internal/confidential/secret 等项目批准等级 |
| `allowed_target_layers` | 是 | 经批准可发布到的逻辑层，不等于表已存在 |
| `current_status` | 是 | `planned/approved/implemented/candidate/legacy_reference` |
| `evidence` | 是 | 仓库文档、契约、审批或运行证据引用 |
| `risk_note` | 是 | 缺口、权限、合规、完整性、新鲜度与退出条件 |

## 硬性规则

1. 非领星来源默认 `RAW_REQUIRED`；任何 `RAW_NOT_APPLICABLE` 必须在 Source Decision 中说明替代证据并由负责人批准。
2. 领星来源必须逐接口、逐版本确认 RAW 状态，不得把单一接口证据推广到整个平台。
3. 旧系统清洗表迁移只能标记为 `legacy_cleaned` 或 `legacy_derived`，并保持 `legacy_reference` 权威状态；不能冒充原始事实。
4. CSV、Excel、飞书表格和文档必须保留原始文件/快照、原始表头、行号、上传人、上传时间与 hash；敏感信息按安全/留存规则最小化。
5. 人工录入必须保留 `before_value`、`after_value`、`operator`、`reason`、`source_page`、`source_action` 和时间。
6. AI 输入材料必须记录 input source 与 retrieval source；secret 级字段不可进入 AI 输入或索引。
7. 禁止外部 API 返回后直接清洗并覆盖业务表而不保留 RAW 或 lineage。
8. 禁止在没有 Source Decision 的情况下接入、读取或同步新来源。

## 采集与安全边界

- RAW 必须不可变；更正通过新版本、补偿记录或获批 override 完成。
- RAW 不得被前端、普通业务 API 或 AI 直接查询；读取必须限于清洗、重放、审计或获批调查。
- API credential、Cookie、Authorization header、连接串和私钥不是 RAW 业务证据，必须由密钥管理系统持有并从日志/载荷中剔除。
- `run_id` 标识一次执行，`batch_id` 标识一组输入，`raw_record_id` 标识原始记录；不得互相替代。
- 失败、分页、空响应、重复上传和 schema 变化也必须形成可审计的 ingestion 结果。

## 示例（非实现）

| source_key | current_status | raw_status | evidence | 结论 |
| --- | --- | --- | --- | --- |
| `example_walmart_listing` | candidate | RAW_REQUIRED | 尚待独立 Source Decision | 仅说明未来需要 RAW，不批准调用 API |
| `legacy_mysql_example` | legacy_reference | NEEDS_RECHECK | 旧系统静态报告 | 可用于调查，不能证明生产库当前状态 |

## Forbidden patterns

- 一个 `raw_status` 覆盖整个平台全部接口。
- RAW 表被当作页面 read model。
- 只保存成功记录，不记录失败与空批次。
- 将旧表名、接口文档或候选 endpoint 写成已实现权威源。
- 在 registry、文档、日志、测试或 RAW 中保存真实 Token、密码、Cookie 或完整请求头。
