"""Fail-closed local production-tunnel write policy (no real DB)."""
from __future__ import annotations

from app.core.local_scoped_writes import permitted_local_write

ID = "00000000-0000-0000-0000-000000000001"


def test_explicitly_allowed_writes() -> None:
    allowed = (
        "/api/auth/login", "/api/auth/logout",
        f"/api/warehouse/wfs-fee-cases/{ID}/follow",
        f"/api/approvals/wfs-cases/{ID}/decision",
        f"/api/approvals/{ID}/decision",
        f"/api/approvals/{ID}/supplement",
    )
    for path in allowed:
        assert permitted_local_write("POST", path)


def test_synchronization_and_other_mutations_are_denied() -> None:
    forbidden = (
        f"/api/integrations/sync-configs/{ID}/run",
        f"/api/integrations/sync-runs/{ID}/retry",
        f"/api/integrations/sync-configs/{ID}/backfill",
        "/api/warehouse/wfs-fee-cases/sync-legacy-execute",
        "/api/warehouse/wfs-fee-cases/sync-legacy-preview",
        "/api/approvals/workflow/bulk-approve",
        f"/api/warehouse/wfs-fee-cases/{ID}/mark-recovered",
        f"/api/approvals/wfs-cases/{ID}/decision/extra",
        "/api/auth/login/extra",
        "/api/products/sync",
    )
    for path in forbidden:
        assert not permitted_local_write("POST", path), path
    assert not permitted_local_write("DELETE", "/api/auth/login")
    assert not permitted_local_write("PUT", f"/api/warehouse/wfs-fee-cases/{ID}/follow")
