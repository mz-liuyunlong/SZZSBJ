# 环境变量与配置规则

## 文件用途

本文件用于约束项目环境变量、配置文件和不同环境的管理方式。

## 总原则

1. 真实密钥不进入 Git。
2. 必须提供 `.env.example`，只写变量名和示例说明。
3. 前端只能读取公开配置，不得读取密钥。
4. 后端读取数据库、Redis、Celery、OpenAI、平台 API 等敏感配置。
5. 不允许在代码里硬编码数据库地址、API Key、Token、服务器密码。

## 前端环境变量

前端变量必须是可公开的，例如：

```text
VITE_API_BASE_URL=
VITE_APP_NAME=
```

前端禁止保存：OpenAI API Key、平台 API Key、数据库连接、服务器密码、私钥。

## 后端环境变量

建议：

```text
APP_ENV=
DATABASE_URL=
REDIS_URL=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
OPENAI_API_KEY=
SESSION_SECRET=
```

## 环境区分

推荐区分：

```text
local
staging
production
```

AI 不允许把 production 配置复制到本地文档或日志中。
