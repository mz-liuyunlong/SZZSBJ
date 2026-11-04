"""Durable, idempotent Feishu contact-event inbox.

Delivery is authenticated at the router. The inbox stores only event identifiers,
type and optional open_id; never raw Feishu payloads, encryption secrets or tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.iam.organization_events import FeishuEvent

_MAX_ATTEMPTS = 6


def enqueue_contact_event(session: Session, event: FeishuEvent) -> bool:
    """Insert once; return False for a repeated Feishu delivery."""
    inserted = session.execute(
        text(
            """
            INSERT INTO iam_feishu_org_events
                (event_id, event_type, open_id, revoke_session, status, next_attempt_at)
            VALUES
                (:event_id, :event_type, :open_id, :revoke_session, 'pending', now())
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
            """
        ),
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "open_id": event.open_id,
            "revoke_session": event.revoke_session,
        },
    ).scalar()
    return inserted is not None


def revoke_linked_sessions(session: Session, open_id: str) -> None:
    """Immediately revoke Feishu-linked sessions for verified offboarding events."""
    session.execute(
        text(
            """
            UPDATE app_sessions s
            SET revoked_at = now()
            FROM app_users u
            WHERE s.user_id = u.id
              AND s.revoked_at IS NULL
              AND u.feishu_open_id = :open_id
            """
        ),
        {"open_id": open_id},
    )


def claim_events(session: Session, *, limit: int = 25) -> list[dict[str, object]]:
    """Lock and claim ready events; stale in-progress leases can be reclaimed."""
    rows = session.execute(
        text(
            """
            WITH picked AS (
                SELECT event_id
                FROM iam_feishu_org_events
                WHERE (
                    status IN ('pending', 'retry')
                    AND next_attempt_at <= now()
                ) OR (
                    status = 'processing'
                    AND updated_at < now() - interval '15 minutes'
                )
                ORDER BY received_at, event_id
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            )
            UPDATE iam_feishu_org_events e
            SET status = 'processing',
                attempt_count = attempt_count + 1,
                updated_at = now()
            FROM picked
            WHERE e.event_id = picked.event_id
            RETURNING e.event_id, e.event_type, e.open_id, e.attempt_count
            """
        ),
        {"limit": limit},
    ).mappings()
    return [dict(row) for row in rows]


def acknowledge_events(session: Session, event_ids: list[str], run_id: str) -> None:
    if not event_ids:
        return
    session.execute(
        text(
            """
            UPDATE iam_feishu_org_events
            SET status = 'applied', last_run_id = :run_id,
                last_error_code = NULL, processed_at = now(), updated_at = now()
            WHERE event_id = ANY(:event_ids) AND status = 'processing'
            """
        ),
        {"event_ids": event_ids, "run_id": run_id},
    )


def reschedule_events(
    session: Session,
    events: list[dict[str, object]],
    *,
    error_code: str,
    manual_review: bool = False,
) -> None:
    """Bounded exponential retry; identity-risk events always require review."""
    for event in events:
        attempts = int(event["attempt_count"])
        review = manual_review or attempts >= _MAX_ATTEMPTS
        delay = min(60 * 2 ** max(attempts - 1, 0), 3600)
        next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        session.execute(
            text(
                """
                UPDATE iam_feishu_org_events
                SET status = :status, next_attempt_at = :next_attempt_at,
                    last_error_code = :error_code, updated_at = now()
                WHERE event_id = :event_id AND status = 'processing'
                """
            ),
            {
                "event_id": event["event_id"],
                "status": "needs_review" if review else "retry",
                "next_attempt_at": next_attempt_at,
                "error_code": error_code,
            },
        )
