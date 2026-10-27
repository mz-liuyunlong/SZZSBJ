from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.modules.warehouse_wfs import read_only_detection as module
from app.modules.warehouse_wfs.anomaly_detection import WfsStandardFee
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore

STORE = WfsSettlementStore(
    source_account_ref="primary",
    store_id="110704872940532224",
    store_name="Test Store",
    sid="",
)


def sample_rows():
    rows = []
    for n in (1, 2):
        base = {
            "uniqueId": f"u{n}",
            "storeName": "Test Store",
            "storeId": STORE.store_id,
            "platformCode": "10008",
            "transactionTypes": 0,
            "currencyCode": "USD",
            "msku": "YC00115-1A",
            "platformOrderNo": f"order{n}",
            "settlementDate": "2026-10-01",
        }
        rows.extend(
            [
                {**base, "rowIndex": 1, "salesNum": 5, "platformLogisticsAmount": 0},
                {**base, "rowIndex": 2, "salesNum": 0, "platformLogisticsAmount": "-34.75"},
            ]
        )
    return rows


def test_full_detection_with_dynamic_standard(monkeypatch):
    session = MagicMock()
    session.execute.return_value.all.return_value = [("YC00115-1A", "20500114893")]

    def standards(_session, *, identities):
        return {
            identity: WfsStandardFee(
                source_account_ref=identity[0],
                store_id=identity[1],
                msku=identity[3],
                unit_fee=Decimal("6.55"),
                source="product_management_live",
                rule_version="current",
            )
            for identity in identities
        }

    monkeypatch.setattr(module, "read_product_management_wfs_fees", standards)

    def fetch(_interface, params):
        rows = sample_rows()
        offset = params["offset"]
        return {
            "code": 0,
            "total": len(rows),
            "data": {"list": rows[offset : offset + params["length"]]},
        }

    result = module.run_wfs_read_only_detection(
        session,
        fetch_page=fetch,
        store=STORE,
        detection_date=date(2026, 10, 19),
    )

    assert result.collected_rows == 4
    assert result.result.detection.anomalies == 1
    case = result.result.detection.candidates[0]
    assert case.actual_unit_fee == Decimal("6.95")
    assert case.standard_unit_fee == Decimal("6.55")
    assert case.unit_overcharge == Decimal("0.40")
    session.commit.assert_not_called()
    session.flush.assert_not_called()


def test_unmapped_product_never_creates_candidate():
    session = MagicMock()
    session.execute.return_value.all.return_value = []

    result = module.run_wfs_read_only_detection(
        session,
        fetch_page=lambda _interface, _params: {
            "code": 0,
            "total": 4,
            "data": {"list": sample_rows()},
        },
        store=STORE,
        detection_date=date(2026, 10, 19),
    )

    assert result.unresolved_listings == 1
    assert result.result.detection.missing_standard == 1
    assert result.result.detection.anomalies == 0
    session.commit.assert_not_called()
