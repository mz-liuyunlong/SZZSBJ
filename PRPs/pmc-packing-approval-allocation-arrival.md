# 打包审批 WFS 与到货、比例预填

状态：负责人在 2026-10-28 对上轮具体改动表确认“确认修改，在当前分支”；本文件落实该已批准范围，不扩大授权。当前 develop 工作区开始时干净；不建分支、不提交、不部署、不连接生产数据库。

2026-10-28 后续明确授权：修复 quantity_receive 语义错误。已到从原采购明细 payload_json.quantity_entry 读取，未到从 quantity_receive 读取；缺失保留未知，无新表字段迁移。仅修复本轮到货投影、对应合成用例与文档；保留当前工作区其他改动，不运行测试，不修改已有审批历史快照。

数据源决策：[decision](../docs/data-sources/decisions/pmc-packing-approval-allocation-arrival-decision.md)。先决策后本 PRP 再实现。已检查数据库分层、字段标准和 API 契约规则。

## 后端模块设计方案

- API Route：复用原路由及权限、账号 scope、统一返回、response_model；添加 split_arrival=all/yes/no/unknown 查询。
- Pydantic Schema：arrival_status 扩展 full/partial/none/unknown；增加 split_arrival(bool|null)、arrival_batch_count/index(int|null)、quantity_suggestion（规则、计划权重、箱规、尾差、提示、来源证据）。均默认兼容历史快照。
- Service：严格 WFS 1，人工请求和修改身份同样重验。保留原幂等、库存锁、分配和审计事务。
- Repository：有界读取上述新系统表；单独采购证据 repository；纯函数负责到货与分配计算，禁止 Route 查询或计算。
- Model / Migration：复用既有表和 JSON 快照；无迁移。
- Integration / Celery Task：无新增、无外部调用。
- 权限与日志：不新增权限；原订单、分配、审批快照和审计事件持有最终人工数量及建议依据。

## 组件拆分与复用计划

- 页面职责：原 Panel 管理请求；不添加页面。
- 页面专属：原 Table 展示到货数量、状态、分批、建议及原因；原 DecisionModal 默认建议且可编辑；目标改变提示比例仅适用原身份。
- 复用：ReportTableShell、ResizableColumnTitle、CopyableTextCell、Ant Design Tag/Tooltip/Select/Form/InputNumber；不新增 Shared 组件或依赖。
- Hooks/API/类型：复用原查询 hooks 和 packingApprovalApi/Types，新增字段和筛选参数。
- 不封装重复体系；未知展示 — / 未知，0 是真实零。

## 测试与验收

纯规则覆盖累计到货、重复行去重、未知、超收、箱规尾差、歧义拒绝建议、库存上限、先审后建议。Repository 合成数据检查账号/店铺/SKU 隔离和最新成功版本。Service 校验 WFS0 不可通过、WFS1 可选。前端 Vitest 验证建议可编辑及筛选参数；Playwright 使用合成 API 验证列表/筛选，不依赖生产或真实账号。运行 scoped pytest、Vitest、TypeScript、lint、E2E；不运行需要本地真实数据库的集成 fixture。

## 回滚与交付

按本轮精确 diff 回退代码，无表结构或真实数据回滚。更新 API、SOP、registry、handoff；报告实际通过与未执行检查。不得宣称已部署或已同步真实数据。
