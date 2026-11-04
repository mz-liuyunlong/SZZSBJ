"""物流看板 API shape and store scope, over the 8088 golden cases (no database)."""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api import install_api_foundation
from app.modules.pmc_logistics import router as logistics_router
from app.modules.pmc_logistics import service as logistics_service
from app.modules.pmc_logistics.build import LogisticsInputs
from app.modules.pmc_logistics.rules import default_rules, enrich_sp
from app.modules.pmc_logistics.service import LogisticsService, LogisticsSnapshot

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures_8088_logistics_20261102.json").read_text("utf-8")
)


@pytest.fixture(autouse=True)
def _no_lookups(monkeypatch):
    """Item ID / owner lookups read other modules' tables; empty here."""

    monkeypatch.setattr(logistics_service, "item_ids_by_store_msku", lambda *a: {})
    monkeypatch.setattr(logistics_service, "owners_by_sku", lambda *a: {})


def _service(stores=None) -> LogisticsService:
    sps = [c["sp"] for c in FIXTURE["cases"]]
    wm = {k: v for c in FIXTURE["cases"] for k, v in c["wm"].items()}
    rules = default_rules(sps)
    today = date.fromisoformat(FIXTURE["today"])
    rows = []
    for c in FIXTURE["cases"]:
        view = enrich_sp(c["sp"], c["track"], wm, set(FIXTURE["wm_stores"]), rules, today)
        rows.append({"sp": c["sp"], "track": c["track"], "view": view})
    svc = LogisticsService(None, ["primary"], stores)  # type: ignore[arg-type]
    svc._snapshot = LogisticsSnapshot(
        today=today,
        publication_ids=[],
        inputs=LogisticsInputs(sps=sps, fcs={}, stores={}, providers={}, channels=[]),
        rules=rules,
        wm_stores=set(FIXTURE["wm_stores"]),
        wm_day=FIXTURE["wm_day"],
        wm=wm,
        rows=rows,
    )
    return svc


def _client(svc: LogisticsService) -> TestClient:
    app = FastAPI()
    install_api_foundation(app)
    app.include_router(logistics_router.router)
    app.dependency_overrides[logistics_router.service] = lambda: svc
    return TestClient(app)


API = "/api/pmc/logistics"


def test_overview_is_server_paginated_with_8088_fields_and_rule_date():
    client = _client(_service())
    body = client.get(f"{API}/overview", params={"page_size": 5}).json()
    data = body["data"]
    assert body["meta"]["rule_date"] == "2026-11-02" and body["meta"]["provider_calls"] is False
    assert body["meta"]["total"] == data["total"] == len(FIXTURE["cases"])
    assert len(data["items"]) == 5 and data["page"] == 1
    row = data["items"][0]
    for key in ("code", "stage", "arrivalDate", "sellableDate", "deadline", "penalty", "ex"):
        assert key in row
    assert "goods" not in row and row["cargo_count"] >= 0
    assert data["summary"]["cards"]["all"] == len(FIXTURE["cases"])
    page2 = client.get(f"{API}/overview", params={"page_size": 5, "page": 2}).json()["data"]
    assert {r["code"] for r in page2["items"]}.isdisjoint({r["code"] for r in data["items"]})


def test_overview_filters_and_cards():
    client = _client(_service())
    over = client.get(f"{API}/overview", params={"card": "over"}).json()["data"]
    assert over["total"] == over["summary"]["cards"]["over"]
    assert all(r["overdue"] for r in over["items"])
    code = FIXTURE["cases"][3]["sp"]["code"]
    hit = client.get(f"{API}/overview", params={"keyword": code[-6:]}).json()["data"]
    assert code in {r["code"] for r in hit["items"]}
    assert client.get(f"{API}/overview", params={"card": "nope"}).status_code == 422


def test_options_alerts_forecast_rules():
    client = _client(_service())
    opts = client.get(f"{API}/options").json()["data"]
    assert sum(opts["stage_counts"].values()) == opts["total"] == len(FIXTURE["cases"])
    assert opts["rules"]["penalty_per_kg_day"] == 0.5 and "已超合同时效" in opts["alert_types"]

    alerts = client.get(f"{API}/alerts", params={"page_size": 200}).json()["data"]
    assert (
        alerts["total"]
        == alerts["summary"]["all"]
        == sum(len(c["gold"]["ex"]) for c in FIXTURE["cases"])
    )
    sev = [a["sev"] for a in alerts["items"]]
    assert sev == sorted(sev, key={"high": 0, "mid": 1, "low": 2}.get)
    high = client.get(f"{API}/alerts", params={"sev": "high"}).json()["data"]
    assert {a["sev"] for a in high["items"]} == {"high"}

    fc = client.get(f"{API}/forecast").json()["data"]
    assert fc["summary"]["buffer"] == 10
    totals = [r["total"] for r in fc["items"]]
    assert totals == sorted(totals, reverse=True)

    rules = client.get(f"{API}/rules").json()["data"]
    assert rules["editable"] is False
    assert {t["key"] for t in rules["thresholds"]} >= {"remind_before", "wm_receive_buffer"}
    assert rules["counts"]["contracts"] and rules["counts"]["cycles"]


def test_rule_tables_are_server_paginated_with_a_sort_whitelist():
    client = _client(_service())
    first = client.get(f"{API}/rules/contracts", params={"page_size": 2}).json()
    data = first["data"]
    assert len(data["items"]) == 2 and data["total"] == data["summary"]["all"] > 2
    assert first["meta"]["total"] == data["total"]
    desc = client.get(
        f"{API}/rules/contracts", params={"sort": "days", "order": "desc", "page_size": 200}
    ).json()["data"]["items"]
    days = [c["days"] for c in desc]
    assert days == sorted(days, reverse=True)
    east = client.get(f"{API}/rules/contracts", params={"region": "美东"}).json()["data"]
    assert {c["region"] for c in east["items"]} == {"美东"}
    assert client.get(f"{API}/rules/contracts", params={"sort": "provider_id"}).status_code == 422
    assert client.get(f"{API}/rules/nope").status_code == 422


def test_carriers_filter_by_provider_and_search_field():
    svc = _service()
    sp = FIXTURE["cases"][0]["sp"]
    base = {"status": "已开船", "store_id": "", "stale": False, "trackCn": "", "lastTrack": ""}
    svc.snapshot().carrier_orders = [
        {
            **base,
            "number": "ZY1",
            "customerNumber": "C1",
            "sp": sp["code"],
            "provider_id": "6995",
            "provider": "众壹物流",
        },
        {
            **base,
            "number": "ZY2",
            "customerNumber": "ZY1-C",
            "sp": "",
            "provider_id": "6995",
            "provider": "众壹物流",
        },
    ]
    client = _client(svc)

    def total(**params):
        return client.get(f"{API}/carriers", params=params).json()["data"]["total"]

    assert total(provider="6995") == 2 and total(provider="7001") == 0
    assert total(keyword="zy1") == 2  # 全部字段
    assert total(keyword="zy1", field="number") == 1
    assert total(keyword="zy1-c", field="customer") == 1
    assert total(keyword=sp["code"], field="sp") == 1 and total(keyword="zy1", field="sp") == 0
    data = client.get(f"{API}/carriers").json()["data"]
    assert data["summary"]["providers"] == [{"value": "6995", "label": "众壹物流", "count": 2}]
    assert client.get(f"{API}/carriers", params={"field": "track"}).status_code == 422


def test_forecast_search_by_logistics_numbers():
    client = _client(_service())
    rows = client.get(f"{API}/forecast", params={"page_size": 1000}).json()["data"]["items"]
    row = next(r for r in rows if r["trackings"])
    for field, value in (
        ("sp", row["codes"][0]),
        ("cargo", row["cargos"][0]),
        ("track", row["trackings"][0]),
    ):
        hits = client.get(f"{API}/forecast", params={"field": field, "keyword": value}).json()
        assert row["key"] in {r["key"] for r in hits["data"]["items"]}, field
    none = client.get(f"{API}/forecast", params={"field": "sku", "keyword": row["codes"][0]})
    assert none.json()["data"]["total"] == 0
    assert client.get(f"{API}/forecast", params={"field": "nope"}).status_code == 422


def test_carriers_empty_without_files_and_404_detail():
    client = _client(_service())
    data = client.get(f"{API}/carriers").json()["data"]
    assert data["total"] == 0 and data["summary"]["orders"] == 0
    assert client.get(f"{API}/carriers/ZY404").status_code == 404


def test_detail_and_store_scope():
    code = FIXTURE["cases"][0]["sp"]["code"]
    store = FIXTURE["cases"][0]["sp"]["store_id"]
    detail = _client(_service()).get(f"{API}/shipping-lists/{code}").json()["data"]
    assert detail["row"]["code"] == code
    other = _client(_service(stores={"not-my-store"}))
    assert other.get(f"{API}/shipping-lists/{code}").status_code == 404
    assert other.get(f"{API}/overview").json()["data"]["items"] == []
    assert other.get(f"{API}/forecast").json()["data"]["items"] == []
    mine = _client(_service(stores={store})).get(f"{API}/overview").json()["data"]
    assert code in {r["code"] for r in mine["items"]}
