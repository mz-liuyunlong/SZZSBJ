"""Fail-closed store-bound SSH dispatch for the legacy Walmart read-only worker.

Run only from a protected, isolated scheduler process. SSH identities, routes,
worker source and outputs are provided by the deployment owner; no fallbacks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.integrations.walmart.legacy_worker_contract import (
    build_legacy_worker_argv,
    build_ssh_command,
)

STORES = frozenset(
    {"HK2612", "HK2613", "HK2614", "HK2615", "CN2501", "CN2502", "CN2601", "CN2602", "CN2603"}
)
RUN_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,80}$")
HOST_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,127}$")
ALLOWED_KEYS = frozenset(
    {"wfs_inventory", "inbound_shipments", "inbound_shipment_items", "inventory_log"}
)


class DispatchRejected(RuntimeError):
    """Stable, non-sensitive rejection reason."""


@dataclass(frozen=True)
class WorkerRoute:
    store_code: str
    ssh_host: str
    worker_path: str


def parse_routes(raw: str) -> dict[str, WorkerRoute]:
    """Explicit operator-reviewed JSON; all nine stores required, no IP inference."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        raise DispatchRejected("REMOTE_ROUTES_INVALID") from None
    if not isinstance(data, dict) or set(data) != STORES:
        raise DispatchRejected("REMOTE_ROUTES_INCOMPLETE")
    routes = {}
    hosts = set()
    for store, item in data.items():
        if not isinstance(item, dict) or set(item) != {"ssh_host", "worker_path"}:
            raise DispatchRejected("REMOTE_ROUTE_INVALID")
        host, worker_path = item["ssh_host"], item["worker_path"]
        if not isinstance(host, str) or not HOST_PATTERN.fullmatch(host):
            raise DispatchRejected("REMOTE_HOST_INVALID")
        if host in hosts:
            raise DispatchRejected("REMOTE_HOST_REUSED")
        if (
            not isinstance(worker_path, str)
            or not worker_path.startswith("/opt/szzsbj/walmart/")
            or not re.fullmatch(r"/[a-zA-Z0-9_./-]+", worker_path)
            or ".." in Path(worker_path).parts
        ):
            raise DispatchRejected("REMOTE_WORKER_PATH_INVALID")
        hosts.add(host)
        routes[store] = WorkerRoute(store, host, worker_path)
    return routes


def verify_result(run_dir: Path, *, run_id: str) -> dict[str, Any]:
    """Validate manifest and SHA256SUMS before any downstream use."""
    if not RUN_PATTERN.fullmatch(run_id):
        raise DispatchRejected("REMOTE_RUN_INVALID")
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise DispatchRejected("REMOTE_RESULT_MISSING")
    manifest_path = run_dir / "manifest.json"
    checksum_path = run_dir / "SHA256SUMS"
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise DispatchRejected("REMOTE_RESULT_INCOMPLETE")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("status") != "SUCCESS":
            raise ValueError
        if manifest.get("run_id") != run_id:
            raise ValueError
        lines = checksum_path.read_text(encoding="utf-8").splitlines()
        if not lines or len(lines) > 1000:
            raise ValueError
        checked = set()
        for line in lines:
            matched = re.fullmatch(r"([a-f0-9]{64})  ([a-zA-Z0-9_./-]+)", line)
            if matched is None:
                raise ValueError
            digest, name = matched.groups()
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or name in checked:
                raise ValueError
            target = run_dir / rel
            if not target.is_file() or target.is_symlink():
                raise ValueError
            if target.stat().st_size > 50 * 1024 * 1024:
                raise ValueError
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError
            checked.add(name)
        if "manifest.json" not in checked:
            raise ValueError
        if manifest.get("manifest_version") != 2:
            raise ValueError
        if manifest.get("credential_files_read") != 0 or manifest.get("auth_failed") is not False:
            raise ValueError
        requested = manifest.get("endpoints_requested")
        outcomes = manifest.get("endpoints")
        files = manifest.get("files")
        if not isinstance(requested, list) or not requested or len(set(requested)) != len(requested):
            raise ValueError
        if not set(requested) <= ALLOWED_KEYS or not isinstance(outcomes, dict):
            raise ValueError
        if set(outcomes) != set(requested) or not isinstance(files, dict):
            raise ValueError
        if any(
            not isinstance(outcomes[key], dict) or outcomes[key].get("status") != "SUCCESS"
            for key in requested
        ):
            raise ValueError
        expected_hashes = {name: digest for digest, name in (line.split("  ", 1) for line in lines)}
        for name, info in files.items():
            if (
                not isinstance(name, str)
                or name not in checked
                or not isinstance(info, dict)
                or expected_hashes[name] != info.get("sha256")
            ):
                raise ValueError
        return {"status": "verified", "run_id": run_id, "files_verified": len(checked)}
    except (OSError, UnicodeError, ValueError):
        raise DispatchRejected("REMOTE_RESULT_VERIFICATION_FAILED") from None


def run_existing_worker(
    *,
    route: WorkerRoute,
    run_id: str,
    operations: tuple[str, ...],
    token: str,
    timeout_seconds: int = 600,
    store_id: str | None = None,
    date_iso: str | None = None,
) -> None:
    """Invoke an owner-installed worker. Token ONLY in SSH stdin, never argv/logs.

    Worker must accept --run-id / --operations; adapter does not guess legacy CLI.
    The worker is responsible for atomic lock and status/manifest emission.
    """
    if not RUN_PATTERN.fullmatch(run_id) or not operations:
        raise DispatchRejected("REMOTE_RUN_INVALID")
    if not set(operations) <= ALLOWED_KEYS or len(set(operations)) != len(operations):
        raise DispatchRejected("REMOTE_OPERATION_DENIED")
    if not isinstance(token, str) or not 1 <= len(token) <= 8192:
        raise DispatchRejected("REMOTE_TOKEN_INVALID")
    if not 1 <= timeout_seconds <= 900:
        raise DispatchRejected("REMOTE_TIMEOUT_INVALID")
    # No arbitrary command parameters, no password-based fallback.
    if store_id is None or date_iso is None:
        raise DispatchRejected("REMOTE_WORKER_PARAMETERS_MISSING")
    if route.worker_path != "/opt/szzsbj/walmart/run_worker.py":
        raise DispatchRejected("REMOTE_WORKER_UNVERIFIED")
    try:
        worker_args = build_legacy_worker_argv(
            store_id=store_id,
            run_id=run_id,
            endpoints=operations,
            date_iso=date_iso,
        )
        remote_command = build_ssh_command(worker_args)
    except ValueError:
        raise DispatchRejected("REMOTE_WORKER_PARAMETERS_INVALID") from None
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "--",
        route.ssh_host,
        remote_command,
    ]
    try:
        result = subprocess.run(
            command,
            input=token + "\n",
            text=True,
            encoding="utf-8",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
            env={
                "HOME": os.environ.get("HOME", "/nonexistent"),
                "PATH": "/usr/bin:/bin",
            },
        )
        if result.returncode != 0:
            raise DispatchRejected("REMOTE_EXECUTION_FAILED")
    except subprocess.TimeoutExpired:
        raise DispatchRejected("REMOTE_EXECUTION_TIMEOUT") from None
    except OSError:
        raise DispatchRejected("REMOTE_EXECUTION_UNAVAILABLE") from None
