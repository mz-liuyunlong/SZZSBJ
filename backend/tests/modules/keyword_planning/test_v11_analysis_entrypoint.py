from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.modules.keyword_planning.analysis_entrypoint import prepare_verified_analysis
from app.modules.keyword_planning.analysis_execution import AnalysisBlocked, _digest
from app.modules.keyword_planning.rule_gates import (
    REQUIRED_PRODUCT_FIELDS,
    ColdStartLimits,
)

NOW = datetime.now(UTC)
PRODUCT = uuid4()
FACT = uuid4()
PAGE = uuid4()
RULE = uuid4()
UPLOAD = uuid4()
TERM = uuid4()
TERM2 = uuid4()
R1 = uuid4()
R2 = uuid4()
R3 = uuid4()


class Session:
    def __init__(self):
        raw = {
            name: {
                "value": name + " verified",
                "source": "operator",
                "evidence_ref": "signed:" + name,
            }
            for name in REQUIRED_PRODUCT_FIELDS
        }
        raw["risk_boundary"] = {"mode": "none", "acknowledged": True}
        self.fact = NS(
            id=FACT,
            source_account_ref="acct",
            product_id=PRODUCT,
            item_id="item-1",
            status="confirmed",
            item_verified=True,
            facts_sha256=_digest(raw),
            facts_with_sources_json=raw,
            walmart_page_snapshot_id=PAGE,
        )
        self.page = NS(
            id=PAGE,
            source_account_ref="acct",
            product_id=PRODUCT,
            item_id="item-1",
            verification_status="verified",
            store_id="store-1",
        )
        self.version = NS(
            status="published",
            config_json={
                "limits": asdict(ColdStartLimits()),
                "confirmed_brands": {},
                "suspected_brands": {},
            },
            rule_set_id=uuid4(),
            config_sha256="a" * 64,
        )
        self.upload = NS(
            id=UPLOAD,
            source_account_ref="acct",
            product_id=PRODUCT,
            status="parsed",
            parser_version="test-parser",
        )
        self.rows = [
            NS(
                id=R1,
                keyword_raw="pantry organizer",
                keyword_normalized="pantry organizer",
                parse_errors=[],
                sheet_name="Main",
                row_number=2,
            ),
            NS(
                id=R2,
                keyword_raw="Pantry Organizer",
                keyword_normalized="pantry organizer",
                parse_errors=[],
                sheet_name="Main",
                row_number=3,
            ),
            NS(
                id=R3,
                keyword_raw=None,
                keyword_normalized=None,
                parse_errors=["NON_KEYWORD_SHEET"],
                sheet_name="Notes",
                row_number=2,
            ),
        ]
        self.terms = [NS(id=TERM, normalized_keyword="pantry organizer")]
        self.scalar_index = 0
        self.scalars_index = 0

    def scalar(self, stmt):
        self.scalar_index += 1
        values = (
            [self.fact, self.page, None, self.upload]
            if self.version.status == "published"
            else [self.fact, self.page, self.upload]
        )
        return values[self.scalar_index - 1]

    def get(self, model, id):
        return self.version

    def scalars(self, stmt):
        self.scalars_index += 1
        return [self.rows, self.terms][self.scalars_index - 1]


def prepare(s=None):
    return prepare_verified_analysis(
        s or Session(),
        account="acct",
        product_id=PRODUCT,
        item_id="item-1",
        fact_id=FACT,
        rule_version_id=RULE,
        upload_id=UPLOAD,
        request_key="key",
        actor="user",
    )


def test_db_only_request_deduplicates_without_erasing_raw_references():
    command, product, policy = prepare()
    assert len(command.candidates) == 1
    assert command.source_total_rows == 1
    assert command.candidates[0].assessment.source_row_refs == (str(R1), str(R2))
    assert command.candidates[0].assessment.match is None
    assert command.candidates[0].assessment.exact_requested is False
    assert command.candidates[0].assessment.labels[0].name == "人工确认词"
    assert command.input_sha256 != "0" * 64
    assert policy.version_id == str(RULE) and product.item_verified


def test_wrong_item_blocks_before_writes():
    with pytest.raises(AnalysisBlocked, match="PRODUCT_FACT_NOT_VERIFIED"):
        prepare_verified_analysis(
            Session(),
            account="acct",
            product_id=PRODUCT,
            item_id="different",
            fact_id=FACT,
            rule_version_id=RULE,
            upload_id=UPLOAD,
            request_key="key",
            actor="user",
        )


def test_unverified_page_blocks():
    s = Session()
    s.page.verification_status = "partial"
    with pytest.raises(AnalysisBlocked, match="VERIFIED_WALMART_PAGE_REQUIRED"):
        prepare(s)


def test_draft_rule_allows_internal_review_only():
    s = Session()
    s.version.status = "draft"
    _, _, policy = prepare(s)
    assert policy.status == "draft"


def test_retired_rule_blocks():
    s = Session()
    s.version.status = "retired"
    with pytest.raises(AnalysisBlocked, match="RULE_VERSION_NOT_AVAILABLE"):
        prepare(s)


def test_upload_not_parsed_blocks():
    s = Session()
    s.upload.status = "failed"
    with pytest.raises(AnalysisBlocked, match="VERIFIED_UPLOAD_REQUIRED"):
        prepare(s)


def test_formula_source_row_blocks():
    s = Session()
    s.rows[0].parse_errors = ["FORMULA_OR_CELL_ERROR"]
    with pytest.raises(AnalysisBlocked, match="SOURCE_ROW_REQUIRES_REVIEW"):
        prepare(s)
