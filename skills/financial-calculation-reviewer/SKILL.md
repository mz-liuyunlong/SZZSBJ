# Skill: Financial Calculation Reviewer

## 用途

本 Skill 用于审查利润、回款、退款、广告花费、成本等公式是否清晰、可验证。

## 必须读取

1. `docs/FINANCIAL_CALCULATION_RULES.md`
2. `docs/TIMEZONE_AND_CURRENCY_RULES.md`
3. `docs/DATA_SOURCE_AND_LINEAGE_RULES.md`

## 输出格式

```md
## 财务公式审查

### 指标名称
### 输入字段
### 公式
### 币种
### 时间口径
### 是否含退款
### 是否含广告费
### 是否含物流/平台费
### 待确认项
### 测试样例
```

## 强制规则

1. 口径不清不能写入生产逻辑。
2. 所有金额必须带币种。
3. 必须给出测试样例。
