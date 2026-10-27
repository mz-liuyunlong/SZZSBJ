"""The batch board shows the current product owner for the row SKU."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.pmc_domestic.board_owners import attach_board_owners, classify_owner


def test_one_owner_resolves_and_several_identities_conflict():
    assert classify_owner([("id-1", "u1", "曾洁茹")]).name == "曾洁茹"
    assert classify_owner([("id-1", "u1", "曾洁茹")]).status == "resolved"
    assert classify_owner([("id-1", "u1", "甲"), ("id-2", "u1", "甲")]).status == "conflict"
    assert classify_owner([("id-1", "u1", "甲"), ("id-1", "u2", "乙")]).status == "conflict"
    assert classify_owner([]).status == "missing"
    assert classify_owner([("id-1", None, None)]).status == "missing"


def test_attach_reads_the_current_owner_for_the_row_sku():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "create table dwd_lingxing_sku_identity_index ("
            "id varchar, provider varchar, source_account_ref varchar, "
            "lingxing_sku_id varchar, lingxing_sku_code varchar, is_active integer)"
        ))
        conn.execute(text(
            "create table dwd_lingxing_sku_product_info_current ("
            "identity_id varchar, provider varchar, source_account_ref varchar, "
            "lingxing_sku_id varchar, owner_uid varchar, owner_name varchar)"
        ))
        conn.execute(text(
            "insert into dwd_lingxing_sku_identity_index values "
            "('i1','lingxing','primary','sku-1','YC00347',1),"
            "('i2','lingxing','primary','sku-2','YC00999',1),"
            "('i3','lingxing','primary','sku-3','YC00999',1),"
            "('i4','lingxing','other','sku-4','YC00347',1)"
        ))
        conn.execute(text(
            "insert into dwd_lingxing_sku_product_info_current values "
            "('i1','lingxing','primary','sku-1','u1','曾洁茹'),"
            "('i2','lingxing','primary','sku-2','u2','甲'),"
            "('i3','lingxing','primary','sku-3','u3','乙'),"
            "('i4','lingxing','other','sku-4','u9','别人')"
        ))
    known = _row("primary", "YC00347")
    conflict = _row("primary", "YC00999")
    missing = _row("primary", "YC00000")
    with Session(engine) as session:
        attach_board_owners(session, [known, conflict, missing], frozenset({"primary"}))
    assert known.owner.status == "resolved"
    assert known.owner.name == "曾洁茹"
    assert known.owner.uid == "u1"
    assert conflict.owner.status == "conflict"
    assert missing.owner.status == "missing"
    engine.dispose()


def _row(account: str, sku: str):
    row = type("Row", (), {})()
    row.source_account_ref = account
    row.sku = sku
    row.owner = None
    return row
