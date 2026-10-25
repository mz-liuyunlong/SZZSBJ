"""Synthetic contract only. No actual Walmart template or upload authority."""

import hashlib

import pytest

from app.modules.keyword_planning.internal_export import _make_xlsx
from app.modules.keyword_planning.official_template import (
    OfficialTemplateBlocked,
    OfficialTemplateContract,
    render_verified_bulk,
    verify_official_template,
)

HEADERS = ("Keyword", "Match Type", "Bid", "Suggested Bid", "Total Budget", "Item Name")


def synthetic_template():
    blob = _make_xlsx([("Synthetic Bulk", HEADERS, [])])
    contract = OfficialTemplateContract(
        version="synthetic-v1",
        sha256=hashlib.sha256(blob).hexdigest(),
        sheet_name="Synthetic Bulk",
        headers=HEADERS,
        approved_by="synthetic-reviewer",
        approval_ref="synthetic:evidence",
    )
    return blob, contract


def test_synthetic_template_hash_header_and_rows_are_exact():
    blob, contract = synthetic_template()
    verify_official_template(blob, contract)
    row = dict(zip(HEADERS, ("synthetic term", "Exact", "0.50", "", "", ""), strict=True))
    rendered = render_verified_bulk(
        template_blob=blob, contract=contract, rows=[row], explicit_user_confirmation=True
    )
    assert rendered.startswith(b"PK")
    assert rendered != blob


def test_unverified_template_and_fields_fail_closed():
    blob, contract = synthetic_template()
    row = dict(zip(HEADERS, ("synthetic term", "Exact", "0.50", "", "", ""), strict=True))
    with pytest.raises(OfficialTemplateBlocked, match="USER_EXPORT_CONFIRMATION_REQUIRED"):
        render_verified_bulk(
            template_blob=blob, contract=contract, rows=[row], explicit_user_confirmation=False
        )
    with pytest.raises(OfficialTemplateBlocked, match="TEMPLATE_HASH_MISMATCH"):
        verify_official_template(blob + b"x", contract)
    with pytest.raises(OfficialTemplateBlocked, match="BULK_SYSTEM_FIELD_MUST_BE_BLANK"):
        render_verified_bulk(
            template_blob=blob,
            contract=contract,
            rows=[{**row, "Suggested Bid": "1"}],
            explicit_user_confirmation=True,
        )
    with pytest.raises(OfficialTemplateBlocked, match="BULK_DUPLICATE_TARGET"):
        render_verified_bulk(
            template_blob=blob, contract=contract, rows=[row, row], explicit_user_confirmation=True
        )
