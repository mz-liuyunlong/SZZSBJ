# 采购与批次 ItemID 旧行为对齐

2026-10-27。负责人在对比旧 build_from_daily.py 实际行为后要求当前分支修改；不新建分支、不提交推送、不真实同步或写业务库。仅处理采购与批次 ItemID，不包含审批、数量分配、OWS、货件、旧货件追溯或人工对照表迁移。现有其他任务改动保留。

## 数据源决策与实现契约

复用既有采购决策及批次身份决策的数据源；本次负责人最新决定替代其计划优先与多值冲突规则。采购/批次备注合并提取独立11位数字，明细备注在前、计划备注在后，稳定去重；使用同账号同店铺同SKU的Listing校验。未验证备注保留证据，不直接归属。无有效备注时使用原Listing兜底。继续保留账号隔离及已知店铺边界，不复制旧系统跨店铺猜测、货件或人工映射逻辑。

多值为有效关联集合，不等同冲突，不拆数量或金额。采购DWS既有source_lineage_json新增item_identities与备注证据，单值列只在唯一时赋值。ItemIdRef追加identities列表，每项item_id、msku、gtin、fulfillment_type；旧快照默认空列表。列表、详情、ItemID/GTIN/MSKU搜索和待处理统计支持多值。批次identity_status多值使用multiple，页面明确显示多listing，不当作错误冲突；partial保留原缺失语义。无有效备注时同店铺SKU的Listing集合也保留多值，不强选第一条。

无新表、迁移或权限；GET不新增数据源。DWS刷新阶段构建采购身份；批次沿用现有备注读取位置，仅校验匹配规则。本次不执行真实刷新，因此现有DWS数据需另行授权刷新才带新增集合。

## 分层与验收

Route沿用；Schema追加向后兼容字段；Service仅映射DWS；Repository搜索集合；Model复用JSON；Integration/Celery不改。前端复用ItemIdCell、CopyableTextCell、Tag和既有API客户端，新增集合多值展示。数据源/字段分层标准已检查。测试覆盖双备注、多值、Listing校验、14位GTIN排除、账号店铺隔离、读接口与搜索、展示；本次仅隔离测试。旧代码只读参考，不导入复制。

## 执行与交接

实际分支develop，按负责人要求不新建分支/worktree，不提交推送。保留原同步流水线和任务页面等其他未提交改动，不把它们计作本次实现。使用项目backend-module-designer和react-component-architect规则核对既有分层与组件复用；无第三方库API升级或新增依赖，无需新增文档查询。

结果：计划A与明细B经Listing校验均有效时，采购与批次均显示全部有效身份（明细先、计划后、去重）。采购标量为空不再误计待处理；集合按ItemID/GTIN/MSKU可查；GTIN与各ItemID对应展示。DWD标量无法表达多个备注身份时保持空，后续DWS从现有ODS备注重建集合；不改采购数量金额计算，不改审批身份或库存逻辑。

实际验证：pytest 7个定向文件131通过；Vitest采购API/页面2文件16项通过；Edge模拟接口Playwright多值场景1项通过；TypeScript tsc -b通过；定向Ruff、ESLint及git diff --check通过。浏览器测试曾因错误拦截/src/api模块失败，修正为仅/api/后通过，不是业务接口故障。首次TS检查曾发现其他任务已有mock返回格式问题，后来复查通过，未修改该无关测试。

未连接本地/生产业务数据库、未真实同步、未刷新DWD/DWS、未改.env/权限/数据库结构、未执行领星或Walmart写操作。测试数据库仅隔离内存SQLite。现有业务DWS仍为旧快照，要显示真实多值需要另行运行原同步/刷新流程；本任务不自动执行。旧标量消费者必须使用identities集合判断多值，不能把null等同未归属。SOP/API及Data Interface Registry已补充。

回滚时仅还原本任务精确代码差异，保留其他未提交改动。无迁移、无真实数据改动，不应整库恢复。若后续重新计算DWS，可按旧代码原刷新流程重算，必须另行授权。
