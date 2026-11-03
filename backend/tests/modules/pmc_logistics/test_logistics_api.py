"""物流看板 API shape and store scope, over the 8088 golden cases (no database)."""

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api import install_api_foundation
from app.modules.pmc_logistics import router as logistics_router
from app.modules.pmc_logistics.build import LogisticsInputs
from app.modules.pmc_logistics.rules import default_rules, enrich_sp
from app.modules.pmc_logistics.service import LogisticsService, LogisticsSnapshot

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures_8088_logistics_20261102.json").read_text("utf-8")
)


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


def test_board_returns_every_sp_with_8088_fields_and_rule_date():
    body = _client(_service()).get("/api/pmc/logistics/board").json()
    data = body["data"]
    assert data["today"] == "2026-11-02" and body["meta"]["rule_date"] == "2026-11-02"
    assert body["meta"]["provider_calls"] is False
    assert len(data["rows"]) == len(FIXTURE["cases"])
    row = data["rows"][0]
    for key in (
        "code",
        "stage",
        "arrivalDate",
        "sellableDate",
        "deadline",
        "penalty",
        "ex",
        "goods",
    ):
        assert key in row
    assert sum(data["stage_counts"].values()) == len(FIXTURE["cases"])
    assert data["rules"]["penalty_per_kg_day"] == 0.5


def test_detail_and_store_scope():
    code = FIXTURE["cases"][0]["sp"]["code"]
    store = FIXTURE["cases"][0]["sp"]["store_id"]
    detail = _client(_service()).get(f"/api/pmc/logistics/shipping-lists/{code}").json()["data"]
    assert detail["row"]["code"] == code
    other = _client(_service(stores={"not-my-store"}))
    assert other.get(f"/api/pmc/logistics/shipping-lists/{code}").status_code == 404
    assert other.get("/api/pmc/logistics/board").json()["data"]["rows"] == []
    mine = _client(_service(stores={store})).get("/api/pmc/logistics/board").json()["data"]
    assert {r["code"] for r in mine["rows"]} >= {code}
