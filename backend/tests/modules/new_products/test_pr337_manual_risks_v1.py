import pytest
from pydantic import ValidationError
from app.modules.new_products.schemas import MarketWrite

_ID = {"source_account_ref":"primary","store_id":"100","item_id":"123",
       "score":7,"reason":"市场竞争情况分析完整","expected_version":0}

def test_manual_risk_must_be_explicitly_chosen():
    with pytest.raises(ValidationError):
        MarketWrite(**_ID)
    with pytest.raises(ValidationError):
        MarketWrite(**_ID, risk_conditions=[])

def test_manual_risk_none_is_a_valid_exclusive_selection():
    assert MarketWrite(**_ID, risk_conditions=["无"]).risk_conditions == ["无"]
    with pytest.raises(ValidationError):
        MarketWrite(**_ID,risk_conditions=["无", "质量风险"])

def test_manual_risk_multiple_conditions_and_deduplication():
    assert MarketWrite(**_ID,risk_conditions=["价格风险", "质量风险"]).risk_conditions == ["价格风险", "质量风险"]
    with pytest.raises(ValidationError):
        MarketWrite(**_ID,risk_conditions=["质量风险", "质量风险"])
    with pytest.raises(ValidationError):
        MarketWrite(**_ID,risk_conditions=["不在允许列表"])
