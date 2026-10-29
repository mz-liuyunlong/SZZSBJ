"""Offline conversion tests on original manifest v2 and WFS payload shape."""

import hashlib
import json

import pytest

from app.integrations.walmart.remote_daily import convert_verified_run
from app.integrations.walmart.remote_dispatch import DispatchRejected


def test_wfs_verified_csv_and_no_overwrite(tmp_path):
    run_id = "wmt-12345678"
    store_id = "110687428693128704"
    run_dir = tmp_path / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True)
    page = {
        "params": {"limit": 100, "offset": 0},
        "body": {
            "payload": {
                "inventory": [{"itemInformation": {"sku": "TEST-SKU", "gtin": "0123456789012"}}]
            }
        },
    }
    raw = json.dumps(page) + "\n"
    (raw_dir / "wfs_inventory.jsonl").write_text(raw, encoding="utf-8")
    raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    manifest = {
        "manifest_version": 2,
        "run_id": run_id,
        "store_id": store_id,
        "date": "2026-10-29",
        "status": "SUCCESS",
        "credential_files_read": 0,
        "auth_failed": False,
        "endpoints_requested": ["wfs_inventory"],
        "endpoints": {"wfs_inventory": {"status": "SUCCESS", "rows": 1, "total_count": 1}},
        "files": {"raw/wfs_inventory.jsonl": {"sha256": raw_hash}},
    }
    manifest_bytes = json.dumps(manifest).encode()
    (run_dir / "manifest.json").write_bytes(manifest_bytes)
    (run_dir / "SHA256SUMS").write_text(
        hashlib.sha256(manifest_bytes).hexdigest()
        + "  manifest.json\n"
        + raw_hash
        + "  raw/wfs_inventory.jsonl\n",
        encoding="utf-8",
    )
    destination = tmp_path / "converted"
    result = convert_verified_run(
        run_dir=run_dir, output_root=destination, run_id=run_id, store_id=store_id
    )
    assert result["files"] == 1
    csv_file = destination / "20261029" / "walmart" / store_id / run_id / "wfs_inventory.csv"
    assert csv_file.exists()
    assert "TEST-SKU" in csv_file.read_text(encoding="utf-8-sig")
    with pytest.raises(DispatchRejected, match="REMOTE_CONVERSION_ALREADY_EXISTS"):
        convert_verified_run(
            run_dir=run_dir, output_root=destination, run_id=run_id, store_id=store_id
        )
