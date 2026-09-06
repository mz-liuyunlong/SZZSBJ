# 领星 Walmart OpenAPI 精简只读参考资料

本目录是本项目内的领星 Walmart OpenAPI 精简只读参考资料。它用于后续数据源评估、接口候选筛选和 PRP 设计，不是运行时代码、不是官方事实权威，也不能直接生成后端接口。

## 来源与状态

| 项目 | 状态 |
|---|---|
| 资料来源 | 负责人提供的 `lingxing-walmart` 精简资料包 |
| 快照日期 | 待确认 |
| 官方文档版本 | 待确认 |
| 项目整理日期 | 2026-09-05 |
| 导入范围 | 精简索引与项目决策说明 |
| 完整原始包 | 未导入本仓库 |

> `normalized/` 文件是整理后的派生索引，不是官方文档或事实权威。使用任何接口前，必须重新核对官方文档、认证方式、限流、错误码、费用、字段含义和账号权限。

## 目录结构

```text
docs/integrations/lingxing-walmart-openapi/
├── README.md
├── phase-1-candidate-apis.md
├── phase-1-candidate-apis.csv
├── do-not-use.md
├── api-verification-status.csv
└── normalized/
    ├── interfaces.csv
    ├── request_params.csv
    ├── response_fields.csv
    ├── module_mapping.csv
    └── deleted_interfaces.csv
```

相关数据源候选映射位于：

```text
docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.md
docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.csv
```

## 当前索引统计

| 项目 | 数量 |
|---|---:|
| 保留接口 | 329 |
| 删除接口 | 335 |
| 请求参数行 | 2842 |
| 响应字段行 | 12050 |
| 抓取失败页 | 0 |
| Phase 1 候选映射行 | 163 |
| Phase 1 去重候选接口 | 103 |

## AI 读取顺序

1. 先读本文件。
2. 再读 `do-not-use.md`。
3. 再读 `normalized/deleted_interfaces.csv`。
4. 再读 `phase-1-candidate-apis.md`。
5. 再读 `api-verification-status.csv`。
6. 最后按需查询 `normalized/*.csv`。
7. 如涉及旧库、新系统页面或后端 API 设计，必须同时查看 `docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.*`。

## 语义约束

- candidate 不等于 approved。
- verification status 不等于开发批准。
- `do-not-use.md` 和 `normalized/deleted_interfaces.csv` 是最高优先级禁止清单。
- deleted interface 默认禁止重新接入。
- 接口存在不代表新系统需要开发。
- 文档存在不代表接口实际可用，也不代表当前账号有权限。
- 文档存在不代表旧系统正在使用；旧系统实际使用情况必须结合 `old-system/` 源码、cron、数据库表、同步脚本和生产只读盘点确认。
- 当前资料不得驱动前端直接调用外部 API。

## 接入前强制要求

任何真实领星 API 接入前，必须另行完成：

1. PRP。
2. 官方文档复核。
3. 账号权限与认证方式确认。
4. 限流、分页、错误码和重试策略设计。
5. 数据范围、时区、金额、币种和字段口径确认。
6. 安全边界和审计日志设计。
7. 后端任务拆分和测试计划。
8. 负责人明确批准。

## 推荐使用方式

1. 先做服务器旧库只读盘点，确认现有数据表、更新频率、当前页面/API/cron 依赖。
2. 再维护 `docs/data-sources/lingxing-walmart-api-to-system-data-map-draft.*`，判断每类数据短期读旧库、长期新系统重新拉取，还是归档观察。
3. 只从候选接口中选择只读、低风险、可验证的接口进入 PRP。
4. 写入类接口、平台改价、上传、删除、创建、批量更新接口一律暂缓。

## 不要混淆三类证据

| 资料 | 能证明什么 | 不能证明什么 |
|---|---|---|
| 本目录 OpenAPI 索引 | 领星文档中可能存在的接口 | 旧系统实际使用、账号权限、字段完整性 |
| `old-system/` 源码 | 旧系统代码如何调用或计算 | 当前生产实时运行状态 |
| 服务器数据库只读盘点 | 当前旧库有哪些表、大小、更新时间 | 数据来自哪个 API 的完整链路 |

## 维护规则

- 不要直接修改 `normalized/` 下的来源索引；如需更新，应重新生成资料包并整体替换。
- 新增实测结果时，只更新 `api-verification-status.csv`、PRP 和数据源映射文件。
- 如负责人要求保留原始完整快照，应放在本地归档或外部资料库，不建议进入项目仓库。
