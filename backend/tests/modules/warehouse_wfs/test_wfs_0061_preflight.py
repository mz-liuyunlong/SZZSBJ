import pytest

from scripts import preflight_wfs_0061


def test_preflight_is_default_deny(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("WFS_0061_PREFLIGHT_ALLOW_DB_READ", raising=False)

    assert preflight_wfs_0061.main() == 2
    assert capsys.readouterr().out.strip() == ("STOP: WFS_0061_PREFLIGHT_ALLOW_DB_READ_REQUIRED")
