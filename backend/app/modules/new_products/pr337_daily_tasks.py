"""Explicitly gated PR337 daily recompute, using the existing Celery/Redis worker."""
from __future__ import annotations

import os
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import get_engine
from .pr337_daily_db import run_daily

SCHEDULE_FLAG = 'SZZSBJ_NEW_PRODUCTS_DAILY_ENABLED'
WRITE_FLAG = 'SZZSBJ_NEW_PRODUCTS_DAILY_WRITE_ENABLED'


def enabled(key: str) -> bool:
    return os.getenv(key,'').strip().lower() in {'1','yes','true','on'}


@celery_app.task(name='new_products.daily_score_tick', ignore_result=True)
def daily_score_tick() -> dict:
    if os.getenv('APP_ENV','').strip().lower() != 'production' or not enabled(SCHEDULE_FLAG):
        return {'status':'disabled'}
    apply=enabled(WRITE_FLAG)
    with Session(bind=get_engine(),autoflush=False,expire_on_commit=False) as session:
        with session.begin():
            if apply:
                session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            else:
                session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            session.execute(text("SELECT set_config('statement_timeout','120000',true)"))
            session.execute(text("SELECT set_config('lock_timeout','3000',true)"))
            return run_daily(session,apply=apply)
