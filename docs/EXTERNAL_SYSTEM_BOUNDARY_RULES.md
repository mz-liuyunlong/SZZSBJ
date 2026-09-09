# External System Boundary Rules

## Required Rules

- 每个外部系统必须有明确 provider、owner、用途、环境、auth/secret_ref、允许读写方向、数据范围和退出策略。
- “文档存在”不等于接口可用或获批；离线资料只能作为候选证据。
- 飞书表格可作为人工查看副本/镜像，不是仓库规则、接口登记或权威业务数据的默认真源。
- 外部系统不可成为未声明的 fallback、第二权威源或事务的一部分。
- 写操作、Webhook、通知、OAuth、机器人、浏览器自动化和 production 验证分别需要 PRP 与负责人授权。
- 失败、延迟和 schema 变化不得静默改变新系统数据。

新增连接必须更新 Data Interface Registry；真实调用和凭据使用必须另行授权。
