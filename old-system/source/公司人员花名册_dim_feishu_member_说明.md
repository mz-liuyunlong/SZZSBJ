# 公司人员花名册 dim_feishu_member（统一基础数据）

## 它是什么
全公司"姓名 → 飞书 open_id"的统一名册。任何与人相关的项目，都从这里取 open_id（用于私聊、@、归属等），不要再各自手工维护一份。

## 存在哪里
- 数据库：MySQL `walmart_ai_data`（服务器 127.0.0.1:3306）
- 表名：`dim_feishu_member`
- 字段：
  - `open_id` VARCHAR(64) 主键 —— 飞书用户 open_id
  - `name` VARCHAR(128) —— 飞书显示名
  - `updated_at` TIMESTAMP —— 最近刷新时间（自动）

## 数据从哪来 / 多久更新
- 来源：公司总群成员名单（chat_id `oc_6b819b42aab6efe7a60ef9b008a2fd90`），通过飞书应用 `cli_aab5fe407d395bd5` 拉取。
- 刷新脚本：`/opt/lingxing-auto/src/refreshFeishuMembers.ts`
  - 手动：`cd /opt/lingxing-auto && npx ts-node src/refreshFeishuMembers.ts --write`
  - 自动：crontab 每天 08:50 跑一次（`/var/log/refresh-feishu-members.log`）
- 重名处理：同名多人会被**跳过**（记日志），不写入，避免发错人。需要时在手工表里单独指定。

## 任何项目怎么用
```sql
SELECT name, open_id FROM dim_feishu_member;
```
按姓名查 open_id 即可。新人只要被拉进公司总群，次日 08:50 自动出现在这张表里。

## 与不出单通知的关系
不出单脚本 `noOrderNotify.ts` 取 open_id 的顺序：
1. 先读 `dim_feishu_member`（全员名册，含新人）作底；
2. 再用手工表 `config/ownerOpenIds.json` 覆盖（手工优先，用于重名/特例）；
3. 仍查不到 open_id 的负责人 → 消息回落到原飞书群。

## 注意
- `dim_feishu_member` 是"基础数据表"，不要随意 DROP / TRUNCATE。
- 飞书 App Secret 仅存服务器 `.env`，不要外泄；如泄露请在飞书后台重置后只更新 `.env`。
- open_id 按应用隔离：这张表里的 open_id 属于应用 `cli_aab5...`，换应用需重新拉取。
