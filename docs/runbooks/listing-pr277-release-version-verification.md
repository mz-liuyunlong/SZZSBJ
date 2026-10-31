# Listing PR #277 运行版本核对（LM-008）

状态：供获授权运维在维护窗口执行的只读门禁；本 PR 未连接或切换生产服务。

## 为什么要核对进程

代码 checkout 的 HEAD、较新的 Release 目录和前端构建存在，均不能证明 Backend、Celery Worker、Celery Beat 实际使用该版本。必须核对运行进程的工作目录、systemd 有效启动路径以及数据库 Revision。历史进程截图不代表当前状态。

## 输入和停止条件

由已经批准的发布记录提供实际的 `PROJECT_ROOT`、`BACKEND_UNIT`、`WORKER_UNIT`、`BEAT_UNIT`、目标完整 SHA、制品哈希和目标 Alembic Revision。核对它们与当前服务器身份一致后再执行命令。缺少任何输入、哈希不符或服务不属于本项目时停止；不从目录名推断版本，不猜数据库名。

## 只读检查

1. 校验源码包和前端包哈希，并记录发布记录中的目标完整 SHA。
2. 在实际 checkout 记录 HEAD 与脏文件；这只是代码来源证据，不是运行版本证据。
3. 对三个 unit 分别读取 `ActiveState`、`MainPID`、`WorkingDirectory`。对非零 PID 读取 `/proc/<pid>/cwd`，并核对有效 `ExecStart` 路径是否属于同一个已核验 Release。不要打印 EnvironmentFile 内容、完整环境变量或进程命令行参数。
4. 由已核实的数据库只读连接查询 `alembic_version`，要求恰好一行。用候选 Release 的 Alembic 执行不连接数据库的 `heads` 和 `history`，要求唯一 Head，并审阅当前到目标的迁移链。
5. 若数据库尚未达到目标代码要求的 Revision，或已超出目标代码迁移链，禁止切换服务；迁移及停写需独立授权。不得手改 `alembic_version`。
6. 只读核对 `/health` 和必要 Listing API；页面 HTTP 200 不能替代进程与数据库核验。

以下命令仅在输入值已经由发布记录核实且目标服务器身份确认后执行：

```bash
cd "$PROJECT_ROOT"
git status --short --untracked-files=all
git branch --show-current
git rev-parse HEAD

for unit in "$BACKEND_UNIT" "$WORKER_UNIT" "$BEAT_UNIT"; do
  state=$(systemctl show -P ActiveState "$unit")
  pid=$(systemctl show -P MainPID "$unit")
  configured_dir=$(systemctl show -P WorkingDirectory "$unit")
  printf '%s state=%s pid=%s configured_dir=%s\n' "$unit" "$state" "$pid" "$configured_dir"
  if [ "$pid" -gt 0 ]; then
    printf 'actual_cwd=%s\n' "$(readlink -f "/proc/$pid/cwd")"
  fi
done
```

运维还需查看三个 unit 的有效 `ExecStart` 路径。`MainPID=0`、路径不符、三项版本不一致或无法证明制品哈希时，发布验收为 **NO-GO**。

确认数据库身份与只读访问权限后，执行：

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT count(*) AS revision_rows,
       min(version_num) AS current_revision,
       max(version_num) AS same_revision_check
FROM alembic_version;
ROLLBACK;
```

`revision_rows` 必须等于 1。不得运行 `upgrade`、`stamp` 或 `downgrade` 完成这项核对。

## 交付

记录每个 unit 的实际 CWD、有效启动路径、已核验制品 SHA、唯一数据库 Revision、目标 Head、迁移链兼容结论和检查时间。缺任一证据，LM-008 仍为待验收；本文件不授权部署、重启、迁移或生产写入。
