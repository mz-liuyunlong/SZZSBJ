# Notification Boundary Rules

## Required Rules

- 通知不是业务状态；发送成功不等于业务处理成功。
- 通知失败默认不回滚核心业务事务，除非获批 PRP 明确要求并证明一致性方案。
- 每次发送有 `notification_id` 并可追溯 source event、template/version、recipient scope、attempt 和结果。
- 消息不得泄露 secret、敏感字段或越权数据。
- 必须有去重、冷却、限流和失败重试，禁止重复轰炸。
- 人工点击并通过后端鉴权确认后才算确认；消息发出或送达不算业务确认。
- 通道 credential 只保存 `secret_ref`，前端不可见。

真实飞书/企业微信/Webhook 接入、交互卡片和审批均需要独立 PRP 与负责人授权。
