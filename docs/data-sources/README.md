# 数据源候选映射

本目录保存旧库、外部 API、新系统页面之间的数据源候选映射。这里的内容默认是草稿和分析依据，不是最终架构批准。

## 使用边界

- 数据源映射是候选 / 草稿。
- 旧库、领星 API 和新系统数据源必须分别标记。
- 未确认字段必须标记“待确认”。
- 财务字段不得自行推导公式。
- 时间字段必须注明时区状态。
- 映射文件不是最终架构批准。
- 任何真实 API 接入、数据库迁移或业务接口实现必须另行 PRP。

## 当前文件

- `lingxing-walmart-api-to-system-data-map-draft.md`
- `lingxing-walmart-api-to-system-data-map-draft.csv`

## 状态说明

- `draft_candidate`：候选草稿，仅供讨论和盘点。
- `unverified` / `未验证`：尚未做真实 API 或旧库字段验证。
- `待确认`：需要负责人、架构师或只读盘点补证据。

不得在本目录中使用未经负责人确认的 final、approved 或 ready 语义。
