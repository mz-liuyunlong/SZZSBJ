# Documentation Lifecycle Rules

## Required Rules

- 文档必须标明适用的 status、scope、owner 和实现证据；不把未来设计写成已实现。
- PRP、ADR、registry、catalog、contract、SOP 和运行手册各有独立职责，互相链接而不复制第二套真源。
- 代码/接口/表/页面/任务变更必须在同 PR 更新触发的文档。
- 被取代文档保留历史并标记 `superseded/historical_reference_only`，链接新权威文档。
- 固定文件引用必须存在；重命名/移动需更新入口并检查死链接。
- 文档不得保存 secret、生产数据样本或未经批准的事实。
- 定期 Review owner、状态、链接和实现漂移；过期不等于可删除。

GitHub 仓库是规则和 registry 真源；聊天或外部表格不是最终记录。
