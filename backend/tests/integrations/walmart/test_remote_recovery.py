"""No-token recovery and cleanup gates for the original Walmart worker."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import Mock

import pytest

from app.integrations.walmart import remote_recovery
from app.integrations.walmart.remote_dispatch import DispatchRejected, WorkerRoute

ROUTE = WorkerRoute(
    store_code="CN2502",
    ssh_host="worker-cn2502",
    worker_path="/opt/szzsbj/walmart/run_worker.py",
)


def test_recovery_rejects_wrong_store_without_fetch(monkeypatch):
    remote = {
        "manifest_version": 2,
        "run_id": "wmt-12345678",
        "store_id": "22222222",
        "status": "SUCCESS",
        "endpoints_requested": ["wfs_inventory"],
        "credential_files_read": 0,
        "auth_failed": False,
    }
    fetch = Mock()
    monkeypatch.setattr(
        remote_recovery,
        "_ssh",
        lambda host, argv, **k: (
            0,
            json.dumps({"run_id": "wmt-12345678", "store_id": "11111111", "state": "SUCCESS"})
            if ".runs/" in argv[-1]
            else json.dumps(remote),
        ),
    )
    monkeypatch.setattr(remote_recovery, "fetch_verified_run", fetch)
    with pytest.raises(DispatchRejected, match="REMOTE_RECOVERY_MANIFEST_INVALID"):
        remote_recovery._completed_manifest(ROUTE, "wmt-12345678", "11111111", ("wfs_inventory",))
    fetch.assert_not_called()


def test_cleanup_disabled_never_issues_remote_command(monkeypatch, tmp_path):
    ssh = Mock()
    monkeypatch.delenv("SZZSBJ_WALMART_REMOTE_CLEANUP_ENABLED", raising=False)
    monkeypatch.setattr(remote_recovery, "_ssh", ssh)
    assert not remote_recovery.cleanup_verified_run(
        route=ROUTE,
        store_id="11111111",
        run_id="wmt-12345678",
        archive_root=tmp_path,
        manifest={},
    )
    ssh.assert_not_called()


def test_recovery_unconfirmed_does_not_fetch(monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(remote_recovery, "_ssh", lambda *a, **k: (255, ""))
    monkeypatch.setattr(remote_recovery, "fetch_verified_run", fetch)
    with pytest.raises(DispatchRejected, match="REMOTE_RECOVERY_UNCONFIRMED"):
        remote_recovery._completed_manifest(ROUTE, "wmt-12345678", "11111111", ("wfs_inventory",))
    fetch.assert_not_called()


def test_file_only_recovery_validates_all_endpoint_csvs(tmp_path):
    output = tmp_path / "daily"
    folder = output / "20261029" / "walmart" / "11111111" / "wmt-12345678"
    folder.mkdir(parents=True)
    raw = b"sku\nTEST\n"
    (folder / "wfs_inventory.csv").write_bytes(raw)
    expected_hash = hashlib.sha256(raw).hexdigest()
    (folder / "_convert_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "wmt-12345678",
                "store_id": "11111111",
                "date": "20261029",
                "written": [{"file": "wfs_inventory.csv", "rows": 1, "sha256": expected_hash}],
            }
        )
    )
    manifest = {"date": "2026-10-29", "endpoints_requested": ["wfs_inventory"]}
    assert remote_recovery._converted_files(output, manifest, "11111111", "wmt-12345678") == 1
    manifest["endpoints_requested"].append("inventory_log")
    with pytest.raises(DispatchRejected, match="REMOTE_RECOVERY_OUTPUT_INVALID"):
        remote_recovery._converted_files(output, manifest, "11111111", "wmt-12345678")
    manifest["endpoints_requested"].pop()
    (folder / "wfs_inventory.csv").write_bytes(b"sku\nTEST\nEXTRA\n")
    with pytest.raises(DispatchRejected, match="REMOTE_RECOVERY_OUTPUT_INVALID"):
        remote_recovery._converted_files(output, manifest, "11111111", "wmt-12345678")


def test_uncertain_conversion_and_checksum_errors_require_review():
    from inspect import getsource

    from app.modules.walmart_remote.tasks import execute_remote_job

    source = getsource(execute_remote_job)
    assert '"REMOTE_CONVERSION_FAILED"' in source
    assert '"REMOTE_RESULT_VERIFICATION_FAILED"' in source
    assert '"REMOTE_RESULT_INCOMPLETE"' in source
