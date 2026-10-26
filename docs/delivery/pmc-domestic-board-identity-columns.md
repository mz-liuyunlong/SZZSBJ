# 批次看板身份列展示交付

2026-10-26。负责人将首期范围收窄为“先把参数补齐到表格”。当前只完成前端展示，不代表后端身份与负责人归属已实现。

## 已修改

- 在店铺后增加 ItemID、GTIN、负责人三列，复用 ProTable、CopyableTextCell、Tag、Tooltip。
- 前端类型预留可选 item_identities、identity_status、owner；不是后端已实现的响应承诺。
- 旧接口没有相关字段时分别显示“待归属”“待补齐”“未知”，不按 SKU 猜测、不用采购员代替负责人。
- 若未来提供多值身份，ItemID/GTIN 在同一行成对展示，库存行不展开；归属 conflict/partial 与负责人 conflict 有明确标签。
- 列偏好从版本 1 兼容到版本 2，旧用户插入三列、保留列宽及其他隐藏列；版本 2 主动隐藏新增列后不再强制恢复。该版本只是浏览器偏好格式，与 Git/应用版本无关。

## 验证

- Vitest：偏好迁移与原 API 契约共 7 项通过。
- 定向 ESLint：页面、类型、表格、偏好助手与测试通过。
- Playwright（Edge，完全 mock API）：新增三列、旧偏好升级、旧接口缺值展示 1 项通过。无真实后端或外部 API 调用。
- 全项目 TypeScript 检查被范围外文件 frontend/src/pages/data-center/integrationSyncTaskApi.domestic.test.ts:17 的 mock 返回类型错误阻断（缺少完整 envelope）；没有修改该同步模块文件。本轮涉及页面不再有类型错误报告。

## 风险与后续

后台 InboundRow 当前没有身份和负责人字段，所以真实列表暂显示缺值标记。实际填充需按完整 PRP 实现身份物化、负责人读取和接口扩展，再对现有版本做单独授权的重新发布。

不改数据库、.env、后端审批/仓库代码、旧系统或生产；不新建分支、提交、推送或修改 Git 版本。保留用户已有修改。没有把页面标记 ready。
