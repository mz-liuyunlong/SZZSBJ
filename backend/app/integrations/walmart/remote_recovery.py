"""Recover a completed remote Walmart run without issuing any token or API call.

A disconnected SSH session is not proof of failed collection. Inspect only
the original run ID and fetch verified files; never start the worker again.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from app.db.session import get_session_factory
from app.integrations.walmart.remote_ingest import ingest_verified_archive

from app.integrations.walmart.legacy_execution import _ssh
from app.integrations.walmart.legacy_worker_contract import DEFAULT_REMOTE_TMP_DIR
from app.integrations.walmart.remote_daily import convert_verified_run
from app.integrations.walmart.remote_dispatch import (
    ALLOWED_KEYS,
    RUN_PATTERN,
    DispatchRejected,
    WorkerRoute,
    verify_result,
)
from app.integrations.walmart.remote_transfer import fetch_verified_run


def _completed_manifest(
    route: WorkerRoute, run_id: str, store_id: str, operations: tuple[str, ...]
) -> dict[str, object]:
    """Demand an existing SUCCESS manifest for this exact store and run."""
    if not RUN_PATTERN.fullmatch(run_id) or not store_id.isdecimal():
        raise DispatchRejected("REMOTE_RECOVERY_ID_INVALID")
    if not operations or not set(operations) <= ALLOWED_KEYS:
        raise DispatchRejected("REMOTE_RECOVERY_ENDPOINT_INVALID")
    state_path = DEFAULT_REMOTE_TMP_DIR + "/.runs/" + run_id + "/state.json"
    code, state_raw = _ssh(route.ssh_host, ["cat", state_path], timeout=30)
    if code != 0:
        raise DispatchRejected("REMOTE_RECOVERY_UNCONFIRMED")
    try:
        state = json.loads(state_raw)
        if state.get("run_id") != run_id or state.get("store_id") != store_id:
            raise ValueError
        if state.get("state") not in {"RUNNING", "SUCCESS"}:
            raise DispatchRejected("REMOTE_RECOVERY_NOT_COMPLETE")
    except (TypeError, ValueError, AttributeError):
        raise DispatchRejected("REMOTE_RECOVERY_STATE_INVALID") from None
    remote_path = DEFAULT_REMOTE_TMP_DIR + "/" + run_id + "/manifest.json"
    code, output = _ssh(route.ssh_host, ["cat", remote_path], timeout=30)
    if code != 0:
        raise DispatchRejected("REMOTE_RECOVERY_UNCONFIRMED")
    try:
        manifest = json.loads(output)
        if (
            not isinstance(manifest, dict)
            or manifest.get("manifest_version") != 2
            or manifest.get("run_id") != run_id
            or manifest.get("store_id") != store_id
            or set(manifest.get("endpoints_requested", [])) != set(operations)
        ):
            raise ValueError
        if manifest.get("status") != "SUCCESS":
            raise DispatchRejected("REMOTE_RECOVERY_NOT_COMPLETE")
        if manifest.get("auth_failed") is not False or manifest.get("credential_files_read") != 0:
            raise DispatchRejected("REMOTE_RECOVERY_CREDENTIAL_ANOMALY")
        return manifest
    except (ValueError, TypeError):
        raise DispatchRejected("REMOTE_RECOVERY_MANIFEST_INVALID") from None


def _converted_files(
    output_root: Path, manifest: dict[str, object], store_id: str, run_id: str
) -> int | None:
    """Validate existing conversion instead of overwriting or reconverting."""
    day = str(manifest.get("date", "")).replace("-", "")
    if len(day) != 8 or not day.isdecimal():
        raise DispatchRejected("REMOTE_RECOVERY_DATE_INVALID")
    target = output_root / day / "walmart" / store_id
    if not target.exists():
        return None
    if target.is_symlink() or not target.is_dir():
        raise DispatchRejected("REMOTE_RECOVERY_OUTPUT_INVALID")
    try:
        meta = json.loads((target / "_convert_manifest.json").read_text(encoding="utf-8"))
        if meta.get("run_id") != run_id or meta.get("store_id") != store_id:
            raise ValueError
        written = meta["written"]
        if not isinstance(written, list) or not written:
            raise ValueError
        for item in written:
            name = item["file"]
            if name not in (
                "wfs_inventory.csv",
                "shipments.csv",
                "items.csv",
                "inventory_log.csv",
            ):
                raise ValueError
            path = target / name
            if path.is_symlink() or not path.is_file():
                raise ValueError
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError
        return len(written)
    except (OSError, KeyError, TypeError, ValueError):
        raise DispatchRejected("REMOTE_RECOVERY_OUTPUT_INVALID") from None


def recover_completed_run(
    *,
    route: WorkerRoute,
    store_id: str,
    run_id: str,
    operations: tuple[str, ...],
    archive_root: Path,
    job_id: UUID,
    source_account_ref: str,
) -> dict[str, object]:
    """Return only after verified artifacts and original-compatible CSVs exist."""
    manifest = _completed_manifest(route, run_id, store_id, operations)
    if archive_root.is_symlink() or not archive_root.is_dir():
        raise DispatchRejected("REMOTE_ARCHIVE_INVALID")
    local = archive_root / route.store_code / run_id
    try:
        verified = verify_result(local, run_id=run_id)
    except DispatchRejected as exc:
        if str(exc) not in {
            "REMOTE_RESULT_MISSING",
            "REMOTE_RESULT_INCOMPLETE",
            "REMOTE_RESULT_VERIFICATION_FAILED",
        }:
            raise
        if local.exists() or local.is_symlink():
            if local.is_symlink():
                raise DispatchRejected("REMOTE_RECOVERY_LOCAL_SYMLINK")
            partial = local.with_name(run_id + ".partial-" + uuid4().hex[:12])
            local.rename(partial)  # Keep failed download for forensics.
        verified = fetch_verified_run(
            route=route,
            run_id=run_id,
            archive_root=archive_root,
        )
    converted_root = archive_root / "daily"
    count = _converted_files(converted_root, manifest, store_id, run_id)
    if count is None:
        result = convert_verified_run(
            run_dir=local,
            output_root=converted_root,
            run_id=run_id,
            store_id=store_id,
        )
        count = int(result["files"])
    with get_session_factory()() as session:
        ingest_verified_archive(
            session, job_id=job_id, source_account_ref=source_account_ref,
            store_code=route.store_code, store_id=store_id, run_id=run_id,
            archive_root=archive_root,
        )
        session.commit()
    cleaned = cleanup_verified_run(
        route=route,
        store_id=store_id,
        run_id=run_id,
        archive_root=archive_root,
        manifest=manifest,
    )
    return {
        "status": "verified",
        "run_id": run_id,
        "files_verified": verified["files_verified"],
        "files_converted": count,
        "remote_cleaned": cleaned,
    }


def cleanup_verified_run(
    *,
    route: WorkerRoute,
    store_id: str,
    run_id: str,
    archive_root: Path,
    manifest: dict[str, object],
) -> bool:
    """Opt-in cleanup; lock and state evidence are never deleted."""
    if os.getenv("SZZSBJ_WALMART_REMOTE_CLEANUP_ENABLED") != "1":
        return False
    local = archive_root / route.store_code / run_id
    verify_result(local, run_id=run_id)
    if _converted_files(archive_root / "daily", manifest, store_id, run_id) is None:
        raise DispatchRejected("REMOTE_CLEANUP_CONVERSION_MISSING")
    digest = hashlib.sha256((local / "manifest.json").read_bytes()).hexdigest()
    remote_dir = DEFAULT_REMOTE_TMP_DIR + "/" + run_id
    code, raw = _ssh(route.ssh_host, ["sha256sum", "--", remote_dir + "/manifest.json"])
    if code != 0 or not raw.startswith(digest + " "):
        raise DispatchRejected("REMOTE_CLEANUP_HASH_MISMATCH")
    code, _ = _ssh(route.ssh_host, ["find", remote_dir, "-mindepth", "1", "-delete"])
    if code != 0 or _ssh(route.ssh_host, ["rmdir", "--", remote_dir])[0] != 0:
        raise DispatchRejected("REMOTE_CLEANUP_UNCONFIRMED")
    return True
