"""Celery keyword orchestration. Persists run status independent of browser sessions."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
from uuid import UUID
from sqlalchemy import text
from app.celery_app import celery_app, AI_QUEUE
from app.db.session import get_session_factory
from app.modules.keyword_planning.analysis_entrypoint import create_analysis_from_stored_sources

@celery_app.task(name="ai_runtime.execute_keyword_ai_job", ignore_result=True)
def execute_keyword_ai_job(job_id: str) -> None:
    identifier=UUID(job_id)
    with get_session_factory()() as session:
        row=session.execute(text("""UPDATE ai_runtime_jobs SET status='running',phase='rule_analysis',started_at=coalesce(started_at,now()),lease_until=now()+interval '10 minutes'
          WHERE id=:id AND status='queued' RETURNING input_json"""),{"id":identifier}).mappings().first()
        session.commit()
        if row is None:
            return
        p=row["input_json"]
        try:
            receipt=create_analysis_from_stored_sources(session,account=p["source_account_ref"],product_id=UUID(p["product_id"]),
                item_id=p["item_id"],fact_id=UUID(p["product_fact_snapshot_id"]),rule_version_id=UUID(p["rule_version_id"]),
                upload_id=UUID(p["upload_file_id"]),request_key=p["request_key"],actor=_requested_by(identifier),
                selected_asins=tuple(p["selected_asins"]) if p.get("selected_asins") is not None else None)
            # Do not alter immutable keyword rows or existing score/grade/export content.
            session.execute(text("""UPDATE ai_runtime_jobs SET status=:status,phase='finished',progress=100,total=:total,completed=:count,run_id=:run,finished_at=now(),lease_until=NULL
                WHERE id=:id AND status='running'"""),{"status":"succeeded" if receipt.status=="succeeded" else "partial_success","total":receipt.keyword_count,"count":receipt.keyword_count,"run":receipt.run_id,"id":identifier})
            session.commit()
        except Exception:
            session.rollback()
            session.execute(text("""UPDATE ai_runtime_jobs SET status='failed',phase='failed',error_code='ANALYSIS_EXECUTION_FAILED',finished_at=now(),lease_until=NULL
                WHERE id=:id AND status='running'"""),{"id":identifier})
            session.commit()

def _requested_by(job_id:UUID)->str:
    with get_session_factory()() as session:
        return str(session.execute(text("SELECT requested_by FROM ai_runtime_jobs WHERE id=:id"),{"id":job_id}).scalar_one())

@celery_app.task(name="ai_runtime.recover_keyword_jobs", ignore_result=True)
def recover_keyword_jobs() -> None:
    # A one-minute scheduler re-dispatches durable queued jobs after broker outages.
    with get_session_factory()() as session:
        session.execute(text("""UPDATE ai_runtime_jobs SET status='failed',phase='failed',error_code='WORKER_LEASE_EXPIRED',finished_at=now(),lease_until=NULL
          WHERE status='running' AND lease_until < now()"""))
        rows=session.execute(text("SELECT id FROM ai_runtime_jobs WHERE status='queued' ORDER BY created_at LIMIT 20")).scalars().all()
        session.commit()
    for job_id in rows:
        try:
            execute_keyword_ai_job.apply_async(args=[str(job_id)],queue=AI_QUEUE,routing_key=AI_QUEUE)
        except Exception:
            break
