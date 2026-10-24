"""Pure V1.1 rule-contract gates; deliberately NO inferred product facts or API calls.

This is a safe deterministic FOUNDATION, not a claim to implement the complete 49-chapter
classifier. Upstream must produce evidence-backed 25-type classifications and six scoring
components. Unknown components cause review, never guessed numeric scores.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Literal

NORMALIZER_VERSION = "v1_trim_casefold_whitespace"
ALGORITHM_VERSION = "v1_1_safe_gates_20261023"
ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
MISSING_MARKERS = frozenset(
    {
        "待核对",
        "待采集",
        "暂无",
        "未知",
        "无数据",
        "unknown",
        "n/a",
        "--",
        "null",
        "undefined",
        "tbd",
        "none",
    }
)
REQUIRED_PRODUCT_FIELDS = (
    "title",
    "item_type",
    "brand",
    "material",
    "color",
    "pack",
    "size",
    "structure",
    "use",
    "owner",
)
KEYWORD_TYPES = (
    "核心本体词",
    "核心材质长尾词",
    "核心场景长尾词",
    "核心规格/数量词",
    "精准长尾词",
    "同义表达词",
    "复数变体词",
    "拼写变体词",
    "相邻结构词",
    "相邻用途词",
    "次级场景词",
    "泛流量词",
    "品牌/竞品词",
    "配件/替换词",
    "错货架词",
    "结构冲突词",
    "材质不符词",
    "规格/尺寸不符词",
    "Pack/数量不符词",
    "颜色/款式不符词",
    "合规/认证风险词",
    "机器设备词",
    "食材本身词",
    "低价值重复词",
    "人工确认词",
)
COVERAGE = (
    "标题已埋词",
    "标题意思已覆盖",
    "详情/属性已埋词",
    "场景/用途能接住",
    "用户确认能接住",
    "页面没埋但可优化",
    "页面埋得弱，先验证",
    "页面看不出来",
    "页面不建议埋",
)
PAGE_POINTS = dict(zip(COVERAGE, (20, 18, 16, 14, 13, 10, 8, 4, 0), strict=True))
PAGE_TEXT_EVIDENCE = frozenset({"标题已埋词", "标题意思已覆盖", "详情/属性已埋词"})
RISK_PRIMARY_TYPES = frozenset(
    {
        "错货架词",
        "配件/替换词",
        "结构冲突词",
        "材质不符词",
        "规格/尺寸不符词",
        "Pack/数量不符词",
        "颜色/款式不符词",
        "合规/认证风险词",
        "机器设备词",
        "食材本身词",
    }
)
Grade = Literal["P0", "P1", "P2", "品牌等级", "候选复查", "不投放"]
BroadRole = Literal["root", "long_tail", "none"]


def normalize_keyword(value: str) -> str:
    """Conservative normalization: NOT stemming, punctuation deletion, or plural merging."""
    return " ".join(value.casefold().strip().split())


def parse_asins(raw: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    seen: set[str] = set()
    valid, invalid = [], []
    for item in re.split(r"[\s,，;；]+", raw.upper()):
        term = item.strip()
        if not term or term in seen:
            continue
        seen.add(term)
        (valid if ASIN_PATTERN.fullmatch(term) else invalid).append(term)
    return tuple(valid), tuple(invalid)


def is_real_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().casefold() not in MISSING_MARKERS
    )


@dataclass(frozen=True)
class ProductField:
    value: str
    source: Literal["walmart", "operator", "product_management"]
    evidence_ref: str | None = None


@dataclass(frozen=True)
class ProductConfirmation:
    item_id: str
    item_verified: bool
    source_item_id: str | None
    facts: Mapping[str, ProductField]
    risk_boundary_acknowledged: bool
    # A separate explicit 'none' acknowledgement is needed if no risk directions exist.
    risk_boundary_mode: Literal["provided", "none", "unreviewed"]


def product_confirmation_errors(value: ProductConfirmation) -> tuple[str, ...]:
    errors: list[str] = []
    if not value.item_verified or not value.item_id or value.item_id != value.source_item_id:
        errors.append("ITEM_ID_UNVERIFIED")
    for key in REQUIRED_PRODUCT_FIELDS:
        f = value.facts.get(key)
        if f is None or not is_real_text(f.value):
            errors.append(f"PRODUCT_REQUIRED_MISSING:{key}")
        elif f.source == "walmart" and not f.evidence_ref:
            errors.append(f"PRODUCT_WALMART_EVIDENCE_MISSING:{key}")
    if not value.risk_boundary_acknowledged or value.risk_boundary_mode == "unreviewed":
        errors.append("RISK_BOUNDARY_NOT_REVIEWED")
    return tuple(errors)


@dataclass(frozen=True)
class ColdStartLimits:
    max_p0: int = 5
    max_p1: int = 10
    max_p2: int = 30
    max_exact: int = 20
    max_broad_roots: int = 5
    max_broad_long_tails: int = 15

    def validate(self) -> None:
        numbers = (
            self.max_p0,
            self.max_p1,
            self.max_p2,
            self.max_exact,
            self.max_broad_roots,
            self.max_broad_long_tails,
        )
        if any(type(n) is not int or n < 0 for n in numbers):
            raise ValueError("RULE_QUOTA_INVALID")


@dataclass(frozen=True)
class KeywordEvidence:
    keyword: str
    primary_type: str | None
    core_root: str | None
    root_grade: str | None
    page_coverage: str | None
    page_snapshot_verified: bool
    page_evidence_ref: str | None
    match_points: int | None
    intent_points: int | None
    page_points: int | None
    root_points: int | None
    data_points: int | None
    risk_points: int | None = 0
    hard_risk_reasons: tuple[str, ...] = ()
    brand_status: Literal["none", "confirmed", "suspected"] = "none"
    exact_eligible: bool = False
    broad_eligible: bool = False
    broad_role: BroadRole = "none"
    broad_risk: Literal["low", "medium", "high", "unknown"] = "unknown"
    # Evidence for the original 14-layer stable tie-breaking order.
    is_standard_expression: bool = True
    is_correct_spelling: bool = True
    is_low_value_duplicate: bool = False


@dataclass(frozen=True)
class KeywordDecision:
    keyword: str
    score: int | None
    base_grade: Grade
    allocation_grade: Grade
    exact_selected: bool = False
    broad_selected: bool = False
    broad_role: BroadRole = "none"
    reasons: tuple[str, ...] = ()
    source: KeywordEvidence | None = None


def _points_ok(value: int | None, ceiling: int, floor: int = 0) -> bool:
    return type(value) is int and floor <= value <= ceiling


def score_evidence(e: KeywordEvidence) -> KeywordDecision:
    """Never create classifications or numeric evidence from missing data."""
    reasons: list[str] = []
    if not normalize_keyword(e.keyword):
        reasons.append("KEYWORD_EMPTY")
    if e.primary_type not in KEYWORD_TYPES:
        reasons.append("TYPE_NOT_EVIDENCED")
    if e.page_coverage not in COVERAGE:
        reasons.append("PAGE_COVERAGE_MISSING")
    if e.page_coverage in PAGE_TEXT_EVIDENCE and (
        not e.page_snapshot_verified or not e.page_evidence_ref
    ):
        reasons.append("PAGE_TEXT_CLAIM_NOT_EVIDENCED")
    if e.page_coverage in PAGE_POINTS and (e.page_points != PAGE_POINTS[e.page_coverage]):
        reasons.append("PAGE_POINTS_INCONSISTENT")
    if not _points_ok(e.match_points, 30):
        reasons.append("MATCH_POINTS_MISSING_OR_INVALID")
    if not _points_ok(e.intent_points, 20):
        reasons.append("INTENT_POINTS_MISSING_OR_INVALID")
    if not _points_ok(e.page_points, 20):
        reasons.append("PAGE_POINTS_MISSING_OR_INVALID")
    if not _points_ok(e.root_points, 15):
        reasons.append("ROOT_POINTS_MISSING_OR_INVALID")
    if not _points_ok(e.data_points, 15):
        reasons.append("DATA_POINTS_MISSING_OR_INVALID")
    if not _points_ok(e.risk_points, 0, -40):
        reasons.append("RISK_POINTS_MISSING_OR_INVALID")
    hard = bool(e.hard_risk_reasons) or e.primary_type in RISK_PRIMARY_TYPES
    if hard:
        return KeywordDecision(
            e.keyword, None, "不投放", "不投放", reasons=tuple(reasons) + ("HARD_RISK",), source=e
        )
    if e.primary_type == "人工确认词":
        return KeywordDecision(
            e.keyword,
            None,
            "候选复查",
            "候选复查",
            reasons=tuple(reasons) + ("TYPE_NEEDS_CONFIRMATION",),
            source=e,
        )
    if e.page_coverage == "页面不建议埋":
        return KeywordDecision(
            e.keyword,
            None,
            "不投放",
            "不投放",
            reasons=tuple(reasons) + ("PAGE_UNSUITABLE",),
            source=e,
        )
    if e.brand_status == "suspected":
        return KeywordDecision(
            e.keyword,
            None,
            "候选复查",
            "候选复查",
            reasons=tuple(reasons) + ("BRAND_UNCONFIRMED",),
            source=e,
        )
    if e.brand_status == "confirmed":
        return KeywordDecision(
            e.keyword,
            None,
            "品牌等级",
            "品牌等级",
            reasons=tuple(reasons) + ("BRAND_CONFIRMED",),
            source=e,
        )
    if reasons:
        return KeywordDecision(
            e.keyword, None, "候选复查", "候选复查", reasons=tuple(reasons), source=e
        )
    components = (
        e.match_points,
        e.intent_points,
        e.page_points,
        e.root_points,
        e.data_points,
        e.risk_points,
    )
    assert all(isinstance(x, int) for x in components)
    total = max(0, min(100, sum(x for x in components if x is not None)))
    base: Grade = (
        "P0"
        if total >= 85
        else "P1"
        if total >= 75
        else "P2"
        if total >= 60
        else "候选复查"
        if total >= 45
        else "不投放"
    )
    return KeywordDecision(e.keyword, total, base, base, source=e)


def _sort_key(d: KeywordDecision) -> tuple[object, ...]:
    e = d.source
    assert e is not None
    root_order = {"R0": 0, "R1": 1, "R2": 2}
    page_order = {name: i for i, name in enumerate(COVERAGE)}
    # Original V1 §17.5: all 14 tie-breaker rules, followed in exact order.
    return (
        -(d.score or 0),  # 01 score
        page_order.get(e.page_coverage, 99),  # 02 page evidence
        -(e.match_points or 0),  # 03 product match
        -(e.intent_points or 0),  # 04 search intent
        root_order.get(e.root_grade or "", 99),  # 05 root grade
        e.root_grade != "R0",  # 06 core root priority
        e.primary_type != "核心材质长尾词",  # 07 core material
        e.primary_type != "核心规格/数量词",  # 08 spec / pack
        e.primary_type != "核心场景长尾词",  # 09 core scene
        not e.is_standard_expression,  # 10 standard expression
        not e.is_correct_spelling,  # 11 correct spelling
        e.is_low_value_duplicate,  # 12 not low-value duplicate
        len(normalize_keyword(d.keyword)),  # 13 shorter wording
        normalize_keyword(d.keyword),  # 14 alphabetical
    )


def allocate_ads(
    evidence: tuple[KeywordEvidence, ...], limits: ColdStartLimits | None = None
) -> tuple[KeywordDecision, ...]:
    """Stable V1 quota allocation. Broad is NOT inferred from P-grade or Exact eligibility."""
    limits = limits or ColdStartLimits()
    limits.validate()
    decisions = [score_evidence(e) for e in evidence]
    if len({normalize_keyword(d.keyword) for d in decisions}) != len(decisions):
        raise ValueError("ANALYSIS_DUPLICATE_KEYWORDS; raw rows must remain preserved")
    active = [d for d in decisions if d.base_grade in ("P0", "P1", "P2")]
    direct = {
        g: sorted((d for d in active if d.base_grade == g), key=_sort_key)
        for g in ("P0", "P1", "P2")
    }
    p0 = direct["P0"][: limits.max_p0]
    p1_candidates = direct["P0"][limits.max_p0 :] + direct["P1"]
    p1_candidates.sort(key=_sort_key)
    p1 = p1_candidates[: limits.max_p1]
    p2_candidates = p1_candidates[limits.max_p1 :] + direct["P2"]
    p2_candidates.sort(key=_sort_key)
    p2 = p2_candidates[: limits.max_p2]
    allocation = {
        normalize_keyword(x.keyword): grade
        for grade, items in (("P0", p0), ("P1", p1), ("P2", p2))
        for x in items
    }
    accepted = [
        replace(d, allocation_grade=allocation.get(normalize_keyword(d.keyword), "候选复查"))
        if d.base_grade in ("P0", "P1", "P2")
        else d
        for d in decisions
    ]
    accepted.sort(
        key=lambda d: (
            {"P0": 0, "P1": 1, "P2": 2, "品牌等级": 3, "候选复查": 4, "不投放": 5}[
                d.allocation_grade
            ],
            _sort_key(d),
        )
    )
    # One keyword can have two independent possible ad targets; both require separate evidence.
    exact_count = root_count = tail_count = 0
    seen_roots: set[str] = set()
    out: list[KeywordDecision] = []
    for d in accepted:
        e = d.source
        assert e is not None
        is_active = d.allocation_grade in ("P0", "P1", "P2") and not d.reasons
        exact = (
            is_active
            and e.exact_eligible
            and e.page_coverage not in ("页面看不出来", "页面不建议埋")
            and exact_count < limits.max_exact
        )
        if exact:
            exact_count += 1
        broad = False
        if (
            is_active
            and e.broad_eligible
            and e.broad_risk in ("low", "medium")
            and e.page_coverage in COVERAGE[:5]
        ):
            if e.broad_role == "root" and normalize_keyword(e.core_root or ""):
                root = normalize_keyword(e.core_root or "")
                if root not in seen_roots and root_count < limits.max_broad_roots:
                    broad = True
                    root_count += 1
                    seen_roots.add(root)
            if e.broad_role == "long_tail" and tail_count < limits.max_broad_long_tails:
                broad = True
                tail_count += 1
        out.append(
            replace(
                d,
                exact_selected=exact,
                broad_selected=broad,
                broad_role=e.broad_role if broad else "none",
            )
        )
    return tuple(out)


def can_generate_official_file(
    *,
    run_succeeded: bool,
    input_snapshot_unchanged: bool,
    user_confirmed: bool,
    template_verified: bool,
    all_hard_checks_passed: bool,
) -> bool:
    """Prohibit official-output actions until consent and format/version verification."""
    return all(
        (
            run_succeeded,
            input_snapshot_unchanged,
            user_confirmed,
            template_verified,
            all_hard_checks_passed,
        )
    )


def decimal_positive(value: Decimal | None) -> bool:
    return value is not None and value.is_finite() and value > 0


@dataclass(frozen=True)
class ExecutionParams:
    manual_bid: Decimal | None
    auto_bid: Decimal | None
    manual_daily_budget: Decimal | None
    auto_daily_budget: Decimal | None
    start_date_us_eastern: str | None  # YYYY-MM-DD in America/New_York
    published_rule_version_ref: str | None


def execution_parameter_errors(x: ExecutionParams) -> tuple[str, ...]:
    errors: list[str] = []
    for field in ("manual_bid", "auto_bid", "manual_daily_budget", "auto_daily_budget"):
        if not decimal_positive(getattr(x, field)):
            errors.append(f"EXECUTION_PARAMETER_MISSING:{field}")
    if not x.published_rule_version_ref:
        errors.append("EXECUTION_RULE_NOT_PUBLISHED")
    if not x.start_date_us_eastern:
        errors.append("EXECUTION_US_DATE_MISSING")
    else:
        try:
            if date.fromisoformat(x.start_date_us_eastern).isoformat() != x.start_date_us_eastern:
                errors.append("EXECUTION_US_DATE_FORMAT_INVALID")
        except ValueError:
            errors.append("EXECUTION_US_DATE_INVALID")
    return tuple(errors)
