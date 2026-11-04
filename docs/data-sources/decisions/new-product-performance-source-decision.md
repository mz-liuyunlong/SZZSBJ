# PR #278 新品表现与打品跟踪数据源决策（待负责人定稿）

- 调查日期：2026-11-04
- 接口：`/api/new-products/*`
- 接口总体状态：**BLOCKED_BY_OWNER_DECISION**
- 是否包含 NEED_OWNER_DECISION：**是**
- 负责人批准状态：整体开发目标已授权；关键计算公式与最终来源仍未批准
- 生产访问：未运行；禁止生产同步、迁移、重算
- 本文是对已有 #278 路由的事后证据登记，不构成此前数据源门禁已履行的虚假声明。

## 来源与处理

| 字段组 | 来源 | 分类 | 状态 |
|---|---|---|---|
| SKU 账户与身份 | `dwd_lingxing_sku_identity_index` | REBUILD_SYNC | 账户范围已实现，跨店实数待验收 |
| 销量/订单/销售额 | `mart_order_profit_sku_day` | REBUILD_SYNC | 读路径实现；无销量日与发布覆盖须核实 |
| 利润、成本完整性 | 同一 MART 的 `gross_profit_amount`、`cost_status`、币种 | REBUILD_SYNC | 实算对账和 ROI 口径待确认 |
| 广告点击、花费、归因 | `fact_walmart_ad_item_sp_daily` + `dim_walmart_listings` | REBUILD_SYNC | `attributed_sales_currency_code` 上游空值风险，NEED_OWNER_DECISION |
| 库存 | `mart_listing_management_current` | REBUILD_SYNC | WFS 与普通可售分别呈现，去重和刷新质量未实证 |
| 人工市场分、到货/可售日、复盘、事件 | `product_new_workflows` + 事件 | NEW_SYSTEM_OWNED | 草稿与审计接口实现，真实人工作业待验收 |
| 正式规则与独立采购计划 | 尚无完整已批准合同 | NEED_OWNER_DECISION | 不能标记 READY_FOR_PRP |

所有业务数据都是已同步 PostgreSQL 读模型，不在路由中请求 Walmart/Lingxing。账户范围按已有 RBAC/IAM 检查。

## 当前口径

- LA 业务日 `[start, end)`；连续 30/60/90 天。MART 日期记录缺失不代表实际销量为零，不能补造 0。
- ACOS：广告归因花费 ÷ 广告归因销售额 ×100；广告费占比：MART 广告费 ÷ 总销售额 ×100。
- 币种不明或不一致不合并；当缺少归因币种时 ACOS 为空，不假定 USD。
- 可售观察起点来自人工确认的到货日与可售日的较晚值；未确认不得自动判定成功/失败。
- 利润及利润率继承订单利润页现有敏感字段权限，而非新增隐式角色授权。

## 待决策（不可自动推断）

1. 订单速度、首单时点、7/10/20 天段的评分映射和例外。
2. CPC/CVR/成交关键词归因时点、广告异常分档与无广告时的规则。
3. ROI 的权威计算口径（历史结算及成本数据）、S/A/B/C/D/Pass 扣分/否决/数量范围。
4. 业务销售 0 日的 MART 发布完整性证据、商品多店 SKU 映射；来源归因币种的落库合同。
5. 独立新品采购计划的正式业务状态、重试键、审计及人工审批操作的批准规则。
6. 供应链到货、不可售/重新上架、暂停售卖对观察期的影响。

以上任一项尚未核实均不允许宣称相关正式接口或采购自动化 READY。数据源门禁参见 `docs/delivery/backend-data-source-decision-gate.md`。

## 聚合完整性补充
- 仅通过 `count(distinct currency_code)=1` 不能证明全部日明细都具备币种；只要存在 NULL 币种行，就把该期间相关财务或广告归因计算视为不可验证。
- 广告事实表可能只记录存在广告活动的日期；没有来源发布证明时，`ad_days < days` 不能被推断为确实零广告。返回 `ad_coverage_unverified`，不生成完整评分。
