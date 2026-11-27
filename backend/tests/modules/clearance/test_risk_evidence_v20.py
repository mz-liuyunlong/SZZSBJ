from datetime import UTC, date, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[3] / "app/modules/clearance/risk_evidence_v20.py"
SPEC = spec_from_file_location("risk_evidence_v20", SOURCE)
assert SPEC and SPEC.loader
_MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(_MODULE)
evidence_for_snapshot = _MODULE.evidence_for_snapshot


def rules():
    return SimpleNamespace(
        highCoverage=180,
        mediumCoverage=90,
        assistCoverage=60,
        enableCoverage=True,
        enableZero=True,
        zeroLookback=30,
        minListingDays=60,
        enableProfit=True,
        enableMargin30=True,
        margin30Threshold=8,
        enableDecline=True,
        salesDropPercent=40,
        enableReturns=True,
        returnRate=8,
        enableRating=True,
        ratingThreshold=3.8,
        enableNewProductProtection=True,
        newProductProtectionDays=60,
        enableCapitalPriority=True,
        minStockCapital=3000,
        enableInboundConflict=True,
        inboundConflictMin=1,
    )


def base(risk="high"):
    return {
        "risk": risk,
        "rule_version": 3,
        "signals": [],
        "data_gaps": [],
        "metrics": {
            "wfs_available": 843,
            "sales_30d": 60,
            "complete_30d_window": True,
            "sales_7d": 14,
            "sales_14d": 28,
            "complete_7d_window": True,
            "complete_14d_window": True,
            "first_wfs_days": 100,
            "listing_days": 200,
            "profit_7d_usd": -3,
            "profit_14d_usd": -9,
            "margin_30d_percent": 2,
            "rating": 4.4,
            "review_count": 100,
            "return_rate_30d_percent": 1,
            "returns_30d": 1,
            "ad_ratio_7d_percent": 22,
            "ad_ratio_30d_percent": 10,
            "capital_at_cost_usd": 4020,
        },
    }


def entry(result, code):
    return next(item for item in result["rule_hits"] if item["code"] == code)


def test_all_rule_evidence_contains_date_formula_source_and_threshold():
    snapshot = base()
    listing = SimpleNamespace(listing_start_at_utc=datetime(2026, 3, 15, 10, tzinfo=UTC))
    result = evidence_for_snapshot(
        snapshot, rules(), listing=listing, first_wfs_date=date(2026, 8, 1), as_of=date(2026, 11, 7)
    )
    assert result["risk"] == "high"
    assert entry(result, "coverage_high")["status"] == "hit"
    assert entry(result, "coverage_high")["actual_value"] == 422
    assert entry(result, "loss_7d_14d")["status"] == "hit"
    assert result["time_evidence"]["first_wfs_available_date_la"] == "2026-08-01"
    assert result["time_evidence"]["listing_start_at_utc"].startswith("2026-03-15")
    assert all("evidence" in x and "threshold" in x for x in result["rule_hits"])
    assert not any("aged" in x["code"] for x in result["rule_hits"])


def test_missing_daily_evidence_never_marks_rule_hit():
    snapshot = base("unknown")
    snapshot["metrics"].pop("complete_30d_window")
    snapshot["metrics"]["incomplete_30d"] = True
    result = evidence_for_snapshot(snapshot, rules())
    assert entry(result, "coverage_high")["status"] == "insufficient"
    assert entry(result, "returns_30d")["status"] == "insufficient"
    assert result["risk"] == "unknown"


def test_no_risk_only_when_evidence_is_complete_and_no_hits():
    snapshot = base("low")
    snapshot["metrics"].update(
        {
            "wfs_available": 1,
            "sales_30d": 100,
            "profit_7d_usd": 10,
            "profit_14d_usd": 14,
            "margin_30d_percent": 35,
            "rating": 4.9,
            "ad_ratio_7d_percent": 1,
            "ad_ratio_30d_percent": 2,
            "capital_at_cost_usd": 5,
            "first_wfs_days": 200,
        }
    )
    snapshot["metrics"]["sales_7d"] = 50
    snapshot["metrics"]["sales_14d"] = 100
    result = evidence_for_snapshot(snapshot, rules())
    assert result["risk"] in ("none", "unknown")
    assert entry(result, "coverage_high")["status"] == "not_hit"


def test_no_sales_is_infinite_coverage_but_not_verified_if_dates_missing():
    snapshot = base()
    snapshot["metrics"]["sales_30d"] = 0
    result = evidence_for_snapshot(snapshot, rules())
    assert entry(result, "coverage_high")["actual_value"] == "∞"
    assert entry(result, "coverage_high")["status"] == "hit"
    snapshot["metrics"]["incomplete_30d"] = True
    snapshot["metrics"].pop("complete_30d_window")
    result = evidence_for_snapshot(snapshot, rules())
    assert entry(result, "coverage_high")["status"] == "insufficient"
