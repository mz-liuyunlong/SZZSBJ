from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.operation_plans.repository import OperationPlanRepository
from app.modules.operation_plans.schemas import OperationPlanProductQuery


def test_unassigned_owner_filter_matches_dashboard_sentinel() -> None:
    session = MagicMock()
    session.execute.return_value.scalar_one.side_effect = [False, 0]
    session.execute.return_value.mappings.return_value = []

    repository = OperationPlanRepository(session)
    rows, total = repository.list_products(
        period_id=uuid4(),
        query=OperationPlanProductQuery(
            period_key="2026-10",
            owner_ref="unassigned",
        ),
        account_refs=frozenset({"synthetic-account"}),
    )

    assert rows == []
    assert total == 0

    count_calls = [
        call for call in session.execute.call_args_list if "select count(*)" in str(call.args[0])
    ]
    assert len(count_calls) == 1

    sql = str(count_calls[0].args[0])
    params = count_calls[0].args[1]

    assert "nullif(a.actual_owner_ref, ''), 'unassigned')" in sql
    assert "= :owner_ref" in sql
    assert params["owner_ref"] == "unassigned"
