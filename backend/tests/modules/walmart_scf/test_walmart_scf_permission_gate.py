"""Ensure Walmart SCF endpoints cannot be called with read-only task-center grants."""

from app.core.permission_policy_v2 import permission_for_request


def test_walmart_scf_requires_execute_permission():
    for method, path in (
        ("GET", "/api/integrations/walmart-scf/wfs-inventory"),
        ("POST", "/api/integrations/walmart-scf/read"),
    ):
        assert permission_for_request(method, path, "integrations:execute") == (
            "action:data-center:task-center:execute"
        )


def test_other_task_center_reads_unchanged():
    assert (
        permission_for_request("GET", "/api/integrations/sync-runs", "integrations:read")
        == "page:data-center:task-center:view"
    )
