# Walmart 订单身份与送样事实完整性修复

状态：`implementation ready for review`；未合并、未部署，未执行生产 migration、同步、重算或历史修复。

## Purpose

本修复关闭三个相互关联的数据风险：可变字段参与订单行 Hash 导致重复事实、v5 重采集可能覆盖历史 v3 送样事实，以及 Daily Sales 将缺少送样证据显示为确认零。生产审计数字仅作为验收基线，不作为代码中的常量或自动修复目标。

## 根因结论

1. 旧订单写入把完整 `item` 和 ordinal 放入 `source_line_hash`。价格、数量、状态或折扣变化会生成新 Hash，同一来源订单行因而产生多个物理版本。
2. 新稳定 Hash 不能自动消除旧 Hash 行；若没有显式历史采用机制，下一次同步仍会在旧版本旁新增一行。
3. 送样刷新曾删除非当前 v5 已核验规则的行，MART 也只读取 v5，导致合法 v3 历史事实在重采集或重算时面临静默归零风险。
4. Daily Sales 的数值 `0` 无法区分“已采集且核验为零”与“未采集/待核验”。

## 规范订单身份

规范业务键固定为：

```text
source_account_ref + store_id + source_order_id + source_order_line_id
```

- `store_id` 防止不同店铺复用订单号/行号时误合并。
- `source_order_line_id` 必须来自提供商订单商品行标识；缺失时失败或将潜在送样候选隔离，禁止以 SKU、金额或 ordinal 推断。
- 数量、金额、商品身份、状态、折扣和取消信息只属于可变快照，不参与身份 Hash。
- 仓库离线契约把 `platform_order_no`、`reference_no` 列为 Order V2 响应字段，但接口仍标记为 `UNVERIFIED`，parser 也未将两者设为必填；现有证据没有证明它们始终存在或永不变化。因此二者不参与规范身份，而是纳入可审计快照：首次缺失、后续补齐或变化会建立新物理版本并记录差异，旧版本原值不被覆盖。
- 一个身份最多有一行 `is_identity_current=true`。历史物理版本保留为证据，不自动删除。
- 历史物理行不再作为可写锚点。首次再次观察历史身份时，应用新增一行独立 canonical current；例如 12 个 legacy 版本、5 个身份首次采用后为 12 个不可变 legacy + 5 个 current。
- 相同来源快照重放只更新 current 的 `synced_at`，不改变业务字段、`updated_at` 或物理行数。来源业务快照发生变化时，旧 current 仅撤销 current 标记并完整保留业务值，随后新增一行 current；因此只在真实版本变化时增加一个物理版本。
- Provider 原始 Item ID 保存在 `provider_item_id`；`item_id` 是供下游读取的有效身份。Provider 缺失时，只有唯一 Listing 匹配才可补全，并通过 `item_id_resolution_source` 记录 `local_sku` 或 `local_sku + msku` 匹配依据。补全值不伪装成 Provider 证据，也不参与 Provider 快照差异判断。
- Provider 后续返回与 Listing 补全相同的 Item ID 时，建立一条有来源证据的新版本；返回不同 Item ID 时以 `DATA_PAGES_ORDER_ITEM_ID_RESOLUTION_CONFLICT` 阻断。匹配不唯一时保持 unresolved，禁止任意选择。
- `audit_walmart_order_item_conflicts` 使用物理 `prior_fact_id → canonical_fact_id` 作为版本转换身份，并保存 canonical identity、prior/observed Hash 与差异字段名。同型 A→B 转换发生在不同物理版本时分别保留，同一个物理转换重试保持幂等；完整前像由不可变事实行保存，不复制 RAW payload。
- 身份补全只处理规范 current 行。退款匹配优先读取 current 行；迁移后尚未再次观察的身份仅在物理历史行唯一时允许兼容读取，存在多个旧 Hash 版本则继续 fail closed，禁止任意挑选。

## Migration 边界

`20261020_0047_walmart_order_identity_guard` 只新增：

- `canonical_identity_hash`；
- `is_identity_current`；
- `provider_item_id` 与 `item_id_resolution_source`；
- current identity 完整性 CHECK（非空且非空字符串的账号、店铺、订单、订单行及小写 64 位 SHA-256）；
- current identity partial unique index；
- 无业务值的冲突审计表。

Migration 不执行 `UPDATE`、`DELETE`、历史回填、版本合并或送样确认。旧行初始均为 non-current，只有后续已批准的提供商观察才可逐身份采用一行。生产执行前必须先完成冲突预检、可恢复备份和隔离恢复演练；本 PR 不授权执行 migration。

0047 downgrade 仅是空证据状态下的 schema 回退：只要存在 current 行或转换审计，PostgreSQL migration 会在任何 DROP 前 fail-closed。数据级回退必须另行取得 DBA/Owner 授权，先归档并验证可恢复备份；普通 `alembic downgrade` 不是无损生产回退方案。

## v3 / v5 送样兼容

- 历史已确认规则 `zero-total-provider-status-strict-triple-v3` 与当前平台证据规则 `provider-verified-sample-v5` 都可进入 MART。
- 相同、未取消的提供商重放保留原规则版本；v3 不会被自动升级为 v5。
- 已核验重放在写入前锁定并完整比对业务日期、订单/店铺/平台/订单行、Item ID、MSKU、local SKU、数量、单价及币种、订单金额及币种、取消信息。缺少关键证据或任何实质变化均返回 `DATA_PAGES_VERIFIED_SAMPLE_CHANGED`，事务回滚且既有事实/MART 不变。
- 未核验的零元/全额折扣记录继续写为 `candidate-unverified-v5`，不能自动成为正式送样。
- 已核验事实发生身份、数量、金额、商品或取消状态变化时，单日事务失败；禁止静默降级、覆盖或归零。
- 出现未登记的已核验规则版本时，采集提交和 MART 发布均以 `DATA_PAGES_SAMPLE_RULE_VERSION_UNSUPPORTED` 停止。
- MART 重算先通过规则、身份和 SaleStat 上限校验，再替换结果；失败事务保留既有 MART。

## Daily Sales 口径

- 送样单量：已核验事实中的不同 `platform_order_no` 数量。
- 送样量：已核验、唯一订单明细的 `quantity` 合计。
- v3/v5 仅作为已核验事实版本集合，不允许候选进入成本、利润或广告占比。
- 缺少商品维度采集记录时返回 `sample_data_not_observed`；存在未核验候选时返回 `sample_verification_pending`。
- 前端显示“未知”或“待核验”，不把这两种状态展示为确认零。
- SaleStat 仍是销售聚合事实；本修复不改变其数量，也不硬编码任何 SKU 的预期送样量。

## 只读生产预检

只允许在单独授权后，用只读数据库账号运行：

```bash
cd backend
uv run python -m scripts.audit_walmart_order_identity_conflicts \
  --start 2026-10-01 --end 2026-10-17 \
  --account '<approved-source-account-ref>' --limit 100
```

预期输出只包含范围 Hash、业务日期、物理/current 版本数、各可变字段版本数及 `write_performed=false`。不得输出订单号、店铺、SKU、商品名、金额值、RAW、Token 或凭据。该预览只识别冲突，不选择删除对象或授权修复。

## 发布和生产数据门禁

1. 在隔离 PostgreSQL 完成 0046→0047 migration、5 身份/12 历史版本和重复同步验证。
2. 获得可恢复的生产备份及恢复演练证据。
3. 只读运行冲突预检；Owner 审核聚合结果和拟处理日期。
4. 暂停相关调度，准备并校验同一已合并版本的 FastAPI、Worker、Beat 发布产物；不得先启动依赖 0047 字段的新代码。
5. 在同一获批变更窗口内，由 DBA 单独执行 0047，再切换已校验代码；确认 API 与 Worker 正常后才能恢复 Beat。切换过程不自动同步、不重算、不回填。
6. 后续每个业务日期的真实采集、送样核验、MART 重算和历史数据修复均需独立授权；任一对账不一致立即停止。

禁止把 migration 成功理解为历史去重完成；禁止自动删除旧行、自动确认送样或将 v3 批量改写为 v5。失败时优先停止新写入并修复前进；已有 current/审计数据后，0047 downgrade 会被门禁拒绝。任何 schema/data 回退必须由 DBA 基于已验证归档与恢复演练另行审批。

时间语义：`synced_at` 是最近一次成功观察该来源事实的 UTC-aware 时间；`updated_at` 是该物理版本业务快照的建立时间。相同重放只推进 `synced_at`；真实业务变化创建新 current，失败事务不会推进任何时间。

## Explicitly Not Implemented

- 未调用 Walmart/Lingxing、未请求 Token、未执行 `saleStatPageList`。
- 未连接生产数据库、未执行生产 migration、未重建 Daily Sales/Order Profit。
- 未删除、更新或回填生产订单/送样历史。
- 未自动确认 5 件送样或任何其他送样数量。
- 未修改 `old-system/**`、生产服务、Nginx、systemd、Celery 配置或调度状态。
