# 批次看板身份与负责人补齐 PRP

日期：2026-10-26。状态：待负责人确认，尚未进入实现。主执行角色：后端工程师（本页面全栈交付）。

2026-10-26 范围调整：负责人要求“批次看板先把这几个参数补齐到表格”。本轮仅实施 ItemID、GTIN、负责人三列、缺值展示及列偏好兼容；不执行本文后续的数据归属物化、后台接口扩展或重新发布。后续完整身份规则仍需确认。已完成范围及验证见[表格交付记录](../docs/delivery/pmc-domestic-board-identity-columns.md)。

## 1. Goal and scope

补齐批次看板 ItemID、GTIN、负责人三列及来源、缺失、冲突标记；主行仍是入库单 × SKU × 来源店铺，不增行、不拆库存、不改总量。只影响国内仓入库看板模块。

不修改打包单审批的候选或 ItemID 来源，不实现业务状态，不新增真实同步，不发布生产，不新增表或迁移。用户要求不新建分支；检查时分支 develop，既有审批/仓库修改全部保留，不暂存、提交、推送或变更 Git 版本。

## 2. Data source and approval

引用[数据源决策](../docs/data-sources/decisions/pmc-domestic-board-identity-decision.md)，总体状态 READY_FOR_PRP。方案为采购计划原备注确定商品，Listing 校验并补充 GTIN，当前产品资料确定负责人。不读旧库，不把采购看板回填 ItemID 用作来源。

功能范围已经用户明确；本 PRP 具体契约和实施尚待确认。不是本地业务写入或生产授权。

## 3. Navigation and permissions

沿用 `/pmc/domestic/batches`、原 PageShell 帮助入口、页面权限及账号范围。复用 ProTable、列设置、Tag、Tooltip、CopyableTextCell、现有详情抽屉；不引入 UI 框架或新页面。

## 4. API contract

原 GET `/api/pmc/domestic/inbound-batches` 和 `/{inbound_id}` / trace 内 batch 使用同一扩展 InboundRow，保留原字段、统一 envelope、request_id、错误码与分页。追加：

| 字段 | 约定 |
|---|---|
| item_identities | 数组；每项 item_id:string、gtin:string/null、listing_status、关联采购/计划证据和 issue_codes。按 ItemID 确定性排序，GTIN 不脱离 ItemID 展示 |
| identity_status | resolved / missing / partial / conflict；存在明确矛盾优先 conflict，证据不完整且有部分结果为 partial，完整唯一解析且精确 Listing / GTIN 合法才 resolved |
| identity_issues | 稳定代码数组；采购关联缺失、计划缺失、SKU/店铺冲突、备注缺失/歧义、多个计划身份、Listing 缺失/歧义、GTIN 缺失/冲突、历史发布未物化 |
| identity_meta | 来源 purchase_plan_remark、rule_version、materialized_at、来源观察时间范围；完整证据按决策中的 source refs，不输出完整备注 |
| owner | uid/name 可空；status=resolved/missing/conflict；source=current_product_owner；身份歧义不返回任意负责人；可附 product observed_at |

无新增筛选/排序参数。负责人既有筛选继续生效；为每页 SKU 批量获取负责人及状态，避免 N+1 和 join 倍增。identity 依据发布版本、owner 依据当前资料，meta 分别说明新鲜度和依赖对象，不能用批次时间冒充所有字段同步时间。

旧发布缺少字段按 missing 展示，不能静默运行写入或实时扫描 ODS。历史 JSON 不强制改写，接口新字段有安全默认值。

## 5. Publisher and UI

发布器在原 builder 之后批量关联采购计划与 Listing；计划原备注仅在发布阶段读取与 DWD 对应的 ODS 版本。解析、关系验证和去重为可测试纯逻辑。写入原 MART payload 的身份快照，失败不切换当前版本；缺失/业务冲突作为质量结果保留，不伪造已解析。

三列顺序为店铺之后 ItemID、GTIN、负责人，再接现有数量等字段；本期不顺带重排其他已有字段。多 ItemID 在同一入库行显示，不复制数量。缺失和冲突标签可查看稳定原因及计划单号；GTIN 与 ItemID 成对。负责人名缺失但 UID 已确定时显示 UID 并注明名称缺失。

列设置升级须保留已存列宽和顺序，让旧用户获得新增三列；提供版本化偏好迁移，不能仅更改默认列后使旧用户看不到新字段。不覆盖用户隐藏其他列的偏好。

## 6. Files and delivery

拟新增本模块身份解析/物化助手及定向测试；修改 inbound_publisher.py、inbound_service.py、inbound_schemas.py、必要的 filter_sources.py、前端 domesticWarehouseTypes.ts、DomesticBatchTable.tsx、DomesticBatchDetail.tsx 与列设置兼容逻辑。不得修改既有脏的审批/仓库文件。若发生意外文件冲突，保留现场并报告。

同步更新入库 API 文档、数据中心 API 目录、SOP/help、Data Interface Registry、模块交接与本地计划。无需更换技术栈；涉及库用法时按项目规则核对 Context7 或官方文档。

## 7. Validation gates

- 后端：唯一计划、plan_remark 兜底、同备注多 ID、跨计划多 ID、部分计划缺失、无计划、跨账号/店铺/SKU、Listing/GTIN 歧义、旧发布兼容、负责人缺失/冲突、数量及分页不变。
- 使用独立合成数据测试；需要 PostgreSQL 时仅明确的隔离目标，不依赖生产或真实外部 API。
- 前端：三列、多值配对、来源和异常提示、旧偏好迁移、详情、加载和失败状态。
- Playwright：mock 统一接口合成数据，验收三列展示、负责人筛选及错误状态；不伪称真实业务数据验收。
- 定向 pytest / Vitest / Ruff / ESLint / TypeScript；必要时构建，检查 diff。不得把本次页面功能标 ready，直至相关文档、帮助入口及测试完成。

## 8. Rollback and risk

回滚仅撤回本切片文件差异，不能 reset 既有工作区。新增 JSON 字段为附加契约，旧发布保留；若后续获准重新发布，保留旧版并记录版本切换方案。本次不实际发布。

主要风险：历史备注覆盖率不足、大量 identity missing；采购单级关联不能证明精确计划入库分配；身份与负责人新鲜度不同；多值映射复制数量；既有用户列设置不显示新增字段。均按上述标记与测试处理。

## 9. Acceptance and requested approval

- 三列可见且来源可追溯，缺失/冲突不选任意值，入库行数和库存量不变。
- 不改变原审批/仓库行为、权限或数据范围。
- 不新建分支、不提交、不改 .env 或生产数据。
- 请求负责人确认本 PRP 后实施代码与隔离测试。实际本地数据重新发布另行说明准确来源 run 和影响范围，不默认执行。
