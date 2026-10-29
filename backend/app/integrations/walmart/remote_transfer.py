"""Read-only fetch and checksum verification of per-store worker artifacts.

Any production cleanup is deliberately separate and owner-authorized. This
module does not infer SSH destinations or permit alternate hosts on failure.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from app.integrations.walmart.remote_dispatch import (
    RUN_PATTERN,
    DispatchRejected,
    WorkerRoute,
    verify_result,
)

_ROOT = re.compile(r"^/opt/szzsbj/walmart/runs$")
_MAX_TIMEOUT = 120


def fetch_verified_run(
    *,
    route: WorkerRoute,
    run_id: str,
    archive_root: Path,
    remote_root: str = "/opt/szzsbj/walmart/runs",
) -> dict[str, object]:
    """Fetch a single run; reject bad paths, incomplete or changed checksums.

    The caller must independently enforce a trusted route and the declared run
    belongs to the requesting principal/store. Tokens never enter this step.
    """
    if not RUN_PATTERN.fullmatch(run_id) or not _ROOT.fullmatch(remote_root):
        raise DispatchRejected("REMOTE_RUN_INVALID")
    if archive_root.is_symlink() or not archive_root.is_dir():
        raise DispatchRejected("REMOTE_ARCHIVE_INVALID")
    store_root = archive_root / route.store_code
    store_root.mkdir(mode=0o700, exist_ok=True)
    destination = store_root / run_id
    if destination.exists() or destination.is_symlink():
        raise DispatchRejected("REMOTE_ARCHIVE_ALREADY_EXISTS")
    source = route.ssh_host + ":" + remote_root + "/" + run_id
    try:
        result = subprocess.run(
            [
                "scp",
                "-r",
                "-p",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=10",
                source,
                str(store_root),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_MAX_TIMEOUT,
            check=False,
            env={
                "HOME": os.environ.get("HOME", "/nonexistent"),
                "PATH": "/usr/bin:/bin",
            },
        )
        if result.returncode != 0:
            raise DispatchRejected("REMOTE_FETCH_FAILED")
        status = verify_result(destination, run_id=run_id)
        return {"store_code": route.store_code, **status}
    except subprocess.TimeoutExpired:
        raise DispatchRejected("REMOTE_FETCH_TIMEOUT") from None
    except OSError:
        raise DispatchRejected("REMOTE_FETCH_UNAVAILABLE") from None
