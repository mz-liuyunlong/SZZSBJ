# Code Comment and Docstring Rules

## Purpose

只在维护者需要业务或风险上下文的位置写注释；不做全项目机械补注释。

本文件补充 `docs/CODE_COMMENT_RULES.md`；如旧示例要求机械注释，以“必要、可维护、不重复代码”的本规则为准。

## Required Comments

业务逻辑、财务/利润/费用/佣金、库存/补货、广告、权限/data scope、同步、字段映射、人工覆盖、事务边界和 AI 输出必须用注释或 docstring 说明适用的：why、business boundary、risk、source、rule version、side effect。

- Backend service：输入、输出、业务边界、事务和副作用。
- Repository：查询 grain/性能，并明确不 commit、不做权限判断、不调用外部 API、不访问 legacy MySQL runtime source。
- Task：幂等键、重试、停止条件、run/batch、发布边界。
- Permission helper：资源、permission key、fail-closed 条件。
- Frontend 临时能力：明确标记 `mock-only`、`no-api page shell`、`display-only estimate`、`not authoritative` 或 `future API boundary`。
- 金额/规则计算：`currency_code`、Decimal/Numeric、`rounding_rule`、`rule_version`、effective date、grain、历史重算边界。

## Forbidden Patterns

- 只翻译代码，例如“设置 loading 为 true”。
- 与实现不一致、过期或承诺 future scope 的注释。
- 用 TODO 代替边界、测试、安全或负责人决定。
- 在注释/docstring 中记录 secret、连接串或生产数据。

PR 可因缺少必要维护型注释被拒绝；简单、自解释且无业务风险的代码无需废话注释。
