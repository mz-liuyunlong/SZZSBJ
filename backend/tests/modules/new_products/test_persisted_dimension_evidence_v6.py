"""Read-only saved evidence projection regression: no DB calls, no scoring writes."""
from datetime import date
from types import SimpleNamespace

from app.modules.new_products.persisted_projection import merge_persisted_page_row

FIELDS = ("sales_orders", "sales_units", "sales_amount_usd", "ad_spend_usd",
          "ad_clicks", "ad_sales_usd", "roi", "profit_margin_pct", "profit_usd",
          "return_rate_units_pct", "return_rate_orders_pct", "first_order_date_la",
          "calculated_at", "metric_window_start_la", "metric_window_end_la",
          "first_wfs_available_date_la", "data_status", "data_coverage_json")


def specimen(ad_score="9.04", trust_score="4.30", single=1):
    coverage = {"auto_dimension_scores": {"dimensions": {
        "speed":"4.30", "ad":ad_score, "profit":"5.74", "trust":trust_score},
        "automatic_points": "5.0", "covered_weight_pct":"85"},
        "ad_history_full": {"status":"scored", "source":"fact_walmart_ad_item_sp_daily",
            "cutoff_la":"2026-11-11", "ad_rows":15, "core_incomplete_rows":0,
            "unverified_sales_rows":0, "spend_usd":"6.19", "clicks":13,
            "attributed_orders":1, "attributed_sales_reported":"20.99",
            "ad_score":"9.035653"}}
    perf = SimpleNamespace(**{k:None for k in FIELDS})
    perf.data_coverage_json = coverage
    perf.sales_units = 1
    perf.sales_orders = 1
    perf.ad_spend_usd = 6.19
    perf.ad_clicks = 4
    perf.first_wfs_available_date_la = date(2026,11,9)
    perf.metric_window_start_la = date(2026,11,9)
    perf.metric_window_end_la = date(2026,11,11)
    perf.data_status = "partial"
    registry = SimpleNamespace(category_l1=None,category_l2=None,listing_date_la=None)
    row = {"listing":{},"facts":{},"evaluation":{"dimensions":{
        "speed":None, "ad":None,"profit":None,"trust":None},
        "observation_state":"not_calculated", "rule_version":0, "missing":[]}}
    return row,registry,perf


def call(row,registry,perf):
    merge_persisted_page_row(row,(registry,perf),date(2026,11,14))


def test_saved_ad_fact_fields_and_existing_scores_unchanged():
    row,reg,perf=specimen()
    call(row,reg,perf)
    f = row['facts']
    assert f['ad_status'] == 'active'
    assert f['ad_clicks'] == 13 and f['ad_spend_usd'] == '6.19'
    assert f['ad_orders'] == 1 and f['ad_revenue_usd'] == '20.99'
    assert f['ad_evidence_cutoff_la']=='2026-11-11'
    assert f['single_unit_orders_14d'] == 1
    assert f['single_unit_orders_evidence'] == 'derived_from_equal_saved_units_and_orders'
    assert row['evaluation']['dimensions']['ad'] == '9.04'
    assert row['evaluation']['dimensions']['trust'] == '4.30'
    assert row['evaluation']['total'] if 'total' in row['evaluation'] else True


def test_does_not_fabricate_single_when_units_not_equal_orders():
    row,reg,perf=specimen()
    perf.sales_units = 3
    perf.sales_orders = 2
    call(row,reg,perf)
    assert 'single_unit_orders_14d' not in row['facts']


def test_ad_status_invalid_source_or_score_does_not_promote():
    row,reg,perf=specimen()
    perf.data_coverage_json['ad_history_full']['status']='missing_core_metrics'
    call(row,reg,perf)
    assert 'ad_status' not in row['facts']
    row,reg,perf=specimen(ad_score='5.00')
    call(row,reg,perf)
    assert 'ad_status' not in row['facts']


def test_ad_currency_uncertain_or_order_inconsistent_is_not_promoted():
    row,reg,perf=specimen()
    perf.data_coverage_json['ad_history_full']['unverified_sales_rows']=1
    call(row,reg,perf)
    assert 'ad_orders' not in row['facts']
    row,reg,perf=specimen()
    perf.data_coverage_json['ad_history_full']['attributed_orders']=14
    call(row,reg,perf)
    assert 'ad_orders' not in row['facts']


def test_frozen_snapshot_gets_no_new_evidence():
    row,reg,perf=specimen()
    row['evaluation']['observation_state']='frozen'
    call(row,reg,perf)
    assert 'ad_status' not in row['facts']
    assert 'single_unit_orders_14d' not in row['facts']


def test_trust_not_inferred_on_nondefault_rule_version():
    row,reg,perf=specimen()
    row['evaluation']['rule_version']=1
    call(row,reg,perf)
    assert 'single_unit_orders_14d' not in row['facts']


def test_explicit_saved_order_fact_takes_precedence():
    row,reg,perf=specimen()
    perf.sales_units=3
    perf.sales_orders=2
    perf.data_coverage_json['trust_history_full']={
       'status':'scored','source':'fact_walmart_order_items',
       'valid_units_14d':3,'valid_orders_14d':2,'single_unit_orders_14d':1}
    call(row,reg,perf)
    assert row['facts']['single_unit_orders_14d']==1
    assert row['facts']['single_unit_orders_evidence']=='saved_order_fact_snapshot'
