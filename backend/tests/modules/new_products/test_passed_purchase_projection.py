from types import SimpleNamespace as NS

from app.modules.new_products.workflow_read import _approved_purchase_stores


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def scalars(self, statement):
        self.calls.append(statement)
        return self.rows


def event(account, app, target):
    return NS(
        source_account_ref=account,
        store_id="s1",
        item_id="i1",
        payload_json={"application_id": app, "purchase_store_id": target},
    )


def test_approval_event_is_bound_to_latest_application_and_identity():
    purchases = {
        ("a", "s1", "i1"): NS(status="approved", id="new"),
        ("b", "s1", "i1"): NS(status="rejected", id="other"),
    }
    db = FakeSession(
        [
            event("a", "old", "bad"),
            event("b", "new", "bad"),
            event("a", "new", "s2"),
            event("a", "new", "old_target"),
        ]
    )
    source = FakeSession(
        [
            NS(source_account_ref="a", store_id="s2", store_name="2603"),
            NS(source_account_ref="b", store_id="s2", store_name="wrong"),
        ]
    )
    assert _approved_purchase_stores(db, source, purchases) == {
        ("a", "s1", "i1", "new"): ("s2", "2603")
    }
    assert len(db.calls) == len(source.calls) == 1


def test_missing_and_unchanged_target_are_not_inferred():
    purchases = {("a", "s1", "i1"): NS(status="approved", id="new")}
    source = FakeSession([])
    assert _approved_purchase_stores(FakeSession([]), source, purchases) == {}
    assert _approved_purchase_stores(FakeSession([event("a", "new", "s1")]), source, purchases) == {
        ("a", "s1", "i1", "new"): ("s1", None)
    }
    assert not source.calls
