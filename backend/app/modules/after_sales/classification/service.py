from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.modules.after_sales.classification.repository import (
    AfterSalesClassificationRepository,
    SqlExecutor,
)
from app.modules.after_sales.classification.schemas import (
    ClassificationRule,
    ClassificationSource,
    ReasonDefinition,
    ResponsibilityDefinition,
)

_WHITESPACE_RE = re.compile(r"\s+")
_SOURCE_ORDER = {
    "EXACT_PAIR": 0,
    "EXACT_DESCRIPTION": 1,
    "KEYWORD": 2,
    "CODE_DEFAULT": 3,
}


def _normalize_code(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_text(value: object) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip()).casefold()


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    normalized_reason_code: str
    reason_category_code: str
    responsibility_code: str
    classification_source: ClassificationSource
    classification_confidence: str
    classification_rule_id: str | None
    classification_rule_version: str | None
    classified_at: datetime

    def as_storage_values(self) -> dict[str, Any]:
        return {
            "normalized_reason_code": self.normalized_reason_code,
            "reason_category_code": self.reason_category_code,
            "responsibility_code": self.responsibility_code,
            "classification_source": self.classification_source,
            "classification_confidence": self.classification_confidence,
            "classification_rule_id": self.classification_rule_id,
            "classification_rule_version": self.classification_rule_version,
            "classified_at": self.classified_at,
        }


class AfterSalesReasonClassifier:
    """Classify Walmart reason code + description with governed DB rules.

    Precedence is locked to:
    EXACT_PAIR > EXACT_DESCRIPTION > KEYWORD > CODE_DEFAULT > FALLBACK.
    Manual overrides are intentionally not applied here; they live on the fact row and
    take precedence only when the API resolves the final presentation fields.
    """

    def __init__(
        self,
        *,
        reasons: dict[str, ReasonDefinition],
        responsibilities: dict[str, ResponsibilityDefinition],
        rules: list[ClassificationRule],
    ) -> None:
        self.reasons = reasons
        self.responsibilities = responsibilities
        self.rules = sorted(
            rules,
            key=lambda rule: (
                _SOURCE_ORDER.get(rule.match_type, 99),
                -rule.priority,
                rule.id,
            ),
        )

    @classmethod
    def from_executor(
        cls,
        executor: SqlExecutor,
        *,
        platform_code: str = "walmart",
    ) -> AfterSalesReasonClassifier:
        repository = AfterSalesClassificationRepository(executor)
        return cls(
            reasons=repository.load_reason_definitions(),
            responsibilities=repository.load_responsibility_definitions(),
            rules=repository.load_rules(platform_code),
        )

    def classify(
        self,
        raw_reason_code: object,
        raw_description: object,
        *,
        classified_at: datetime | None = None,
    ) -> ClassificationResult:
        code = _normalize_code(raw_reason_code)
        description = _normalize_text(raw_description)
        when = classified_at or datetime.now(UTC)

        for rule in self.rules:
            if self._matches(rule, code, description):
                reason = self.reasons.get(rule.normalized_reason_code)
                if reason is None:
                    continue
                responsibility = self.responsibilities.get(rule.responsibility_code)
                if responsibility is None:
                    continue
                return ClassificationResult(
                    normalized_reason_code=reason.reason_code,
                    reason_category_code=reason.category_code,
                    responsibility_code=responsibility.code,
                    classification_source=rule.match_type,
                    classification_confidence=rule.confidence,
                    classification_rule_id=rule.id,
                    classification_rule_version=rule.rule_version,
                    classified_at=when,
                )

        fallback_reason = self.reasons.get("UNCLASSIFIED")
        fallback_responsibility = self.responsibilities.get("PENDING")
        return ClassificationResult(
            normalized_reason_code=(
                fallback_reason.reason_code if fallback_reason else "UNCLASSIFIED"
            ),
            reason_category_code=(fallback_reason.category_code if fallback_reason else "PENDING"),
            responsibility_code=(
                fallback_responsibility.code if fallback_responsibility else "PENDING"
            ),
            classification_source="FALLBACK",
            classification_confidence="LOW",
            classification_rule_id=None,
            classification_rule_version=None,
            classified_at=when,
        )

    @staticmethod
    def _matches(rule: ClassificationRule, code: str, description: str) -> bool:
        rule_code = _normalize_code(rule.raw_reason_code)
        if rule_code and rule_code != code:
            return False

        if rule.match_type == "EXACT_PAIR":
            return bool(rule_code) and description == _normalize_text(rule.match_value)

        if rule.match_type == "EXACT_DESCRIPTION":
            return description == _normalize_text(rule.match_value)

        if rule.match_type == "CODE_DEFAULT":
            return bool(rule_code) and rule_code == code

        if rule.match_type != "KEYWORD":
            return False

        all_words = tuple(_normalize_text(value) for value in rule.keywords_all)
        any_words = tuple(_normalize_text(value) for value in rule.keywords_any)
        excluded = tuple(_normalize_text(value) for value in rule.keywords_exclude)

        if any(word and word in description for word in excluded):
            return False
        if all_words and not all(word and word in description for word in all_words):
            return False
        if any_words and not any(word and word in description for word in any_words):
            return False
        return bool(all_words or any_words)
