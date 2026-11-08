"""Allow normal lifecycle recalculation after completion, not before."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def can_resume_lifecycle(session: Session, listing) -> bool:
    """Only workflow-owned completed Clearance may release a 清货期 listing.

    Old/manual clearance labels without a recorded finished task remain protected.
    A new pending/running request keeps the protection until that task closes.
    """
    status = session.execute(text("""
        SELECT status FROM biz_clearance_applications
        WHERE source_account_ref=:account AND store_id=:store AND item_id=:item
        ORDER BY submitted_at DESC, id DESC LIMIT 1
    """), {"account": listing.source_account_ref, "store": listing.store_id,
            "item": listing.item_id}).scalar_one_or_none()
    return status == "done"
