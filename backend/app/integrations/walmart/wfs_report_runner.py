"""WFS 费用报表：生产服务器上的远端执行（Rocky 2026-11-13 批准；默认关闭）。

每次运行、每个店：
  1. SSH 到这家店的路由服务器（沿用沃尔玛远程采集的路由 SZZSBJ_WALMART_REMOTE_ROUTES，
     同样只认已批准的店）；
  2. 原子 mkdir 加锁（同一 run_id 不重入），上传执行器 wfs_report_engine.py 和本次计划，
     逐个核对 sha256；
  3. 锁和上传都好了才去要短期令牌，令牌只走标准输入，不进命令行 / 文件 / 日志；
  4. 执行器跑完（只会做 白名单里的 list / submit / fetch），把结果目录拉回本机，
     按 SHA256SUMS 逐个核对；
  5. 删掉远端这次的目录和锁。执行器每次重新上传，店铺服务器上不安装任何东西。

开关：SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED=1 且 SZZSBJ_WALMART_WFS_REPORTS_ENABLED=1。
任何一步不对都抛 DispatchRejected（固定错误码，不带远端输出）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.integrations.walmart import wfs_report_engine as engine
from app.integrations.walmart.legacy_execution import _exec, _ssh
from app.integrations.walmart.remote_dispatch import (
    REMOTE_COLLECTION_STORES,
    RUN_PATTERN,
    DispatchRejected,
    WorkerRoute,
    parse_routes,
)

REMOTE_BASE = "/tmp/szzsbj-wfs-reports"
ENGINE_FILE = Path(engine.__file__)
ENGINE_TIMEOUT = 900
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
EXIT_OK_CODES = (engine.EXIT_OK, engine.EXIT_PARTIAL, engine.EXIT_TOKEN)
SUM_LINE = re.compile(r"^([a-f0-9]{64})  ([A-Za-z0-9_./-]+)$")


@dataclass(frozen=True)
class RemoteReportResult:
    """执行器的 results.json + 本机核对过的文件目录（调用方读完自己删）。"""

    exit_code: int
    results: list[dict[str, Any]]
    files_dir: Path
    local_dir: Path  # 这次拉回来的整个临时目录，用完删掉


def enabled() -> bool:
    return (
        os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") == "1"
        and os.getenv("SZZSBJ_WALMART_WFS_REPORTS_ENABLED") == "1"
    )


def approved_routes() -> dict[str, WorkerRoute]:
    """已批准的店 → 路由；没开 / 配置不全就抛错，不退而求其次。"""
    if not enabled():
        raise DispatchRejected("WFS_REPORTS_DISABLED")
    routes = parse_routes(os.getenv("SZZSBJ_WALMART_REMOTE_ROUTES", ""))
    allowed = frozenset(
        code.strip()
        for code in os.getenv("SZZSBJ_WALMART_REMOTE_APPROVED_STORES", "").split(",")
        if code.strip()
    )
    if not allowed or not allowed <= REMOTE_COLLECTION_STORES:
        raise DispatchRejected("REMOTE_STORE_NOT_APPROVED")
    return {code: route for code, route in routes.items() if code in allowed}


def store_token_supplier(store_code: str) -> Callable[[], str]:
    """和远程采集同一套：腾讯云角色 → 云函数换这家店的短期令牌。"""
    from app.integrations.walmart.scf_read_factory import RefreshingScfApi
    from app.integrations.walmart.tenc_sts_identity import CachedScfAssumeRoleIdentity
    from app.integrations.walmart.token_client import store_token_invoker

    cvm_role = os.getenv("SZZSBJ_WALMART_SCF_CVM_ROLE", "")
    target_role = os.getenv("SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN", "")
    if not cvm_role or not target_role:
        raise DispatchRejected("REMOTE_CLOUD_IDENTITY_MISSING")
    allowed = frozenset(approved_routes())

    def obtain() -> str:
        cloud_api = RefreshingScfApi(
            CachedScfAssumeRoleIdentity(cvm_role=cvm_role, target_role_arn=target_role)
        )
        token = store_token_invoker(
            cloud_api=cloud_api, store_code=store_code, authorized_stores=allowed
        )
        return token.access_token

    return obtain


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _upload(host: str, local: Path, remote: str) -> None:
    rc, _ = _exec(["scp", *SSH_OPTS, "--", str(local), host + ":" + remote], timeout=120)
    if rc != 0:
        raise DispatchRejected("WFS_REPORTS_UPLOAD_FAILED")
    rc, raw = _ssh(host, ["sha256sum", "--", remote])
    if rc != 0 or not raw.startswith(_sha256(local) + " "):
        raise DispatchRejected("WFS_REPORTS_UPLOAD_HASH_MISMATCH")


def _verify_sums(out_dir: Path) -> None:
    """拉回来的每个文件都要在 SHA256SUMS 里、哈希一致；多一个少一个都不认。"""
    sums = out_dir / "SHA256SUMS"
    if not sums.is_file() or sums.is_symlink():
        raise DispatchRejected("WFS_REPORTS_SUMS_MISSING")
    listed: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = SUM_LINE.match(line)
        if match is None or ".." in Path(match.group(2)).parts:
            raise DispatchRejected("WFS_REPORTS_SUMS_INVALID")
        listed[match.group(2)] = match.group(1)
    present = {
        str(path.relative_to(out_dir))
        for path in out_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if any(path.is_symlink() for path in out_dir.rglob("*")) or present != set(listed):
        raise DispatchRejected("WFS_REPORTS_FILES_MISMATCH")
    for name, digest in listed.items():
        if _sha256(out_dir / name) != digest:
            raise DispatchRejected("WFS_REPORTS_FILE_HASH_MISMATCH")


def run_plan(
    *,
    route: WorkerRoute,
    run_id: str,
    plan: dict[str, Any],
    token_supplier: Callable[[], str],
    local_root: Path,
) -> RemoteReportResult:
    """在这家店的服务器上跑一次计划。不自动重试：沃尔玛下单每小时一次，重试交给下一轮。"""
    if not RUN_PATTERN.fullmatch(run_id):
        raise DispatchRejected("REMOTE_RUN_INVALID")
    if plan.get("store_code") != route.store_code:
        raise DispatchRejected("WFS_REPORTS_PLAN_STORE_MISMATCH")
    host = route.ssh_host
    lock = REMOTE_BASE + "/.runs/" + run_id
    run_dir = REMOTE_BASE + "/" + run_id
    if _ssh(host, ["true"], timeout=30)[0] != 0:
        raise DispatchRejected("REMOTE_UNREACHABLE")
    if _ssh(host, ["mkdir", "-p", REMOTE_BASE + "/.runs"])[0] != 0:
        raise DispatchRejected("REMOTE_LOCK_ROOT_FAILED")
    if _ssh(host, ["mkdir", lock])[0] != 0:  # 不带 -p：已有同名锁就不进
        raise DispatchRejected("REMOTE_ALREADY_RUNNING")
    try:
        if _ssh(host, ["mkdir", "-p", run_dir])[0] != 0:
            raise DispatchRejected("REMOTE_RUN_DIR_FAILED")
        with tempfile.TemporaryDirectory(prefix="wfs-plan-") as temporary:
            plan_file = Path(temporary) / "plan.json"
            plan_file.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            _upload(host, ENGINE_FILE, run_dir + "/wfs_report_engine.py")
            _upload(host, plan_file, run_dir + "/plan.json")
        token = token_supplier()
        if not isinstance(token, str) or not 1 <= len(token) <= 8192:
            raise DispatchRejected("REMOTE_TOKEN_UNAVAILABLE")
        try:
            engine_rc, _ = _ssh(
                host,
                [
                    "python3",
                    run_dir + "/wfs_report_engine.py",
                    "--plan",
                    run_dir + "/plan.json",
                    "--out",
                    run_dir + "/out",
                    "--token-stdin",
                ],
                data=token + "\n",
                timeout=ENGINE_TIMEOUT,
            )
        finally:
            del token
        if engine_rc == engine.EXIT_SAFETY:
            raise DispatchRejected("WFS_REPORTS_ENGINE_REFUSED")
        if engine_rc not in EXIT_OK_CODES:
            # 可能超时、执行器还在跑：不标结果，下一轮再看（下单前会先查已有请求，不会重复下单）。
            raise DispatchRejected("WFS_REPORTS_ENGINE_UNCONFIRMED")
        local_root.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix="wfs-" + run_id + "-", dir=local_root))
        try:
            rc, _ = _exec(
                ["scp", "-r", *SSH_OPTS, "--", host + ":" + run_dir + "/out", str(target)],
                timeout=600,
            )
            out_dir = target / "out"
            if rc != 0 or not out_dir.is_dir():
                raise DispatchRejected("WFS_REPORTS_FETCH_FAILED")
            _verify_sums(out_dir)
            doc = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
            results = doc.get("results")
            if not isinstance(results, list) or doc.get("store_code") != route.store_code:
                raise DispatchRejected("WFS_REPORTS_RESULTS_INVALID")
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return RemoteReportResult(
            exit_code=engine_rc, results=results, files_dir=out_dir / "files", local_dir=target
        )
    finally:
        # 远端不留东西：这次的目录和锁一起删（文件都已拉回本机核对过）。
        _ssh(host, ["rm", "-rf", "--", run_dir, lock])
