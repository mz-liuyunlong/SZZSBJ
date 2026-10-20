from pathlib import Path

import pytest

from app.modules.operation_logs.owner_mapping_reconcile import reconcile_owner_mappings


def test_name_based_reconciliation_never_writes_even_with_apply():
    with pytest.raises(RuntimeError, match="forbidden"):
        reconcile_owner_mappings(None, apply=True)


def test_periodic_owner_auto_authorization_is_not_registered():
    root = Path(__file__).resolve().parents[3]
    celery = (root / "app/celery_app.py").read_text(encoding="utf-8")
    tasks = (root / "app/modules/operation_logs/tasks.py").read_text(encoding="utf-8")
    assert "operation-owner-mapping-reconcile" not in celery
    assert "owner_mapping_reconcile_tick" not in tasks


def test_explicit_admin_assignment_never_upserts_an_existing_uid():
    root = Path(__file__).resolve().parents[3]
    router = (root / "app/modules/operation_logs/router.py").read_text(encoding="utf-8")
    start = router.index("def assign_owner_mapping(")
    end = router.index("@router.delete(", start)
    body = router[start:end]
    assert "_admin_only(access)" in body
    assert "access.require_account(account)" in body
    assert "on conflict (source_account_ref, owner_uid) do nothing" in body
    assert "ops_lingxing_owner_mapping_audit" in body
