"""The DWS refresh script refuses without the explicit authorization gate."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "refresh_pmc_purchase_dws.py"
ENV_KEYS = (
    "PMC_PURCHASE_DWS_REFRESH_AUTHORIZED",
    "PMC_PURCHASE_SOURCE_ACCOUNT_REF",
    "PMC_PURCHASE_DWS_AS_OF",
)


def _run(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> int:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = runpy.run_path(str(SCRIPT), run_name="refresh_pmc_purchase_dws")
    code = int(module["main"]())
    sys.modules.pop("refresh_pmc_purchase_dws", None)
    return code


def test_script_refuses_without_authorization(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, {"PMC_PURCHASE_SOURCE_ACCOUNT_REF": "primary"}) == 2
    assert "PMC_PURCHASE_DWS_REFRESH_REQUIRES_AUTHORIZATION" in capsys.readouterr().out
    assert _run(monkeypatch, {"PMC_PURCHASE_DWS_REFRESH_AUTHORIZED": "yes"}) == 2


def test_script_rejects_invalid_account_and_date_before_touching_the_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(
        monkeypatch,
        {"PMC_PURCHASE_DWS_REFRESH_AUTHORIZED": "true", "PMC_PURCHASE_SOURCE_ACCOUNT_REF": ""},
    )
    assert code == 2
    assert "ACCOUNT" in capsys.readouterr().out.upper()

    code = _run(
        monkeypatch,
        {
            "PMC_PURCHASE_DWS_REFRESH_AUTHORIZED": "true",
            "PMC_PURCHASE_SOURCE_ACCOUNT_REF": "primary",
            "PMC_PURCHASE_DWS_AS_OF": "2026/09/23",
        },
    )
    assert code == 2
    assert "PMC_PURCHASE_DWS_AS_OF_INVALID" in capsys.readouterr().out
