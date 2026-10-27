"""OpenAI request failures distinguish definite rejection from uncertain billing."""

from decimal import Decimal

from app.integrations.llm.openai_provider import failed_call_reservation


def test_definite_provider_rejection_releases_reserved_cost() -> None:
    cost, code = failed_call_reservation(Decimal("0.0123"), 401)
    assert cost == Decimal("0")
    assert code == "AI_PROVIDER_REJECTED"


def test_rate_limit_rejection_releases_reserved_cost() -> None:
    cost, code = failed_call_reservation(Decimal("0.0123"), 429)
    assert cost == Decimal("0")
    assert code == "AI_PROVIDER_REJECTED"


def test_indeterminate_failure_retains_conservative_reservation() -> None:
    cost, code = failed_call_reservation(Decimal("0.0123"), None)
    assert cost == Decimal("0.0123")
    assert code == "AI_PROVIDER_FAILURE"
