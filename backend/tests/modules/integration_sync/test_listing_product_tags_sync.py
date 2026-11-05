"""Product Management tags have an account-specific, non-custom-tag write path."""

from unittest.mock import MagicMock

import pytest

from app.modules.integration_sync.listing_product_tags_sync import (
    PRODUCT_TAG_SQL,
    refresh_listing_product_tags,
)


def test_product_tags_update_is_scoped_and_never_mutates_custom_tags() -> None:
    statement = PRODUCT_TAG_SQL.lower()
    assert "where p.source_account_ref = :account" in statement
    assert "where l.source_account_ref = :account" in statement
    assert "target.product_tags_json" in statement
    assert "target.product_tags_match_status" in statement
    assert "tags_json =" not in statement.replace("product_tags_json =", "")
    assert "product_custom_tag_assignments" not in statement
    assert "when s.candidates > 1 then 'ambiguous'" in statement
    assert "is distinct from" in statement
    session = MagicMock()
    session.execute.return_value.rowcount = 3
    assert refresh_listing_product_tags(session, " acct-01 ") == 3
    assert session.execute.call_args.args[1] == {"account": "acct-01"}
    session.commit.assert_not_called()


@pytest.mark.parametrize("account", ["", " ", "	"])
def test_product_tags_sync_refuses_empty_account(account: str) -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="source_account_ref"):
        refresh_listing_product_tags(session, account)
    session.execute.assert_not_called()
