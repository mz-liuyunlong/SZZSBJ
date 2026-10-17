# Walmart 送样全链路修复 — PR #228 取证与验收

> 状态：**Draft / 未获生产执行授权**。只修改新系统；不依赖旧系统；不自动同步、不迁移、不回填、不部署。

## 已经由只读生产查询确认

- 2026-10-01 至 2026-10-17：YC00512 / YC00512-1A / 20828004969，SaleStat 总量 **9**、订单统计 **9**；普通订单事实（按真实洛杉矶购买日及订单商品明细去重）仅 **6 件 / 6 个不同订单号**，差额 3 件全部集中于 2026-10-16。
- 这 6 件中 **3 件订单总额 0、商品折扣 24.99、状态 9**，另 3 件是有价订单。
- 6 件普通订单的历史 `business_date_la` 均与真正洛杉矶购买日期不一致；共存在 11 行版本，不可把版本总数当销量。
- 正式 `saleStatPageList` 同步未调用送样写入；`fact_walmart_sample_order_items` 的最近业务日期停留于 2026-09-30，10 月没有有效事实，日报显示 0。
- 领星后台和 Walmart 后台均报告该 SKU 送样 **5 件**；**但尚未从新系统原始订单中证明缺失的 2 件身份**。

## 本 PR 的程序修复

1. 订单接口按 `America/Los_Angeles` 自然日取 `global_purchase_time`（自动 DST），而不是把中国自然日视为美国业务日。
2. 对每条订单使用其 `global_purchase_time` 计算洛杉矶业务日，无法解析/不符则中止单日事务；严禁悄悄保存错日。
3. 正式 `saleStatPageList` 执行订单写入、送样识别、送样事实持久化、身份解析后再计算日报。
4. 识别逻辑兼顾未取消的订单总额零或商品全额折扣，保留折扣/取消原始字段，缺少必需订单商品明细号则显式失败。
5. 普通订单采用稳定的源订单号和商品行号计算哈希；重跑时同步更新状态、折扣和归属日期。

## 必须澄清的边界

- **全额折扣 ≠ 在所有业务场景下必然属于「送样」**。PR 采用候选判定策略，必须用领星真实业务规则核对混合订单、优惠券、促销和特殊折扣，避免误将广告促销计为送样。
- `fact_walmart_sample_order_items.unit_price_amount` 的来源字段应确认是单件金额还是整行金额；有多件订单时不可双重乘数量。
- 现有订单事实已包含历史可变字段导致的重复版本。改用稳定行身份不等于自动删除历史旧版本。历史去重、追溯与归属修复属于需授权的数据修复。
- SaleStat 的 `order_count` 是提供商聚合指标，不等同于我们逐笔去重得到的源订单数。
- 同步即使 succeeded，也不能证明采集覆盖或样本数量齐全；要在受控重算后进行全店铺、SKU、日期聚合对账。

## 上线前验收门槛

- [ ] CI：ruff format、ruff check、pytest、应用导入通过。
- [ ] 完整订单窗口：LA 夏令时、冬令时以及 23:59:59 边界。
- [ ] 多店铺、多 SKU、同单多明细、多件订单、重复响应、状态变更、取消及退款。
- [ ] 区分普通折扣、全额折扣候选和平台真实送样记录。
- [ ] 对所有店铺 2026-10-01 起受影响日期提供只读聚合差异表，明确“零”和“未同步”。
- [ ] YC00512 逐笔匹配领星/Walmart 的 5 件样本和 SaleStat 9 件总量。
- [ ] 确认利润、佣金、采购成本、头程与物流费用归集，不仅核对数量。
- [ ] 经审批后独立部署和有上限的定向历史回填，备份/回滚方案和幂等验证齐备。

## 只读检查样本事实覆盖范围

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT business_date_utc_minus_7 AS day_us,
       COUNT(*) AS captured_lines,
       COUNT(*) FILTER (WHERE is_valid_sample) AS valid_lines,
       COALESCE(SUM(quantity) FILTER (WHERE is_valid_sample), 0) AS valid_sample_qty,
       COUNT(*) FILTER (WHERE store_id IS NULL OR item_id IS NULL OR NULLIF(TRIM(msku),'') IS NULL) AS unresolved_lines
FROM public.fact_walmart_sample_order_items
WHERE business_date_utc_minus_7 BETWEEN DATE '2026-10-01' AND DATE '2026-10-17'
GROUP BY 1 ORDER BY 1;
ROLLBACK;
```

**注意：此 SQL 显示数据缺口，并不能独立证明真实送样总量。** 不要在生产直接执行插入、更改 `is_sample_order` 或调用回填脚本。
