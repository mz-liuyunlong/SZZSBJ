# 批次看板身份与负责人补齐需求

日期：2026-10-26。主执行角色：后端工程师，兼顾本页面前端集成。

## FEATURE

在 PMC → 国内仓 → 批次看板补齐 ItemID、GTIN、负责人，以及来源、缺失和冲突标记。用户已要求完成此切片，并明确不新建分支；PRP 另行确认后进入实现。

## BUSINESS RULES

保留入库单 × SKU × 来源店铺的行粒度和库存数量。ItemID 经采购单明细关联采购计划备注确定；Listing 校验商品并补充 GTIN。负责人沿用当前产品资料负责人。身份多值不得增行、复制或拆分库存，未知不补造。

## NAVIGATION AND PERMISSION

页面 `/pmc/domestic/batches`；复用现有页面权限及可信来源账号范围，不新增动作权限。详情仅显示当前可见入库行关联证据。

## DATA SOURCE

见[数据源决策](../data-sources/decisions/pmc-domestic-board-identity-decision.md)。旧系统仅只读规则参考，不作为在线来源；不新增外部调用。

## UI AND API

扩展现有列表与详情响应，追加 item_identities、identity_status、identity_issues、owner 和 identity_meta。新增三列及行内来源/异常提示，保留原列设置。业务状态列不在本期。

## TESTS AND ACCEPTANCE

pytest 验证关系、歧义、隔离、数量不变；Vitest / TypeScript / scoped ESLint 验证展示；Playwright 使用合成数据验收三列及错误状态。更新 API、SOP、接口登记与交接。

## FORBIDDEN

不新建分支、不提交推送、不改版本；不覆盖既有审批/仓库修改，不修改旧系统、.env、生产数据，不修改已审批 PK 或审批 ItemID 规则。
