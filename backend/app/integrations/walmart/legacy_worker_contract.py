"""Exact CLI contract for the supplied Walmart remote-pull worker v1.3.2.

Derived from the owner's 2026-10-26 source package, not the older handoff.
This is an offline argument builder: no secrets, SSH or Walmart calls.
"""

from __future__ import annotations

import re
import shlex
from datetime import date
from pathlib import PurePosixPath

ALLOWED_ENDPOINTS = frozenset(
    {"wfs_inventory", "inbound_shipments", "inbound_shipment_items", "inventory_log"}
)
RUN_ID = re.compile(r"^[A-Za-z0-9._-]{4,80}$")
STORE_ID = re.compile(r"^[0-9]{1,24}$")
REMOTE_ROOT = re.compile(r"^/tmp/[A-Za-z0-9._/-]+$")
DEFAULT_REMOTE_TMP_DIR = "/tmp/pmc-walmart-worker"


class LegacyWorkerContractError(ValueError):
    """No secrets or remote response bodies."""


def build_legacy_worker_argv(
    *,
    store_id: str,
    run_id: str,
    endpoints: tuple[str, ...],
    date_iso: str,
    remote_tmp_dir: str = DEFAULT_REMOTE_TMP_DIR,
    window_days: int = 90,
    min_interval_ms: int = 1200,
    gtin_file: str | None = None,
) -> list[str]:
    """Emit the original worker's CLI. No credentials or access tokens in argv."""
    if not STORE_ID.fullmatch(store_id) or not RUN_ID.fullmatch(run_id):
        raise LegacyWorkerContractError("WORKER_ID_INVALID")
    if (
        not REMOTE_ROOT.fullmatch(remote_tmp_dir)
        or ".." in PurePosixPath(remote_tmp_dir).parts
        or remote_tmp_dir.endswith("/")
    ):
        raise LegacyWorkerContractError("WORKER_REMOTE_PATH_INVALID")
    if (
        not endpoints
        or len(set(endpoints)) != len(endpoints)
        or not set(endpoints) <= ALLOWED_ENDPOINTS
    ):
        raise LegacyWorkerContractError("WORKER_ENDPOINT_INVALID")
    try:
        date.fromisoformat(date_iso)
    except (ValueError, TypeError):
        raise LegacyWorkerContractError("WORKER_DATE_INVALID") from None
    if type(window_days) is not int or not 1 <= window_days <= 365:
        raise LegacyWorkerContractError("WORKER_WINDOW_INVALID")
    if type(min_interval_ms) is not int or not 1200 <= min_interval_ms <= 60000:
        raise LegacyWorkerContractError("WORKER_INTERVAL_INVALID")
    run_dir = remote_tmp_dir + "/" + run_id
    if gtin_file is not None and gtin_file != run_dir + "/input/gtins.csv":
        raise LegacyWorkerContractError("WORKER_GTIN_FILE_INVALID")
    args = [
        "python3",
        run_dir + "/run_worker.py",
        "--collect",
        "--store-id",
        store_id,
        "--run-id",
        run_id,
        "--remote-tmp-dir",
        remote_tmp_dir,
        "--endpoints",
        ",".join(endpoints),
        "--date",
        date_iso.replace("-", ""),
        "--window-days",
        str(window_days),
        "--output-mode",
        "mac_file",
        "--min-interval-ms",
        str(min_interval_ms),
    ]
    if gtin_file is not None:
        args.extend(["--gtin-file", gtin_file])
    return args


def build_ssh_command(remote_args: list[str]) -> str:
    """SSH remote command is a single shell-escaped argument, not joined raw."""
    if not remote_args or any(not isinstance(arg, str) or not arg for arg in remote_args):
        raise LegacyWorkerContractError("WORKER_COMMAND_INVALID")
    return shlex.join(remote_args)
