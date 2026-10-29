"""No-token recovery and cleanup gates for the original Walmart worker."""

from __future__ import annotations

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
        remote_recovery, "_ssh", lambda *a, **k: (0, json.dumps(remote))
    )
    monkeypatch.setattr(remote_recovery, "fetch_verified_run", fetch)
    with pytest.raises(DispatchRejected, match="REMOTE_RECOVERY_MANIFEST_INVALID"):
        remote_recovery._completed_manifest(
            ROUTE, "wmt-12345678", "11111111", ("wfs_inventory",)
        )
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
        remote_recovery._completed_manifest(
            ROUTE, "wmt-12345678", "11111111", ("wfs_inventory",)
        )
    fetch.assert_not_called()
