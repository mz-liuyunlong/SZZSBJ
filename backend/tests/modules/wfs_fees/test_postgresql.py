"""WFS 费用导入 → 归期 → 归属 → 核对 → 调整，走真实 PostgreSQL（没配测试库就跳过）。

全部合成数据。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

import tests.modules.wfs_fees.synth as S
from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.data_pages.models import WalmartListingDimension
from app.modules.walmart_bills.models import WalmartBillLine, WalmartBillPeriod
from app.modules.wfs_fees import reader
from app.modules.wfs_fees.models import WalmartWfsFeeCheck, WalmartWfsFeeFile, WalmartWfsFeeLine
from app.modules.wfs_fees.service import WfsFeeError, WfsFeeService

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
RK_1020 = "rk-synthetic-1020"
RK_1103 = "rk-synthetic-1103"


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            yield db
        transaction.rollback()
    engine.dispose()


def _listing(
    session: Session, gtin: str, item_id: str, msku: str, store_id: str = S.STORE_A
) -> None:
    session.add(
        WalmartListingDimension(
            id=uuid4(),
            source_account_ref="primary",
            store_id=store_id,
            item_id=item_id,
            msku=msku,
            local_sku=msku.split("-")[0],
            gtin=gtin,
            fulfillment_type="1",
            synced_at=NOW,
        )
    )


def _bill(
    session: Session,
    key: str,
    report_date: str,
    start: str,
    end: str,
    lines: list[tuple[str, str, str]],
) -> None:
    """lines = (transaction_description, posted_date, amount)。"""
    session.add(
        WalmartBillPeriod(
            source_account_ref="primary",
            store_id=S.STORE_A,
            store_name="ZZ9901-synthetic",
            report_key=key,
            report_date=date.fromisoformat(report_date),
            period_start_date=date.fromisoformat(start),
            period_end_date=date.fromisoformat(end),
            currency_code="USD",
            line_count=len(lines),
            excluded_line_count=0,
            amount_sum=Decimal(0),
            payable_amount=Decimal(0),
            status="normal",
            refreshed_at=NOW,
        )
    )
    for index, (desc, posted, amount) in enumerate(lines):
        session.add(
            WalmartBillLine(
                source_account_ref="primary",
                store_id=S.STORE_A,
                line_key=f"{key}-{index}",
                lx_line_id=f"{key}{index}",
                report_key=key,
                report_date=date.fromisoformat(report_date),
                posted_at=datetime.fromisoformat(posted),
                posted_date=date.fromisoformat(posted),
                transaction_type="Adjustment",
                transaction_description=desc,
                amount=Decimal(amount),
                currency_code="USD",
                delete_flag=0,
                row_hash=f"h{key}{index}",
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )


@pytest.fixture
def service(session: Session, tmp_path: Path) -> WfsFeeService:
    _listing(session, S.GTIN_1, "30000000001", "MSKU-1")
    _listing(session, S.GTIN_2, "30000000002", "MSKU-2")
    _bill(
        session,
        RK_1020,
        "2026-10-20",
        "2026-10-03",
        "2026-10-16",
        [
            ("WFS LostInventory", "2026-10-09", "21.57"),
            ("WFS Returned Item Disposal Fee", "2026-10-07", "-0.55"),
        ],
    )
    _bill(
        session,
        RK_1103,
        "2026-11-03",
        "2026-10-17",
        "2026-10-30",
        [("WFS LostInventory", "2026-10-23", "6.27")],
    )
    session.flush()
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = tmp_path
    return WfsFeeService(session, settings)


def _upload(service: WfsFeeService, content: bytes, name: str = "report.csv", **kw):
    return service.upload(
        file_name=name, content=content, actor="synthetic-user", request_id="req", **kw
    )


def _lines(session: Session, **where):
    query = select(WalmartWfsFeeLine).where(
        WalmartWfsFeeLine.store_id == S.STORE_A, WalmartWfsFeeLine.parent_line_id.is_(None)
    )
    for key, value in where.items():
        query = query.where(getattr(WalmartWfsFeeLine, key) == value)
    return list(
        session.scalars(
            query.order_by(WalmartWfsFeeLine.transaction_date, WalmartWfsFeeLine.amount_usd)
        )
    )


def test_settlement_upload_matches_items_bills_periods_and_checks(service, session, tmp_path):
    content = S.settlement(
        [
            S.fee("LostInventory", "2026-10-07", "-21.57", gtin=S.GTIN_1, ref="R1", qty="3"),
            S.fee("RC_InventoryDisposalFee", "2026-10-07", "0.55", gtin=S.GTIN_2, ref="R2"),
            S.fee("LostInventory", "2026-10-21", "-6.27", gtin=S.GTIN_1, ref="R3"),
            S.fee("Refund", "2026-10-08", "-3.00", reason="StorageFeeDispute", ref="R4"),
        ]
    )
    result = _upload(service, content, store_id=S.STORE_A)
    assert result.status == "parsed" and result.rows_new == 4 and result.rows_duplicate == 0
    assert result.store_id == S.STORE_A and result.fee_source == "settlement"
    raw = session.get(WalmartWfsFeeFile, result.file_id)
    assert (tmp_path / raw.storage_path).read_bytes() == content

    lost = _lines(session, fee_type="LostInventory")
    assert [(x.date_charged.isoformat(), x.report_key, x.bill_match) for x in lost] == [
        ("2026-10-09", RK_1020, "领星同类同日"),
        ("2026-10-23", RK_1103, "领星同类同日"),
    ]
    assert (
        lost[0].item_id == "30000000001"
        and lost[0].msku == "MSKU-1"
        and lost[0].attribution == "matched"
    )
    assert lost[0].amount_usd == Decimal("21.57")
    disposal = _lines(session, fee_type="RC_InventoryDisposalFee")[0]
    assert disposal.date_charged == date(2026, 10, 7) and disposal.report_key == RK_1020  # 按天出账
    dispute = _lines(session, fee_type="Refund")[0]
    assert (
        dispute.attribution == "company"
        and dispute.report_key == RK_1020
        and dispute.bill_match == "领星同店同日"
    )

    checks = {(c.report_key, c.fee_type): c for c in session.scalars(select(WalmartWfsFeeCheck))}
    assert checks[(RK_1020, "LostInventory")].status == "ok"
    assert checks[(RK_1020, "RC_InventoryDisposalFee")].status == "ok"
    assert checks[(RK_1103, "LostInventory")].status == "ok"
    assert checks[(RK_1020, "Refund")].status == "report_only"

    again = _upload(service, content, store_id=S.STORE_A)
    assert again.duplicate_of_file and again.rows_new == 0 and again.rows_duplicate == 4
    assert (
        session.scalar(select(__import__("sqlalchemy").func.count()).select_from(WalmartWfsFeeLine))
        == 4
    )


def test_store_is_recognised_without_choosing(service, session):
    """不用选店铺：Partner ID 配置 / 以前导入过 / 商品投票；认不出才拒收并让页面选店。"""
    unknown = S.settlement(
        [S.fee("LostInventory", "2026-10-07", "-1.00", gtin=S.GTIN_3, ref="R9", partner="P-Y")]
    )
    rejected = _upload(service, unknown)
    assert rejected.status == "rejected" and rejected.needs_store
    assert "认不出是哪家店" in (rejected.reject_reason or "")

    # 商品投票：GTIN 只在 A 店 → A 店
    voted = _upload(
        service,
        S.settlement([S.fee("LostInventory", "2026-10-07", "-1.00", gtin=S.GTIN_1, ref="R1")]),
    )
    assert voted.status == "parsed" and voted.store_id == S.STORE_A

    # 同一个 Partner ID 以前导入过 → 没有 GTIN 的行也能认
    learned = _upload(
        service,
        S.settlement(
            [S.fee("Refund", "2026-10-08", "-3.00", reason="StorageFeeDispute", ref="R2")]
        ),
    )
    assert learned.status == "parsed" and learned.store_id == S.STORE_A

    # 空的仓储费报表没有商品：看卖家后台文件名里的 Partner ID（以前从内容里学到过的）
    empty = _upload(
        service,
        S.storage([], period=("2026-10-17", "2026-10-30"), total="0"),
        name=f"StorageFee_2026-10-17_{S.PARTNER_A}.zip/StorageFee.csv",
    )
    assert empty.status == "empty" and empty.store_id == S.STORE_A
    # 文件名里的数字没学到过 → 不认
    stranger = _upload(
        service,
        S.storage([], period=("2026-10-31", "2026-11-13"), total="0"),
        name="StorageFee_2026-10-31_99999999999.zip/StorageFee.csv",
    )
    assert stranger.status == "rejected" and stranger.needs_store

    # 页面选的店只补认不出的；认得出的不被覆盖
    kept = _upload(
        service,
        S.settlement([S.fee("LostInventory", "2026-10-21", "-2.00", gtin=S.GTIN_1, ref="R5")]),
        store_id=S.STORE_B,
    )
    assert kept.store_id == S.STORE_A
    filled = _upload(service, unknown, store_id=S.STORE_B)
    assert filled.status == "parsed" and filled.store_id == S.STORE_B


def test_store_vote_uses_sku_and_refuses_ambiguous_products(service, session):
    _listing(session, S.GTIN_2, "30000000002", "B-MSKU-2", store_id=S.STORE_B)
    session.flush()
    # 同一 GTIN 两家店都有、没有 SKU → 分不出来
    ambiguous = _upload(
        service,
        S.settlement(
            [S.fee("LostInventory", "2026-10-07", "-1.00", gtin=S.GTIN_2, ref="R7", partner="P-X")]
        ),
    )
    assert ambiguous.status == "rejected" and ambiguous.needs_store
    # 仓储费报表带 SKU（店铺自己的编码）→ 能分开
    storage = _upload(
        service,
        S.storage(
            [(S.GTIN_2, "B-MSKU-2", "1.00", "1.00", "0")],
            period=("2026-10-03", "2026-10-16"),
            total="1.00",
        ),
    )
    assert storage.status == "parsed" and storage.store_id == S.STORE_B


def test_storage_period_overlap_is_rejected_and_same_period_replaces(service, session):
    first = _upload(
        service,
        S.storage(
            [
                (S.GTIN_1, "MSKU-1", "9.65", "10.62", "0.97"),
                (S.GTIN_2, "MSKU-2", "20.25", "22.16", "1.91"),
            ],
            period=("2026-10-03", "2026-10-16"),
            total="29.90",
        ),
        store_id=S.STORE_A,
    )
    assert first.status == "parsed" and first.rows_new == 2
    rows = _lines(session, fee_type="StorageFee")
    assert {r.item_id for r in rows} == {"30000000001", "30000000002"}
    assert rows[0].report_key == RK_1020 and rows[0].date_charged == date(2026, 10, 16)
    overlap = _upload(
        service,
        S.storage(
            [(S.GTIN_1, "MSKU-1", "1", "1", "0")], period=("2026-10-10", "2026-10-23"), total="1"
        ),
        store_id=S.STORE_A,
    )
    assert overlap.status == "rejected" and "账期重叠" in (overlap.reject_reason or "")
    replaced = _upload(
        service,
        S.storage(
            [(S.GTIN_1, "MSKU-1", "9.70", "10.62", "0.92")],
            period=("2026-10-03", "2026-10-16"),
            total="9.70",
        ),
        store_id=S.STORE_A,
    )
    assert replaced.status == "parsed" and replaced.rows_new == 0 and replaced.rows_duplicate == 1
    rows = {r.gtin: r for r in _lines(session, fee_type="StorageFee")}
    assert rows[S.GTIN_1].amount_usd == Decimal("-9.70") and rows[S.GTIN_1].missing_since is None
    assert rows[S.GTIN_2].missing_since is not None
    empty = _upload(
        service, S.storage([], period=("2026-10-17", "2026-10-30"), total="0"), store_id=S.STORE_A
    )
    assert empty.status == "empty" and empty.rows_parsed == 0


def test_inbound_is_unallocated_until_adjusted_and_adjustments_are_recorded(service, session):
    result = _upload(
        service,
        S.inbound(
            [(S.CARGO, "2026-10-05", "Parcel", "Base", "$93.60")], ("2026-10-03", "2026-10-16")
        ),
        store_id=S.STORE_A,
    )
    assert result.status == "parsed"
    [row] = _lines(session, fee_type="InboundTransportationFee")
    assert (
        row.attribution == "unallocated"
        and row.po_number == S.CARGO
        and row.amount_usd == Decimal("-93.60")
    )
    with pytest.raises(WfsFeeError, match="不相等"):
        service.adjust(
            row.id,
            kind="realloc",
            payload={"shares": [{"gtin": S.GTIN_1, "amount": "-50"}]},
            reason="合成原因",
            actor="u",
            request_id=None,
        )
    with pytest.raises(WfsFeeError, match="要写原因"):
        service.adjust(row.id, kind="company", payload={}, reason="  ", actor="u", request_id=None)
    adjusted = service.adjust(
        row.id,
        kind="realloc",
        payload={
            "shares": [
                {"gtin": S.GTIN_1, "amount": "-70.20"},
                {"gtin": S.GTIN_2, "amount": "-23.40"},
            ]
        },
        reason="按实发 300:100",
        actor="u",
        request_id=None,
    )
    assert adjusted.attribution == "allocated"
    children = list(
        session.scalars(select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id == row.id))
    )
    assert sorted((c.item_id, c.amount_usd) for c in children) == [
        ("30000000001", Decimal("-70.20")),
        ("30000000002", Decimal("-23.40")),
    ]
    # 入库运费多收退款按这个货件的比例分
    refund = _upload(
        service,
        S.settlement(
            [
                S.fee(
                    "Refund",
                    "2026-10-13",
                    "-9.36",
                    reason="InboundTransportationShippingRefund",
                    detail=f"Refund for _{S.CARGO}_ overcharge",
                    ref="R5",
                )
            ]
        ),
        store_id=S.STORE_A,
    )
    assert refund.status == "parsed"
    [refund_row] = _lines(session, fee_type="Refund")
    assert refund_row.attribution == "allocated"
    kids = list(
        session.scalars(
            select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id == refund_row.id)
        )
    )
    assert sorted(k.amount_usd for k in kids) == [Decimal("2.34"), Decimal("7.02")]
    # 再传同一份入库报告：人工调整过的不被重算
    _upload(
        service,
        S.inbound(
            [(S.CARGO, "2026-10-05", "Parcel", "Base", "$93.60")], ("2026-10-03", "2026-10-16")
        ),
        store_id=S.STORE_A,
    )
    assert session.get(WalmartWfsFeeLine, row.id).attribution == "allocated"
    company = service.adjust(
        row.id, kind="company", payload={}, reason="老板说记公司", actor="u", request_id=None
    )
    assert company.attribution == "company"
    assert not list(
        session.scalars(select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id == row.id))
    )


def test_check_diff_can_be_verified_and_resets_when_amounts_change(service, session):
    _upload(
        service,
        S.settlement([S.fee("LostInventory", "2026-10-07", "-20.00", gtin=S.GTIN_1, ref="R1")]),
        store_id=S.STORE_A,
    )
    check = session.get(WalmartWfsFeeCheck, ("primary", S.STORE_A, RK_1020, "LostInventory"))
    assert (
        check.status == "diff"
        and check.lingxing_amount == Decimal("21.57")
        and check.report_amount == Decimal("20.00")
    )
    service.verify_check(
        store_id=S.STORE_A,
        report_key=RK_1020,
        fee_type="LostInventory",
        reason="报表漏一行，已向 Walmart 核实",
        actor="u",
    )
    assert (
        session.get(
            WalmartWfsFeeCheck, ("primary", S.STORE_A, RK_1020, "LostInventory")
        ).verified_by
        == "u"
    )
    _upload(
        service,
        S.settlement(
            [
                S.fee("LostInventory", "2026-10-07", "-20.00", gtin=S.GTIN_1, ref="R1"),
                S.fee("LostInventory", "2026-10-08", "-1.57", gtin=S.GTIN_2, ref="R2"),
            ]
        ),
        store_id=S.STORE_A,
    )
    check = session.get(WalmartWfsFeeCheck, ("primary", S.STORE_A, RK_1020, "LostInventory"))
    assert check.status == "ok" and check.verified_by is None
    with pytest.raises(WfsFeeError, match="没有这条核对记录"):
        service.verify_check(
            store_id=S.STORE_A, report_key="nope", fee_type="LostInventory", reason="x", actor="u"
        )


def test_unmatched_gtin_and_rejected_file_are_kept_for_review(service, session):
    result = _upload(
        service,
        S.settlement([S.fee("LostInventory", "2026-10-07", "-1.00", gtin=S.GTIN_3, ref="R1")]),
        store_id=S.STORE_A,
    )
    assert result.status == "parsed"
    [row] = _lines(session)
    assert row.attribution == "unmatched" and row.item_id == ""
    bad = _upload(service, b"not,a,report\n1,2,3\n", name="x.csv", store_id=S.STORE_A)
    assert bad.status == "rejected"
    files = list(session.scalars(select(WalmartWfsFeeFile).order_by(WalmartWfsFeeFile.created_at)))
    assert [f.status for f in files] == ["parsed", "rejected"]


def test_periods_list_bill_periods_with_store_code_and_stores_without_bills(service, session):
    # 用不属于任何店的条码：认不出店，才会用传进来的 B 店
    _upload(
        service,
        S.storage(
            [(S.GTIN_3, "B-ONLY", "1.20", "1.20", "0")],
            period=("2026-10-03", "2026-10-16"),
            total="1.20",
        ),
        store_id=S.STORE_B,
    )
    items = reader.list_periods(session, "primary")
    assert [(i.store_id, i.store_code, i.report_key) for i in items] == [
        (S.STORE_A, "ZZ9901", RK_1103),
        (S.STORE_A, "ZZ9901", RK_1020),
        (S.STORE_B, S.STORE_B, None),
    ]
    assert items[0].period_start_date == date(2026, 10, 17)
