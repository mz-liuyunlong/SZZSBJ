# Listing 计算记录 API（PR #277）

## 范围

本接口读取已有诊断运行及逐商品快照，不触发计算、同步或发布。诊断候选不等于正式评级。

`GET /api/listings/evaluation-runs/{run_id}/snapshots?limit=50&offset=0`

- 权限：`page:products:listing-management:view`。
- 数据范围：服务端限定当前用户可访问的 `source_account_ref`；不可访问或不存在的运行统一返回 404。
- `limit` 为 1–200，`offset` 不小于 0；`total` 仅统计可见账号的快照。
- 结果包含 Listing 标识、当前值、候选值、规则版本、证据错误码和发布状态。不返回 RAW、广告明细或其他账号的运行计数。
- 返回统一 `{success,data,error,meta,request_id}` 信封；`meta.source=scoped_diagnostic_snapshots`。
- 错误：401 未登录、403 无页面权限、404 运行不可见、422 参数无效。

页面“Listing 计算记录与 C/D 跟进”抽屉通过“逐商品”按钮分页读取本接口。刷新后仍由数据库快照恢复；接口读取不会写入 Listing 等级或生命周期。

## 审计与回退

本接口只读；无写入可回退。诊断运行与快照由原有批处理保留，无法凭本接口批准发布。生产启用正式评级、调度及历史回填仍需独立授权。

## 人工生命周期调整（本地实现，生产开关默认关闭）

人工调整复用 Listing 管理页面，不新建管理站点。所有响应使用
`{success,data,error,meta,request_id}`，OpenAPI 由对应 FastAPI route 生成。

| 接口 | 权限 | 用途 |
| --- | --- | --- |
| `GET /api/listings/lifecycle-adjustments?listing_id=<UUID>&limit=50&offset=0` | `page:products:listing-management:view` | 当前账号内的申请、审批与历史 |
| `POST /api/listings/lifecycle-adjustments` | `action:products:listing-management:request-lifecycle` | 申请调整 WFS Listing；请求体含 `listing_id`、`requested_stage`、`reason` 和二次确认文字 |
| `POST /api/listings/lifecycle-adjustments/{id}/decision` | `action:products:listing-management:approve-lifecycle` | 由**不同**授权用户批准或驳回；请求体含 `decision`、`note` 和二次确认文字 |

服务端始终重新检查账号数据权限、WFS、归档状态、稳定 Listing 身份和申请时的原阶段。
审批、Listing 写入与审计记录在同一事务内提交；并发修改导致 409，事务回滚。
批准记录保存原阶段、新阶段、原因、申请人和审批人及时间。需要修正时发起新的反向调整申请，
保留原审计记录，不直接删除历史。

生产 `LISTING_EVALUATION_PUBLISH_ENABLED` 默认为 false，写入接口返回 503。
该开关不能由本 PR 自行启用；数据库迁移 0073–0075、权限分配、隔离数据库验收及正式发布审批均须单独完成。

## 自动发布（本地实现，生产默认禁用）

已启用的每日诊断任务在同一规则版本下形成冻结快照。只有运行完整成功、快照没有缺失证据、
T-2 财务及广告完成事件、WFS 完成事件、归档状态和历史阶段来源均可核对时，发布器才在
Listing 独立的 SERIALIZABLE 事务里复算并对比候选值、原状态及稳定业务键。
任何不一致写入安全错误码，不覆盖 Listing。已批准人工阶段优先。
成功快照记录发布时刻和系统身份；C/D 跟进只由已发布快照生成。
此处的「自动发布」不是生产启用授权，也不代表旧历史日期可被回填。

## 人工全量诊断与发布撤回

| 接口 | 权限 | 行为 |
| --- | --- | --- |
| `POST /api/listings/evaluation-runs/manual` | `action:products:listing-management:calculate-all` | 需确认文字，账号范围必须覆盖全部 Listing；只排队后台诊断，不发布结果 |
| `GET /api/listings/evaluation-runs/manual` | 同上 | 读取本人最近 20 次请求、关联运行和安全错误码 |
| `POST /api/listings/evaluation-snapshots/{id}/revert` | `action:products:listing-management:revert-evaluation` | 需原因与确认文字；仅撤回最新且当前值未变的发布，保留原快照和撤回审计 |

人工诊断要求 `LISTING_EVALUATION_MANUAL_ENABLED=true`；默认关闭。后台重新核对账号全集、
请求有效期及全局互斥锁。手动批次不会被后续自动调度发布。撤回要求
`LISTING_EVALUATION_PUBLISH_ENABLED=true`；默认关闭。它仅恢复该次发布前的 Listing
等级与生命周期，后续发布或人工调整已发生时返回 409，不自动更改其他业务数据。

## C/D 提醒

`listing_evaluation.followup_tick` 默认关闭，需单独启用
`LISTING_EVALUATION_FOLLOWUP_NOTIFICATIONS_ENABLED` 及正式发布开关。
它仅向已有业务通知队列投递不含商品明细的当日去重提醒与逾期提示；
实际对外发送仍受业务通知独立开关与路由控制。未配置时间或无待办时不排队。
