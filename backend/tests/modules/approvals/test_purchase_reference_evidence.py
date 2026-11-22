"""As-submitted purchase evidence: no HTTP, credentials, network, or database writes."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.approvals.purchase_reference_evidence import purchase_reference_evidence


class ReadOnlySession:
    def __init__(self, events):
        self.events = events

    def scalar(self, _stmt):
        return SimpleNamespace(config_json={"weights": {"market": 15, "speed": 30, "ad": 20, "profit": 25, "trust": 10}})

    def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: self.events)


def application():
    now = datetime(2026, 11, 20, 12, tzinfo=UTC)
    dims = {"market": "7", "speed": "6", "ad": "2", "profit": "3", "trust": "4.6"}
    return SimpleNamespace(
        source_account_ref="a", store_id="s", item_id="20858150090",
        created_at=now, score_rule_version=12,
        score_snapshot={
            "evaluation": {"dimensions": dims, "total": "6", "grade": "C", "risk": []},
            "facts": {},
            "score_correction": {
                "system": {"dimensions": {**dims, "speed": "4.6", "profit": "0"}},
                "effective": {"dimensions": dims},
                "history": [
                    {"dimension": "speed", "before": "4.6", "after": "6", "reason": "周期修正", "at": now.isoformat()},
                    {"dimension": "profit", "before": "0", "after": "3", "reason": "修正利润口径", "at": now.isoformat()},
                ],
            },
        },
    )


def market_event(now, risk, ids, none):
    return SimpleNamespace(event_type="market_score", source_account_ref="a", store_id="s",
        item_id="20858150090", created_at=now - timedelta(seconds=1), id="1",
        payload_json={"score": 7, "reason": "已核实竞品价格", "risk_conditions": risk,
                      "competitor_ids": ids, "no_competitors": none})


def test_preserves_historical_system_and_effective_scores():
    app = application()
    result = purchase_reference_evidence(ReadOnlySession([market_event(app.created_at, ["资金占用率高"], ["1234"], False)]), app)
    assert result["effective_dimensions"]["speed"] == "6"
    assert result["system_dimensions"]["speed"] == "4.6"
    assert result["weights"]["speed"] == 30
    assert result["correction_history"][1]["reason"] == "修正利润口径"
    assert result["manual_risks"] == ["资金占用率高"]
    assert result["competitor_ids"] == ["1234"]
    assert result["manual_conclusion"] is None  # Never fabricate a human conclusion from C-grade


def test_explicit_none_is_distinct_from_unknown():
    app = application()
    yes = purchase_reference_evidence(ReadOnlySession([market_event(app.created_at, ["无"], [], True)]), app)
    missing = purchase_reference_evidence(ReadOnlySession([]), app)
    assert yes["manual_risks"] == ["无"]
    assert yes["no_competitors"] is True
    assert missing["manual_risks"] is None
    assert missing["no_competitors"] is None
