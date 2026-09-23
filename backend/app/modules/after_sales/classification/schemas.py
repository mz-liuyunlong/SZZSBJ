from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MatchType = Literal["EXACT_PAIR", "EXACT_DESCRIPTION", "KEYWORD", "CODE_DEFAULT"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
ClassificationSource = Literal[
    "EXACT_PAIR",
    "EXACT_DESCRIPTION",
    "KEYWORD",
    "CODE_DEFAULT",
    "FALLBACK",
]


@dataclass(frozen=True, slots=True)
class ReasonDefinition:
    reason_code: str
    reason_name_cn: str
    category_code: str
    category_name_cn: str
    tag_color: str


@dataclass(frozen=True, slots=True)
class ResponsibilityDefinition:
    code: str
    name_cn: str
    tag_color: str


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    id: str
    raw_reason_code: str | None
    match_type: MatchType
    match_value: str | None
    keywords_all: tuple[str, ...]
    keywords_any: tuple[str, ...]
    keywords_exclude: tuple[str, ...]
    normalized_reason_code: str
    responsibility_code: str
    priority: int
    confidence: Confidence
    rule_version: str
