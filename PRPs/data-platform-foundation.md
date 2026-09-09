# Data Platform Foundation PRP

```text
Status: Draft
Owner Approval Required: Yes
Implementation Allowed: No
Database Access Authorized: No
Server Access Authorized: No
SQL or Migration Authorized: No
External API Access Authorized: No
Deployment Authorized: No
```

本文是数据平台的总体设计基线，不是一个实现任务。即使负责人批准并合并本文，也不得连续实现本文列出的能力；每个未来阶段仍须有独立 PRP、独立负责人授权、一个主执行角色、一个分支和一个 PR，并能够独立测试与回滚。

## 1. Authorization Boundary

本 PRP 只批准设计边界和后续实施顺序，不批准任何代码、数据库或外部系统操作。

- 不允许创建 schema、表、索引、migration、ORM model、mart/read model 或对象存储资源。
- 不允许连接数据库、服务器、SSH tunnel、Redis、Celery broker 或外部平台。
- 不允许执行 SQL、同步、回填、重算、导入、导出、通知或部署。
- 不允许修改前端、后端、`old-system/`、生产配置、CI、密钥或真实 `.env`。
- 不允许在本文记录真实 Token、Webhook URL、连接串、账号、主机或生产数据样本。
- 本文中的实体名均是 `planned` 逻辑能力，不证明物理表或服务存在，也不批准最终 schema。
- 当前文档任务的回滚边界仅为本 PRP 文件；合并后使用普通 docs-only revert。

任何后续实现必须先确认适用的 Source Decision、字段标准、数据层、权限、DQ、血缘、留存、审计和回滚边界。业务数据来源存在 `NEED_OWNER_DECISION` 或未达到精确范围的 `READY_FOR_PRP` 时，不得进入实现 PRP。

## 2. Current Project State

当前基线为最新 `origin/main`，本任务开始时 HEAD 与 `origin/main` 均为 `e8c374f8dbea513a0d2097b27fae461a4b827be3`。

- 前端页面壳工作已经合并；本 PR 不修改既有前端实现。
- 产品管理当前仍是 No-API 页面能力，不代表真实产品数据接口已接入。
- Backend API Foundation 已完成，提供 request ID、统一响应、错误、认证入口、权限和资源级 data scope 基础。
- Data Governance Catalog 已存在，但仅是规则基线；数据库分层、来源登记、同步、规则计算、通知、字段监控和 read model 仍未实现。
- PostgreSQL 数据层、Celery/Redis 同步任务、对象存储、通知通道和业务数据模型尚未由本文批准实现。
- 既有前端、后端、规则文档和 PRP 只作为当前基线证据，不得因本文被顺手修改。

## 3. New-System Runtime Decision

负责人已撤回“新系统业务 API 运行时读取旧系统 MySQL”的实施路线。

```text
New-system runtime:
External source -> governed ingestion -> new-system PostgreSQL layers/read model -> Backend API -> Frontend

Legacy use:
legacy_reference -> discovery/reconciliation/comparison only
```

- 新系统业务 API 必须读取新系统 PostgreSQL 中已批准的数据层或 read model。
- 旧系统代码和 legacy MySQL 仅可作为字段口径、历史证据、对账与迁移验收参考，不得成为新系统运行时 read source。
- `PRPs/phase-2a-product-basic-information-query-api.md` 中的 `READ_LEGACY_TEMPORARILY` 实施路线已被负责人决定取代，不得再下发实现 Prompt。
- `docs/01_PROJECT_DECISIONS.md` 的 D-003 以及数据分层文档中的 legacy runtime 示例与最新决定不一致；在任何数据平台实现 PRP 获批前，必须通过独立 docs-only 任务对齐这些历史规则入口。本文不修改它们。
- 本决定不授权默认双读、双写或静默 fallback。任何迁移切换都必须由独立 PRP 定义对账、切换、退出和回滚。
- 产品、销售、库存、利润、广告和财务 API 必须等待各自的新系统数据层和查询边界获批。

## 4. Platform / Store / Identity Boundary

平台模型必须预留 `platform`、`marketplace`、`store`、`store_account`、`owner` 和 `data_scope` 的独立职责，但本 PRP 不批准相应物理表。

- 新系统维护不可变、无业务推断含义的内部稳定 ID。
- SKU、MSKU、ItemID、seller SKU、store ID 和外部账号 ID 均不是跨平台全局唯一身份。
- Listing identity 至少需要平台、店铺/账号和外部 listing/item 上下文；最终 grain 由后续 Source Decision 和实体模型 PRP 确认。
- 一个内部产品可以关联多个平台、店铺、账号、listing 和外部标识，禁止逗号拼接或单字段强行合并。
- 身份映射必须记录来源、证据、方法、置信度、状态、版本和合并/拆分历史。
- 低置信度、冲突或上下文不足的映射进入 quarantine/review，不得直接发布到 Core、DIM/MASTER 或 read model。
- 人工确认不能被同步任务静默覆盖；自动匹配不得替负责人或数据 steward 作最终决定。
- `owner` 是业务归属实体；`data_scope` 是授权结果，二者不得混同，也不得用前端筛选代替后端授权。

## 5. Data Layer Foundation

固定技术边界：PostgreSQL、SQLAlchemy 2、Alembic only。未来 Data Layer implementation PRP 至少定义：

- 环境化 config，只保存变量名和校验规则，不保存真实连接值；
- engine/session factory、declarative base 和 repository boundary；
- route -> schema -> service -> repository -> model 的分层；
- request/service transaction boundary、commit/rollback 所有权和只读事务行为；
- Alembic revision、升级、降级、锁定、失败恢复与禁止手工改生产 schema 的规则；
- 本地/CI 隔离 test DB 策略，测试不得误连 staging/production；
- UTC 存储的 `created_at`、`updated_at` 等技术时间字段，以及 actor/request/run/audit metadata 约定；
- 连接池、statement timeout、健康检查和敏感日志边界；
- repository 不承担权限决策，service 不散写 SQL，route 不堆业务逻辑。

本文不批准真实 schema、表名、migration 顺序、ORM model、数据库连接或依赖变更。每个业务表仍须在自己的 PRP 中声明 layer、grain、identity、owner、writer/readers、authority、retention、lineage、DQ、敏感性和回滚。

## 6. RAW Storage Foundation

未来 Source Registry + RAW Storage implementation 必须遵循：

- Source Registry 精确登记 source、endpoint/file type、版本、owner、authority、RAW policy、敏感性和状态；
- RAW metadata 存于 PostgreSQL；大 payload/file 存于经批准的 object/file storage；本文不选择供应商；
- metadata 至少预留 `run_id`、`batch_id`、`endpoint_key`、hash、size、compression、`storage_uri`、ingested time 和 schema/contract version；
- `storage_uri` 只能是受控引用，不得包含凭据或签名查询参数；
- 成功、失败、空页、分页、重试和 schema drift 都必须留下运行证据；
- RAW 默认不可变或 append-only，支持 retention、archive、replay 和 dedup；
- credential、Cookie、Authorization header、Webhook URL 和连接串必须在落 RAW 前剔除；
- RAW 只用于来源证据、重放、审计和清洗输入，不是业务权威；
- frontend、普通业务 API 和 read model 不得直接查询 RAW；AI 也不得直接读取 RAW。

每个来源、接口和版本的 `RAW_REQUIRED`/`RAW_CONFIRMED` 等状态必须独立决定，不得用一个结论覆盖整个平台。

## 7. Ingestion / Scheduled Sync Foundation

未来同步基础固定使用 Redis + Celery，Scheduler/Celery Beat 负责触发，Worker 负责执行。不得引入第二套任务系统。

- 领星固定时间同步、人工触发、补数和重试均创建受治理的后台任务，不在 FastAPI request path 批量拉取。
- 预留 `ingestion_runs`、`ingestion_run_pages` 和 `sync_locks` 等逻辑记录；物理设计由独立 PRP 决定。
- 每次运行必须有 source/endpoint、参数摘要、watermark、run/batch ID、页状态、计数、错误、开始/结束时间和触发人。
- 任务必须声明幂等键、分页去重、watermark 推进条件、可重试错误、backoff、最大次数和停止条件。
- backfill 必须限定来源、时间范围、店铺/账号、最大规模、并发、成本、审计和取消/恢复策略。
- 任务锁要防止同一来源/范围的危险并发，不得依赖单机内存锁作为生产保障。
- 生产 Scheduler 必须单实例；Worker 可以多实例横向扩展。
- 定时规则必须可由数据库配置、版本化和审计，不能只硬编码在代码或服务器 crontab。
- 外部 API credential 只由后端 secret 管理，不能进入任务参数、日志、RAW 或前端。

## 8. Frontend Sync Control Foundation

后续“数据中心 -> 任务中心”可提供任务控制界面，但必须通过独立前端页面 PRP 和后端 API PRP 实现。

任务中心需支持查看、启用/停用、修改获准时间、手动运行、补数、重试、失败原因和历史记录。权限不同的用户只能看到和执行其获准范围内的动作。

- 前端只能通过 FastAPI 创建任务请求、修改允许的任务配置、查询任务状态。
- 前端不得直接控制 Celery/Beat、Redis、服务器脚本、数据库或外部平台。
- 前端不得读取完整外部 API 密钥、Webhook URL 或连接串。
- 启用/停用、改时间、手动运行、补数和重试必须分别受 action permission、data scope、二次确认（高风险时）和审计控制。
- 页面状态不能作为任务真源；刷新后必须以后端运行与配置状态为准。
- 普通运营与管理员的差异由动态 permission/data scope 配置表达，代码不得硬编码角色名。

## 9. Business Rules / Metric Calculation Foundation

利润、库存、补货、广告、财务、产品等级等权威计算必须在后端/数据平台统一完成。前端只可展示、筛选或提供明确标记为非权威的临时预估。

未来逻辑实体预留：

```text
metric_definitions
business_rule_definitions
business_rule_versions
rule_parameters
calculation_runs
calculation_results
calculation_lineage
```

- 每个指标必须定义 name、business meaning、grain、owner、formula、inputs、inclusion/exclusion、time semantics、currency semantics、rule version、effective date 和 lineage。
- calculation run 必须绑定输入版本、规则版本、数据范围、run ID、状态、control totals 和输出位置。
- read model 只能消费可追溯结果，不能在查询时隐藏计算公式。
- route、前端或报表不得各自复制利润、库存、佣金或费用公式。
- 任何具体公式、阈值、来源和发布规则仍需专项 Source Decision/业务 PRP 与负责人确认。

## 10. Effective-Dated Rule Policy

所有会改变历史业务结果的规则必须支持：

```text
effective_from
effective_to
rule_version
change_reason
approved_by
approved_at
```

- 已生效且影响历史结果的规则不得原地覆盖或物理删除。
- 规则修改必须明确属于未来生效、尚未生效版本修改，或历史重算。
- 历史订单和已锁定期间默认不得被新规则静默重算。
- 历史重算必须创建 `recalculation_run`，记录原因、批准人、输入与规则版本、影响范围、旧结果引用、新结果和对账结论。
- 未来生效规则不得提前改变当前结果；撤销或替换也必须保留版本链。
- 重算、解锁和回写属于高风险动作，需要独立权限、审批、审计和可回滚设计。

## 11. Commission / Fee Rule Policy

佣金与费用属于高风险财务规则；本文只预留能力，不批准公式或数据源。

未来逻辑实体预留：

```text
commission_policies
commission_policy_versions
commission_policy_tiers
order_commission_results
```

- 店铺佣金可按销售额阶梯并支持生效日期。
- 计算模式预留 `FULL_TIER_RATE` 和 `MARGINAL_TIER_RATE`，具体语义、边界和示例必须由专项 PRP 批准。
- 每笔订单佣金结果必须绑定 `commission_policy_version_id`，不得因未来规则变化改写早期订单结果。
- 采购成本、头程运费、WFS 费用、仓储费、广告费、退款成本、人工调整和汇率规则分别建模并保留各自口径，不得因名称相似合并。
- 金额必须使用 Decimal/`numeric(18,4)` 等获批精度，包含 `amount`、`currency_code`、`precision`、`scale`、`rounding_rule`；换汇还需 `fx_rate`、`fx_date`、`fx_source`，禁止 float 和默认币种。
- 财务结果必须有 metric definition、control totals、lineage、期间锁定、权限和审批。

## 12. Manual Override Policy

- 外部同步字段与人工覆盖字段必须分开保存；不得写入同一列后失去来源区分。
- 人工记录至少包含 target entity/field、`before_value`、`after_value`、`operator`、`reason`、`source_page`、`source_action`、`effective_from`、可选 `effective_to`、approval status 和 audit reference。
- 同步任务只更新来源值，不得静默覆盖有效人工值，也不得把人工值回写 RAW。
- 人工覆盖必须有字段和动作权限、data scope、有效期、来源页面、操作原因以及必要的二次确认/审批。
- 前端在权限允许时应区分 source value、manual value 和 effective value，并能显示冲突/待审核状态。
- 人工归档/解档不物理删除证据；撤销通过新状态或补偿记录完成。
- AI 建议只有在有权限人员明确采纳后，才能形成独立 manual override/event/audit。

## 13. Field Watch Foundation

字段变化、阈值、状态变化、数据缺失、数据延迟、任务失败、计算异常和人工覆盖必须可监控。该能力是第一版数据平台地基的一部分，但实现仍需独立 PRP。

未来逻辑实体预留：

```text
field_watch_definitions
field_watch_events
```

definition/event 至少表达 platform、store/account、resource type/id、field path、condition、threshold、`severity`、`effective_from`、`dedup_key`、`cooldown`、owner 和 notification route。

- 监控定义必须版本化；阈值和条件不得散落在前端或任务代码。
- 事件必须引用 source/run/record 或 calculation/audit evidence，并区分 detected、deduplicated、suppressed 和 delivered。
- 对缺失和延迟的判断必须基于已批准 freshness/SLA，不得用猜测时间。
- 监控失败不得阻塞或悄悄改变业务数据；必须形成可观测运行状态。

## 14. Alert / Notification Foundation

未来逻辑实体预留：

```text
alert_rule_definitions
alert_rule_versions
alert_events
alert_event_status_logs
alert_silences
alert_escalation_policies
```

- Alert lifecycle 至少支持 `acknowledged`、`resolved`、`ignored` 和 `suppressed`，并保留每次状态变化的 actor、reason 和 time。
- 支持去重、冷却、升级提醒、暂停提醒和恢复，不得靠前端本地状态实现。
- Alert event 必须追溯到来源规则、字段、任务、calculation run、资源对象和通知发送记录。
- silence 必须限定对象、规则、范围、开始/结束、原因和批准人，不能成为永久静默开关。
- AI 可以解释和汇总预警，但不能静默关闭、确认或解决预警。
- 具体规则、阈值、渠道和升级策略由独立 PRP 批准。

## 15. Feishu Notification Foundation

- Feishu Webhook Bot 是第一正式通知通道。
- Feishu App Bot 预留给后续交互卡片、审批、用户身份关联和 `@` 机器人查询；本 PRP 不调用或配置它。
- 未来逻辑实体预留 `notification_channels`、`notification_routes` 和 `notification_deliveries`。
- channel 只保存 provider、用途、状态、权限和 `secret_ref`；不得保存或返回明文 Webhook URL。
- delivery 必须记录 route/template/version、alert/event reference、状态、尝试次数、成功/失败、脱敏 error 和 `external_message_id`。
- 必须设计失败重试、发送限流、通知模板版本和按 severity/业务范围路由。
- 前端永远不接收完整密钥；密钥新增、替换、测试和停用需权限与审计。
- 本文只确认正式通道方向和模型边界，不批准真实发送、应用权限或 credential 创建。

## 16. WeCom / WeChat Boundary

- provider 枚举预留 `WECOM_GROUP_BOT`，作为候选正式通知通道。
- 普通个人微信群不属于正式系统通知链路。
- 第一版候选能力仅为系统字段监控/预警向获准企业微信群推送，不读取普通微信群聊天内容。
- 不允许依赖非官方个人微信机器人、桌面自动化或个人账号作为核心通知链路。
- 企业微信真实接入前必须完成单独 PRP、官方能力验证、权限/密钥设计、失败策略和负责人批准。

## 17. Read Model / Frontend Query Policy

- 前端只通过受保护 FastAPI 查询获批 read model/mart 或适合直接查询的 Core/DIM/FACT 服务。
- 前端不得直查 PostgreSQL、RAW、对象存储或外部平台。
- 前端不得承担最终利润、库存、补货、广告、佣金、费用或财务计算。
- 产品、销售、利润、库存、广告、财务、任务和预警领域均预留独立 read model 方向，但只在存在明确查询/性能需要时创建，禁止预建空壳。
- Read Model 是可重建查询优化层，不是权威数据源，不接收人工或来源直接写入。
- 每个 read model 必须记录来源层、grain、writer、reader、refresh trigger、freshness、rule version、lineage、DQ、permission/data scope、retention 和 rebuild/rollback。
- API 响应必须标明适用的 freshness、warning 和 request ID，不能用 read model 的更新时间伪装来源新鲜度。

## 18. Permission / Data Scope / Field Permission

所有能力必须 fail closed，并至少区分：

- page permission；
- action permission；
- store/account/resource data scope；
- field permission；
- export permission；
- high-risk action permission。

预警、通知、任务、规则、费用、佣金、重算、导入和导出必须分别声明资源键与 permission key，不得只依赖前端隐藏。

- 普通运营、管理、财务、采购和 AI 用途代表可配置职责场景，不得在代码中硬编码角色名。
- data scope 由可信后端 provider 按 resource/page 解析；unknown/missing/`NONE` 必须拒绝。
- field permission 必须在 backend/read model/export/AI input 层执行，不能只隐藏表格列。
- 高风险动作需二次确认、必要审批、幂等、审计和可回滚。
- service/repository 不得信任客户端声明的全店铺、管理员或字段可见性。

## 19. Audit / Operation Log

修改规则、费用、佣金、人工覆盖、同步任务、通知通道、重算任务、导入导出和其他高风险配置必须审计。

审计记录至少包含：

```text
actor
action
target
before
after
reason
request_id
ip
user_agent
occurred_at
approval_or_confirmation_status, when applicable
```

- 敏感值只记录安全引用或脱敏摘要，不在 before/after 中复制 secret。
- 审计日志与业务当前状态分离，不得被普通业务流程更新或删除。
- 失败、拒绝和越权尝试也应按安全策略记录，但不得记录密码、Token、完整请求体或 SQL。
- retention、访问权限、防篡改和归档策略由独立 Audit Foundation PRP 决定。

## 20. Import / Export Foundation

- Excel、CSV 和飞书表格导入必须保存获准的 RAW 文件/快照、原始表头、`row_number`、file hash、uploader、batch/run 和 contract version。
- 导入支持 dry-run、validation errors、`import_runs`、幂等、partial failure policy 以及 rollback/void；具体状态由实现 PRP 批准。
- 导入不得直接写业务权威表，必须经过来源登记、mapping、字段标准化、DQ、权限、lineage 和发布边界。
- invalid/rejected/quarantined 行不能静默丢失，也不能因默认值伪装成功。
- 导出必须执行 page/action/data/field/export permission，记录 actor、筛选范围、字段、数量、request/run ID 和结果引用。
- 导出不得绕过店铺权限、字段权限、敏感字段脱敏、最大规模和审计；不得生成无限期公开 URL。
- 导入/导出文件留存、病毒/格式检查和对象存储策略由独立 PRP批准。

## 21. Legacy Comparison Foundation

旧系统仅用于对账比较和迁移验收，不得成为新系统生产运行时依赖。

未来逻辑实体预留：

```text
comparison_runs
comparison_results
```

结果类型至少预留：

```text
missing_in_new
missing_in_legacy
value_mismatch
count_mismatch
dq_difference
accepted_difference
```

- comparison run 必须记录两侧来源快照/版本、grain、字段、规则、范围、时间、control totals、执行人和结果。
- `accepted_difference` 必须有负责人/授权人员、原因和证据，不得等同“忽略”。
- 比较结果不能回写旧库，也不能自动覆盖新系统权威数据。
- 访问 legacy 数据仍需独立只读 PRP、最小权限、字段/表 allowlist、性能边界和负责人授权。
- 旧系统 comparison 是迁移验收工具；新系统 API 不得在请求时等待或 fallback 到 comparison/legacy 查询。

## 22. AI Data Usage Boundary

- AI 只能读取调用者获准的 read model、metric 和 published document；不得直接读取 RAW、secret、越权字段或未批准来源。
- AI 不得直接修改 Core、DIM/MASTER、FACT、read model、manual override、规则、费用或预警状态。
- 每次 AI 运行必须记录 input snapshot/reference、retrieval source、prompt/template version、model/version、权限/data scope、cost、operator、citation 和 review status。
- AI output 在人工确认前只能是 `candidate`/`suggestion`，不能作为权威事实或触发高风险动作。
- 人工采纳必须生成独立 action、before/after、reason、audit 和目标权限校验。
- 文档检索必须在检索前执行 ACL；Draft、撤回或用户不可见的文档不能作为正式依据。
- 每个 AI use case 需要独立 PRP、purpose、模型白名单、预算、保留、评估和 prompt-injection 防护。

## 23. Environment / Deployment Boundary

环境固定为 `local`、`dev`、`staging`、`production`；每个未来 PRP 必须声明该环境是否允许真实来源、通知、同步和写入。

- local/CI 默认只能使用 synthetic fixture/fake，不得因缺少配置而误连真实外部平台或生产数据库。
- dev/staging 需要独立凭据、数据隔离和显式开关；不得复用 production credential。
- production Scheduler 只能一个实例；Worker 可以多个实例并必须保证任务幂等。
- secret 只存在于环境变量或获批密钥管理系统；Git、文档、日志、测试和前端不得包含真实值。
- 部署前必须验证 migration、worker/scheduler 版本兼容、回滚、告警、限流和停机边界。
- 本 PRP 不批准部署、环境配置修改、服务重启、真实连接或通知发送。

## 24. Explicitly Not Implemented

本文明确不实现：

- PostgreSQL 数据库、schema、表、索引、SQLAlchemy model 或 Alembic migration；
- 数据库/Redis/Celery/object storage 配置或连接；
- 同步、定时、补数、重试或 legacy comparison 任务；
- 领星、Walmart、飞书、企业微信或其他真实外部调用；
- 飞书/企业微信群真实通知；
- 前端页面或既有前端修改；
- 产品 API、利润公式、库存/补货/广告计算、佣金或费用计算；
- Source Registry、RAW、Core、DIM/FACT、MART/read model 的物理实现；
- 字段监控、Alert、Audit、Import/Export 或 AI 运行；
- 旧系统修改、复制、执行、迁移或运行时读取；
- 生产配置、密钥、CI、部署或服务操作。

不得用本文中的实体名称或阶段列表声称能力已经 `implemented`。

## 25. Future Implementation Phases

下列每项都是独立候选任务，不构成连续执行授权，顺序仍需负责人逐项确认：

1. 项目决策与 legacy runtime 文档对齐（docs-only prerequisite）。
2. Data Layer implementation。
3. Source Registry + RAW Storage implementation。
4. Sync Control implementation。
5. Feishu Notification implementation。
6. Field Watch + Alert implementation。
7. First Lingxing endpoint Source Decision and ingestion。
8. Cleaning / Standardization implementation。
9. Product Core Data Model。
10. Product Read Model implementation（仅在查询需求证明必要时）。
11. Product API reading the new-system DB/read model。
12. Frontend pages connecting approved APIs。
13. Legacy comparison reports。
14. Business Rules / Metrics implementation；在任何指标 read model/API 前完成对应规则。
15. Commission / Fee Rules implementation。
16. Import / Export implementation。
17. AI Data Usage implementation。

每个阶段必须：

- 从当时最新且干净的 `main` 创建独立分支；
- 有单一主执行角色、精确 allowlist、禁止范围、Source Decision/PRP 前置和回滚边界；
- 不把多个阶段合并为超级 PR；
- 对数据库、外部 API、真实通知、部署或生产访问取得单独负责人授权；
- 由工程师实现与测试，架构师只读复审，负责人本人执行 git add、commit、push、PR 和 merge。

后续 PRP 可按精确任务分配 `engineering-backend-architect`、`engineering-minimal-change-engineer`、`engineering-technical-writer`、`testing-api-tester`、`testing-evidence-collector`、`engineering-database-optimizer` 或 `engineering-database-reliability-engineer`。Agent Skill 只是工作模式，不产生数据库、外部 API、部署、文件或 Git 权限；高风险 Skill 仍需独立 PRP 和负责人授权。

### Phase gates

- Data Layer implementation 必须先解决第 3 节的规则入口冲突，并单独批准依赖、config、test DB 和 migration 边界。
- 任何 ingestion 必须先有 endpoint-level Source Decision、RAW policy、contract、credential boundary 和失败/重放策略。
- 任何 read model 必须先有已批准权威来源、grain、lineage、freshness、DQ、permission 和可重建策略。
- 任何财务、利润、费用、佣金、库存或广告能力必须由负责人专项确认。
- 任何前端 API 接入必须等待后端 contract、权限、data scope、错误和 freshness 行为获批。

## 26. Owner Approval Checklist

- [ ] 确认本文仍为 `Draft`，合并前不授权实现。
- [ ] 确认新系统 API 不再运行时读取 legacy MySQL。
- [ ] 确认旧产品 API PRP 的 `READ_LEGACY_TEMPORARILY` 路线不得继续实施。
- [ ] 确认需要独立 docs-only 任务对齐 D-003 和 legacy runtime 示例。
- [ ] 确认平台/店铺/账号/身份与 data scope 边界。
- [ ] 确认 PostgreSQL、SQLAlchemy、Alembic、Redis 和 Celery 固定技术栈，但本文不批准安装或配置。
- [ ] 确认 RAW、Source Registry、同步、read model、监控、Alert、通知、规则和审计均为 planned。
- [ ] 确认 Feishu Webhook Bot 为第一正式通知通道，`WECOM_GROUP_BOT` 仅为候选预留。
- [ ] 确认财务、利润、库存、广告、费用、佣金与历史重算需专项批准。
- [ ] 确认每个 Future Phase 必须独立 PRP、分支、PR、Review 和回滚。
- [ ] 确认负责人批准本文后，仍需逐项下发实施 Prompt；不得自动开始任何阶段。

## 27. PRP-Authoring Validation

本分支只允许新增本文件。Docs-only 任务不运行前后端测试，不安装依赖。

```bash
bash scripts/check-rule-pack.sh
git diff --check
git status --short --untracked-files=all
git diff --stat
```

如果 rule-pack 只因 git worktree 的 `.git` 文本指针路径命中禁用项目代号，应记录为已知本地误报，不得在本 PRP 中修改检查脚本。任何目标 PRP 正文中的真实规则命中必须先修正。
