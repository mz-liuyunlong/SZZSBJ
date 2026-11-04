# PRP：WFS 待发货打包单 V2 本地后端、前端及联调

日期：2026-10-29。状态：APPROVED_FOR_IMPLEMENTATION（本地切片）。

这是在完整 V2 目标中的第一实施切片，不将本地验证称为真实 Walmart 完成。主执行角色：后端工程师，兼顾本页面前端及联调。2026-10-29，在展示本文并解释新表和页面创建入口后，用户明确指令“执行代码开发把”。批准范围为本文本地实施，不包括真实平台或生产执行。原整行草稿 PRP 的历史批准不被覆盖。

## 1 Goal / Why

在 `/pmc/wfs/pending-packing` 将选装箱行改为按发货箱数、计划票数分配；后端真实持久化、恢复并隔离账号权限，前端直接消费本系统 API。移除本页面创建审批表达，不要求 OWS，不强制探测。先后端验收，再前端，最后隔离联调。

## 2 Scope

包含本页面列表/统计、分箱预览、创建操作/票/占用/事件、结果查询、可选探测的端口与测试、箱唛状态、页面交互、API/SOP/测试及登记。沿用当前 develop_backup；保留现存修改，不提交推送。

不包含其他三个 Tab 实现、真实平台写入、领星同步、历史草稿执行或释放、已创建货件取消、库存或国内仓规则重构、生产及部署、公共 CI/启动脚本/调度修改。外部正式适配器为后续契约闭环，不能用本地测试实现开启正式能力。

## 3 Data Source

引用 `docs/data-sources/decisions/pmc-wfs-pending-packing-v2-local-decision.md`：READY_FOR_PRP。国内仓/WFS 自有事务事实，身份复用已治理模型。列表为受范围约束投影，禁止 RAW、旧库或页面 mock 兜底。完整 V2 的外部未决项仍见总决策。

## 4 Business Contract

1. 单次选择一个已完成、未作废 PK。OWS 不进入必填 schema 或资格判定。已批准国内仓少装/多装处理不改变；复核装箱行件数之和等于 BoxSet.total_qty。
2. 输入本次箱数及各票箱数，每票正整数、总和一致、不能超可用量。拆票数由列表长度校验，不固定为箱规组数。
3. 按 line_no 再行内序号分配剩余完整箱。主箱、混合箱规及尾箱用真实件数计算。返回每票箱范围、件数、尺寸及重量；用户确认可核对的组成。不得平均分摊件数，不跨 PK 合票。
4. 原 pending 草稿占用继续按整行处理，不迁移、不发平台、不释放。新分配按实物箱身份唯一占用；国内仓现有改箱/身份变更守卫须能识别新占用。
5. 预览只读。确认提交在事务中重新校验版本、权限及箱集合；本地多票全成功或全失败。账号内幂等键相同内容返回原操作，不同内容 409，重放仍校验当前权限。
6. 未配置可执行集成时提交明确拒绝，无假任务成功、无永久占用。模拟平台仅可通过隔离测试依赖注入，不加生产可选 mock 开关。
7. 执行状态 QUEUED/RUNNING/SUCCEEDED/FAILED/UNKNOWN/PARTIAL；箱唛状态独立。执行未知不释放箱子、不自动再次 POST；回查确认后转换。箱唛失败只补取。
8. 一个计划票可关联多个实际平台货件，分别记录计划箱数和实际返回数。拿不到可核验实际 ID 不记成功。混箱平台报文无法准确表达时明确阻断真实提交，不能静默拆票或抹平箱规。
9. 提交前取消仅关闭界面。提交后关闭页面不取消任务，重新打开可查询结果。无创建审批、批准或驳回状态。

## 5 API / Fields

复用 `/api/pmc/wfs/pending-packing`，统一 envelope、response_model、OpenAPI、错误码和 request_id。

| 接口 | 请求/响应 |
|---|---|
| GET orders / summary / orders/{id} | 延续查询；增加总箱数、占用箱数、可用箱数、安排状态和最近操作引用；列表与统计同范围 |
| POST allocation-preview | order_id、order_version、box_version、shipping_boxes、shipment_count、shipment_boxes；输出各票稳定箱范围及件数、版本、preview_hash；不写数据 |
| POST creation-operations | 上述输入及预览哈希、退货地址、预计到仓时间、ITS、idempotency_key；由服务端读取店铺/商品身份；返回 operation_id 及逐票状态 |
| GET creation-operations | PK/状态/分页过滤，只读持久记录，可从新浏览器会话找回 |
| GET creation-operations/{id} | 来源/确认快照、逐票结果、实际货件、错误及箱唛状态 |
| POST optional-previews | 相同商品/箱分配/地址快照；不占用、不创建；结果关联输入哈希 |
| POST creation-operations/{id}/reconcile | 只请求核实，禁止直接重发创建 |
| POST shipments/{id}/labels/retry | 仅补取标签；不重建货件 |
| GET shipments/{id}/labels | 有权限的文件响应，不泄露凭据或任意远程 URL |

所有路径为候选施工契约，批准后纳入类型化 schema。错误场景：权限 403、不可见 404、版本/占用/幂等冲突 409、非法数量 422、执行能力未启用 503。业务接口不得返回测试模拟货件。

## 6 Persistence / Execution

候选新增 WFS operation、ticket、box hold、append-only event 四类实体；独立于原 pending-only 草稿模型。箱子身份 `(box_line_id,box_version,box_ordinal)`，有效占用唯一；订单/装箱外键 RESTRICT。操作保存确认快照、请求摘要、操作者、UTC 时间及版本。平台实际结果放逐票结果快照/明确字段，不与本地请求混用。

锁顺序沿用国内仓账号/仓库锁和 PK 行锁；旧 drafts 提交与新提交必须共享占用检查，禁止并发从旧端点绕过。新增表存在性不能以数据库异常当无占用。

复用现有 Celery，业务记录先持久化、提交后派发；派发失败保留 QUEUED，可按同一 operation_id 受控恢复。worker 原子领取，重复消息不重复写平台。RUNNING 崩溃恢复按未知处理，不盲目重试。不得增加公共定时任务或第二套任务平台。

迁移仅新增本任务 Alembic 文件，先核对当前 head，禁止改历史版本或现有库结构。隔离测试库可执行本任务迁移验证；降级遇业务记录时拒绝破坏性删除，代码回滚保留事实及审计。

## 7 Permissions

复用 page:pmc:wfs:view；新动作候选为 action:pmc:wfs-pending-packing:create、preview、reconcile、label-retry。旧 draft-submit 不自动获得创建权限。仅登记定义，不给既有角色/用户赋权。所有列表、统计、操作、票、箱唛校验来源账号及店铺范围。地址只在有权详情展示。操作者来自登录主体。

## 8 Component Reuse Plan

保留 PageShell/MainLayout/WfsFrame、ProTable、ManagementStatCards、CommittedSearch、ResetButton、WalmartItemLink 和既有 HTTP/查询层。不引入新框架或重复页面。创建窗口使用 Ant Design/ProComponents，按箱数→分配→发货信息→确认→结果组织。展开装箱仅核对，无选择装箱行入口。

创建表单无 OWS 必填项、审批步骤或强制探测。确认按钮受新动作权限及执行能力控制。未启用外部能力时说明原因，不用“草稿已保存”冒充“货件创建成功”。错误保留输入，冲突要求刷新，未知结果引导核实。详情和查询入口可恢复持久结果。

## 9 Allowlist / Deliverables

允许 pmc_wfs 模块及专属测试、待发货前端/API/types/queries/弹窗/测试、必要的既有国内仓占用守卫、权限定义、模型登记、本任务新增迁移、API 文档和数据中心本接口条目、SOP/帮助、registry 精确新增行、任务专属计划与 handoff。

不覆盖原 staged 修改，不修改其他任务登记；每次修改前核对现有内容。其他 WFS 页面、公共配置不顺手整理。后续结构/依赖问题若必须扩大范围，应先列出具体差异。

## 10 Validation Gates

- 后端：分箱纯函数及 schema 测试；隔离 PostgreSQL 上事务、并发、幂等、旧占用兼容、权限及状态恢复；FastAPI 契约测试。
- 测试数据不使用 szzsbj_dev/public。现有 test_pending.py fixture 会读取该库，不能未经调整直接运行。新增专属隔离 fixture，只用合成数据和明确测试 URL，不读 .env。
- 前端：Vitest 验证 30 箱发 20 拆 12+8、混箱尾箱、缺 OWS、不探测、无审批、取消及恢复；ESLint、tsc、build。
- Playwright：真实本地前端→真实本地 FastAPI→隔离数据库；仅平台端模拟。禁止把浏览器 route mock 测试说成前后端数据联调。
- 后端命令按环境使用 uv run ruff check 目标文件、uv run pytest 专属测试；前端 npm exec tsc -- -b、npm run build、npm run test -- --run 目标文件、npm run test:e2e -- 专属文件。不运行公共 CI 修改或生产依赖测试。
- 第三方具体实现按锁定版本查官方文档；本 PRP 不引入外部 Skill 或子 Agent。

## 11 Acceptance / Handoff

必测：缺 OWS 能预览及受控测试创建；不探测直接创建；数量守恒；混箱真实件数；并发仅一次占用；旧草稿不重发；未知结果不重复写；箱唛失败仅补取；权限变更后幂等重放受限；关闭页面仍可查；失败无 mock 兜底。

API、SOP、帮助、registry、来源及测试报告齐全后只声明本地切片验收结果；外部适配器、真实 Walmart 写入及整个页面 ready 必须等完整 V2 能力完成。交接列出实际测试与未运行项。

## 12 Owner Approval

已确认：用户以“执行代码开发把”批准本 PRP 的本地实施范围、必要新模型/迁移文件及隔离测试写入；不授权现有业务库 DDL、生产或真实平台调用。批准后按本文件顺序实施，不再次询问已明确的 OWS、审批和探测产品规则。

## 13 用户后续确认与最终实施口径

用户后续明确“先不要手动审批，程序自动审批”；程序在确认提交的同一事务记录自动审批检查及事件，之后执行平台创建。页面没有人工审批动作。沿用旧业务同账号、同店铺、同测试标记多 PK 合并，单 PK 也可拆多票；此前单 PK 限制不再适用。OWS 不必填、探测可选不变。
最终接口按 docs/api/pmc-wfs-pending-packing-api.md 的 V2 补充执行，历史候选路径以实际路由为准。现有其他改动保留，本次不修改公共 CI、启动脚本、调度或生产。

## 14 本地完整迁移补充授权与执行

2026-10-29用户明确允许在本地开发库执行完整迁移链。已备份并由Alembic升级127.0.0.1:55432/szzsbj_dev至20261029_0068_wfs_creation，包含已列明前置迁移；详情和验证见docs/delivery/pmc-wfs-pending-packing-v2-handoff.md。本补充覆盖此前“不迁移本地业务库”的限制，仅限此目标和此链，不授权生产/外部写入。
