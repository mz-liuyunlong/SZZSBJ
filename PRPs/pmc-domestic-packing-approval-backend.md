# 国内仓打包单审批后端与前端联调 M1

2026-10-20；负责人已授权实施本地范围。来源决策见pmc-domestic-packing-approval-decision.md；继承dev，不新建分支、不提交推送、不动生产。

## 目标与业务
候选不落表，从当前入库发布+Listing计算；稳定候选UUID包含账号/仓库/入库SKU店铺/ItemID。四表：ops_domestic_pk_sequences、ops_domestic_packing_orders、ops_domestic_packing_allocations、evt_domestic_packing_events。订单唯一候选包含approved/rejected，驳回不可再审；M1无void/reapprove。每PK仅一来源分配。来源使用publication_id+board_id复合FK及业务键快照，不挂收货DWD外键。数据库version从1起，candidate_version是来源指纹；所有ID用字符串/UUID，不转浮点。

本地验证单is_test固定true，审批并发锁与库存占用真实执行；库存上限=规范化良品减领星良品锁定减本地有效分配，未知阻断，过量409。多ItemID数量默认未知，审批弹窗必须填写正整数。通过/驳回由可信actor决定，客户端不传审批人。PK全系统北京业务日统一001..999，不按账号重号；幂等键同账号唯一，比较动作/候选/actor及完整请求摘要，相同返回原响应、不同409；发布切换和审批复用仓库事务锁。事件、订单、分配、发号同事务。审计保存来源/商品快照与结果，EVT数据库触发器禁止更新删除。

## API契约
前缀/api/pmc/domestic/packing-approval。GET /pending、/pending/summary、/filter-options、/orders、/orders/{uuid}、/orders/{uuid}/events；POST /pending/{candidate_id}/approve 与/reject。标准SuccessEnvelope及page/page_size；读权限page:pmc:domestic-warehouse-board:view；写动作action:pmc:domestic-warehouse-board:packing-approve/packing-reject，修复广义路径权限映射覆盖。权限种子仅新增定义、不授予角色。读取还要求来源账号scope，越权不泄露对象。

列表字段：id、candidate_version、source_account_ref、warehouse_id、publication_id、board_id、inbound_order_sn、sku、store_id/name、item_id、gtin、msku、purchase_order_sns、arrival_purchased/received/pending、arrival_status、candidate_created_on、overdue、stock_balance、available_quantity、default_quantity、can_approve、blocked_reasons、source_observed_at。summary与列表共享过滤，pending/overdue/blocked及相同筛选下approved/rejected分别统计。filter-options来自审批候选，不借用其他页面局部结果。

approve body：source_account_ref、warehouse_id、candidate_version、idempotency_key(UUID)、qty(严格整数1..1000000)、customs(default/declare/skip)、rwh(选填<=128)、is_test=true；reject同源字段及note(1..500)。错误401/403/404/409/422/500；冲突附稳定reason；写响应order完整DTO。候选变化409要求刷新。

## 分层及复用
Route只鉴权/envelope；Schema定义契约；Service负责事务/幂等/发号/本地写保护；Repository候选/来源与审计读取；rules纯数量/指纹；Model+Alembic管理四表。复用既有来源scope、DIM、入库发布器锁。无外部Integration写入、无Celery。

React Component Architect：沿用PageShell、ReportTableShell、ResizableColumnTitle、Toolbar、Table；新增API封装、React Query hook、审批弹窗；Panel只组合。Loading/Empty/Error/retry/pagination齐全，账号preferenceScope作为query key，mutation后刷新pending/summary/orders；权限从auth/me正常会话读取，服务端为最终边界。manual保留禁用说明，新增已审批记录及审计详情入口，不伪造成功。

## 迁移与逐表范围
四新表及索引/约束/事件保护触发器，新增app_permissions两行；model registry与Alembic元数据注册。现有MART无DDL，仅builder添加库存证明字段并本地从同源ODS重新发布，旧版本保留；GOV发布表新增一个版本并切换current，不改ODS/DWD/DIM/采购/用户/角色授权。0048/0049不改，实施前核对实际head后接续。本地全库备份与目录校验后迁移；升级仅本地。已有业务记录时downgrade拒绝，不能清空审计。

## 验证与交付
PostgreSQL集成：权限非管理员、跨账号、库存超量、不同Item共用库存、同候选并发、幂等同/异payload、并发发号、来源切换、reject终态、事件不可改与原子回滚。真实本地数据GET与写入回滚验证；前端类型检查、单元测试、Playwright真实后端桥接测试（合成鉴权仅测试进程，明确不等同真人登录）。常规登录继续验证运行服务。API/SOP/registry/module catalog/help/handoff同步，仍testing、未部署。回滚仅本地备份恢复，生产禁止。
