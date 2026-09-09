# Human / AI Decision Boundary Rules

## AI May

分析仓库证据、提出候选方案、实现已批准范围、运行已授权验证并如实报告。

## AI May Not Decide

AI 不能替负责人做业务口径、技术栈、数据真源、权限、上线或高风险变更决定，也不能把建议当执行命令。

必须由负责人批准：

- 新增、删除或重命名导航。
- 新增核心业务字段。
- 修改利润、费用、佣金、库存、广告或财务口径。
- 接入真实外部 API或连接真实数据库。
- 执行 migration、回填、重算或生产变更。
- 修改权限模型、CI、部署或生产配置。
- 删除旧代码、旧字段或旧文档。

## Stop Boundary

从分析到批准、建议到执行、planned 到 implemented、mock 到真实数据、当前到 future scope 时必须停止并取得明确授权。
