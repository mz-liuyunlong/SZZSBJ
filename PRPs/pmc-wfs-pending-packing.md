# PRP：待发货打包单后台与前端联调

日期：2026-10-23。状态：APPROVED_FOR_IMPLEMENTATION。负责人在完整PRP及本地新增结构/新记录范围展示后明确回复“确认，开发”；不包含生产或外部执行授权。

## 1. Goal / Why

将现有示例页面接入本系统国内仓事实，真实保存待审批WFS草稿并防止重复占用装箱。主执行角色为后端工程师，承担本页面前端联调；不启用子Agent。保留当前未提交修改，不做无关页面重构。

## 2. 已有授权与范围

用户已确认：接续当前 `dev_wfs` 未提交WFS改动；不改Git版本号、不建/切分支、不提交推送打标签；继续现有本地数据库连接。不修改 .env 或生产；保留既有项目数据。

本阶段包含列表、统计、筛选、分页、详情、刷新、业务测试筛选、装箱行勾选、改装箱、换店铺/链接、改报关及生成草稿。截止于草稿 pending。Rocky审批、部署AI执行、Walmart写入、箱唛、外部取消/改数量全部属于下一阶段，前端不能暴露可执行入口。

## 3. Navigation / Page

PMC → WFS → 待发货打包单；`/pmc/wfs/pending-packing`；保持building直至验收通过。保留当前页面布局。其他WFS页面不接真实写接口；可增加草稿详情弹窗查看本次提交结果，不以其他页面示例记录冒充真实草稿。

## 4. Data Source

引用先行决策：`docs/data-sources/decisions/pmc-wfs-pending-packing-decision.md`，静态调查状态READY_FOR_PRP，待负责人确认。需求：`docs/delivery/pmc-wfs-pending-packing-initial-feature.md`。

权威来源为新系统国内仓订单、装箱、事件、差异/库存分配和已发布身份资料；新草稿及占用NEW_SYSTEM_OWNED。旧系统legacy_reference，不查询旧库、旧CSV/JSONL或RAW。数据分层与字段标准遵循项目现行标准。

## 5. Business Rules

1. 列表只含有效approved PK且BoxSet.completed_at非空；未完成只进统计，不进表。无装箱/版本缺失返回明确阻断，不使用领星装箱兜底。OWS不必填，页面旧OWS前置文案删除；无依据不显示虚构OWS。
2. 原审批Q与实际T分列；合法少装/多装沿用国内仓规则，不强制Q=T。仅当前真实完成行进入草稿；超装阻塞提议不能替代当前装箱。
3. 默认保留已完成但被占用/资料缺失的行供追溯，不能选；可用量按尚未有效占用行计算。统计明确已完成PK数与可用行/件/箱数，不能把多行PK重复计张数。
4. 草稿只能同来源账号、同店铺、同业务测试标记；测试与正式不能混合。环境is_test限制继续保留；候选业务标记business_test须通过现有语义核对，禁止修改历史标记。
5. 按稳定box_line_id及box_version整体占用，同PK主箱/尾箱可分草稿；本阶段不支持单装箱行拆部分箱数。相同SKU不同每箱件数拆成独立草稿，弹窗先展示分组，批量提交全成功或全回滚。
6. 草稿保存商品、装箱、退货地址、ITS选择及来源版本快照；不得只保存前端传来的件数。服务端重新计算数量，校验GTIN与同SKU身份。ITS仅保存用户选择，不宣称平台资格验证。
7. 草稿提交事务锁顺序沿用国内仓账号/仓库锁→PK稳定排序→装箱行→分配；有效占用唯一约束兜底，命令有账号范围幂等键及请求哈希。重复同请求返回同草稿，不同请求复用键409。
8. 有有效草稿占用时禁止该PK改装箱、换身份及改报关；国内仓原入口也必须执行同一守卫，不能只在WFS隐藏按钮。待审批占用不因页面刷新释放。本阶段不提供撤回/批准/执行/释放接口，避免越过后续阶段。
9. 改装箱复用仓库规则、少装/多装预算、版本及不可变事件；不足仅记录提议/阻塞，不能提示实际已改成功。
10. 换店铺/链接沿用旧单作废、新PK继承已完成装箱的业务方向；仅同账号同SKU有效Listing，服务端生成新PK，原来源分配原子转移而非额外扣库存，保留原Q、来源、差异与新旧追溯。任何状态不能安全转移时整笔409，禁止静默丢弃未装/额外分配/差异。是否使用此语义是本PRP需要确认的内容。
11. 报关修改使用现有仓库customs规则，必填原因、预期版本及幂等键；复用已有动作权限，不自行授予用户。
12. 所有动作操作者取可信登录用户，不接受自由输入姓名或共享口令；缺权限前端不可操作，后端始终校验。

## 6. API Contract（候选）

前缀 `/api/pmc/wfs/pending-packing`，与已存在PMC接口保持路径风格；不在本轮统一改全局/v1路由。统一 `{success,data,error,meta,request_id}`、response_model、OpenAPI和错误模型。

| 方法/后缀 | 用途与请求 |
|---|---|
| GET /orders | store_id、keyword、only_test、page/page_size、排序；返回已完成PK及装箱行、占用/阻断原因 |
| GET /summary | 同权限和筛选口径的完成/可选/测试/未完成统计及店铺汇总 |
| GET /filter-options | 账号范围内真实店铺，不依赖本页分页结果 |
| GET /orders/{id} | 最新单据/装箱/版本/身份/占用；只读 |
| GET /orders/{id}/identity-options | 同账号同SKU有效Listing目标及身份版本 |
| POST /orders/{id}/identity | 新店铺/ItemID、身份版本、order/box预期版本、原因、幂等键；原子换身份 |
| POST /drafts | 来源账号、所选order_id/box_line_id及预期版本、地址、ITS选择、幂等键；服务端分组并一次性提交pending草稿 |
| GET /drafts/{id} | 本阶段只读回执：草稿号、状态、快照、来源装箱；账号/店铺范围鉴权 |

改装箱、改报关优先复用 `/api/pmc/domestic/packing-warehouse/orders/{id}/rebox`、`.../customs`；前后端保留原请求契约并增加跨模块占用守卫。不新增重复库存算法。

写请求不接受客户端库存余额或自行指定状态/actor。401未登录；403无权限/无账号范围；404不可见对象；409版本变化、占用冲突、状态冲突、幂等冲突；422字段错误。缺少本地结构必须明确配置错误，不能回退mock。meta包含来源表、筛选/分页口径；时间UTC返回，由前端Asia/Taipei展示。

## 7. Permissions

实施前沿用导航既有page permissionKey，核对其定义后登记；候选新增动作：`action:pmc:wfs-pending-packing:draft-submit`、`action:pmc:wfs-pending-packing:identity-switch`。改箱/报关仍分别要求既有packing-rebox/packing-customs；页面可见不等于可写。

来源账号范围贯穿列表、统计、详情、选项、草稿与写入；目标店铺另检验实际已有店铺数据范围，禁止把来源账号授权等同全店权限。新权限仅登记定义，不写现有用户/角色授权。

## 8. Model / 本地结构方案（未执行）

不新增待发货事实表。候选四表：

- `ops_pmc_wfs_drafts`：UUID/草稿号、账号/店铺、pending状态、业务测试、op=create、地址/ITS快照、版本、登录人、UTC时间、账号幂等请求/哈希。仅内部草稿编号，本阶段不占用外部计划号。
- `ops_pmc_wfs_draft_items`：草稿FK、SKU/GTIN/MSKU/ItemID/标题、每箱件数、箱数/件数及来源快照。
- `ops_pmc_wfs_box_allocations`：草稿商品、PK、box_set/box_line、版本、分配数量/快照、占用状态；有效装箱行唯一，账号/店铺一致性约束。历史快照不可被改箱删除级联清除；FK生命周期设计须兼容未来释放后改箱。
- `evt_pmc_wfs_draft_events`：不可变submitted事件、登录人/时间、幂等请求哈希/结果引用；不为复用而放宽国内仓已有事件域。

换身份如需新事件类型/序列能力，明确列入结构差异，不修改已应用迁移历史。已有本地业务数据不覆盖不清理；不新增或执行Alembic版本号，不擅自执行手工DDL。首先产出最终字段/约束/索引/依赖清单，获负责人单独确认后处理本地结构。正式上线迁移另行按Alembic整理。若未获结构写入授权，本PRP不得声称真实草稿联调完成。

## 9. Backend / Frontend Design

后端 `backend/app/modules/pmc_wfs/` 下分router/schemas/service/repository/models；不向Route堆SQL。复用国内仓Service与库存预算，改箱入口增加统一占用守卫；Integration和Celery本阶段不新增，无外部调用。

前端在 `frontend/src/pages/pmc/wfs/` 增加独立API封装、类型、查询hook及必要的草稿/换身份弹窗。保留当前PendingPackingPage/CSS工作；复用PageShell、ProTable、ManagementStatCards、CommittedSearch、ResetButton、WalmartItemLink、已有HTTP认证/错误处理。行内操作明确loading、版本冲突刷新、隐藏无权限动作；成功提交显示真实回执并刷新列表，不用示例数据兜底失败。

本地Skill分配：`skills/backend-module-designer/SKILL.md`、`skills/react-component-architect/SKILL.md`，仅分层和复用工作模式，不扩大权限。未授权高风险Skill或子Agent。第三方API用法实施时查官方当前锁定版本文档，不新增依赖。

## 10. Allowlist / 文档与实施顺序

允许候选代码目录：新pmc_wfs模块及测试；国内仓仓库/身份服务必要守卫和事务复用；路由挂载、权限定义；待发货页面/API/types/hooks/弹窗及相关测试；独立e2e。其他WFS未提交页面不重构，wfsMock仅按必要移除本页依赖，不破坏其他页面示例。

必须交付API文档及数据中心登记、OpenAPI、页面规格、SOP/帮助、接口registry、组件复用说明、测试证据和handoff；不得覆盖其他任务计划。允许本任务专属 `.planning/current/wfs-pending-packing-*.md`。

顺序：负责人确认决策/PRP → 本地结构清单及写入范围确认 → 后端读接口 → 草稿/占用与国内仓守卫/换身份 → 前端所有动作联调 → 验证及交接。不得以查询完成代替全页面功能完成。

## 11. Validation Gates

- pytest：已完成过滤、少装/合法多装、缺身份、GTIN前导零、稳定ID、权限/跨账号/跨店铺、无真实外部调用。
- PostgreSQL隔离测试：并发同装箱只一份草稿、幂等重试/冲突、批量分组事务回滚、占用与rebox/身份变更竞争、事件不可变、改身份库存分配不增不丢。使用批准的独立本地测试库；不修改当前业务数据。
- Vitest：筛选/重置/分页、Loading/Empty/Error、勾选整行主尾箱、真实草稿弹窗和回执、修改原因、失败保留输入、版本冲突及权限。
- Playwright：mock本系统API或隔离本地后端；完成查询→选择→提交pending及改箱/身份/报关关键流程；无真实店铺密码/Token/生产依赖。
- 执行前从package/pyproject确认命令；模块ruff/pytest、前端lint/typecheck/test/build，相关E2E；真实执行结果和未运行项如实记录。未经批准不运行会连接现有库的migration/check命令。

## 12. Forbidden / Rollback

不做Git写操作，不改版本、标签、依赖版本或已应用迁移；不改.env、旧代码、生产配置或业务库历史记录；不调用外部平台。回滚仅撤销本任务确认后的差异，保护已有未提交工作；测试库清理严格核验归属。业务草稿/占用不通过删除表或删审计回滚，后续释放需独立受审计状态动作。

## 13. Acceptance / Owner Approval

- [ ] 负责人确认本PRP及数据源决策；确认换身份作废旧PK/新PK、同SKU不同箱规拆草稿及占用后禁止变更三项规则。
- [ ] 明确本地结构创建与联调写入授权，数据库实际身份/已有结构核实完成。
- [ ] 全部页面按钮真实落地；草稿pending、装箱占用、权限/审计/事务验证通过。
- [ ] 现有数据保留，Git版本不变，无外部写入。
- [ ] API/数据中心/SOP/帮助/registry/handoff与测试证据完整。

批准记录：2026-10-23，负责人“确认，开发”。此前接续dirty worktree的确认与本次PRP批准分别记录；本地连接沿用现有配置。实施及验证结果见专属handoff。
