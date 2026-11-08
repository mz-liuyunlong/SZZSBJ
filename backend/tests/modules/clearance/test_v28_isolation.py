"""Static safety contract tests; never connect to real PostgreSQL."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "app" / "modules" / "clearance"


def test_lifecycle_only_published_in_approved_branch():
    source = (ROOT / "hybrid_v28.py").read_text()
    assert 'elif decision == "rejected":' in source
    assert source.index("publish_approved_lifecycle(") > source.index(
        'status, approval_status = "running", "approved"'
    )
    assert "read_only_source=True" in source
    assert "write.commit()" in source


def test_local_storage_requires_two_specific_databases():
    source = (ROOT / "local_store_v28.py").read_text()
    assert "source.port != 15432" in source
    assert "target.port != 55433" in source
    assert 'target.database != "szzsbj_dev"' in source
    assert "SZZSBJ_CLEARANCE_TEST_WRITES" in source
    assert 'source.database != "szzsbj_app"' in source


def test_isolated_review_does_not_mutate_real_listing():
    source = (ROOT / "hybrid_v28.py").read_text()
    assert 'listing.lifecycle_status = "清货期"' not in source
    assert "read_only_source=True" in source


def test_approval_type_is_clearance_only():
    source = (ROOT / "hybrid_v28.py").read_text()
    assert "clearance_request" in source
    assert '"pending", "running"' not in source  # SQL statuses are explicit, no broad update.


def test_lifecycle_publisher_never_mutates_source_in_local_sandbox():
    import importlib.util
    from types import SimpleNamespace

    path = ROOT / "lifecycle_v28.py"
    spec = importlib.util.spec_from_file_location("clearance_test_lifecycle_v28", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)

    class SessionSpy:
        def __init__(self):
            self.executed = []

        def execute(self, statement, params):
            self.executed.append((str(statement), params))

        def commit(self):
            raise AssertionError("Lifecycle publisher must not commit itself")

    listing = SimpleNamespace(
        source_account_ref="primary",
        store_id="store1",
        item_id="123",
        id="l1",
        msku="m1",
        lifecycle_status="稳定期",
    )
    spy = SessionSpy()
    module.publish_approved_lifecycle(
        spy, listing=listing, actor="reviewer", application_id="app1", read_only_source=True
    )
    assert listing.lifecycle_status == "稳定期"
    assert len(spy.executed) == 2
    assert all("biz_listing_lifecycle_" in query for query, _ in spy.executed)
    assert all(params["stage"] == "清货期" for _, params in spy.executed)


def test_production_publisher_mutates_real_listing_after_audit_writes():
    import importlib.util
    from types import SimpleNamespace

    path = ROOT / "lifecycle_v28.py"
    spec = importlib.util.spec_from_file_location("clearance_test_lifecycle_prod_v28", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)

    class SessionSpy:
        def __init__(self):
            self.count = 0

        def execute(self, stmt, params):
            self.count += 1

    listing = SimpleNamespace(
        source_account_ref="primary",
        store_id="store1",
        item_id="123",
        id="l1",
        msku="m1",
        lifecycle_status="稳定期",
    )
    spy = SessionSpy()
    module.publish_approved_lifecycle(
        spy, listing=listing, actor="reviewer", application_id="app1", read_only_source=False
    )
    assert spy.count == 2
    assert listing.lifecycle_status == "清货期"
