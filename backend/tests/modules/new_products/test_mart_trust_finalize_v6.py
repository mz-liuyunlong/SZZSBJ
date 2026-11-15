"""PR337 local V6: only pending trust with MART speed already verified."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.modules.new_products import mart_trust_finalize_v6 as v6
from app.modules.new_products.rules import DEFAULT_PARAMETERS, DEFAULT_WEIGHTS

CASES = {
    'YC00665': {
        'store': '110689966555011584', 'item': '20852223505',
        'start': date(2026, 10, 10), 'first': date(2026, 10, 11),
        'daily': [(11,1,1),(13,3,3),(14,1,1),(15,1,1),(16,3,3),(17,2,2),(18,7,7),(19,1,1)],
        'orders': 19, 'units': 19, 'singles': 19, 'speed': Decimal('9.70'), 'trust': Decimal('9.70'),
    },
    'YC00697': {
        'store': '110711149920800256', 'item': '20874953767',
        'start': date(2026, 10, 9), 'first': date(2026, 10, 16),
        'daily': [(16,1,1),(17,1,1),(18,2,2),(19,2,2),(20,3,4),(21,3,4),(22,1,1)],
        'orders': 13, 'units': 15, 'singles': 11, 'speed': Decimal('6.08'), 'trust': Decimal('8.07'),
    },
    'YC00775': {
        'store': '110711149920800256', 'item': '20890053496',
        'start': date(2026, 10, 21), 'first': date(2026, 10, 24),
        'daily': [(24,1,1),(25,1,1),(26,5,6),(27,7,8),(28,3,3)],
        'orders': 17, 'units': 19, 'singles': 15, 'speed': Decimal('8.74'), 'trust': Decimal('9.56'),
    },
}


def faithful_evaluate(facts, config, version):
    z=Decimal('0');ten=Decimal('10')
    first=Decimal(str(facts['first_order_day']))
    orders=Decimal(str(facts['effective_orders_14d']))
    first_score=ten if first<=3 else max(z,min(ten,(Decimal(14)-first)*ten/Decimal(11)))
    volume=min(ten,orders/Decimal(20)*ten)
    speed=first_score*Decimal('.4')+volume*Decimal('.6')
    trust=None
    if all(facts.get(k) is not None for k in ('valid_units_14d','valid_orders_14d','single_unit_orders_14d')):
        units=Decimal(str(facts['valid_units_14d']))
        n=Decimal(str(facts['valid_orders_14d']))
        singles=Decimal(str(facts['single_unit_orders_14d']))
        unit_score=min(ten,units/Decimal(20)*ten)
        ratio_score=max(z,min(ten,((singles/n)*Decimal(100)-Decimal(40))*ten/Decimal(50)))
        trust=unit_score*Decimal('.6')+ratio_score*Decimal('.4')
    return {'dimensions':{'speed':str(speed),'trust':str(trust) if trust is not None else None}}


@pytest.fixture(autouse=True)
def use_faithful_scoring(monkeypatch):
    monkeypatch.setattr(v6,'evaluate', faithful_evaluate)


def fixture(name, *, has_trust=False, date_in_facts=False):
    c = CASES[name]
    first_order_day = (c['first']-c['start']).days+1
    score = faithful_evaluate({'market_score':None,'ad_status':'unknown',
             'first_order_day':first_order_day,'effective_orders_14d':c['orders'],
             'elapsed_days':14}, {'confirmedScoring':DEFAULT_PARAMETERS,'weights':DEFAULT_WEIGHTS},0)
    data = {
        'listing': {
            'source_account_ref':'primary','store_id':c['store'], 'item_id':c['item'],
            'first_wfs_available_date_la':c['start'].isoformat(),
        },
        'facts': {
            'speed_evidence_source':'MART_SALESTAT_VERIFIED_WINDOW_V3',
            'order_unit_display_source':'mart_daily_sales_item_day',
            'effective_orders_14d':c['orders'], 'valid_orders_14d':c['orders'],
            'valid_units_14d':str(c['units']),
            'first_order_day':first_order_day,
            'observation_first_order_date_la':c['first'].isoformat(),
            'order_reconciliation': {'version':'PR337_SALESTAT_PERSISTED_VIEW_V5_20261114',
                'mart_orders':1000, 'current_fact_orders':999},  # Deliberately stale cached metadata.
        },
        'evaluation': {
            'observation_state':'automatic_partial','rule_version':0,
            'dimensions': {'speed':score['dimensions']['speed'],
                'trust':'9.56' if has_trust else None, 'ad':'9.01', 'profit':'4.33', 'market':None},
            'grade':None,'total':None,
            'missing':['FACT\u4e0eMART\u8ba2\u5355\u6570\u6216\u9500\u552e\u4ef6\u6570\u4e0d\u4e00\u81f4\uff0c\u6570\u636e\u53ef\u4fe1\u5ea6\u5f85\u6838\u5b9e'],
        },
        'suggested_qty':None,
    }
    if date_in_facts:
        data['facts']['first_wfs_available_date_la']=c['start'].isoformat()
    return data


class Result:
    def __init__(self, rows): self._rows = rows
    def mappings(self): return iter(self._rows)

class Session:
    def __init__(self, names):
        self.names=names
        self.calls=[]
        self.table = {}
        for name in names:
            c = CASES[name]
            key = ('primary',c['store'],c['item'])
            self.table[key]=[{
                'account':key[0], 'store':key[1], 'item':key[2],
                'locked_day':c['start'], 'day':date(2026,10,day),
                'order_count':orders, 'sales_qty':units,
            } for day,orders,units in c['daily']]
    def execute(self, sql, values):
        src = str(sql)
        assert 'fact_walmart_order_items' not in src
        assert 'listing_wfs_first_stock_la_locked' in src
        assert 'mart_daily_sales_item_day' in src
        self.calls.append((src,values))
        import json
        keys = {(w['account'],w['store'],w['item']) for w in json.loads(values['wanted'])}
        return Result([item for k, rows in self.table.items() if k in keys for item in rows])


@pytest.mark.parametrize('name', ['YC00665','YC00697'])
@pytest.mark.parametrize('date_in_facts', [False,True])
def test_recovers_trust_with_mart_verified_speed_without_legacy_snapshot_gate(monkeypatch,name,date_in_facts):
    monkeypatch.setenv('APP_ENV','local')
    row=fixture(name,date_in_facts=date_in_facts)
    before=deepcopy(row)
    db=Session([name]);v6.finalize_missing_mart_trust(db,[row])
    c=CASES[name]
    assert len(db.calls)==1
    assert abs(Decimal(row['evaluation']['dimensions']['trust'])-c['trust'])<Decimal('0.005')
    assert row['facts']['single_unit_orders_14d']==c['singles']
    assert row['facts']['trust_evidence_source']==v6.VERSION
    assert row['facts']['order_reconciliation']['decision']=='MART_DAILY_UNIQUE_SINGLE_ORDER_DISTRIBUTION'
    for dimension in ('speed','ad','profit','market'):
        assert row['evaluation']['dimensions'][dimension]==before['evaluation']['dimensions'][dimension]
    assert row['facts']['effective_orders_14d']==before['facts']['effective_orders_14d']
    assert row['facts']['valid_units_14d']==before['facts']['valid_units_14d']
    assert row['evaluation']['total'] is None and row['evaluation']['grade'] is None


def test_two_same_page_and_775_existing_trust_untouched(monkeypatch):
    monkeypatch.setenv('APP_ENV','local')
    rows=[fixture(n,has_trust=n=='YC00775') for n in CASES]
    prior=deepcopy(rows[2]);db=Session(CASES)
    v6.finalize_missing_mart_trust(db,rows)
    assert len(db.calls)==1
    assert rows[2]==prior
    assert set(tuple((w['store'],w['item']) for w in __import__('json').loads(db.calls[0][1]['wanted'])))=={
        (CASES[n]['store'],CASES[n]['item']) for n in ('YC00665','YC00697')}
    assert [r['facts']['single_unit_orders_14d'] for r in rows[:2]]==[19,11]


@pytest.mark.parametrize('change', [
    'status','version','has_total','has_grade','non_mart_speed_source',
    'wrong_daily_orders','wrong_daily_units','wrong_speed','wrong_first_day',
    'wrong_observed_first','wrong_wfs_facts','wrong_wfs_listing','wrong_sales_source',
])
def test_conflicts_do_not_rewrite_facts(monkeypatch,change):
    monkeypatch.setenv('APP_ENV','local')
    row=fixture('YC00697')
    v=row['facts'];ev=row['evaluation']
    if change=='status':ev['observation_state']='frozen'
    if change=='version':ev['rule_version']=1
    if change=='has_total':ev['total']='7.22'
    if change=='has_grade':ev['grade']='B'
    if change=='non_mart_speed_source':v['speed_evidence_source']='UNKNOWN'
    if change=='wrong_daily_orders':v['valid_orders_14d']=14
    if change=='wrong_daily_units':v['valid_units_14d']=16
    if change=='wrong_speed':ev['dimensions']['speed']='1.00'
    if change=='wrong_first_day':v['first_order_day']=3
    if change=='wrong_observed_first':v['observation_first_order_date_la']='2026-10-15'
    if change=='wrong_wfs_facts':v['first_wfs_available_date_la']='2026-10-11'
    if change=='wrong_wfs_listing':row['listing']['first_wfs_available_date_la']='2026-10-10'
    if change=='wrong_sales_source':v['order_unit_display_source']='fact_walmart_order_items'
    prior=deepcopy(row);db=Session(['YC00697'])
    v6.finalize_missing_mart_trust(db,[row])
    assert row==prior


@pytest.mark.parametrize('violation', ['more_units_ambiguous','less_units','duplicate_day','wrong_lock'])
def test_invalid_mart_or_lock_cannot_promote_trust(monkeypatch,violation):
    monkeypatch.setenv('APP_ENV','local')
    row=fixture('YC00697');db=Session(['YC00697']);k=next(iter(db.table))
    if violation=='more_units_ambiguous':db.table[k][4]['sales_qty']=12
    if violation=='less_units':db.table[k][0]['sales_qty']=0
    if violation=='duplicate_day':db.table[k].append(deepcopy(db.table[k][0]))
    if violation=='wrong_lock':
        for r in db.table[k]:r['locked_day']=date(2026,10,11)
    original=deepcopy(row)
    v6.finalize_missing_mart_trust(db,[row])
    assert row==original


def test_disabled_in_production_and_no_queries(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    row=fixture('YC00697');old=deepcopy(row);db=Session(['YC00697'])
    v6.finalize_missing_mart_trust(db,[row])
    assert row==old and not db.calls


def test_no_queries_if_only_775_already_scored(monkeypatch):
    monkeypatch.setenv('APP_ENV','local')
    row=fixture('YC00775',has_trust=True);db=Session(['YC00775'])
    v6.finalize_missing_mart_trust(db,[row])
    assert not db.calls
