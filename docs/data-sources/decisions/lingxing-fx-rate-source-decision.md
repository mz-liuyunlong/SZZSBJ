# 财务 · 领星月汇率 数据源决策

- 调查日期：2026-11-05
- 调查人：Rocky 侧代码 AI（财务板块）
- 目标 method/path：领星 `POST /erp/sc/routing/finance/currency/currencyMonth`（`LX-C6759B059E67`）；系统内 `GET /api/finance/cashflow/fx-rates`、`GET` / `POST /api/finance/cashflow/fx-rates/sync`
- 业务用途：全系统统一一个汇率来源。财务在领星填「我的汇率」，系统同步过来，日记账按业务日所在月折人民币。
- 接口总体状态：**READY_FOR_PRP**（由 `DELETED` 经负责人例外改来，见下）
- 结论：**领星只读同步，`SOURCE_SYNC`**
- 是否包含 NEED_OWNER_DECISION：否
- 负责人批准状态：rocky（PR / PRP 负责人，经项目负责人授权）2026-11-05 决定
- 关联 PRP：`PRPs/lingxing-fx-rate-v1.md`
- 关联证据：
  - 接口契约快照：`docs/integrations/lingxing/contracts/finance-lx-c6759b059e67.md`。
  - 只读探测：部署 AI 2026-11-02、2026-11-05 各一次，都返回 `code=0`，每月 24 个币种，字段一致。原始响应留在 Rocky 侧工作区，不进仓库。
  - 旧系统代码：`old-system/source/src/syncLingxingFxRate.ts`。

## 接口状态变更

接口清单里这个接口原来是 `DELETED`。2026-11-02、2026-11-05 两次只读探测确认仍可用，rocky 2026-11-05 决定重新启用，状态改为 `READY_FOR_PRP`。这只代表可以进 PRP，生产打开同步和第一次运行要单独授权。

## 1. 旧系统与来源调查（强制前置）

| 前置调查项 | 证据位置与调查结论 |
|---|---|
| 旧页面 | 旧系统 AI 财务工具页 `old-system/source/admin-frontend/src/AiFinanceTools.tsx` 的汇率区，只读展示领星汇率；需求方 2026-08-13 决定不再人工维护。 |
| 旧 API | `GET /fx/lingxing`（读领星汇率）；`GET /fx/list`、`POST /fx/upsert`（人工台账，保留未删）。都在 `old-system/source/src/aiFinanceRoutes.ts`。 |
| 读取表 | 旧 MySQL `fact_lingxing_fx_rate`（主口径）；`biz_finance_exchange_rate`（人工台账，历史留档）。 |
| 表写入方 | `fact_lingxing_fx_rate`：只有脚本 `syncLingxingFxRate.ts`，先写原始层再写事实表。`biz_finance_exchange_rate`：`/fx/upsert`。 |
| cron / 脚本 / 外部 API | 脚本调领星 `currencyMonth`，默认拉近 13 个月。旧系统没挂 cron（`old-system/source/context/TASK_CHANGE_LOG.md`），领星改汇率后要手工跑。 |
| 人工写库入口 | 旧系统有 `POST /fx/upsert`。新系统没有：汇率不能在系统里改，只能到领星改后同步；上线种子只补缺。 |
| 能否重新获取 | 可以：按月份请求，可重复执行，按「月份 + 币种」覆盖。 |
| 少量配置数据可行性 | 不适用。上线种子放在不进仓库的部署文件里，只为同步打开前有数可看。 |
| 短期策略 | 任务中心同步：手动按钮 + 每周一上海时间 02:00。 |
| 长期策略 | 同上。产品定价、日销利润等其余读取方另开 PR 切换（见 PRP 的 PR-2）。 |

和旧系统的口径差别：旧系统折算取归属月的**上一个月** `my_rate`，缺了退 `rate_org`。新系统日记账取业务日**所在月** `my_rate`，没有就留空，不退 `rate_org`（rocky 2026-11-04、2026-11-05）。

## 2. 决定

1. 全系统只用一个汇率来源：领星月汇率的 `my_rate`，不能两个接口各用各的。
2. 这个接口在接口清单里原来是 `DELETED`，但只读探测（2026-11-02、2026-11-05）确认仍可用，字段稳定。按本决定重新评估为 `READY_FOR_PRP`。
3. 同步放在任务中心，默认关闭；生产开启、首次运行、定时开启都要授权。打开脚本会同时打开每周一次的定时（周一上海 02:00），授权要覆盖这一点。
3a. 领星改汇率后，日记账折人民币金额跟着变。财务一个月只填一次汇率，所以不做结账锁汇率（rocky 2026-11-05）。
4. 日记账：当月没有汇率就显示「—」，不兜底，也不用 `rate_org`。
5. 产品定价、日销利润等其余读取方另开 PR-2 切换，本决定只定方向，切换前先出差异报告。PR-2 已定：定价当月没有汇率用上个月兜底并标明月份，上个月也没有就算缺失；日销利润按销售月，没有汇率留空并标记 `fx_rate_missing`。

## 3. 不做

不写回领星；不改 `ref_product_pricing_rule_versions.usd_cny_rate`，PR-2 之前定价仍读它。

## 4. 例外：派安盈提现

派安盈提现按派安盈实际成交汇率折人民币，不用领星 `my_rate`（rocky 2026-11-05 定）。实现在 PR #320，规则见 `docs/api/finance-cashflow-import.md`「派安盈月结补充」。

其他场景仍只用领星汇率。
