"""Draft numbers follow the purchase board, not a second numbering scheme."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.pmc_domestic.draft_numbers import attach_draft_numbers


class Row:
    def __init__(self, account: str, sku: str, orders: list[str]) -> None:
        self.source_account_ref = account
        self.sku = sku
        self.purchase_order_sns = orders
        self.draft_nos: list[str] = []


def test_draft_numbers_follow_purchase_order_then_sku():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "create table dws_purchase_board ("
                "source_account_ref varchar, order_sn varchar, sku varchar, draft_no varchar)"
            )
        )
        conn.execute(
            text(
                "insert into dws_purchase_board values "
                "('primary','PO2','YC1','CG261020-002'),"
                "('primary','PO1','YC1','CG261020-009'),"
                "('primary','PO1','YC1','CG261020-001'),"
                "('other','PO1','YC1','CG261020-888'),"
                "('primary','PO1','YC2','CG261020-003')"
            )
        )
    with Session(engine) as session:
        rows = [
            Row("primary", "YC1", ["PO1", "PO2"]),
            Row("primary", "YC2", ["PO1"]),
            Row("primary", "YC9", []),
        ]
        attach_draft_numbers(session, rows, frozenset({"primary"}))
    assert rows[0].draft_nos == ["CG261020-001", "CG261020-009", "CG261020-002"]
    assert rows[1].draft_nos == ["CG261020-003"]
    assert rows[2].draft_nos == []
    engine.dispose()


def test_missing_purchase_board_leaves_drafts_empty():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as session:
        row = Row("primary", "YC1", ["PO1"])
        attach_draft_numbers(session, [row], frozenset({"primary"}))
    assert row.draft_nos == []
    engine.dispose()
