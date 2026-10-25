"""Select the current persisted rule for internal keyword analysis.

An enabled account rule takes precedence over the immutable system baseline.
The browser never supplies a fallback rule or a substitute version identifier.
"""

from __future__ import annotations

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from .models import AiKwRuleSet, AiKwRuleVersion

SYSTEM_DEFAULT_RULE_KEY = "keyword_v11_internal_default"


def effective_scoring_rule(session: Session, account: str) -> AiKwRuleVersion | None:
    if not account or len(account) > 128:
        return None
    return session.scalar(
        select(AiKwRuleVersion)
        .join(AiKwRuleSet, AiKwRuleSet.id == AiKwRuleVersion.rule_set_id)
        .where(
            AiKwRuleSet.rule_type == "scoring",
            AiKwRuleSet.is_enabled.is_(True),
            AiKwRuleVersion.status == "published",
            or_(
                AiKwRuleSet.scope_key == account,
                and_(
                    AiKwRuleSet.scope_key == "global",
                    AiKwRuleSet.rule_key == SYSTEM_DEFAULT_RULE_KEY,
                ),
            ),
        )
        .order_by(
            case((AiKwRuleSet.scope_key == account, 0), else_=1),
            AiKwRuleVersion.published_at.desc(),
            AiKwRuleVersion.version_number.desc(),
            AiKwRuleVersion.id.desc(),
        )
        .limit(1)
    )
