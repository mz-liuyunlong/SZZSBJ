# 集成配置与密钥安全规则

## 1. 放置位置

AI Token、飞书 Webhook、外部 API Key、App Secret 等敏感配置统一放在：

```text
⚙️ 设置 → 系统配置 → 集成配置
```

不新增第二套后台系统。

## 2. 权限点

```text
settings.integration_config.view
settings.integration_config.edit
settings.secret.manage
settings.secret.rotate
settings.secret.test
settings.ai_provider.manage
settings.notification_channel.manage
```

默认只给超级管理员，但代码不写死角色名，最终由 permissionKey 控制。

## 3. 展示规则

可以展示：

```text
配置名称
服务商
用途模块
启用状态
创建人
更新时间
最后测试时间
最后使用时间
Token 后 4 位 / masked_value
今日调用量
月度预算
失败次数
```

禁止展示：

```text
完整 Token
API Key
App Secret
Webhook Secret
数据库密码
JWT Secret
.env 真实值
```

## 4. 存储规则

```text
Token 不允许写死在代码里
Token 不允许提交到 Git
Token 不允许进入前端构建产物
Token 不允许通过 API 明文返回给前端
Token 必须服务端加密存储
页面保存后只显示脱敏值
替换 Token 必须重新输入完整值
Token 变更必须写审计日志
```

## 5. AI 服务配置

必须支持：

```text
服务商
Base URL
默认模型
备用模型
API Key secret_id
用途模块
是否启用
每日调用上限
每月费用上限
单任务最大 token
模型白名单
超额处理方式
最后测试时间
状态
```

## 6. 飞书通知配置

通知渠道和通知规则分开。

渠道：

```text
群名称
Webhook URL secret_id
Secret secret_id
启用状态
最后测试时间
失败次数
```

规则：

```text
库存预警 → 库存预警群
同步失败 → 系统异常群
广告异常 → 广告运营群
审批待处理 → 管理审批群
AI任务完成 → AI通知群
财务重算完成 → 财务群
```

一个事件可以发到多个渠道，一个渠道也可以接收多个事件。

## 7. 审计规则

所有密钥相关操作都要记录：

```text
新增 Token
替换 Token
停用 Token
测试 Token
修改飞书群
修改 AI 默认模型
修改费用上限
修改用途模块
```

审计日志不得记录完整密钥。
