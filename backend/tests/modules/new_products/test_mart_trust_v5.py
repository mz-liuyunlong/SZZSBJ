"""Local only V5: view can omit a fact WFS date while locked/listing WFS proves it."""
from copy import deepcopy
from datetime import date

import pytest

from app.modules.new_products import mart_only_v4 as v5
from app.modules.new_products import order_lineage_view as v3
from test_mart_only_v4 import CASES, Session, _source, _as_score


@pytest.mark.parametrize('name', CASES)
def test_missing_fact_first_wfs_does_not_block_proven_trust(monkeypatch, name):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setattr(v5, 'evaluate', _as_score)
    daily, snap, row = _source(name)
    snap['locked_first_wfs_day'] = snap['start_day']
    row['listing']['first_wfs_available_date_la'] = snap['start_day'].isoformat()
    row['facts'].pop('first_wfs_available_date_la')
    row['evaluation']['dimensions']['speed'] = '8.123456'  # V3 speed already present
    db = Session([name])
    key = ('primary', CASES[name]['store'], CASES[name]['item'])
    db.inputs[key] = (daily, snap)
    v5.reconcile_mart_only_pending_rows(db, [row])
    assert len(db.queries) == 2
    assert row['evaluation']['dimensions']['speed'] == '8.123456'  # never replace valid speed
    assert row['evaluation']['dimensions']['trust'] is not None
    assert row['facts']['single_unit_orders_14d'] == CASES[name]['singles']
    assert row['facts']['valid_orders_14d'] == CASES[name]['orders']
    assert row['facts']['valid_units_14d'] == str(CASES[name]['units'])
    assert row['facts']['trust_evidence_source'] == v5.VERSION
    assert row['facts']['order_reconciliation']['version'] == v5.VERSION
    # The already-installed V3 source must not wipe the proven result.
    assert v3._candidate(row) is None


@pytest.mark.parametrize('name', CASES)
def test_locked_wfs_day_is_sufficient_even_if_display_view_omits_both_dates(monkeypatch, name):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setattr(v5, 'evaluate', _as_score)
    daily, snap, row = _source(name)
    snap['locked_first_wfs_day'] = snap['start_day']
    row['facts'].pop('first_wfs_available_date_la')
    db = Session([name])
    db.inputs[('primary', CASES[name]['store'], CASES[name]['item'])] = (daily, snap)
    v5.reconcile_mart_only_pending_rows(db, [row])
    assert row['evaluation']['dimensions']['trust'] is not None
    assert row['facts']['first_wfs_available_date_la'] == snap['start_day'].isoformat()


@pytest.mark.parametrize('name', CASES)
@pytest.mark.parametrize('part', ['locked', 'facts', 'listing'])
def test_conflicting_wfs_dates_prevent_trust(monkeypatch, name, part):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setattr(v5, 'evaluate', _as_score)
    daily, snap, row = _source(name)
    snap['locked_first_wfs_day'] = snap['start_day']
    row['listing']['first_wfs_available_date_la'] = snap['start_day'].isoformat()
    if part == 'locked':
        snap['locked_first_wfs_day'] = date(2026, 1, 1)
    if part == 'facts':
        row['facts']['first_wfs_available_date_la'] = '2026-01-01'
    if part == 'listing':
        row['listing']['first_wfs_available_date_la'] = '2026-01-01'
    before = deepcopy(row)
    db = Session([name])
    db.inputs[('primary', CASES[name]['store'], CASES[name]['item'])] = (daily, snap)
    v5.reconcile_mart_only_pending_rows(db, [row])
    assert row == before


def test_no_wfs_proof_blocks_trust(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setattr(v5, 'evaluate', _as_score)
    daily, snap, row = _source('YC00697')
    row['facts'].pop('first_wfs_available_date_la')
    db = Session(['YC00697'])
    v5.reconcile_mart_only_pending_rows(db, [row])
    assert row['evaluation']['dimensions']['trust'] is None


def test_unfinalized_only_and_no_database_write(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setattr(v5, 'evaluate', _as_score)
    daily, snap, row = _source('YC00665')
    snap['locked_first_wfs_day'] = snap['start_day']
    row['evaluation']['observation_state'] = 'frozen'
    before = deepcopy(row)
    db = Session(['YC00665'])
    v5.reconcile_mart_only_pending_rows(db, [row])
    assert row == before and not db.queries


def test_v3_unaffected_existing_trust(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setattr(v5, 'evaluate', _as_score)
    daily, snap, row = _source('YC00665')
    snap['locked_first_wfs_day'] = snap['start_day']
    row['evaluation']['dimensions']['trust'] = '9.12'
    row['evaluation']['dimensions']['speed'] = '9.70'
    before = deepcopy(row)
    db = Session(['YC00665'])
    v5.reconcile_mart_only_pending_rows(db, [row])
    assert row == before and not db.queries
