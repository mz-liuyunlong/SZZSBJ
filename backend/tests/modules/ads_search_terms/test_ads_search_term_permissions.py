from app.core.permission_policy_v2 import permission_for_request
from app.modules.iam.permission_catalog_v2 import PERMISSION_KEYS


def test_search_terms_read_routes_use_canonical_page_permission() -> None:
    expected = "page:ads:search-terms:view"
    assert (
        permission_for_request(
            "GET",
            "/api/ads/search-terms/aggregates",
            "ads.search_terms.view",
        )
        == expected
    )
    assert (
        permission_for_request(
            "GET",
            "/api/ads/search-terms/actions",
            "ads.search_terms.view",
        )
        == expected
    )
    assert expected in PERMISSION_KEYS


def test_search_terms_action_routes_use_canonical_action_permission() -> None:
    expected = "action:ads:search-terms:manage-actions"
    assert (
        permission_for_request(
            "POST",
            "/api/ads/search-terms/actions",
            "ads.search_terms.actions.manage",
        )
        == expected
    )
    assert (
        permission_for_request(
            "PATCH",
            "/api/ads/search-terms/actions/00000000-0000-0000-0000-000000000001/complete",
            "ads.search_terms.actions.manage",
        )
        == expected
    )
    assert expected in PERMISSION_KEYS
