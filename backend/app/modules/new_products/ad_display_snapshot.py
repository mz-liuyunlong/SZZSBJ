"""Read-only saved advertising display. No computing or writes."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from .testing_profit import keys_json

_SAVED_PAGE = text("""
WITH wanted AS (
 SELECT account,store,item
 FROM jsonb_to_recordset(CAST(:wanted AS jsonb)) AS j(account text,store text,item text)
)
SELECT w.account,w.store,w.item,p.data_coverage_json->'ad_display_v1' AS snapshot
FROM wanted w JOIN biz_new_product_registry r
  ON r.source_account_ref=w.account AND r.store_id=w.store AND r.item_id=w.item
JOIN biz_new_product_performance_current p ON p.registry_id=r.id
""")

def _finite(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError):
        return None
    return n if n.is_finite() and n >= 0 else None

def overlay_saved_ad_display(row: dict[str,Any], snapshot: Any) -> None:
    """Read-time dict copy only, never recalculate or query source facts."""
    if row.get('evaluation',{}).get('observation_state') == 'frozen':
        return
    if not isinstance(snapshot, dict) or snapshot.get('version') != 1:
        return
    if snapshot.get('source') != 'fact_walmart_ad_item_sp_daily':
        return
    start, end = snapshot.get('window_start_la'), snapshot.get('window_end_la')
    if not (isinstance(start,str) and isinstance(end,str) and len(start)==10 and len(end)==10 and start <= end):
        return
    incoming = snapshot.get('facts')
    if not isinstance(incoming,dict):
        return
    allowed = {
        f'{prefix}_{metric}' for prefix in ('ad_total','auto_ad','manual_ad')
        for metric in ('spend_usd','orders','clicks','impressions','spend_ratio_pct')
    }
    facts = row.get('facts')
    if not isinstance(facts,dict):
        return
    for key in allowed:
        if key in incoming:
            n = _finite(incoming[key])
            facts[key] = str(n) if n is not None else None
    facts['ad_display_window_start_la'] = start
    facts['ad_display_window_end_la'] = end
    facts['ad_display_status'] = snapshot.get('status')

def load_saved_ad_display(target: Session, keys: list[tuple[str,str,str]]) -> dict[tuple[str,str,str],dict]:
    if not keys:
        return {}
    if len(keys)>200:
        raise ValueError('Page limit exceeded')
    return {(r['account'],r['store'],r['item']):r['snapshot']
            for r in target.execute(_SAVED_PAGE, {'wanted':keys_json(keys)}).mappings()
            if isinstance(r['snapshot'],dict)}
