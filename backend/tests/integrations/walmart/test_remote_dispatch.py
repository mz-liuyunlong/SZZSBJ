"""Offline tests for strict store mapping and checksum verification."""

from __future__ import annotations

import hashlib
import json

import pytest

from app.integrations.walmart.remote_dispatch import (
    REMOTE_COLLECTION_STORES,
    DispatchRejected,
    parse_routes,
    verify_result,
)


def test_all_eight_collection_routes_without_cn2502():
    raw = {
        store: {
            "ssh_host": "worker-" + store.lower(),
            "worker_path": "/opt/szzsbj/walmart/run_worker.py",
        }
        for store in REMOTE_COLLECTION_STORES
    }
    assert len(raw) == 8
    assert "CN2502" not in raw
    assert set(parse_routes(json.dumps(raw))) == REMOTE_COLLECTION_STORES


def test_missing_extra_or_shared_routes_are_rejected():
    raw = {
        store: {
            "ssh_host": "worker-" + store.lower(),
            "worker_path": "/opt/szzsbj/walmart/run_worker.py",
        }
        for store in REMOTE_COLLECTION_STORES
    }
    missing = dict(raw)
    missing.pop("HK2612")
    with pytest.raises(DispatchRejected, match="REMOTE_ROUTES_INCOMPLETE"):
        parse_routes(json.dumps(missing))
    extra = dict(raw)
    extra["CN2502"] = {
        "ssh_host": "worker-cn2502",
        "worker_path": "/opt/szzsbj/walmart/run_worker.py",
    }
    with pytest.raises(DispatchRejected, match="REMOTE_ROUTES_INCOMPLETE"):
        parse_routes(json.dumps(extra))
    duplicate = dict(raw)
    duplicate["HK2612"] = raw["HK2613"]
    with pytest.raises(DispatchRejected, match="REMOTE_HOST_REUSED"):
        parse_routes(json.dumps(duplicate))

def test_verifies_manifest_hash_and_detects_tamper(tmp_path):
    path = tmp_path / "run-123456"
    path.mkdir()
    manifest = {
        "run_id": "run-123456",
        "status": "SUCCESS",
        "manifest_version": 2,
        "credential_files_read": 0,
        "auth_failed": False,
        "endpoints_requested": ["wfs_inventory"],
        "endpoints": {"wfs_inventory": {"status": "SUCCESS"}},
        "files": {},
    }
    raw = json.dumps(manifest).encode()
    (path / "manifest.json").write_bytes(raw)
    (path / "SHA256SUMS").write_text(
        hashlib.sha256(raw).hexdigest() + "  manifest.json\n", encoding="utf-8"
    )
    assert verify_result(path, run_id="run-123456")["files_verified"] == 1
    (path / "manifest.json").write_text('{"status": "failed"}')
    with pytest.raises(DispatchRejected, match="REMOTE_RESULT_VERIFICATION_FAILED"):
        verify_result(path, run_id="run-123456")


def test_path_traversal_denied(tmp_path):
    path = tmp_path / "run-123456"
    path.mkdir()
    (path / "manifest.json").write_text('{"run_id": "run-123456", "status": "success"}')
    (path / "SHA256SUMS").write_text("0" * 64 + "  ../outside\n")
    with pytest.raises(DispatchRejected, match="REMOTE_RESULT_VERIFICATION_FAILED"):
        verify_result(path, run_id="run-123456")


def test_missing_endpoint_result_denied(tmp_path):
    path = tmp_path / "run-123456"
    path.mkdir()
    manifest = {
        "run_id": "run-123456",
        "status": "SUCCESS",
        "manifest_version": 2,
        "credential_files_read": 0,
        "auth_failed": False,
        "endpoints_requested": ["wfs_inventory"],
        "endpoints": {},
        "files": {},
    }
    raw = json.dumps(manifest).encode()
    (path / "manifest.json").write_bytes(raw)
    (path / "SHA256SUMS").write_text(
        hashlib.sha256(raw).hexdigest() + "  manifest.json\\n", encoding="utf-8"
    )
    with pytest.raises(DispatchRejected, match="REMOTE_RESULT_VERIFICATION_FAILED"):
        verify_result(path, run_id="run-123456")
