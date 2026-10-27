"""Local-only task registration; no external calls or schedule enablement."""
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
backend = root / 'backend'
sys.path.insert(0, str(backend))
for line in (backend / '.env').read_text(encoding='utf-8-sig').splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    name, value = line.split('=', 1)
    os.environ[name.strip()] = value.strip()

from sqlalchemy import make_url, select
from sqlalchemy.orm import Session

url = make_url(os.environ['DATABASE_URL'])
assert os.environ.get('APP_ENV') == 'local'
assert (url.drivername, url.host, url.port, url.database) == (
    'postgresql+psycopg', '127.0.0.1', 55432, 'szzsbj_dev'
)
assert not url.query

from app.db.model_registry import register_productlist_sync_models
from app.db.session import get_engine
from app.modules.integration_sync.models import IntegrationInterface, IntegrationSyncConfig
from app.modules.integration_sync.pmc_purchase_pipeline_catalog import PURCHASE_SOURCE_KEYS
from app.modules.integration_sync.pmc_purchase_pipeline_repository import PurchasePipelineRepository, purchase_connection

register_productlist_sync_models()
with purchase_connection(get_engine()) as conn:
    assert conn is not None, 'Purchase task active'
    with Session(bind=conn) as session:
        rows = session.execute(select(IntegrationSyncConfig, IntegrationInterface.interface_key).join(
            IntegrationInterface, IntegrationInterface.id == IntegrationSyncConfig.interface_id
        ).where(IntegrationInterface.provider == 'lingxing', IntegrationInterface.interface_key.in_(PURCHASE_SOURCE_KEYS))).all()
        accounts = {config.source_account_ref for config, key in rows}
        assert len(accounts) == 1, 'Expected exactly one local purchase account'
        account = accounts.pop()
        backup = [{'id': str(c.id), 'interface_key': key, 'is_enabled': c.is_enabled,
                   'schedule_enabled': c.schedule_enabled, 'next_run_at': str(c.next_run_at)} for c, key in rows]
        backup_path = root / '.planning/current/pmc-purchase-local-config-before.json'
        if not backup_path.exists():
            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding='utf-8')
        config = PurchasePipelineRepository(session).register(account)
        session.flush()
        assert not config.is_enabled and not config.schedule_enabled
        session.commit()
        print(json.dumps({'registered': True, 'config_id': str(config.id), 'schedule_cron': config.schedule_cron,
                          'is_enabled': config.is_enabled, 'schedule_enabled': config.schedule_enabled,
                          'source_configs_preserved': len(rows)}))
