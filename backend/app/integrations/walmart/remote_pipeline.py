"""Disabled-by-default, owner-controlled remote read-only collection pipeline.

Worker credentials are only used in the protected scheduler process. No token
is ever put in a task payload, result, database or log.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.db.session import get_session_factory
from app.integrations.walmart.remote_ingest import ingest_verified_archive

from app.integrations.walmart.gtin_input import (
    GtinSourceRejected,
    build_gtin_input,
    build_system_gtin_input,
)
from app.integrations.walmart.legacy_execution import collect_with_legacy_worker
from app.integrations.walmart.remote_daily import convert_verified_run
from app.integrations.walmart.remote_dispatch import (
    ALLOWED_KEYS,
    STORES,
    DispatchRejected,
    parse_routes,
)
from app.integrations.walmart.remote_recovery import cleanup_verified_run
from app.integrations.walmart.scf_read_factory import RefreshingScfApi
from app.integrations.walmart.tenc_sts_identity import CachedScfAssumeRoleIdentity
from app.integrations.walmart.token_client import store_token_invoker


def collect_store_read_only(
    *,
    store_code: str,
    operations: tuple[str, ...],
    archive_root: Path,
    run_id: str | None = None,
    store_id: str | None = None,
    job_id: UUID | None = None,
    source_account_ref: str | None = None,
) -> dict[str, object]:
    """Fail closed on missing config, unauthorized store or unverified results.

    Must be called only by an owner-controlled, explicitly approved scheduler.
    The owner must install the compatible worker and approve egress/SSM IAM.
    """
    if os.getenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED") != "1":
        raise DispatchRejected("REMOTE_COLLECTION_DISABLED")
    routes = parse_routes(os.getenv("SZZSBJ_WALMART_REMOTE_ROUTES", ""))
    allowed = frozenset(
        store.strip()
        for store in os.getenv("SZZSBJ_WALMART_REMOTE_APPROVED_STORES", "").split(",")
        if store.strip()
    )
    if not allowed or not allowed <= STORES or store_code not in allowed:
        raise DispatchRejected("REMOTE_STORE_NOT_APPROVED")
    if not operations or not set(operations) <= ALLOWED_KEYS:
        raise DispatchRejected("REMOTE_OPERATION_DENIED")
    rid = run_id or ("wmt-" + uuid4().hex)
    if not store_id:
        raise DispatchRejected("REMOTE_STORE_ID_REQUIRED")
    cvm_role = os.getenv("SZZSBJ_WALMART_SCF_CVM_ROLE", "")
    target_role = os.getenv("SZZSBJ_WALMART_SCF_TARGET_ROLE_ARN", "")
    if not cvm_role or not target_role:
        raise DispatchRejected("REMOTE_CLOUD_IDENTITY_MISSING")

    def obtain_token() -> str:
        cloud_api = RefreshingScfApi(
            CachedScfAssumeRoleIdentity(cvm_role=cvm_role, target_role_arn=target_role)
        )
        token = store_token_invoker(
            cloud_api=cloud_api, store_code=store_code, authorized_stores=allowed
        )
        return token.access_token

    # GTIN input is an ephemeral per-run file, never placed in task messages.
    with tempfile.TemporaryDirectory(prefix="walmart-gtin-") as temporary_dir:
        gtin_csv = None
        if "inventory_log" in operations:
            try:
                if os.getenv("SZZSBJ_WALMART_GTIN_SOURCE_MODE", "system") == "system":
                    if not source_account_ref:
                        raise GtinSourceRejected("GTIN_SOURCE_ACCOUNT_REQUIRED")
                    with get_session_factory()() as session:
                        gtin_csv = build_system_gtin_input(
                            session=session,
                            source_account_ref=source_account_ref,
                            store_id=store_id,
                            directory=Path(temporary_dir),
                        )
                else:
                    gtin_csv = build_gtin_input(
                        store_code=store_code,
                        store_id=store_id,
                        directory=Path(temporary_dir),
                    )
            except GtinSourceRejected as exc:
                raise DispatchRejected(str(exc)) from None
        verified = collect_with_legacy_worker(
            route=routes[store_code],
            store_id=store_id,
            run_id=rid,
            operations=operations,
            archive_root=archive_root,
            date_iso=datetime.now(UTC).date().isoformat(),
            expected_worker_hash=os.getenv("SZZSBJ_WALMART_LEGACY_WORKER_SHA256", ""),
            token_supplier=obtain_token,
            gtin_csv=gtin_csv,
        )
    conversion = convert_verified_run(
        run_dir=archive_root / store_code / rid,
        output_root=archive_root / "daily",
        run_id=rid,
        store_id=store_id,
    )
    manifest = json.loads(
        (archive_root / store_code / rid / "manifest.json").read_text(encoding="utf-8")
    )
    if job_id is None or not source_account_ref:
        raise DispatchRejected("REMOTE_INGEST_CONTEXT_REQUIRED")
    with get_session_factory()() as session:
        ingest_verified_archive(
            session, job_id=job_id, source_account_ref=source_account_ref,
            store_code=store_code, store_id=store_id, run_id=rid, archive_root=archive_root,
        )
        session.commit()
    cleaned = cleanup_verified_run(
        route=routes[store_code],
        store_id=store_id,
        run_id=rid,
        archive_root=archive_root,
        manifest=manifest,
    )
    # Never return raw data or tokens to the calling task.
    return {
        "store_code": store_code,
        "run_id": rid,
        "status": "verified",
        "files_verified": verified["files_verified"],
        "files_converted": conversion["files"],
        "remote_cleaned": cleaned,
    }
