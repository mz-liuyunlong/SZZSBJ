from app.modules.ads_search_terms.models import (
    AdsSearchTermAction,
    AdsSearchTermActionEvent,
    WalmartAdSearchTermDailyFact,
    WalmartManualKeywordDailyFact,
)


def test_search_term_models_register_expected_tables() -> None:
    assert WalmartAdSearchTermDailyFact.__tablename__ == "fact_walmart_ad_search_term_daily"
    assert WalmartManualKeywordDailyFact.__tablename__ == "fact_walmart_keyword_sp_daily"
    assert AdsSearchTermAction.__tablename__ == "ops_ads_search_term_actions"
    assert AdsSearchTermActionEvent.__tablename__ == "ops_ads_search_term_action_events"


def test_action_model_has_no_provider_write_success_state() -> None:
    allowed = {
        item.strip().strip("'")
        for item in next(
            constraint.sqltext
            for constraint in AdsSearchTermAction.__table__.constraints
            if getattr(constraint, "name", "") == "effect_status"
        ).split("IN", 1)[1].strip(" ()")
        .split(",")
    }
    assert "provider_success" not in allowed
    assert "pending" in allowed
