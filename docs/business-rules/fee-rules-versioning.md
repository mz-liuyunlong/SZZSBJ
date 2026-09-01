# 费用规则版本化规则

## 1. 总原则

所有影响利润、成本、佣金、汇率、费用的规则，禁止写死，禁止覆盖历史。

```text
调整规则 = 新增版本
不是覆盖旧值
```

## 2. 必须版本化的规则

```text
店铺佣金比例
平台手续费
广告归因规则
退款费用规则
WFS 费用规则
仓储费规则
物流履约费
采购供货价
汇率
人工成本
包装成本
清货规则
利润计算公式
```

## 3. 核心字段

```text
id
platform
store_id
sku / category / fee_type
rate / amount / formula
currency_code
effective_from
effective_to
rule_version
priority
status
change_reason
created_by
created_at
approved_by
approved_at
```

推荐日期口径：

```text
effective_from <= business_date < effective_to
```

当前生效规则的 `effective_to` 可以为空。

## 4. 佣金示例

| 店铺 | 佣金比例 | 生效日期 | 失效日期 | 状态 |
|---|---:|---|---|---|
| Walmart A | 15% | 2026-01-01 | 2026-04-01 | 历史 |
| Walmart A | 12% | 2026-04-01 | 空 | 当前 |

2026-03-31 的订单用 15%。
2026-04-01 的订单用 12%。

## 5. 利润结果必须保存快照

利润计算结果中建议保存：

```text
commission_rate
commission_amount
commission_rule_id
commission_rule_version
rate_snapshot
calculation_version
calculated_at
```

## 6. 防呆规则

```text
不允许删除历史规则
不允许覆盖历史规则
同一对象、同一费用类型、同一时间段不能有两条生效规则
修改已生效规则必须二次确认
涉及历史日期的修改必须走审批
修改后必须写 audit_action_log
保存前必须显示影响范围
已月结数据默认锁定，不自动重算
没有生效规则时，不得默认为 0，必须标记 fee_rule_missing
```

## 7. 影响预览

保存费用规则前，必须展示：

```text
影响店铺 / SKU / 类目
影响日期范围
可能影响订单数
可能影响报表
是否需要审批
是否需要重算
预计差异金额，如果可估算
```

## 8. 历史重算

历史修正必须走流程：

```text
1. 新建历史修正规则
2. 选择影响日期范围
3. 系统预览影响订单 / SKU / 店铺 / 金额
4. 二次确认
5. 审批
6. 后台任务重算
7. 生成重算批次号
8. 记录审计日志
9. 保留旧结果和新结果差异
```
