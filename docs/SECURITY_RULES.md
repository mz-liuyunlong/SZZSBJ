# 安全规则

## 绝对禁止提交

- `.env`
- `.env.local`
- `.env.production`
- 数据库密码
- OpenAI API Key
- Walmart API Key
- GitHub Token
- SSH 私钥
- 服务器密码
- Cookie
- Session
- 本地数据库文件
- 日志中的敏感信息

## 如果发现敏感信息

AI 必须：

1. 停止提交。
2. 不输出完整密钥。
3. 告知用户风险。
4. 建议从 Git 中移除敏感文件。
5. 建议改用 `.env.example`。

## 前端安全

前端禁止保存或暴露：

- 模型 API Key
- 平台 API Key
- 数据库连接信息
- 服务器密码
- 私钥

## 后端安全

敏感配置必须从环境变量或安全配置系统读取，不得硬编码在代码中。

日志不得输出完整请求凭证、Token、Cookie、Session、密钥、密码。
