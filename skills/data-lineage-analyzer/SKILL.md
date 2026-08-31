# Skill: Data Lineage Analyzer

## 用途

本 Skill 用于梳理页面字段、报表字段、财务字段从哪里来、如何计算、展示口径是什么。

## 必须读取

1. `docs/DATA_SOURCE_AND_LINEAGE_RULES.md`
2. `docs/BUSINESS_GLOSSARY.md`
3. `docs/FINANCIAL_CALCULATION_RULES.md`

## 输出格式

```md
## 数据血缘分析

### 页面 / 报表
### 字段清单
| 展示字段 | 来源系统 | 源字段 | 转换/计算 | 展示口径 | 风险 |
|---|---|---|---|---|---|
### 待确认口径
```

## 强制规则

1. 字段来源不清时必须标记待确认。
2. 财务字段必须说明公式和币种。
3. 时间字段必须说明时区。
