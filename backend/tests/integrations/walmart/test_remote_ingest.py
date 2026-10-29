"""Offline contract tests: reject tampering before database access."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

import pytest

from app.integrations.walmart.remote_dispatch import DispatchRejected
from app.integrations.walmart.remote_ingest import prepare_verified_csv


def test_ingest_verifies_manifest_csv_rows_and_hashes(tmp_path):
    run_id = "wmt-12345678"
    store_id = "110687428693128704"
    store_code = "CN2502"
    run = tmp_path / store_code / run_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    raw_bytes = b'{"params":{},"body":{"payload":{"inventory":[]}}}\n'
    (raw / "wfs_inventory.jsonl").write_bytes(raw_bytes)
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    manifest = {
        "manifest_version": 2,
        "run_id": run_id,
        "store_id": store_id,
        "date": "2026-10-29",
        "status": "SUCCESS",
        "credential_files_read": 0,
        "auth_failed": False,
        "endpoints_requested": ["wfs_inventory"],
        "endpoints": {"wfs_inventory": {"status": "SUCCESS", "rows": 1}},
        "files": {"raw/wfs_inventory.jsonl": {"sha256": raw_hash}},
    }
    data = json.dumps(manifest).encode()
    (run / "manifest.json").write_bytes(data)
    (run / "SHA256SUMS").write_text(
        hashlib.sha256(data).hexdigest() + "  manifest.json\n"
        + raw_hash + "  raw/wfs_inventory.jsonl\n"
    )
    dest = tmp_path / "daily" / "20261029" / "walmart" / store_id
    dest.mkdir(parents=True)
    csv_bytes = b"itemInformation.itemID,itemInformation.sku\n123,DEMO\n"
    (dest / "wfs_inventory.csv").write_bytes(csv_bytes)
    (dest / "_convert_manifest.json").write_text(
        json.dumps({
            "run_id": run_id,
            "store_id": store_id,
            "written": [{"file": "wfs_inventory.csv", "rows": 1,
                         "sha256": hashlib.sha256(csv_bytes).hexdigest()}],
        })
    )
    day, hashes, data = prepare_verified_csv(
        archive_root=tmp_path, store_code=store_code,
        store_id=store_id, run_id=run_id,
    )
    assert day.isoformat() == "2026-10-29"
    assert data["wfs_inventory"][0]["item_id"] == "123"
    assert hashes["wfs_inventory"] == hashlib.sha256(csv_bytes).hexdigest()
    (dest / "wfs_inventory.csv").write_bytes(csv_bytes + b"TAMPER")
    with pytest.raises(DispatchRejected, match="REMOTE_INGEST_VERIFICATION_FAILED"):
        prepare_verified_csv(
            archive_root=tmp_path, store_code=store_code,
            store_id=store_id, run_id=run_id,
        )


def test_ingest_rejects_foreign_store_without_writes(tmp_path):
    with pytest.raises(DispatchRejected):
        prepare_verified_csv(
            archive_root=tmp_path, store_code="CN2502",
            store_id="not-numeric", run_id="wmt-12345678",
        )
