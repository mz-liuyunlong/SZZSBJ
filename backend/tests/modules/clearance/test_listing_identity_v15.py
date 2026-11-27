"""Clearance V15 owner lookup must mirror Listing Management, never mix accounts."""

from types import SimpleNamespace

from app.modules.clearance.read_only_listings import _owner_names_for_listings


class FakeResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeReadSession:
    def __init__(self, rows, table_exists=True):
        self.rows = rows
        self.table_exists = table_exists
        self.sqls = []
        self.params = []

    def scalar(self, stmt, params):
        self.sqls.append(str(stmt))
        return "dwd_lingxing_sku_product_info_current" if self.table_exists else None

    def execute(self, stmt, params):
        self.sqls.append(str(stmt))
        self.params.append(params)
        return FakeResult(self.rows)


def listing(account, sku):
    return SimpleNamespace(source_account_ref=account, local_sku=sku)


def test_owner_matches_account_and_local_sku_not_item_or_title():
    session = FakeReadSession(
        [
            ("A", "SKU-1", "负责人甲"),
            ("B", "SKU-1", "负责人乙"),
            ("A", "SKU-2", "负责人丙"),
        ]
    )
    result = _owner_names_for_listings(session, [listing("A", "SKU-1"), listing("B", "SKU-1")])
    assert result == {("A", "SKU-1"): "负责人甲", ("B", "SKU-1"): "负责人乙"}
    assert len(session.params) == 1
    assert "MAX(NULLIF(BTRIM(owner_name)" in session.sqls[-1]


def test_table_absent_returns_no_owner_and_executes_no_data_sql():
    session = FakeReadSession([], table_exists=False)
    assert _owner_names_for_listings(session, [listing("A", "SKU-1")]) == {}
    assert session.params == []


def test_missing_or_blank_sku_does_not_query():
    session = FakeReadSession([])
    assert _owner_names_for_listings(session, [listing("A", "")]) == {}
    assert session.sqls == []


def test_empty_owner_is_not_fabricated():
    session = FakeReadSession([("A", "SKU-1", None)])
    assert _owner_names_for_listings(session, [listing("A", "SKU-1")]) == {}
