"""Exception center M1: persistence, workflow, and version conflicts."""

import pytest

from app.core.api import ApiError
from app.modules.pmc_wfs.exception_schemas import AssignCommand, CaseEventCommand, ExceptionQuery
from app.modules.pmc_wfs.exception_service import ExceptionCenterService

pytest_plugins = ["tests.modules.pmc_wfs.test_pending"]


def _svc(db, account):
    return ExceptionCenterService(db, frozenset({account}), None)


def _seed_case(db, account, order, shipment_id="WFS-EX-001"):
    svc = _svc(db, account)
    return svc.insert_case_for_tests(
        source_account_ref=account,
        store_id=order.store_id,
        shipment_id=shipment_id,
        rule_family="arrival_overdue",
        summary="测试：预计到仓已过（M1 样例）",
        pk=order.pk,
        business_test=True,
    )


def test_list_detail_and_summary(db):
    from tests.modules.pmc_wfs.test_pending import seed as seed_fn

    account, order, _, _ = seed_fn(db)
    case = _seed_case(db, account, order)
    svc = _svc(db, account)
    listed = svc.list(ExceptionQuery())
    assert listed.total == 1
    assert listed.items[0].rule_label == "超过预计到仓时间"
    detail = svc.detail(case.id)
    assert detail.timeline
    assert detail.timeline[-1].kind == "detection"
    summary = svc.summary(ExceptionQuery())
    assert summary.open_cases == 1
    assert summary.open_shipments == 1


def test_assign_and_close(db):
    from tests.modules.pmc_wfs.test_pending import seed as seed_fn

    account, order, _, _ = seed_fn(db)
    case = _seed_case(db, account, order)
    svc = _svc(db, account)
    updated = svc.assign(case.id, "user-a", AssignCommand(assignee_user_id="owner-1", expected_version=1))
    assert updated.assignee_user_id == "owner-1"
    assert updated.status == "IN_PROGRESS"
    closed = svc.post_event(
        case.id,
        "user-a",
        CaseEventCommand(action="close", expected_version=2, reason="测试关闭"),
    )
    assert closed.status == "CLOSED"


def test_version_conflict(db):
    from tests.modules.pmc_wfs.test_pending import seed as seed_fn

    account, order, _, _ = seed_fn(db)
    case = _seed_case(db, account, order)
    svc = _svc(db, account)
    with pytest.raises(ApiError) as err:
        svc.assign(case.id, "user-a", AssignCommand(assignee_user_id="x", expected_version=99))
    assert err.value.status_code == 409
    assert err.value.code == "CASE_VERSION_CONFLICT"


def test_dedupe(db):
    from tests.modules.pmc_wfs.test_pending import seed as seed_fn

    account, order, _, _ = seed_fn(db)
    first = _seed_case(db, account, order)
    second = _seed_case(db, account, order)
    assert first.id == second.id
    assert _svc(db, account).list(ExceptionQuery()).total == 1
