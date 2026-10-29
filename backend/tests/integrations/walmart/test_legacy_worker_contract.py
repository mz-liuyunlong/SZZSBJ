"""Offline contract tests against the 2026-10-26 original worker CLI."""
from __future__ import annotations

import pytest

from app.integrations.walmart.legacy_worker_contract import (
    LegacyWorkerContractError,
    build_legacy_worker_argv,
    build_ssh_command,
)


def test_real_worker_cli_contains_required_flags_and_no_credentials():
    argv = build_legacy_worker_argv(
        store_id="110711149920800256",
        run_id="20261029-110711149920800256-abcdef12",
        endpoints=("wfs_inventory", "inbound_shipments"),
        date_iso="2026-10-29",
    )
    assert argv[:3] == [
        "python3",
        "/tmp/pmc-walmart-worker/20261029-110711149920800256-abcdef12/run_worker.py",
        "--collect",
    ]
    for option in ("--store-id", "--run-id", "--remote-tmp-dir", "--endpoints", "--date"):
        assert option in argv
    assert "--operations" not in argv
    assert "--credential-path" not in argv
    assert "--gtin-file" not in argv
    assert "20261029" in argv
    assert build_ssh_command(argv).startswith("python3 ")


def test_requires_exact_gtin_path():
    kwargs = {
        "store_id": "110711149920800256",
        "run_id": "test-20261029",
        "endpoints": ("inventory_log",),
        "date_iso": "2026-10-29",
    }
    with pytest.raises(LegacyWorkerContractError):
        build_legacy_worker_argv(**kwargs, gtin_file="/etc/passwd")
    argv = build_legacy_worker_argv(
        **kwargs, gtin_file="/tmp/pmc-walmart-worker/test-20261029/input/gtins.csv"
    )
    assert "--gtin-file" in argv


@pytest.mark.parametrize(
    "overrides",
    [
        {"store_id": "CN2502"},
        {"endpoints": ("delete_inventory",)},
        {"run_id": "a; rm -rf /"},
        {"date_iso": "2026-02-30"},
        {"remote_tmp_dir": "/etc"},
    ],
)
def test_fail_closed_on_invalid_parameters(overrides):
    kwargs = {
        "store_id": "110687428693128704",
        "run_id": "test-20261029",
        "endpoints": ("wfs_inventory",),
        "date_iso": "2026-10-29",
    }
    kwargs.update(overrides)
    with pytest.raises(LegacyWorkerContractError):
        build_legacy_worker_argv(**kwargs)
