"""Focused WFS lifecycle auto-publication contracts (no real database)."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.modules.listing_rule_config.automation import (
    AUTO_STAGES,
    REQUIRED_TABLES,
    _safe_monitor_observation,
    decide_lifecycle,
)
from app.modules.listing_rule_config.evaluation import BusinessDay
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig

CFG = ListingGradeRuleConfig()
CUTOFF = date(2026, 11, 2)


def days(stock: int, sales: int | None, n: int = 30) -> list[BusinessDay]:
    return [
        BusinessDay(
            CUTOFF - timedelta(days=i), Decimal(stock), None if sales is None else Decimal(sales)
        )
        for i in range(n)
    ]


def test_initializes_first_verified_wfs_listing_without_guessing_trend():
    candidate = decide_lifecycle(
        previous_stage=None,
        first_positive=date(2026, 10, 30),
        cutoff=CUTOFF,
        days=days(40, None),
        config=CFG,
    )
    assert candidate.stage == "启动期"
    assert candidate.evidence_complete


def test_no_first_positive_never_initializes():
    candidate = decide_lifecycle(
        previous_stage=None,
        first_positive=None,
        cutoff=CUTOFF,
        days=days(40, 1),
        config=CFG,
    )
    assert candidate.stage is None


def test_absent_cutoff_wfs_snapshot_never_writes():
    candidate = decide_lifecycle(
        previous_stage=None,
        first_positive=date(2026, 10, 1),
        cutoff=CUTOFF,
        days=days(20, 2)[1:],
        config=CFG,
    )
    assert candidate.stage is None
    assert candidate.reason == "CUTOFF_WFS_SNAPSHOT_MISSING"


def test_protected_workflow_stage_cannot_be_auto_overwritten():
    for stage in ["测品期", "打品期", "清货期", "已归档"]:
        candidate = decide_lifecycle(
            previous_stage=stage,
            first_positive=date(2026, 10, 1),
            cutoff=CUTOFF,
            days=days(20, 2),
            config=CFG,
        )
        assert candidate.stage is None


def test_existing_stage_preserved_when_trend_incomplete():
    candidate = decide_lifecycle(
        previous_stage="稳定期",
        first_positive=date(2026, 10, 1),
        cutoff=CUTOFF,
        days=days(20, None),
        config=CFG,
    )
    assert candidate.stage is None
    assert not candidate.evidence_complete


def test_previous_positive_and_seven_low_days_enters_stockout():
    candidate = decide_lifecycle(
        previous_stage="启动期",
        first_positive=date(2026, 9, 20),
        cutoff=CUTOFF,
        days=days(0, 0, 7),
        config=CFG,
    )
    assert candidate.stage == "断货期"
    assert candidate.consecutive_low_stock_days == 7


def test_buybox_normal_is_not_proof_own_store_won():
    obs = SimpleNamespace(
        strike_price_amount=Decimal("25"), sale_price_amount=Decimal("20"), buybox_status="NORMAL"
    )
    assert _safe_monitor_observation(obs) == (False, None)
    obs.buybox_status = "NOT_FOUND"
    assert _safe_monitor_observation(obs) == (False, True)
    obs.buybox_status = "LOST"
    assert _safe_monitor_observation(obs) == (False, True)


def test_price_and_missing_price_handling():
    obs = SimpleNamespace(
        strike_price_amount=None, sale_price_amount=Decimal("20"), buybox_status="NORMAL"
    )
    assert _safe_monitor_observation(obs) == (None, None)
    obs.strike_price_amount = Decimal("19")
    assert _safe_monitor_observation(obs) == (True, None)


def test_schema_prerequisites_and_automatic_stages_are_explicit():
    assert "listing_wfs_first_stock_la_locked" in REQUIRED_TABLES
    assert "biz_listing_lifecycle_manual_states" in REQUIRED_TABLES
    assert "biz_listing_lifecycle_auto_history" in REQUIRED_TABLES
    assert "稳定期" in AUTO_STAGES and "清货期" not in AUTO_STAGES


def test_same_stage_manual_action_still_creates_override_and_history():
    """Operator selecting existing stage must block future automatic writes."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from app.modules.data_pages.lifecycle_manual import set_manual_lifecycle

    ident = uuid4()
    row = SimpleNamespace(
        id=ident,
        source_account_ref="acct",
        store_id="shop",
        item_id="item",
        msku="sku",
        lifecycle_status="启动期",
    )
    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = [row]
    session.execute.return_value.scalars.return_value.all.return_value = []
    changed, unchanged = set_manual_lifecycle(
        session=session,
        listing_ids=[ident],
        stage="启动期",
        reason="人工确认启动期",
        actor_ref="operator",
        account_refs=frozenset({"acct"}),
    )
    assert (changed, unchanged) == (0, 1)
    assert session.execute.call_count == 3
    session.commit.assert_called_once()


def test_incomplete_history_and_zero_current_stock_does_not_initialize():
    candidate = decide_lifecycle(
        previous_stage=None,
        first_positive=date(2026, 10, 1),
        cutoff=CUTOFF,
        days=days(0, None, 3),
        config=CFG,
    )
    assert candidate.stage is None
    assert candidate.reason == "ZERO_WFS_AND_STOCKOUT_EVIDENCE_INCOMPLETE"


def test_explicit_raw_strikethrough_absence_is_abnormal():
    obs = SimpleNamespace(
        strike_price_amount=None, sale_price_amount=Decimal("20"), buybox_status="NORMAL"
    )
    assert _safe_monitor_observation(obs, has_strikethrough=False) == (True, None)
    assert _safe_monitor_observation(obs, has_strikethrough=None) == (None, None)


def test_legacy_stock_observation_cannot_initialize_startup():
    candidate = decide_lifecycle(
        previous_stage=None,
        first_positive=date(2026, 9, 16),
        first_positive_source="historical_wfs_snapshot",
        cutoff=CUTOFF,
        days=days(35, None),
        config=CFG,
    )
    assert candidate.stage is None
    assert candidate.reason == "HISTORICAL_FIRST_WFS_NOT_LAUNCH_VERIFIED"


def test_legacy_stock_observation_can_publish_proven_stable_trend():
    candidate = decide_lifecycle(
        previous_stage=None,
        first_positive=date(2026, 9, 16),
        first_positive_source="historical_wfs_snapshot",
        cutoff=CUTOFF,
        days=days(35, 5),
        config=CFG,
    )
    assert candidate.stage == "稳定期"
    assert candidate.evidence_complete
    assert candidate.reason.startswith("HISTORICAL_WFS_TREND_ONLY:")


def test_legacy_observation_allows_seven_day_stockout_with_proof():
    candidate = decide_lifecycle(
        previous_stage=None,
        first_positive=date(2026, 9, 16),
        first_positive_source="historical_wfs_snapshot",
        cutoff=CUTOFF,
        days=days(0, None, 7),
        config=CFG,
    )
    assert candidate.stage == "断货期"
    assert candidate.evidence_complete


def test_historical_stock_source_is_read_from_locked_table():
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

    from app.modules.listing_rule_config.automation import _first_wfs_date

    row = SimpleNamespace(source_account_ref="acct", store_id="store", item_id="item")
    session = MagicMock(spec=Session)
    session.execute.return_value.mappings.return_value.first.return_value = {
        "first_wfs_available_date_la": date(2026, 9, 16),
        "date_source": "historical_wfs_snapshot",
    }
    assert _first_wfs_date(session, row) == (date(2026, 9, 16), "historical_wfs_snapshot")


def test_multi_msku_one_positive_and_one_explicit_zero_is_not_missing():
    from app.modules.listing_rule_config.automation import _daily_item_sales

    assert _daily_item_sales(
        [("YC00163-1B", Decimal("4")), ("YC00163-1C", Decimal("0"))]
    ) == Decimal("4")
    assert _daily_item_sales(
        [("YC00163-1B", Decimal("1")), ("YC00163-1C", Decimal("0"))]
    ) == Decimal("1")


def test_multi_msku_distinct_positive_quantities_are_item_level_sum():
    from app.modules.listing_rule_config.automation import _daily_item_sales

    assert _daily_item_sales([("A", Decimal("2")), ("B", Decimal("3"))]) == Decimal("5")


def test_multi_msku_missing_or_duplicate_identity_does_not_guess():
    from app.modules.listing_rule_config.automation import _daily_item_sales

    assert _daily_item_sales([("A", Decimal("2")), ("A", Decimal("3"))]) is None
    assert _daily_item_sales([("A", Decimal("2")), (None, Decimal("3"))]) is None
    assert _daily_item_sales([("A", Decimal("2")), (" ", Decimal("3"))]) is None
    assert _daily_item_sales([]) is None
    assert _daily_item_sales([(None, Decimal("0"))]) == Decimal("0")


def test_wfs_inventory_scope_ignores_fulfillment_type():
    """A non-WFS ERP label cannot exclude an actual WFS-positive inventory series."""
    from unittest.mock import MagicMock, patch

    from sqlalchemy.orm import Session

    from app.modules.listing_rule_config.automation import process_lifecycle_batch

    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = []
    with patch("app.modules.listing_rule_config.automation.verify_schema"):
        outcome = process_lifecycle_batch(
            session,
            cutoff=CUTOFF,
            config=CFG,
            rule_version=2,
            dry_run=True,
        )
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "fact_walmart_listing_inventory_daily" in sql
    assert "wfs_available_quantity > 0" in sql
    assert "snapshot_date_la <=" in sql
    assert "fulfillment_type" not in sql
    assert outcome.examined == 0


def test_wfs_inventory_scope_supports_zero_today_after_positive_history():
    """The candidate query has no restriction on current MART stock quantity."""
    from unittest.mock import MagicMock, patch

    from sqlalchemy.orm import Session

    from app.modules.listing_rule_config.automation import process_lifecycle_batch

    session = MagicMock(spec=Session)
    session.scalars.return_value.all.return_value = []
    with patch("app.modules.listing_rule_config.automation.verify_schema"):
        process_lifecycle_batch(
            session,
            cutoff=CUTOFF,
            config=CFG,
            rule_version=2,
            dry_run=True,
            max_listings=3,
        )
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "mart_listing_management_current.wfs_available_quantity" not in sql
    assert "fact_walmart_listing_inventory_daily.wfs_available_quantity > 0" in sql
    assert "LIMIT 3" in sql
