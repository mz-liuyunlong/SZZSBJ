# 数据源候选映射

本目录保存旧库、外部 API、新系统页面之间的数据源候选映射。这里的内容默认是草稿和分析依据，不是最终架构批准。

## 使用边界

- `*-draft` 是候选映射和调查草稿，不是批准结论。
- `decisions/**` 保存接口级数据源决策记录，默认命名为 `{module}-{interface}-decision.md`，文件名使用小写 kebab-case。
- decisions 文件不等于自动批准实现；是否可以进入 PRP，以文件内“接口总体状态”字段为准。
- `docs/integrations/**` 中的离线 API 文档可以作为调查证据，但不能视为已批准的数据源决策。
- 旧库、领星 API 和新系统数据源必须分别标记。
- 未确认字段必须标记“待确认”。
- 财务字段不得自行推导公式。
- 时间字段必须注明时区状态。
- 映射文件不是最终架构批准。
- 任何真实 API 接入、数据库迁移或业务接口实现必须另行 PRP。

## 当前文件

- `lingxing-walmart-api-to-system-data-map-draft.md`
- `lingxing-walmart-api-to-system-data-map-draft.csv`
- `legacy-lingxing-lineage-review.md`：旧系统领星 lineage matrix 的仓库静态证据复核。
- `legacy-lingxing-migration-priority.md`：P0/P1/P2/P3 调查与迁移候选顺序；不授权实现。

## 数据架构标准

- [Database Layering Standard](database-layering-standard.md)：新数据表、同步任务、API PRP、mart/read model、AI 数据使用和文档知识索引的分层边界。
- [Field Standardization Standard](field-standardization-standard.md)：新字段、API response 字段、清洗任务和数据映射的标准化与血缘要求。

## 状态说明

- `draft_candidate`：候选草稿，仅供讨论和盘点。
- `unverified` / `未验证`：尚未做真实 API 或旧库字段验证。
- `待确认`：需要负责人、架构师或只读盘点补证据。

不得在本目录中使用未经负责人确认的 final、approved 或 ready 语义。
