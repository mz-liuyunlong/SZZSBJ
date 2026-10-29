"""Owner-controlled implementation of the original worker staging/lock protocol.

No Walmart HTTP calls and no credentials on remote disks. Requires the owner to
install the reviewed original run_worker.py as an immutable local artifact.
Tokens enter the subprocess via stdin only. No fallback destination.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.integrations.walmart.legacy_worker_contract import (
    DEFAULT_REMOTE_TMP_DIR,
    build_legacy_worker_argv,
    build_ssh_command,
)
from app.integrations.walmart.remote_dispatch import (
    RUN_PATTERN,
    DispatchRejected,
    WorkerRoute,
)
from app.integrations.walmart.remote_transfer import fetch_verified_run


def _exec(
    args: list[str], *, data: str | None = None, timeout: int = 120
) -> tuple[int, str]:
    """Never disclose stderr or remote stdout outside this protected process."""
    try:
        result = subprocess.run(
            args,
            input=data,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            env={"HOME": os.environ.get("HOME", "/nonexistent"), "PATH": "/usr/bin:/bin"},
        )
        return result.returncode, result.stdout[:16384]
    except (OSError, subprocess.TimeoutExpired):
        return 255, ""


def _ssh(host: str, argv: list[str], *, data: str | None = None, timeout: int = 120) -> tuple[int, str]:
    return _exec(
        [
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=10", "--", host, build_ssh_command(argv)
        ],
        data=data, timeout=timeout,
    )


def _state(host: str, base: str, run_id: str) -> str:
    rc, raw = _ssh(host, ["cat", base + "/.runs/" + run_id + "/state.json"])
    if rc != 0:
        return "UNKNOWN"
    try:
        item = json.loads(raw)
        state = item.get("state")
        return state if state in {"STARTING", "RUNNING", "SUCCESS", "FAILED"} else "UNKNOWN"
    except ValueError:
        return "UNKNOWN"


def _write_state(host: str, base: str, run_id: str, store_id: str, status: str) -> None:
    lock_dir = base + "/.runs/" + run_id
    if status not in {"STARTING", "RUNNING", "SUCCESS", "FAILED"}:
        raise DispatchRejected("REMOTE_STATE_INVALID")
    body = json.dumps(
        {"run_id": run_id, "store_id": store_id, "state": status}, separators=(",", ":")
    )
    temp = lock_dir + "/state.json.tmp"
    rc, _ = _ssh(host, ["tee", temp], data=body + "\n")
    if rc != 0 or _ssh(host, ["mv", "-f", "--", temp, lock_dir + "/state.json"])[0] != 0:
        raise DispatchRejected("REMOTE_STATE_WRITE_FAILED")


def _checked_worker(path: str, expected_hash: str) -> str:
    """Only a pinned original worker installed by the deployment owner."""
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
        raise DispatchRejected("REMOTE_WORKER_HASH_REQUIRED")
    local = Path(path)
    if (
        path != "/opt/szzsbj/walmart/run_worker.py"
        or local.is_symlink()
        or not local.is_file()
    ):
        raise DispatchRejected("REMOTE_WORKER_ARTIFACT_MISSING")
    hash_value = hashlib.sha256(local.read_bytes()).hexdigest()
    if hash_value != expected_hash:
        raise DispatchRejected("REMOTE_WORKER_HASH_MISMATCH")
    return hash_value


def collect_with_legacy_worker(
    *,
    route: WorkerRoute,
    store_id: str,
    run_id: str,
    operations: tuple[str, ...],
    date_iso: str,
    archive_root: Path,
    token_supplier: Callable[[], str],
    expected_worker_hash: str,
    gtin_csv: Path | None = None,
) -> dict[str, Any]:
    """One-run protocol; never automatically retries or reuses a remote lock."""
    if not RUN_PATTERN.fullmatch(run_id):
        raise DispatchRejected("REMOTE_RUN_INVALID")
    base = DEFAULT_REMOTE_TMP_DIR
    run_dir = base + "/" + run_id
    argv = build_legacy_worker_argv(
        store_id=store_id,
        run_id=run_id,
        endpoints=operations,
        date_iso=date_iso,
        gtin_file=run_dir + "/input/gtins.csv" if gtin_csv else None,
    )
    if route.worker_path != "/opt/szzsbj/walmart/run_worker.py":
        raise DispatchRejected("REMOTE_WORKER_UNVERIFIED")
    digest = _checked_worker(route.worker_path, expected_worker_hash)
    host = route.ssh_host
    if _ssh(host, ["true"], timeout=30)[0] != 0:
        raise DispatchRejected("REMOTE_UNREACHABLE")
    if _ssh(host, ["mkdir", "-p", base + "/.runs"])[0] != 0:
        raise DispatchRejected("REMOTE_LOCK_ROOT_FAILED")
    # Atomic mkdir: no -p. Existing run-id is never resumed automatically.
    if _ssh(host, ["mkdir", base + "/.runs/" + run_id])[0] != 0:
        state = _state(host, base, run_id)
        raise DispatchRejected("REMOTE_ALREADY_" + state)
    acquired = True
    in_worker = False
    try:
        _write_state(host, base, run_id, store_id, "STARTING")
        if _ssh(host, ["mkdir", "-p", run_dir])[0] != 0:
            raise DispatchRejected("REMOTE_RUN_DIR_FAILED")
        rc, _ = _exec(
            [
                "scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "--", route.worker_path, host + ":" + run_dir + "/run_worker.py"
            ],
            timeout=120,
        )
        if rc != 0:
            raise DispatchRejected("REMOTE_WORKER_UPLOAD_FAILED")
        rc, raw = _ssh(host, ["sha256sum", "--", run_dir + "/run_worker.py"])
        if rc != 0 or not raw.startswith(digest + " "):
            raise DispatchRejected("REMOTE_WORKER_UPLOAD_HASH_MISMATCH")
        if gtin_csv is not None:
            if not gtin_csv.is_file() or gtin_csv.is_symlink():
                raise DispatchRejected("REMOTE_GTIN_SOURCE_INVALID")
            if _ssh(host, ["mkdir", "-p", run_dir + "/input"])[0] != 0:
                raise DispatchRejected("REMOTE_GTIN_DIR_FAILED")
            gtin_digest = hashlib.sha256(gtin_csv.read_bytes()).hexdigest()
            rc, _ = _exec(
                [
                    "scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                    "--", str(gtin_csv), host + ":" + run_dir + "/input/gtins.csv"
                ],
                timeout=120,
            )
            if rc != 0:
                raise DispatchRejected("REMOTE_GTIN_UPLOAD_FAILED")
            rc, raw = _ssh(host, ["sha256sum", "--", run_dir + "/input/gtins.csv"])
            if rc != 0 or not raw.startswith(gtin_digest + " "):
                raise DispatchRejected("REMOTE_GTIN_HASH_MISMATCH")
        # Short-lived token is requested only after lock and immutable uploads.
        token = token_supplier()
        if not isinstance(token, str) or not 1 <= len(token) <= 8192:
            raise DispatchRejected("REMOTE_TOKEN_UNAVAILABLE")
        _write_state(host, base, run_id, store_id, "RUNNING")
        in_worker = True
        try:
            rc, _ = _ssh(host, argv, data=token + "\n", timeout=900)
        finally:
            del token
        if rc != 0:
            # May be a timeout with worker still alive. Do not mark FAILED or retry.
            raise DispatchRejected("REMOTE_WORKER_UNCONFIRMED")
        output = fetch_verified_run(
            route=route,
            run_id=run_id,
            archive_root=archive_root,
            remote_root=base,
        )
        _write_state(host, base, run_id, store_id, "SUCCESS")
        # Retain remote evidence; owner must approve separate cleanup.
        return output
    except Exception:
        if acquired and not in_worker:
            try:
                _write_state(host, base, run_id, store_id, "FAILED")
            except Exception:
                pass
        raise
