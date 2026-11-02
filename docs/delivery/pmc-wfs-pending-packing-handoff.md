# 待发货打包单交接（2026-10-23）

负责人已确认PRP并授权开发、本地新增结构与新记录。沿用dev_wfs及现有未提交工作，未执行Git写操作，未改任何版本号、.env或生产。主执行后端工程师完成同页面前端联调，无子Agent。

## 已实现

- 八个WFS API：已完成PK分页列表、全范围统计、真实店铺选项、单据详情、同SKU身份选项、换身份、新建pending草稿、草稿只读回执。
- 复用国内仓改箱/报关；共享事务锁内增加草稿占用检查，旧HTTP入口不能绕过。
- 本系统装箱事实和行UUID；主尾箱整行分配；同每箱件数组草稿；原审批Q与实际T分开。业务business_test与环境is_test分开，历史标记不改。
- 新草稿、商品快照、占用和不可变事件四表。提交幂等绑定用户和payload，当前范围检查、版本冲突、跨账号/店铺隔离。
- 换身份作废旧PK创建新PK，转移原/额外库存分配、复制完成装箱与差异，不重复占用库存。
- 页面所有原真实业务动作接入，API/type/query/弹窗拆分；错误不回退mock，失败保留表单。详情通过行展开展示装箱；权限控制按钮，服务端独立复验。
- API文档、数据中心API目录、SOP及新标签帮助、页面规格/复用说明。

## 本地结构及数据保护

`backend/scripts/wfs_pending_local_schema.py` 默认只读检查，--apply仅首次创建四表和事件不可变trigger；存在表即拒绝覆盖。`wfs_pending_permissions.py`只插入WFS四项权限定义，ON CONFLICT不覆盖，未改变用户或角色授权。注册元数据供未来正式Alembic方案使用，没有新增修订号或更改已应用历史。

前后核验：PackingOrder 5、BoxSet 0、BoxLine 0、PackingEvent 5；Alembic保持20261022_0054_merge_walmart_identity_and_domestic_packing。本地真实GET orders/summary/filter-options均200，待发货0、待装箱4。没有通过修改既有数据制造成功列表。

## 验证与证据

- pytest `backend/tests/modules/pmc_wfs/test_pending.py`：10通过。真实PostgreSQL临时schema；复制结构不复制内容，无public搜索路径回退；同进程创建和清理。覆盖分组/幂等、主尾箱、冲突回滚、业务测试标记、换身份分配转移、改箱/报关占用守卫、双线程竞争、审计不可变和HTTP鉴权契约。
- Vitest `PendingPackingPage.test.tsx`及`WfsFrontendPage.test.tsx`：10通过；真实查询组件配模拟传输，验证提交、错误与筛选/权限。jsdom伪元素getComputedStyle提示不影响结果。
- Playwright `e2e/wfs-pending-packing.spec.ts`：2通过（Edge），验证选箱→填写地址→保存pending→占用刷新及503无样例兜底。仅模拟API，不宣称浏览器写入了业务库。
- TypeScript tsc -b、所改前端模块ESLint、后端模块Ruff、Vite build通过；不替代未运行的全仓回归。
- `wfs_pending_local_verify.py`通过FastAPI HTTP契约访问真实本地数据库，依赖注入只用于只读验证，不修改真实用户/角色。返回统计不含敏感业务记录。

浏览器截图位于本机临时Playwright结果目录，使用合成数据；不可视为生产证据。当前页面状态testing，待负责人以真实业务装箱验收后再考虑ready。

## 文档核对及限制

使用本地Backend Module Designer、React Component Architect Skill；查阅SQLAlchemy2 ORM写入和FastAPI response_model官方文档。Ant Design站点当前默认6版，项目锁定5版，因此实现复用本项目已有5版Modal/Form用法与本地类型检查，不升级依赖；未使用Context7。

本阶段不开放批准、撤回/释放、部署AI执行、Walmart调用、箱唛及取消/改数量。后续扩展必须新PRP，不能删除草稿或审计释放占用。当前草稿号为系统内部编号，尚无外部计划号。

正式环境部署仍需单独Alembic迁移及演练，不可直接运行本地schema脚本。没有执行全仓回归或生产部署。

回滚需只处理本任务差异，保留原有WFS未提交文件；新增业务记录禁止删审计式回滚。当前public四张WFS表没有填入测试草稿。
