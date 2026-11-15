"""PR337 V4: synthetic regression based on Nov 15 server audit daily totals.

No real orders or production access. Only PR337 local-only read view is tested.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import pytest

from app.modules.new_products import mart_only_v4 as v4

CASES = {
    'YC00665': {'store':'110689966555011584','item':'20852223505',
        'start':date(2026,10,10), 'first':date(2026,10,11),
        'daily':[(11,1,1),(13,3,3),(14,1,1),(15,1,1),(16,3,3),(17,2,2),(18,7,7),(19,1,1)],
        'orders':19,'units':19,'singles':19,'speed':'9.70','trust':'9.70'},
    'YC00697': {'store':'110711149920800256','item':'20874953767',
        'start':date(2026,10,9), 'first':date(2026,10,16),
        'daily':[(16,1,1),(17,1,1),(18,2,2),(19,2,2),(20,3,4),(21,3,4),(22,1,1)],
        'orders':13,'units':15,'singles':11,'speed':'6.08','trust':'8.07'},
    'YC00775': {'store':'110711149920800256','item':'20890053496',
        'start':date(2026,10,21), 'first':date(2026,10,24),
        'daily':[(24,1,1),(25,1,1),(26,5,6),(27,7,8),(28,3,3)],
        'orders':17,'units':19,'singles':15,'speed':'8.74','trust':'9.56'},
}


def _source(name):
    c=CASES[name]
    daily=[{'day':date(2026,10,d),'order_count':n,'sales_qty':u} for d,n,u in c['daily']]
    snapshot={'account':'primary','store':c['store'],'item':c['item'],
              'start_day':c['start'],'end_day':c['start']+timedelta(days=13),
              'saved_first_day':c['first'],'sales_orders':c['orders'],
              'sales_units':Decimal(c['units'])}
    row={'listing':{'source_account_ref':'primary','store_id':c['store'],'item_id':c['item']},
         'facts':{'first_wfs_available_date_la':c['start'].isoformat(),
                  'valid_orders_14d':None,'valid_units_14d':None,
                  'order_reconciliation':{'version':'PR337_SALESTAT_PERSISTED_VIEW_V5_20261114',
                                          'mart_orders':c['orders'],'mart_units':str(c['units'])}},
         'evaluation':{'observation_state':'automatic_partial','rule_version':0,
                       'dimensions':{'speed':None,'trust':None,'ad':'8.27','profit':'4.33'},
                       'total':None,'grade':None,
                       'missing':['FACT与MART订单数或销售件数不一致，数据可信度待核实']},
         'suggested_qty':None}
    return daily,snapshot,row

class Rows:
    def __init__(self, values): self.values=values
    def mappings(self): return iter(self.values)

class Session:
    def __init__(self, names):
        self.inputs={}
        for name in names:
            daily,snap,row=_source(name)
            key=('primary', CASES[name]['store'],CASES[name]['item'])
            self.inputs[key]=(daily,snap)
        self.queries=[]
    def execute(self, stmt, params):
        sql=str(stmt)
        self.queries.append(sql)
        if 'biz_new_product_registry' in sql:
            return Rows([v[1] for v in self.inputs.values()])
        if 'mart_daily_sales_item_day' in sql:
            return Rows([{'account':k[0],'store':k[1],'item':k[2], **r}
                         for k,(daily,_) in self.inputs.items() for r in daily])
        raise AssertionError('OUT_OF_SCOPE_SQL')


def _as_score(facts, config, version):
    """Independent faithful dimension-only formula matching confirmed rules."""
    def clamp(x):return max(Decimal(0),min(Decimal(10),x))
    from decimal import Decimal as D
    f=D(facts['first_order_day']); o=D(facts['effective_orders_14d'])
    u=D(facts['valid_units_14d']); n=D(facts['valid_orders_14d']); s=D(facts['single_unit_orders_14d'])
    first=clamp((D(14)-f)*D(10)/D(11)); volume=clamp(o*D(10)/D(20))
    speed=first*D('.4')+volume*D('.6')
    units=clamp(u*D(10)/D(20)); ratio=clamp(((s/n)*D(100)-D(40))*D(10)/D(50))
    trust=units*D('.6')+ratio*D('.4')
    return {'dimensions':{'speed':str(speed),'trust':str(trust)}}

@pytest.mark.parametrize('name',CASES)
def test_daily_order_math_proves_single_unit_orders(name):
    c=CASES[name]
    daily,snap,row=_source(name)
    evidence=v4.mart_deterministic_evidence(snap['start_day'],snap['end_day'],daily)
    assert evidence=={'orders':c['orders'],'units':c['units'],'singles':c['singles'],'first_date':c['first']}

@pytest.mark.parametrize('name',CASES)
def test_mart_only_projects_correct_two_scores_and_display_without_order_v2(monkeypatch,name):
    monkeypatch.setenv('APP_ENV','local')
    monkeypatch.setattr(v4,'evaluate',_as_score)
    daily,snap,row=_source(name)
    before=deepcopy(row)
    db=Session([name])
    v4.reconcile_mart_only_pending_rows(db,[row])
    assert len(db.queries)==2
    assert all('fact_walmart_order_items' not in x and x.lstrip().startswith('WITH wanted') for x in db.queries)
    c=CASES[name]
    assert row['facts']['valid_orders_14d']==c['orders']
    assert row['facts']['valid_units_14d']==str(c['units'])
    assert row['facts']['single_unit_orders_14d']==c['singles']
    assert row['facts']['effective_orders_14d']==c['orders']
    assert row['facts']['trust_evidence_source']==v4.VERSION
    assert row['facts']['order_reconciliation']['decision']=='MART_DAILY_SINGLE_COUNTS_PROVEN'
    assert abs(Decimal(row['evaluation']['dimensions']['speed'])-Decimal(c['speed']))<Decimal('.005')
    assert abs(Decimal(row['evaluation']['dimensions']['trust'])-Decimal(c['trust']))<Decimal('.005')
    for k in ('ad','profit'):
        assert row['evaluation']['dimensions'][k]==before['evaluation']['dimensions'][k]
    assert row['evaluation']['total'] is None and row['evaluation']['grade'] is None


def test_three_independent_items_2_queries_only(monkeypatch):
    monkeypatch.setenv('APP_ENV','local')
    monkeypatch.setattr(v4,'evaluate',_as_score)
    rows=[_source(k)[2] for k in CASES]
    db=Session(CASES)
    v4.reconcile_mart_only_pending_rows(db,rows)
    assert len(db.queries)==2
    assert {r['listing']['item_id']:r['facts']['valid_orders_14d'] for r in rows}=={
        c['item']:c['orders'] for c in CASES.values()}


def test_ambiguous_daily_bucket_does_not_fabricate_singles():
    start=date(2026,10,10)
    assert v4.mart_deterministic_evidence(start,start+timedelta(days=13),
        [{'day':start,'order_count':2,'sales_qty':4}]) is None
    assert v4.mart_deterministic_evidence(start,start+timedelta(days=13),
        [{'day':start,'order_count':3,'sales_qty':6}]) is None


def test_one_order_many_units_is_proven_not_single():
    start=date(2026,10,10)
    v=v4.mart_deterministic_evidence(start,start+timedelta(days=13),
          [{'day':start,'order_count':1,'sales_qty':7}])
    assert (v['orders'],v['units'],v['singles'])==(1,7,0)

@pytest.mark.parametrize('bad', [
    [{'day':date(2026,10,10),'order_count':3,'sales_qty':2}],
    [{'day':date(2026,10,10),'order_count':0,'sales_qty':1}],
    [{'day':date(2026,10,10),'order_count':-1,'sales_qty':2}],
    [{'day':date(2026,10,10),'order_count':None,'sales_qty':1}],
    [{'day':date(2026,10,10),'order_count':2,'sales_qty':Decimal('2.5')}],
    [{'day':date(2026,10,10),'order_count':1,'sales_qty':1}]*2,
])
def test_invalid_mart_fails_closed(bad):
    start=date(2026,10,10)
    assert v4.mart_deterministic_evidence(start,start+timedelta(days=13),bad) is None

@pytest.mark.parametrize('name',CASES)
def test_frozen_never_queries_or_changes(monkeypatch,name):
    monkeypatch.setenv('APP_ENV','local')
    _,_,row=_source(name)
    row['evaluation']['observation_state']='frozen'
    original=deepcopy(row)
    db=Session([name]);v4.reconcile_mart_only_pending_rows(db,[row])
    assert row==original and not db.queries

@pytest.mark.parametrize('name',CASES)
def test_production_env_never_queries(monkeypatch,name):
    monkeypatch.setenv('APP_ENV','production')
    _,_,row=_source(name)
    original=deepcopy(row)
    db=Session([name]);v4.reconcile_mart_only_pending_rows(db,[row])
    assert row==original and not db.queries

@pytest.mark.parametrize('case', ['sales_orders','sales_units','saved_first_day'])
def test_stale_saved_snapshot_blocks_score(monkeypatch,case):
    monkeypatch.setenv('APP_ENV','local')
    daily,snap,row=_source('YC00697')
    if case=='saved_first_day': snap[case]=date(2026,10,15)
    else: snap[case]+=1
    db=Session(['YC00697'])
    db.inputs[('primary',CASES['YC00697']['store'],CASES['YC00697']['item'])]=(daily,snap)
    old=deepcopy(row)
    v4.reconcile_mart_only_pending_rows(db,[row])
    assert row==old


def test_existing_dimensions_unchanged(monkeypatch):
    monkeypatch.setenv('APP_ENV','local')
    daily,snap,row=_source('YC00665')
    row['evaluation']['dimensions'].update({'speed':'8.25','trust':'5.10'})
    before=deepcopy(row);db=Session(['YC00665'])
    v4.reconcile_mart_only_pending_rows(db,[row])
    assert not db.queries and row==before


def test_selected_saved_score_unchanged_while_missing_other_dimension_recovered(monkeypatch):
    monkeypatch.setenv('APP_ENV','local')
    monkeypatch.setattr(v4,'evaluate',_as_score)
    daily,snap,row=_source('YC00775')
    row['evaluation']['dimensions']['profit']='0.00'
    row['evaluation']['dimensions']['speed']='8.7363'
    db=Session(['YC00775'])
    v4.reconcile_mart_only_pending_rows(db,[row])
    assert row['evaluation']['dimensions']['speed']=='8.7363'
    assert row['evaluation']['dimensions']['trust'] is not None
    assert row['evaluation']['dimensions']['profit']=='0.00'


def test_mart_source_only_after_payment_window_complete(monkeypatch):
    monkeypatch.setenv('APP_ENV','local')
    daily,snap,row=_source('YC00665')
    snap['end_day']=date(2026,12,25)
    db=Session(['YC00665']);db.inputs[('primary',CASES['YC00665']['store'],CASES['YC00665']['item'])]=(daily,snap)
    v4.reconcile_mart_only_pending_rows(db,[row])
    assert row['evaluation']['dimensions']['speed'] is None
