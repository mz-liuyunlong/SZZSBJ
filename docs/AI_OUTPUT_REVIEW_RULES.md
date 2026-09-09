# AI Output Review Rules

## Required Rules

- AI 输出默认是 `candidate/suggestion`，不是事实真源、批准或执行命令。
- AI 不得直接修改权威业务数据，或自动改变价格、广告、Listing、库存、权限和财务结果。
- 采纳必须由有权限人员明确确认，并产生独立 action/audit。
- 每次受治理 AI 输出记录 input snapshot/reference、prompt/template version、model/version、citation、operator、permission/data scope、cost 和 review status。
- AI 不得读取 RAW、secret、越权字段、未批准来源或超出用途的数据。
- 引用必须回到可访问的权威来源；生成文本不能成为自己的证据。
- Prompt injection、敏感信息、模型失败和不确定性必须纳入测试和人工 Review。

每个真实 AI use case 需要独立 PRP、预算、模型白名单、保留策略和负责人批准。
