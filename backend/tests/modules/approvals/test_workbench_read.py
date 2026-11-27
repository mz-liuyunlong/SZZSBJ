from app.modules.approvals.schemas import ApprovalQuery
from app.modules.approvals.workbench_purchase_read import _page_sql
from app.modules.approvals.workbench_read import _clearance_match, _merge_page
from app.modules.new_products.testing_profit import _ADS_SQL, _DAILY_SQL


def test_page_and_counts_share_source_reads():
    calls = []

    def group(name, n):
        def fetch(page, size):
            calls.append((name, page, size))
            return [f"{name}:{i}" for i in range((page - 1) * size, min(n, page * size))], n

        return name, 100, fetch

    groups = [
        group("clearance", 2),
        group("np_purchase", 4),
        group("purchase", 1),
        group("newProduct", 2),
        group("wfs", 3),
        group("finance", 0),
    ]
    rows, total, counts = _merge_page(ApprovalQuery(page=1, page_size=5), groups)
    assert rows == ["clearance:0", "clearance:1", "np_purchase:0", "np_purchase:1", "np_purchase:2"]
    assert total == 12 and counts["purchase"] == 5 and counts["newProduct"] == 2
    assert len(calls) == 6
    rows, total, _ = _merge_page(ApprovalQuery(page=2, page_size=5), groups)
    assert rows == ["np_purchase:3", "purchase:0", "newProduct:0", "newProduct:1", "wfs:0"]
    rows, total, _ = _merge_page(
        ApprovalQuery(approval_type="purchase_exception", page=1, page_size=5), groups
    )
    assert (
        rows == ["np_purchase:0", "np_purchase:1", "np_purchase:2", "np_purchase:3", "purchase:0"]
        and total == 5
    )


def test_exact_filters_and_per_identity_profit_cutoff():
    assert _clearance_match(
        {"risk_at_submission": "high", "local_sku": "ABC-123"},
        ApprovalQuery(risk_level="high", keyword="abc"),
    )
    assert not _clearance_match(
        {"risk_at_submission": "low", "local_sku": "ABC-123"},
        ApprovalQuery(risk_level="high", keyword="abc"),
    )
    for stmt in (_DAILY_SQL, _ADS_SQL):
        sql = _page_sql(stmt).text
        assert "w.cutoff" in sql and ":cutoff" not in sql and "cutoff date" in sql
