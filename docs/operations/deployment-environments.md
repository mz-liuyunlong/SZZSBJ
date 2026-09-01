# 环境规则

## 1. 环境分层

| 环境 | 用途 | 数据 |
|---|---|---|
| local | 本地开发 | mock / 脱敏样本 |
| staging | 预发布测试 | 脱敏或只读测试数据 |
| production | 生产环境 | 真实数据 |

## 2. 禁止事项

```text
local 不允许连接生产写库
staging 不允许使用真实密钥直接调用外部平台，除非明确授权
production 禁止 Codex 直接操作
.env 真实值禁止提交
```

## 3. 配置规则

- 仓库只提交 `.env.example`。
- 真实值只在运行环境配置。
- 前端不得持有数据库密码、AI Token、Webhook Secret。
- 后端配置统一从 `app/core/config.py` 读取。
