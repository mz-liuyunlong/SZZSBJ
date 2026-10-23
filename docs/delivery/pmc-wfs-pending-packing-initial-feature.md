# 待发货打包单：本阶段需求

日期：2026-10-23。状态：负责人已确认PRP并授权本地开发；实现及验证见专属handoff。

## FEATURE

在现有 `/pmc/wfs/pending-packing` 页面实现真实本地后端联调：读取已打包完成的本系统 PK，查询剩余装箱、修改发货前信息，并事务性生成待审批货件草稿。

## BUSINESS RULES

- 上游为国内仓系统打包单审批 → 本系统装箱 → 打包完成；不抓领星备货单装箱，不以 OWS 为必填条件。
- 审批数量 Q、实际装箱 T 分别保留。合法少装或多装完成的 PK 可使用实际完成装箱生成草稿，不强制 Q=T。
- 同草稿同来源账号、同目标店铺、同业务测试标记。GTIN 为保留前导零的字符串。
- 按装箱行占用；主箱、尾箱可进入不同草稿。同一行本阶段整体分配，不支持行内拆部分箱数。
- 生成后状态 pending；不批准、不执行 Walmart、不取箱唛、不取消或修改外部计划。
- 测试记录可查看、可生成同类草稿，不计正式供货/在途/异常。环境保护标记与业务测试标记分别定义，不互相替代。

## NAVIGATION

PMC → WFS → 待发货打包单；沿用现有路由和布局。其他六页继续保持原工作区状态。

## PERMISSION

复用可信登录及来源账号范围；页面查看、生成草稿、换身份、改装箱、改报关分别校验 permissionKey，不按 Rocky 或角色名称硬编码。新权限只定义，不自动授予现有用户。

## DATA SOURCE

国内仓订单/装箱/事件为 NEW_SYSTEM_OWNED；Listing/产品来源复用已有治理发布数据。不读取旧库、旧 CSV/JSONL，不调用外部平台。继续使用已有本地数据库连接，不改 .env。

## UI / API REQUIREMENTS

列表、统计、真实店铺选项、搜索、测试筛选、分页、刷新、详情、装箱行勾选、改装箱、换店铺/链接、改报关、生成草稿确认与结果。所有操作有 loading/error/empty 状态及冲突后刷新机制。

接口与字段定义见 `PRPs/pmc-wfs-pending-packing.md`，数据决策见 `docs/data-sources/decisions/pmc-wfs-pending-packing-decision.md`。

## DOCUMENTATION / TESTS

需要 API/OpenAPI、页面规格、SOP/帮助、接口登记、组件复用说明和交接。验证 pytest、Vitest、类型/静态检查、Playwright；并发占用使用独立受控本地测试库，不向现有业务库灌测试记录。

## FORBIDDEN / ACCEPTANCE

不修改 Git 历史、分支、版本或标签；不提交推送；不修改既有业务数据、真实凭证或生产；不擅自执行建表和迁移。本阶段以真实草稿持久化及前端成功回执为实现目标，必须经 PRP 和本地结构写入授权后实施，不以 message 提示代替保存。
