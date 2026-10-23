# 国内仓六种业务状态后端方案（候选）

2026-10-20；状态：**方案待负责人确认，未批准建表或实施同步**。用户明确截图六项，并确认“没有，按交接文档补做后端数据方案”。本次仅形成方案；店铺/当前产品负责人筛选为独立已授权增量。继续 dev，不提交推送，不部署，不写生产，不调用领星写接口。

## 1. 已确认的证据与缺口

- 业务依据：用户提供《PMC交接文档_20261019.html》国内仓章节；只读参考旧项目 `features/pmc-domestic-warehouse/rules/business-rules.md` §3、4、5 和 `context/decisions.md` 2026-09-18 v3、09-29续、10-13/14。文档内容是来源证据，不自动授权其中部署、写入或历史数据规则。
- 新系统现有入库 MART 是 IB×SKU×店铺，当前只发布入库和批次余额，trace 的 outbound_status=unknown。现有近30天流水不能证明历史发出量完整。旧 Demo 用SKU+日期+数量猜OWS、全SKU跨店 FIFO、零余额视为已发出等逻辑不可直接移植。
- SZZSBJ 打包页只有结构，没有本系统PK主表、装箱完成事件、PK与IB分配、SP发货事实或批次出库分摊事实。不能把备货单存在/默认箱规存在作为打包完成。
- 仓库仅惠州16168，账号必须继承可信scope。主粒度保持现有入库口径；不顺手改变店铺归属或已发布版本。

## 2. 六项定义与计算顺序

`status` 是筛选视图；基础阶段与超时标记分别存储，超时不覆盖阶段。

| 下拉值 | 显示名称 | 证据/规则 | 当前能否认定 |
|---|---|---|---|
| in_stock | 在库 | 余额>0 且在具备完整打包覆盖时无有效已批准打包或完成发出；否则状态未知，不能仅凭余额降级为在库 | 不可，缺打包覆盖 |
| approved | 待打包（领星打包单已建） | 本系统审批有效、PK与IB×SKU×store明确分配、OWS建单或双向关联已核对；尚未有效pack_complete | 不可，缺PK/审批/关联 |
| packed | 已打包待发 | 本系统装箱数据验证通过 AND 仓库pack_complete有效，尚未达到发出阈值；默认箱规/OWS30/40不充分 | 不可，缺装箱完成事实 |
| overdue | 超时未发 | 到仓后>7自然日 AND 当前余额>0 AND 有可信可发量分母 AND 实际净发出/可发量<90%，排除shipped/other_out；未知分母返回overdue=null | 不可，缺可发量和发出事实 |
| shipped | 已发出 | 有6501（旧4107需核实）净出库和未作废SP事实，可靠归属到本行；净发出达到可发量90%；作废/回冲应撤销相应分配 | 不可，缺发货及归属 |
| other_out | 非发货出库 | 有4201/4106等经核实事件、明确关联本行，发货不构成主去向且非发货出库使有效余额清零；部分other_out保留事件，不强行结束行 | 不可，缺事件到IB关联 |

候选基础阶段优先级：可信非发货出清且无有效发出→other_out；可信发出率≥90%→shipped；有效pack_complete→packed；有效审批及OWS→approved；证据覆盖完整且剩余库存>0→in_stock；其余unknown。混合发出/非发货出库、同一IB多个PK部分完成时，必须输出按阶段数量与quality_issue，不能靠单个标签掩盖冲突。overdue独立叠加；多值同字段OR，不同筛选AND。文档中“已完成装箱/发出数量”与“发货完成率”有歧义，建议超时只认实际净发出，装箱不算发出，需确认。

## 3. 数据源决策候选（实现前须补成READY_FOR_PRP）

| 数据集 | 分类 | 权威源/写入方 | 线上API读取层 |
|---|---|---|---|
| 入库/批次 | REBUILD_SYNC，复用 | 已成功W1/W3，入库发布器 | 当前MART |
| 负责人/店铺 | REBUILD_SYNC，复用 | 产品当前资料/店铺DIM | 现有DWD/DIM |
| 备货单OWS快照 | REBUILD_SYNC | listInbound/详情；领星只读集成，完整分页/仓库过滤/历史保留 | DWD/MART，不直查ODS |
| 本系统PK审批与装箱 | NEW_SYSTEM_OWNED | 正式打包/审批服务，审计事件驱动；没有则此阶段先建设 | OPS事实+发布后的状态MART |
| 发货单SP/作废/发货时间 | NEED_OWNER_DECISION | 交接指定旧版 queryShippingListPage，但新项目 API_CONTRACT_SOURCE_MAP.md 对 LX-C99E2D00C76D 标 **DO_NOT_USE**；必须先查明禁用原因、有效替代和合法只读契约，不能调用探测来绕过 | DWD/MART |
| 出库归属 | NEED_OWNER_DECISION | 优先源batch_no/IB或显式PK分配；无直接标识时不猜。本期M1禁止跨店FIFO，旧文档却使用全SKU FIFO，须单独确认受限估算是否接受 | FACT分配+状态MART |
| 可发量/质量分母 | NEED_OWNER_DECISION | 历史QC或可信批次级原始到货和不良证据；当前bad_num是现存不良不一定是历史不良，不能直接当历史分母 | 经审核FACT |

总体状态 **BLOCKED_BY_OWNER_DECISION**（仅状态建设）。不采用旧库运行时回退、不读旧Demo JSON作为生产事实、不人工SQL填状态。

## 4. 逐表改动候选

所有新表须另增Alembic revision，按实施时实际head接续，**不改已应用0048/0049**，不预留可能冲突的0050编号。以下是设计名，尚不存在、未建表。

| 表 | 动作/层 | 粒度/关键字段/约束 | 写入方/范围 |
|---|---|---|---|
| ods_lingxing_domestic_warehouse_statements | 复用，优先无DDL | 当前完整原始payload+statement_id/run/账号/仓库；若缺source batch/type/text/remark则优先从已有payload标准化，必须先核字段 | W3现有受控同步；30天初始授权不自动扩大 |
| ods_lingxing_domestic_batches | 复用，不改 | 当前完整快照，余额和批次；不推断历史发出 | W1既有同步 |
| ods_lingxing_domestic_stock_orders | 候选新增ODS | run+账号+OWS+源行号唯一；source status、create/audit/update、warehouse、sid、SKU、remark及RAW引用，取消/删除留历史 | 只读OWS handler，不写领星 |
| ods_lingxing_domestic_shipping_orders | 候选新增ODS | run+账号+SP+源行号唯一；原状态、delivery_time、仓库、明细和RAW引用；币种/费用只留原始证据，本期不计算 | 等有效SP接口契约获批后同步 |
| dwd_domestic_outbound_events | 候选新增标准化事实 | 账号+仓库+statement_id唯一，kind、signed_qty、SP/OB、batch_no（若源支持）、event_at UTC、原时间、作废/回冲引用 | 成功ODS标准化发布，保留净值证据，不对负数取绝对值 |
| dwd_domestic_shipping_orders | 候选新增DWD | 账号+SP+SKU+店铺/源行稳定键；有效/作废、实际发货时间、源版本；名称不作键 | SP成功批次标准化 |
| ops_domestic_packing_orders | 候选新增业务表 | PK全局唯一、不复用，账号/仓库、SKU、ItemID、GTIN、数量、审批状态、有效版本、source OWS关系；并发version约束 | 正式打包业务Service，不允许同步伪造审批 |
| ops_domestic_packing_allocations | 候选新增关联表 | PK×IB×SKU×store；allocated_qty>0，累计不超可信可用量，未知店铺不可跨店分配 | 正式审批/调整动作，事务锁与审计 |
| ops_domestic_packing_boxes | 候选新增业务表 | PK×box序号；箱数、每箱数量、长宽高/重量及单位、录入版本；数量/箱规合法；装箱段合计匹配PK量 | 仓库填报Service |
| evt_domestic_packing_events | 候选新增EVENT | append-only event_id、PK、approve/reject/link/pack_complete/void、from/to、actor/time/version/idempotency_key/reason；唯一幂等键 | 动作事务内追加，历史不覆盖 |
| fact_domestic_outbound_allocations | 候选新增FACT | 事件×IB×SKU×store，allocated_qty、method=source_direct/explicit/approved_fifo、rule_version、quality、源run；约束净分配不超净事件量和可分量 | 确定性投影器；不越账号/仓库/店铺；FIFO若获批必须标估算、不得冒充来源关联 |
| gov_domestic_board_publications | 复用，候选新增状态来源元数据 | 记录status rule_version、各来源run及覆盖、packing事件水位、quality；优先已有quality_report扩展，不改当前指针规则 | 完整验证后原子发布；失败保留旧版本 |
| mart_domestic_inbound_batch_board | 复用，候选新增索引列/JSON字段 | base_status、status_known、overdue(bool/null)、net_shipped_qty、other_out_qty、shippable_qty及分母来源、completion_rate、packing refs、quality issues；在JSON先验证后按查询需加列/索引 | 投影发布器；同版本绑定当前已有入库行与新状态源 |
| dwd_domestic_receipt_batch / _link、产品/销售/采购表 | 不改 | 本次入库接口不切回旧收货语义，不改产品归属或销售事实 | 只读复用已有主数据 |

source ID/UID均string。数量整数；不输出金额计算。UTC存储、原始时间保留，领星无时区时间按用户已确认Asia/Shanghai解释；项目Asia/Taipei显示，7自然日按业务日计算并记录rule_version。

## 5. API与前端契约候选

- 复用 `/api/pmc/domestic/inbound-batches/filter-options`，状态支持能力按已发布版本开放；未就绪disabled+reason。
- list/summary共同增 `business_status` 重复枚举<=6（含overdue虚拟筛选），不与 `inventory_status=known/unknown` 混用。未知状态不落入六类；详情返回unknown原因和证据，不把unknown当空数据。
- 列表增状态、数量/完成率，trace增打包审批/装箱确认、净出库/回冲、归属方法和质量。汇总相同过滤口径且IB×SKU去重。
- 状态缺任一关键源时可发布带unknown的行，但须明确各能力/覆盖，禁止声明全量状态已验证。可选择“严格模式状态源不齐阻止切换”，由负责人选定。
- 现有只读权限不变。新增审批/装箱动作必须另设permissionKey、可信账号/仓库/字段权限、审计、幂等与并发控制；角色名不硬编码。业务写操作和领星写接口不在此状态查询PRP范围。

## 6. 数据拉取与发布顺序

1. 审批状态源决策，解决SP接口禁用、可发量分母和归属策略；只读契约及字段样本验证另授权。
2. 实施新表与本系统打包事实基础，先合成测试/独立PG迁移演练；生产备份、迁移和同步另明确批准。逐表影响核对。
3. W1当前完整余额+现有近30天W3；OWS/SP有界窗口、offset/total一致、限流、重试、幂等、完整仓库校验，成功RAW→ODS→DWD；不自动补12个月。对老入库行标history_incomplete，历史不齐不算发出率。
4. 明确PK/OWS/IB多对多数量分配，SP作废回冲净额与其他出库对消；直接来源优先，证据不充分留unknown。
5. 生成同水位入库+状态候选，验证净量守恒、行键唯一、无跨域、可发量不被重复分配；事务发布、保留可回滚旧版本。
6. 列表/统计/详情/筛选全链路验收后开放六项。定时同步、历史补齐、生产应用部署各自另授权。

## 7. 必测与验收

无PK仍有余额但覆盖不全→unknown；OWS存在但未确认装箱→approved；只有默认箱规→不可packed；装箱确认幂等/撤销；部分发货<90%保持阶段；达到90%完成；6501撤销净零/作废SP不算发货；3401+1601抵消不算其他出库、2702不混采购；4201/4106部分与全部出库区分；同SKU多IB多店不串货；无分母/30天前历史缺失不判断overdue/shipped；7与8自然日边界及源时区；多PK部分完成；列表统计一致、权限隔离、旧发布不变、失败切换回滚；未知数量非0、状态筛选不隐式漏unknown。

## 8. 待负责人决定（只阻塞状态实施）

1. SP接口在项目登记DO_NOT_USE：查明禁用原因和可批准替代，未解决前不调用。
2. 明确允许的出库归属：仅源batch/显式关联，还是同账号+同仓+同SKU+明确同店的受限FIFO估算；未知店铺禁止混排。
3. 可发量从历史QC/入库证据恢复，是否接受历史未知持续显示unknown；是否把超时分子限定实际净发出（建议）。
4. 批准本系统PK审批/装箱事实基础的独立实施范围；本次不包含领星建单、取消、装箱回写等外部写动作。

回滚仅切回旧发布或撤回API/UI增量；业务事件不可物理删除。不得通过降级迁移删除新产生的业务事实；生产回滚先评估新业务写入水位。以上方案未执行任何新表/生产操作。
