from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
ALLOWED_DIRECT_MEMBERSHIP = {
    "core/permissions.py",
    "modules/integration_sync/dependencies.py",
}


def test_business_routes_do_not_bypass_wildcard_aware_permission_helpers() -> None:
    offenders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative in ALLOWED_DIRECT_MEMBERSHIP:
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if " in principal.permissions" in line or " not in principal.permissions" in line:
                offenders.append(f"{relative}:{line_number}")

    assert offenders == []
