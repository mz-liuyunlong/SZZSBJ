# 最终迁移就绪检查清单

| 检查项 | 结果 | 计数 |
|---|---|---:|
| .DS_Store | 通过 | 0 |
| __MACOSX | 通过 | 0 |
| .env / .env.* | 通过 | 0 |
| node_modules / dist / build 等目录 | 通过 | 0 |
| source 内 SQL | 通过 | 0 |
| 数据库文件 | 通过 | 0 |
| 密钥/证书文件 | 通过 | 0 |
| 未脱敏短 Sheet ID / 内部资源标识 | 通过 | 0 |
| 未脱敏飞书 wiki/docs/bitable 资源 URL | 通过 | 0 |
| schema-only SQL 存在 | 通过 | 1 |
| schema-only SQL 语句级 DML | 通过 | 0 |

说明：字段定义中的 `ON UPDATE CURRENT_TIMESTAMP` 不按语句级 DML 统计。

结论：建议人工复查报告后迁入 `SZZSBJ/old-system/`。
