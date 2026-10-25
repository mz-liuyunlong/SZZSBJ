# Listing 规则配置 — 四模块增量实现与隔离验收

## 功能交付边界

在原「Listing管理 → 规则配置」抽屉，新增并持久化四组配置：

1. 等级评级：7/14、60/40、4/8、A/B/C/D毛利率阈值、参与生命周期。
2. 生命周期：每周有效有货日、30天各阶段有效天数、5档上升/下降幅度及5档稳定波动。
3. 库存与修复：WFS低库存阈值、连续断货天数、长期断货门槛、断货修复日、划线价与购物车异常门槛、连续恢复日。
4. 运营跟进：可选每日提醒时间、完成截止时间、逾期通知开关。固定每天跟进C/D、D优先且无需每天修改广告。未设截止时间时不允许启用逾期通知。

基础规则保持受保护：中国22:30、洛杉矶业务日期T-2、广告及必要费用不完整不能按0、清货期与已归档永久排除、生命周期与等级相互独立。

所有配置都保存在既有 biz_listing_grade_rule_versions.config_json 的单份完整JSON中（字段名兼容原表，虽然名称含 grade，新字段合并放在同一版本）。保存会产生新的不可变全局版本及操作人/时间/原因；不会更新现有评级、销量趋势、库存状态、跟进任务、定时任务或生产报表。这次只构建**规则配置能力**，未来计算服务消费这些参数需要独立开发和回归验收。运营提醒当前仅保存参数，不会自动通知。

## 隔离本地 PostgreSQL 测试库

前置条件：Docker Desktop、PostgreSQL客户端、项目开发依赖。**不要使用原来的「限定业务写入」启动脚本验收保存**，它通过127.0.0.1:15432连接生产数据库隧道，且权限策略主动阻止此类写入。

在项目根目录：

```bash
docker compose -f infra/local-listing-rules/compose.yaml up -d
docker compose -f infra/local-listing-rules/compose.yaml ps
```

专用数据库端口 **127.0.0.1:55432**，数据库 `listing_rules_dev`，仅绑定本机，不使用生产账号、令牌或服务器连接。**不要把原脚本复制到这个环境运行**。

运行任何 Alembic 前，单独在终端设置本地测试环境（不要覆盖已有启动脚本的进程）：

```bash
cd backend
export APP_ENV=test
export TEST_DATABASE_URL='postgresql+psycopg://listing_rules_dev:local_testing_only@127.0.0.1:55432/listing_rules_dev'
export DATABASE_URL="$TEST_DATABASE_URL"
export CELERY_BROKER_URL='memory://'
export LINGXING_ENABLE_REAL_CALLS=false
export LINGXING_ENABLE_TOKEN_REQUESTS=false
export DATA_PAGES_REAL_SYNC_AUTHORIZED=false

python3 - <<'PY'
import os
from sqlalchemy.engine import make_url
u = make_url(os.environ["DATABASE_URL"])
assert os.environ["APP_ENV"] == "test"
assert (u.host, u.port, u.database, u.username) == (
    "127.0.0.1", 55432, "listing_rules_dev", "listing_rules_dev")
print("ISOLATED_DB_GUARD=PASS")
PY

uv run alembic upgrade head
uv run pytest tests/modules/listing_rule_config/ -v
```

如果旧迁移链无法从全新数据库执行，请保留迁移错误并在 PR 中修复；**不得**把生产表复制过来、不得修改本地15432隧道，也不得手工修改生产库。

## 安全与权限验收

- 可登录的**本地测试用户及角色**仍需在隔离数据库里通过仓库IAM初始化流程准备。不可将生产访问令牌复制至开发库。
- 仅有 `page:products:listing-management:view` 的账号应只读；编辑需要 `action:products:listing-management:configure-rules`。
- 原固定生产隧道脚本的登录和看板继续工作，但配置界面必须保持只读。
- 新版使用原有 `GET/PUT /api/listings/rule-config` 与 `GET /history`，统一 envelope，不扩展外部调用权限。
- 在本地独立启动测试后端及前端后验证：4组能编辑、保存成功产生v1、历史保留、重复保存返回409、非法参数422、无权限403、生产隧道不可写。
- 如果独立数据库中无商品数据，不影响规则配置 API 测试；Listing业务表暂无数据属预期。不要用真实SKU和店铺资料做测试。
- 迁移与测试完成后，可用 `docker compose -f infra/local-listing-rules/compose.yaml down` 关闭容器（不要加 `-v`，除非确认删除测试数据）。

## 本地代码检查

```bash
cd frontend
npm run build
npm run lint
npm run test -- --run
cd ../backend
uv run ruff check app/modules/listing_rule_config tests/modules/listing_rule_config
uv run pytest tests/modules/listing_rule_config -v
```

**重要：** 部署或定时任务消费新配置不在本 PR 范围内。未实测通过之前，不合并、不部署。
