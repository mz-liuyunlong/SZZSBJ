# 导入导出规则

## 文件用途

本文件用于约束 Excel / CSV 等导入导出功能。

## 导入规则

导入必须先登记来源与 Data Interface Registry，并有模板/contract 版本、文件 hash、`batch_id`、原始表头、行号、字段映射、权限、幂等、dry-run、DQ、错误行、partial failure、发布和回滚策略。不能直接覆盖 RAW、同步值或权威业务表；大文件导入走批准的 Celery 任务。错误不得静默丢弃，结果必须可追踪并按权限下载。

## 导出规则

导出必须执行 page/action/data/field/export permission，明确字段、过滤范围、行数上限、格式、时区、币种和脱敏。大文件导出走批准的 Celery 任务；结果使用受控限时访问，不得包含密钥或敏感配置。记录操作者、request/run ID、范围、数量、状态和文件引用。

## 禁止

- 前端导出全量后再过滤权限。
- 无限行数、永久公开 URL、真实 secret 或未脱敏敏感字段。
- 把飞书/Excel 副本当正式权威源。
- 无 PRP、审计、失败处理或留存策略的真实导入导出。
