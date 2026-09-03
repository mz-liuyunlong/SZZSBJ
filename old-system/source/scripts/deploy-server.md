# 服务器部署准备

本项目后续在服务器执行每日同步。当前还没有服务器 SSH 信息，所以这里先提供部署步骤和配置清单，不直接部署。

## 需要你补充

- 服务器 IP
- SSH 用户名
- 部署目录，例如 `/opt/lingxing-daily`
- 服务器系统时区，建议设置为 `Asia/Shanghai`
- 领星开放平台服务器 IP 白名单

## 服务器要求

- Node.js >= 18
- npm 或 pnpm
- 可执行 `bash`
- 已配置飞书 `lark-cli`
- 能访问领星 OpenAPI 和飞书 OpenAPI

## 部署步骤

1. 上传项目到服务器部署目录。

2. 安装依赖：

```bash
npm install
```

3. 创建 `.env`，不要把密钥写进代码：

```bash
cp .env.example .env
nano .env
```

必须配置：

```bash
LINGXING_BASE_URL=https://openapi.lingxing.com
LINGXING_APP_ID=你的AppID
LINGXING_APP_SECRET=你的AppSecret
LINGXING_TIMEOUT_MS=120000
ENABLE_AI_DIAGNOSIS=false
```

如果启用小龙虾 AI：

```bash
ENABLE_AI_DIAGNOSIS=true
XIAOLONGXIA_AI_ENDPOINT=正式接口地址
XIAOLONGXIA_AI_API_KEY=正式密钥
```

4. 配置飞书 CLI：

```bash
./scripts/lark-cli --version
./scripts/lark-cli auth status
```

如果未授权，按飞书 CLI 授权流程重新登录。

5. 验证：

```bash
npm run typecheck
npm run auto:daily -- --dry-run
```

6. 安装每天中国时间 17:00 定时任务：

```bash
PROJECT_DIR="/opt/lingxing-daily" bash scripts/install-daily-automation-cron.sh
```

该定时任务执行：

```bash
npm run auto:daily -- --confirm-write
```

## PM2 可选

本项目主要靠 cron 触发，不需要常驻服务。`ecosystem.config.js` 只用于服务器上手动执行或排查：

```bash
npx pm2 start ecosystem.config.js --only lingxing-auto-daily
npx pm2 logs lingxing-auto-daily
```

## 安全边界

- 不提交 `.env`
- 不把 AppSecret、Token、AI Key 写死进代码
- `auto:daily` 只追加/去重写新销售明细 `<REDACTED_FEISHU_SHEET_ID>`
- 不再写旧的 `5月销售明细`
- 只有 `rebuild:sales-detail` 才允许全量覆盖销售明细
- `ENABLE_AI_DIAGNOSIS=false` 时不调用小龙虾 AI
