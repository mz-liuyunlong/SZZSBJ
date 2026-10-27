"""Inbound ItemID comes from this row's store remarks, then that store's listing."""

import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.pmc_domestic.board_item_ids import (
    attach_board_item_ids,
    extract_remark_item_ids,
    resolve_store_item_ids,
)
from app.modules.pmc_purchase.calculations import parse_itemid_remark


def test_parse_prefers_prefixed_item_id_then_the_first_bare_eleven_digits():
    assert parse_itemid_remark("ITEMID:20540519308 草稿") == "20540519308"
    assert parse_itemid_remark("20347351964 报关") == "20347351964"
    assert parse_itemid_remark("00464039347084") is None


def test_extract_keeps_every_eleven_digits_and_skips_gtin():
    assert extract_remark_item_ids(
        ["ITEMID:20403609913 | 草稿:CG261017-039 20347351964", "00465313943732"]
    ) == ["20403609913", "20347351964"]


def test_store_row_uses_its_own_remark_then_listing_gtin():
    lines = [("S1", ["ITEMID:20403609913 20347351964"], ["PP1"])]
    plans = {"PP1": ("S1", ["11111111111"])}
    listings = [
        ("S1", "20403609913", "YC1", "00465313943732"),
        ("S1", "20347351964", "YC1", None),
        ("S1", "11111111111", "OTHER", "000"),
        ("S2", "20403609913", "YC1", "999"),
    ]
    found = resolve_store_item_ids(
        store_id="S1", sku="YC1", lines=lines, plans=plans, listings=listings
    )
    assert found == [
        ("20403609913", "00465313943732"),
        ("20347351964", None),
    ]


def test_same_purchase_order_keeps_each_store_on_its_own_row():
    cn = [("CN", [None], ["PP1"])]
    hk = [("HK", [None], ["PP2"])]
    plans = {
        "PP1": ("CN", ["GTIN：00465313943732"]),
        "PP2": ("HK", ["GTIN：00465271337932"]),
    }
    listings = [
        ("CN", "20068662815", "YC00092", "00465313943732"),
        ("HK", "20067107122", "YC00092", "00465271337932"),
        ("OTHER", "20067107122", "YC00092", "00465271337932"),
    ]
    cn_ids = resolve_store_item_ids(
        store_id="CN", sku="YC00092", lines=cn, plans=plans, listings=listings
    )
    hk_ids = resolve_store_item_ids(
        store_id="HK", sku="YC00092", lines=hk, plans=plans, listings=listings
    )
    assert cn_ids == [("20068662815", "00465313943732")]
    assert hk_ids == [("20067107122", "00465271337932")]


def test_several_listings_on_one_store_stay_on_one_row():
    listings = [("S1", "20000000001", "YC1", "1"), ("S1", "20000000002", "YC1", "2")]
    found = resolve_store_item_ids(store_id="S1", sku="YC1", lines=[], plans={}, listings=listings)
    assert found == [("20000000001", "1"), ("20000000002", "2")]


def test_blank_store_uses_a_listing_only_when_the_sku_has_one_store():
    one = [("ONLY", "20000000001", "YC1", "1")]
    two = [("A", "20000000001", "YC1", "1"), ("B", "20000000002", "YC1", "2")]
    assert resolve_store_item_ids(store_id=None, sku="YC1", lines=[], plans={}, listings=one) == [
        ("20000000001", "1")
    ]
    assert resolve_store_item_ids(store_id="0", sku="YC1", lines=[], plans={}, listings=two) == []


def test_attach_reads_current_remarks_for_the_row_store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "create table ods_lingxing_purchase_order_items ("
            "source_account_ref varchar, order_sn varchar, sku varchar, item_id varchar, "
            "plan_sn varchar, sid varchar, remark varchar, payload_json varchar, "
            "is_delete integer, observed_at varchar, id varchar)"
        ))
        conn.execute(text(
            "create table ods_lingxing_purchase_plans ("
            "source_account_ref varchar, plan_sn varchar, sid varchar, remark varchar, "
            "plan_remark varchar, payload_json varchar, observed_at varchar, id varchar)"
        ))
        conn.execute(text(
            "create table dim_walmart_listings ("
            "source_account_ref varchar, store_id varchar, item_id varchar, "
            "local_sku varchar, gtin varchar)"
        ))
        old_payload = json.dumps(
            {"update_time": "2026-01-01", "item_purchase_remark": "ITEMID:11111111111"}
        )
        new_payload = json.dumps({
            "update_time": "2026-02-01",
            "item_purchase_remark": "20347351964",
            "relation_purchase_plan": ["PP1"],
        })
        conn.execute(
            text("insert into ods_lingxing_purchase_order_items values "
                 "('primary','PO1','YC1','L1','PP1','S1',:old,:payload,0,'2026-01-01','old'),"
                 "('primary','PO1','YC1','L1','PP1','S1','ITEMID:20403609913',:new_payload,0,'2026-02-01','new'),"
                 "('primary','PO1','YC1','L2','PP2','S2',null,null,0,'2026-02-01','hk'),"
                 "('other','PO1','YC1','L9',null,'S1','12345678901',null,0,'2026-02-01','other')"),
            {"old": "old", "payload": old_payload, "new_payload": new_payload},
        )
        conn.execute(text(
            "insert into ods_lingxing_purchase_plans values "
            "('primary','PP1','S1',null,'22222222222',null,'2026-02-01','p1')"
        ))
        conn.execute(text(
            "insert into dim_walmart_listings values "
            "('primary','S1','20403609913','YC1','004'),"
            "('primary','S1','20347351964','YC1',null),"
            "('primary','S1','22222222222','YC1','005'),"
            "('primary','S2','20067107122','YC1','006')"
        ))
    row = type("Row", (), {})()
    row.source_account_ref = "primary"
    row.sku = "YC1"
    row.store_id = "S1"
    row.purchase_order_sns = ["PO1"]
    row.item_identities = []
    row.identity_status = "missing"
    with Session(engine) as session:
        attach_board_item_ids(session, [row], frozenset({"primary"}))
    assert [item.item_id for item in row.item_identities] == [
        "20403609913",
        "20347351964",
        "22222222222",
    ]
    assert row.item_identities[0].gtin == "004"
    assert row.identity_status == "multiple"
    engine.dispose()
