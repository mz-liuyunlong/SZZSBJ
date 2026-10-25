# Listing 规则配置 API — 数据源决策（待负责人确认）
  
- 调查日期：2026-10-25
- 调查依据：GitHub `main` 只读检查、用户确认的 Listing 评级 V1.0 规则及 2026-10-25 服务器只读同步结果
- 目标接口：`GET /api/listing-rule-config`、`PUT /api/listing-rule-config`、`GET /api/listing-rule-config/history`（均为**拟定**接口，非现存接口）
- 业务用途：Listing 管理页右上角「规则配置」，第一切片管理评级参数；不在本任务中修改同步、利润或生命周期算法
- **接口总体状态：READY_FOR_PRP（数据来源设计就绪，不代表代码或 PRP 已获批准）**
- 是否包含 `NEED_OWNER_DECISION` 数据集：否；本切片只持久化新系统自有的规则配置
- 负责人对实现 PRP 的批准状态：**待确认**
- 数据源分类：**NEW_SYSTEM_OWNED**
- 数据粒度：全局唯一一套 Listing 评级配置的不可变版本；多账号、多店铺共享规则，禁止各 Listing 自行覆盖
- 权威写入方：本功能通过经过权限校验的后端服务；不是浏览器本地状态、旧库或外部 API
- 权威读取方：规则查询 API；后续评级任务引用生效版本，不能把前端默认值当成数据库已保存版本

## 1. 强制前置只读调查

| 调查项 | 证据与结论 |
|---|---|
| 旧页面 | **不适用**；本次是新系统 Listing 规则配置功能，不迁移旧配置 |
| 旧 API | **不适用**；不得把旧接口作为权威数据源 |
| 旧接口文件位置 | **不适用**；不读取 `old-system/**` 来实现此功能 |
| 读取表 | 新配置版本表（拟建，名称待 PRP 批准）；不读取原始广告 JSON |
| 表写入方 | 新规则配置 Service/Repository，经后端权限校验 |
| cron / 脚本 / 外部 API | **不适用**；查看、保存配置不调用领星或 Walmart |
| 人工写库入口 | **无**；禁止在生产库手工修改规则 |
| 外部平台重新获取可能性 | **不适用**；规则属于内部管理策略，不以平台为权威 |
| 少量配置数据可行性 | 是；单一全局规则对象及版本历史，数据量小 |
| 短期策略 | 使用默认 V1.0 规则作为只读 fallback；管理员写入时产生可审计新版本 |
| 长期策略 | PostgreSQL 保存生效区间、不可变版本、原因、操作者与审计；评级执行记录引用规则版本 |
| 退出标准 | **不适用**；没有临时旧库来源要退出 |

## 2. 数据集与权威责任

| 数据集 | 分类 | 来源 | 目标与使用边界 |
|---|---|---|---|
| Listing 等级配置参数（7/14、权重、4/8、阈值、纳入阶段） | NEW_SYSTEM_OWNED | 当前负责人批准的 V1.0 规则；后续经授权的管理动作 | PostgreSQL 版本化配置；GET 返回生效版本与默认来源 |
| 规则变更历史 | NEW_SYSTEM_OWNED | 成功配置变更所生成的系统审计事件 | 永久追溯修改人、修改时间、旧/新版本与原因 |
| 编辑权限 | 项目已有 IAM 权威体系，不新建一套角色 | `backend/app/modules/iam/permission_catalog_v2.py` | 新增 Listing 配置动作 permissionKey，后端强制校验 |
| 当前 Listing 经营数据 | **不在本次接口数据集范围** | 现有 `mart_listing_management_current` | 规则配置页不重新聚合商品销售或利润 |
| 广告与财务费用、等级日快照 | **不在本次接口数据集范围** | 后续评级引擎另行做数据源决策 | 配置保存不触发评级、财务回写或历史回填 |

证据：
- `frontend/src/pages/products/ListingManagementPage.tsx` 及 `components/ListingManagementToolbar.tsx` 已有页面与列配置按钮，可新增「规则配置」入口，不新增导航页。
- `backend/app/modules/data_pages/registry.py` 表明现有 Listing 页读 `mart_listing_management_current`，不能把新业务配置混入销售 MART。
- `backend/app/modules/iam/permission_catalog_v2.py` 使用动态 permissionKey、页面与动作权限。
- `AGENTS.md` 要求 PostgreSQL、Alembic、版本化、审计、不得直接修改生产数据库。

## 3. 数据治理与生效边界

1. V1.0 的 `execution_timezone=Asia/Shanghai`、`scheduled_time=22:30`、`business_timezone=America/Los_Angeles`、`closing_lag_days=2` 为**受保护、暂不开放编辑**的策略；保存请求不得覆写。
2. 评分规则编辑项仅包括窗口天数、权重（合计 100%）、最低有效天数、三级阈值及可参与阶段。清货期与已归档始终禁止启用。
3. 保存采用**新增不可变规则版本**而非更新历史行；旧版本保留，下一次评级周期开始前生效；配置保存**不得**自动历史重算。
4. 使用有效期和规则版本保证审计可追溯；规则变更不修改 ERP「每日销售」财务口径。
5. 未确认的费用完整性信息不得默认等于 0；该原则不可由配置禁用。
6. 修改权限建议使用 `action:products:listing-management:configure-rules`，需要确认该键已注册到 IAM 权限目录且后端鉴权可识别；不按角色名称判断。
7. 普通用户可见规则摘要的范围与 `products_listing_management` 页面查看权限一致；修改历史的可见性依现有审计规范落实。
8. 数据库版本表及 API 均属于**拟实施设计**；本决策文档不授权执行迁移、写库或部署。

## 4. 风险与实施门禁

- 新的评级规则不能悄悄改变已出具的历史结果。变更生效时点、审批人与原因必须进入版本记录。
- `product_grade` 等现有 Listing 字段的语义与未来评级引擎需要单独核查，禁止因添加配置功能而改写这些字段。
- 第一 PR 只做「等级评级规则配置」切片。生命周期阈值、库存与修复、C/D 任务截止时间属于不同后续 PRP，不能在此切片写入。
- **下一关：负责人明确审核批准 `PRPs/listing-rule-configuration-v1.md` 后，方可实施接口、新表、迁移、UI 与测试。**
