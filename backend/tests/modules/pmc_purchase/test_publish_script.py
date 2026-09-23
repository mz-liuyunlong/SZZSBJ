"""The DWD publish script refuses without the explicit authorization gate."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "publish_pmc_purchase_dwd.py"


def _run(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> int:
    for key in ("PMC_PURCHASE_DWD_PUBLISH_AUTHORIZED", "PMC_PURCHASE_SOURCE_ACCOUNT_REF"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = runpy.run_path(str(SCRIPT), run_name="publish_pmc_purchase_dwd")
    return int(module["main"]())


def test_script_refuses_without_authorization(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, {"PMC_PURCHASE_SOURCE_ACCOUNT_REF": "primary"}) == 2
    assert "PMC_PURCHASE_DWD_PUBLISH_REQUIRES_AUTHORIZATION" in capsys.readouterr().out
    assert _run(monkeypatch, {"PMC_PURCHASE_DWD_PUBLISH_AUTHORIZED": "yes"}) == 2


def test_script_rejects_invalid_account_before_touching_the_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(
        monkeypatch,
        {"PMC_PURCHASE_DWD_PUBLISH_AUTHORIZED": "true", "PMC_PURCHASE_SOURCE_ACCOUNT_REF": ""},
    )
    assert code == 2
    assert "ACCOUNT" in capsys.readouterr().out.upper()
    sys.modules.pop("publish_pmc_purchase_dwd", None)
