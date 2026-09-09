# Read / Write Permission Boundary Rules

Read access does not imply write permission.

- 可以读取 docs，不代表可以修改 docs。
- 可以读取 `old-system/`，不代表可以修改、运行或复制它。
- 可以读取 frontend/backend，不代表可以修改相应代码。
- 可以读取数据库文档，不代表可以连接数据库或执行 SQL。
- 可以分析接口文档，不代表可以调用接口。
- 可以查看 Git 状态/diff，不代表可以暂存、提交、push、merge 或清理分支。
- PRP Approved 不自动授权实现；实现 Prompt 不自动授权生产操作。

每次从 read 到 write、analysis 到 approval、local 到 production 都必须有当前任务明确授权；边界不清时停止。
