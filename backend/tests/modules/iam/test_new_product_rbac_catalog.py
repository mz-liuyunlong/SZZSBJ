from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS, PERMISSION_KEYS, page_permission_key

def test_new_product_and_tracking_have_separate_page_permissions():
    assert page_permission_key("products_new_product_analysis") == "page:products:new-product-analysis:view"
    assert page_permission_key("products_launch_tracking") == "page:products:launch-tracking:view"

def test_new_product_business_actions_and_sensitive_field_are_registered():
    expected = {
        "action:products:new-product-analysis:score",
        "action:products:new-product-analysis:request-purchase",
        "action:products:new-product-analysis:approve",
        "action:products:new-product-analysis:configure",
        "action:products:launch-tracking:review",
        "field:products:new-product-analysis:unit-cost",
    }
    assert expected <= PERMISSION_KEYS
    definitions = {item.permission_key: item for item in PERMISSION_DEFINITIONS}
    assert definitions["action:products:new-product-analysis:approve"].risk_level == "high"
    assert definitions["action:products:new-product-analysis:configure"].risk_level == "high"
    assert definitions["field:products:new-product-analysis:unit-cost"].risk_level == "high"
    assert definitions["action:products:launch-tracking:review"].page_key == "products_launch_tracking"
