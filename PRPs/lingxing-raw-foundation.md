# Lingxing RAW Foundation PRP

```text
Status: Approved
Owner Approval Required: Completed for Lingxing RAW Foundation implementation gate.
Implementation Allowed: Yes, but only for raw_lingxing_api + Lingxing readonly client + RAW writer, and only through a separate backend implementation prompt.
Main execution role after approval: Backend Engineer
```

## 1. 背景与目标

旧系统 lineage matrix 表明，多条领星链路已有 RAW 留痕，但店铺、部分仓库列表、内存型 PMC 和若干导入链缺少完整证据。新系统在任何标准化、DIM/FACT、读模型或业务发布前，必须先能安全保存真实领星业务响应到 L2 RAW。

RAW 是可回放、可审计的来源证据层，不是业务事实层，也不是前端或业务 API 的查询源。本 PRP 仅设计一个通用 Lingxing RAW Foundation；不声明任何真实接口已验证或已批准调用。

参考证据：

- `old-system/reports/database/LEGACY_LINGXING_API_LINEAGE_MATRIX.md`
- `docs/data-sources/legacy-lingxing-lineage-review.md`
- `docs/data-sources/legacy-lingxing-migration-priority.md`

## 2. Owner 决策已完成的 implementation gate

Owner 已于 2026-09-10 完成本 PRP 的实现门禁决策。批准仅覆盖独立后端实现 PR 中的 L2 RAW 表、readonly client shell、RAW writer/service/repository 和 synthetic/mock 测试，不批准真实领星调用、真实采样、生产数据库操作或部署。

### 2.1 精确 endpoint allowlist

后续代码只能支持以下 P0 endpoint；不得提供任意路径调用能力：

- `POST /basicOpen/multiplatform/walmart/list`
- `POST /basicOpen/platformStatisticsV2/saleStat/pageList`
- `POST /erp/sc/routing/data/local_inventory/batchGetProductInfo`
- `POST /pb/mp/shop/v2/getSellerList`
- `POST /basicOpen/multiplatform/profit/report/order`

### 2.2 已批准的实现边界

- store scope 不得硬编码。未来真实调用必须由运行参数显式传入 store allowlist；空 store allowlist 必须 fail closed。
- 默认 `page_size <= 3`，默认 `max_pages = 1`；full sync 默认禁止。
- 允许保存脱敏后的完整业务 `response_json`。request params/body 必须先脱敏；response 中出现 access token、refresh token、app secret、authorization、webhook、signature 等敏感字段时必须脱敏或拒绝保存。
- 认证响应中的明文 credential 不得保存。
- MVP 不实现自动删除；RAW 作为审计证据保留，archive/delete/retention 变更必须由后续 Owner 任务批准。本 PRP 不授权删除 RAW。
- RAW 默认拒绝读取，不新增前端或业务 API；预留 `lingxing_raw:write`、`lingxing_raw:read`，读取能力必须由后续独立 PRP/任务批准。
- `raw_hash` 只批准普通索引，不批准唯一约束；唯一约束需基于后续真实采样和重复写入策略另行批准。

### 2.3 仍需单独批准的运行边界

- 任何真实领星 API 调用或采样；
- 每次真实运行的 store allowlist、环境、次数和执行人；
- 生产数据库连接、production migration 或部署；
- RAW 读取接口、前端页面、导出、归档、删除或保留期变更；
- 全量同步、定时任务、历史回补或扩大 endpoint allowlist。

## 3. 范围

### 3.1 In scope（仅在后续独立实现任务获批后）

- 设计并实现 `raw_lingxing_api` L2 RAW 表、ORM model 和一个 Alembic migration。
- 设计单一 Lingxing readonly provider client shell，只支持第 2.1 节 endpoint allowlist；实现 PR 只使用 synthetic/mock HTTP，不真实调用领星。
- 设计 RAW repository、service 和 writer 边界。
- 保存成功和失败响应、分页信息、run/batch、trace 和审计元数据。
- 请求、响应、错误和日志写入前执行凭据脱敏。
- 为 hash、幂等、失败响应、分页和 payload 限制提供测试。
- 更新 Data Interface Registry、Backend Module Catalog、任务登记和 API/数据文档。

### 3.2 Explicitly out of scope

- 不写 L3 Standardized、L4 Canonical、L7 DIM、L8 FACT 或 L9 MART / READ MODEL。
- 不写或修改 `products`、`product_platform_listings`。
- 不接前端，不新增前端 RAW 查看页或业务接口。
- 不做全量同步、定时同步、历史回补或生产调度。
- 不实现销售、广告、库存、成本、退款、结算或利润计算。
- 不把旧系统表、接口或计算复制为新系统契约。
- 不调用未在 Owner allowlist 中的接口。
- 不保存认证响应中的明文 access credential。
- 不连接生产数据库、不执行生产 migration、不部署。

## 4. 数据分层与权威边界

| 项目                  | 规则                                                                  |
| --------------------- | --------------------------------------------------------------------- |
| Source                | Lingxing OpenAPI，仅限后续批准 endpoint                               |
| Target layer          | L2 RAW / Bronze                                                       |
| Authority             | 来源证据；不是新系统业务权威                                          |
| Writer                | Lingxing RAW service/writer；route、frontend、repository 外部不得直写 |
| Reader                | 仅经批准的 integration/audit/replay 服务；默认拒绝                    |
| Downstream            | 后续独立 PRP 的 L3/L7/L8，必须保存 `source_raw_id`                    |
| Frontend/business API | 禁止直接查询 RAW                                                      |
| Legacy                | `old-system/**` 仅作证据，不是 runtime dependency                     |

## 5. 组件职责

| 组件                     | 必须负责                                                                            | 明确禁止                                                       |
| ------------------------ | ----------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Lingxing readonly client | endpoint allowlist、认证引用、timeout、限流、重试/backoff、分页、transport 错误映射 | 直接写数据库、返回 secret、被前端/route 直接调用、调用任意路径 |
| RAW service              | 调用 client、建立 run/batch/trace、脱敏、生成 hash、编排每页写入                    | 业务字段标准化、DIM/FACT 写入、利润或费用计算                  |
| RAW writer               | 将已脱敏 envelope 写入 repository；成功/失败均留痕                                  | 直接 commit、权限判断、外部 API 调用                           |
| RAW repository           | 只持久化合法 RAW record；flush 由 service 事务边界管理                              | commit、外部 API、权限判断、legacy MySQL 访问                  |

## 6. 建议表结构

后续独立 implementation Prompt 必须遵守本节，精确文件 allowlist 不得扩大这里的数据边界。所有 JSON 字段都是脱敏后的持久化值。

| 字段                  | 建议类型                           | Nullable | 语义与限制                                              |
| --------------------- | ---------------------------------- | -------: | ------------------------------------------------------- |
| `id`                  | bigint identity 或项目统一 ID 类型 |       No | 新系统 RAW 记录 ID                                      |
| `source_system`       | varchar                            |       No | 固定受控值 `lingxing`                                   |
| `api_path`            | text                               |       No | 不含 host、query credential 或签名                      |
| `request_method`      | varchar(10)                        |       No | 获批接口当前预期 POST；不可据此批准全部 POST 路径       |
| `request_params_json` | jsonb                              |      Yes | 经过 recursive redaction 的请求参数                     |
| `request_body_json`   | jsonb                              |      Yes | 经过 recursive redaction 的请求 body                    |
| `response_json`       | jsonb                              |      Yes | 业务响应的脱敏副本；认证 credential 必须删除或掩码      |
| `response_code`       | integer                            |      Yes | HTTP/transport 响应码                                   |
| `is_success`          | boolean                            |       No | transport/provider 判定，不能代表业务发布成功           |
| `error_code`          | text                               |      Yes | 经脱敏的 provider/transport 错误码                      |
| `error_message`       | text                               |      Yes | 经脱敏、长度受限的安全错误信息                          |
| `data_date`           | date                               |      Yes | 仅在 endpoint 有明确业务日期时填写；不得用拉取日猜测    |
| `pulled_at`           | timestamptz                        |       No | UTC 拉取完成/响应接收时间                               |
| `raw_hash`            | char(64)                           |       No | 对规范化且脱敏后的 hash 输入计算 SHA-256                |
| `page_no`             | integer                            |      Yes | 每页独立记录；非分页接口为空                            |
| `page_size`           | integer                            |      Yes | 实际请求页大小                                          |
| `store_id`            | text                               |      Yes | 来源侧标识，保留字符串语义                              |
| `store_name`          | text                               |      Yes | 来源 metadata/业务响应值，不是权威店铺名称              |
| `object_type`         | text                               |       No | endpoint/object 的受控候选名称                          |
| `trace_id`            | text 或项目统一 trace 类型         |       No | 请求与错误追踪，不包含 credential                       |
| `run_id`              | text 或项目统一 run 类型           |       No | 一次受控执行标识                                        |
| `batch_id`            | text 或项目统一 batch 类型         |       No | 一组分页/店铺采集标识                                   |
| `attempt_no`          | integer                            |       No | 有界重试次数，从 1 开始                                 |
| `extra_json`          | jsonb                              |      Yes | 非 credential envelope 元数据；禁止绕过正式列和脱敏规则 |
| `created_at`          | timestamptz                        |       No | 新系统 UTC 入库时间                                     |

候选索引仅供实现评估：

- `(api_path, data_date, pulled_at)`；
- `(run_id, batch_id, page_no)`；
- `raw_hash` 普通索引；
- `(store_id, data_date)`，仅在获批查询确有需要时建立。

不得为“以后可能查询”预建更多索引。

## 7. 安全与脱敏

### 7.1 写入前强制处理

- 对 params、body、response、error 和 `extra_json` 做递归 key/value 脱敏。
- 至少拒绝或清除以下语义字段：app secret、access/refresh credential、authorization、cookie、signature、webhook、password、private key 及大小写/分隔符变体。
- URL 只保存 `api_path`，不得保存含 credential 的完整 URL 或 query string。
- 日志只记录 trace/run/batch、endpoint ID、页码、状态和计数，不记录完整 payload/header。
- hash 必须在脱敏后计算，避免 credential 通过 hash input、异常或 debug 路径泄漏。
- 认证/token 类 endpoint 的响应不得进入本 RAW 表；credential 只由后续批准的 Secret Storage 边界管理。

### 7.2 Secret boundary

- 代码、PRP、registry、测试和日志只记录 `secret_ref`，不记录真实值。
- 本地/部署凭据由 Owner 在受控环境注入；AI 不读取 `.env` 或要求粘贴 secret。
- 缺少 secret/ref 时 fail closed，不回退到旧系统配置或默认账号。

## 8. Hash 与幂等规则

推荐 hash 输入：

```text
api_path
+ request_method
+ canonical_json(sanitized_request_params)
+ canonical_json(sanitized_request_body)
+ canonical_json(sanitized_response_payload)
+ normalized_data_date_or_null
```

- JSON canonicalization 必须固定 key 顺序和编码，数组顺序按来源原样保留。
- `raw_hash` 用于内容比对、重复检测和回放核验，不自动表示同一次请求。
- **本次只批准普通索引，不批准唯一约束**：RAW 是 append-only 执行证据，相同内容在不同 run、重试或时间再次获得仍可能需要保留；唯一约束会丢失执行历史。
- 若 Owner 后续要求物理去重，必须说明失败重试、分页、run/batch 审计和 collision 处理，并通过独立 schema review；不得只对 `raw_hash` 建全局唯一约束。
- writer 必须保证单页写入原子性；重复处理规则不得通过覆盖旧 RAW 实现。

## 9. 成功、失败与错误响应

- API 失败也必须写 RAW envelope，保存 `response_code`、`error_code`、安全 `error_message`、attempt、run/batch/page 和时间。
- HTTP 成功不等于 provider 业务成功；`is_success` 判定规则必须按 endpoint contract 测试。
- 外部调用成功不等于 RAW 写入成功，更不等于清洗、DQ 或发布成功。
- 错误 payload 仍需脱敏；无法确认安全时只存安全摘要和 hash，不存原文。
- 重试必须有上限和 backoff；最终失败不得静默吞掉或标记成功。

## 10. 分页和规模边界

- 每页响应独立一条或一个受控 envelope RAW，保存相同 `run_id` / `batch_id` 和各自 `page_no` / `page_size`。
- 页码必须单调、可核对；缺页、重复页、空页和 provider total 变化必须记录为执行结果。
- client 默认 `page_size <= 3`、`max_pages = 1`；不得通过调用方绕过上限。
- store scope 不得硬编码；未来真实调用必须显式传入非空 store allowlist，否则拒绝执行。
- 全量同步默认禁止。实现 PR 只验证第 2.1 节 endpoint allowlist 和分页边界，不授权真实调用。
- payload 超过批准大小时停止，不截断后冒充完整 RAW；需记录安全错误并请求新决策。
- 业务 API route 不得实时触发批量外部拉取。

## 11. 后续结构化回指

- 后续 L3/L7/L8 记录必须保留不可变 `source_raw_id` 或经批准的多源 lineage edge。
- 一个结构化记录来自多条 RAW 时，必须通过 lineage 表/关系记录全部来源，不得只保留最后一条。
- 标准化规则必须可版本化并重放；RAW 不因下游修正规则而被覆盖。
- RAW 不直接写 `products`、`product_platform_listings` 或任何权威表。

## 12. 权限、审计与保留

- RAW 默认高敏、默认不可见、default deny。
- 预留 `lingxing_raw:write` 和 `lingxing_raw:read`；本次实现只可使用 write 边界，不实现 read API、前端读取或导出。
- 未来读取必须另行批准，并定义 data scope、字段白名单、原因和审计记录。
- 不提供通用“下载全部 JSON”能力。
- MVP 不实现自动删除；RAW 作为审计证据保留，删除、归档和 retention 变更只能由后续 Owner 批准的任务决定。
- 每次写入可追踪至 endpoint、run、batch、trace、时间、代码版本和执行结果。

## 13. 实现文件边界（由独立 backend implementation Prompt 精确限定）

后续实现 Prompt 才可列出精确文件。预期领域仅包括：

- 一个 Alembic migration 和 RAW ORM model；
- Lingxing integration client；
- RAW repository/service/writer；
- synthetic/mock HTTP tests；
- 必要 registry/catalog/docs 更新。

不得因为本段存在就创建文件。实现 Prompt 必须给出 exact allowlist，并从最新干净 `main` 建立独立 worktree/branch/PR。

## 14. 测试计划（后续实现阶段）

- 全部 HTTP 使用 synthetic fixture / mock；CI 不调用真实领星。
- 验证递归脱敏覆盖 params、body、response、error、extra 和大小写变体。
- 验证 secret 不进入日志、异常文本、数据库 record 或 hash input fixture。
- 验证 canonical JSON 和 `raw_hash` 稳定性。
- 验证成功响应、业务失败、HTTP 失败、timeout 和最终重试失败均正确留痕。
- 验证每页独立 RAW、run/batch 关联、重复页和页数上限。
- 验证 repository 不 commit、不调用外部 API、不写结构化表。
- 验证 RAW 不写 DIM/FACT、`products` 或 `product_platform_listings`。
- 数据库测试只可使用明确批准的隔离 test database；无授权时如实 skip。

## 15. 验收标准

本次 docs-only approval patch：

- [x] PRP 状态和 Owner Approval Record 已更新为 `Approved`。
- [x] endpoint、store/page、payload、retention、permission 和 `raw_hash` 决策已限定。
- [x] Task Registry 已记录规划 PR #43 合并事实和独立 implementation task。
- [x] Data Interface Registry 仅更新为 `approved`，明确尚未 `implemented`。
- [x] 没有 backend/frontend/migration/SQL 或外部调用。
- [x] 没有读取或提交 secret。

后续实现 PR（仅在另行批准后）：

- [ ] migration/model/repository/service/client/writer 符合精确 allowlist。
- [ ] 仅 mock HTTP 测试通过。
- [ ] 脱敏、hash、失败、分页和禁止结构化写入测试通过。
- [ ] registry/catalog/docs 与真实实现状态一致。
- [ ] 未执行生产连接、真实 API、全量同步或部署。

## 16. 停止条件

出现以下任一情况必须停止并请求 Owner：

- 需要调用第 2.1 节以外的 endpoint，或需要硬编码 store scope；
- 需要在未获独立运行授权时真实调用领星，或真实运行参数没有非空 store allowlist；
- 需要 `page_size > 3`、`max_pages > 1`、full sync、定时任务或历史回补；
- 需要读取 `.env`、真实 credential 或在对话/日志中回显 secret；
- response 无法在保持业务证据的同时安全脱敏；
- 需要保存 token/认证响应；
- 需要写 DIM/FACT/Core/read model 或连接前端；
- 需要任何 production execution；
- 需要修改 `old-system/**` 或复制旧实现；
- payload 无法安全脱敏，或需要实现 RAW 读取、导出、删除、归档或 retention 变更；
- 需要连接生产数据库、执行 production migration 或部署。

## 17. 回滚边界

当前 docs-only approval patch 可通过回滚 PRP 审批字段、implementation task、registry `approved` 状态和模块候选登记独立撤销，不影响 PR #43 已合并的证据文档，也不影响代码或数据库。

后续实现 PR 的回滚必须在实施前单独设计：停止 client/writer、保留已写 RAW 作为审计证据、禁止自动删除数据，并为 migration 提供在隔离环境验证过的 downgrade/forward-fix 方案。该段不授权执行回滚或删除 RAW。

## 18. Owner Approval Record

```text
Approved by: Project Owner
Approved date: 2026-09-10
Approval type: RAW Foundation implementation gate
Approval scope:
- implement raw_lingxing_api L2 RAW table
- implement Lingxing readonly client shell
- implement RAW writer/service/repository
- implement redaction/hash/pagination/failure-response tests
- no DIM/FACT/Core/read model/frontend/full sync
- no real Lingxing API call in implementation PR
- no .env or secret read/output
```

本 PRP 已完成实现门禁审批，但仍必须由 Owner 下发独立 backend implementation Prompt 后才能开始；本审批不授权真实 API、真实采样、生产 migration、部署或 RAW 读取能力。
