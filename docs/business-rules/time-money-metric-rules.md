# 时间、金额、指标口径规则

## 1. 时间口径

| 类型 | 规则 |
|---|---|
| 数据库存储时间 | UTC，PostgreSQL 使用 `timestamptz` |
| 前端展示时间 | 默认 Asia/Taipei |
| Walmart 销售 / 广告业务日期 | America/Los_Angeles |
| 任务执行时间 | UTC 存储，Asia/Taipei 展示 |
| 字段命名 | `created_at`、`updated_at` 为 UTC；`business_date` 为业务日期 |

规则：

```text
时间戳 UTC 存，页面按 Asia/Taipei 展示，Walmart 业务日按 America/Los_Angeles 归属。
```

## 2. 金额口径

```text
金额字段禁止使用 float
PostgreSQL 使用 numeric(18,4)
所有金额必须带 currency_code
Walmart 销售、广告、退款、结算默认 USD
国内采购、工资、内部成本可以 RMB
涉及换汇必须记录 fx_rate、fx_source、fx_date
利润计算必须记录 calculation_version
财务报表不能直接用前端计算金额
```

建议字段：

```text
amount
currency_code
fx_rate
fx_source
fx_date
amount_usd
amount_rmb
calculation_version
```

## 3. 指标字典

每个核心指标必须定义：

```text
指标名称
英文字段
数据来源
计算公式
时间口径
金额币种
是否含退款
是否含广告费
更新时间
适用页面
负责人
版本记录
```

硬规则：

```text
没有指标口径定义，不允许开发对应页面。
同一个指标在不同页面必须使用同一口径，除非文档明确说明差异。
```

常见需要定义的指标：

```text
今日销售
今日利润
广告花费
退款率
库存预警
Review 预警
单品现金利润
订单利润
广告 ACOS
补货建议
WFS 费用异常
```
