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
    constraint = next(
        item
        for item in AdsSearchTermAction.__table__.constraints
        if getattr(item, "name", "") == "ck_ops_ads_search_term_actions_effect_status"
    )
    sql = str(constraint.sqltext)
    assert "provider_success" not in sql
    assert "pending" in sql
