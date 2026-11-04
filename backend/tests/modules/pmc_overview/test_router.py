"""PMC overview read routes: fail-closed auth / scope / not-ready, envelope, filters, paging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.core.permission_policy_v2 import permission_for_request
from app.main import create_app
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_overview import snapshot
from app.modules.pmc_overview.registry import PMC_OVERVIEW_API_REGISTRY

READ = "page:pmc:overview:view"
TODAY = "2026-11-02"


def _inp(item_id: str, sku: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "item_id": item_id,
        "sku": sku,
        "daily": 0,
        "n30": 0,
        "oos_days": None,
        "no_stock_90": True,
        "tail_stock": False,
        "max_start": 0,
        "supply": 0,
        "wm_available": 0,
        "sellout": None,
        "gap_days": None,
        "resume": None,
        "next_date": None,
        "lead_total": 60,
        "lead_avg": None,
        "suggest": 0,
        "suggest_raw": 0,
        "cap_on": False,
        "capped": False,
        "box": 20,
        "listing": "PUBLISHED",
        "tags": ["在售产品"],
    }
    base.update(kw)
    return base


def _item(inp: dict[str, Any], store: str, owner: str) -> dict[str, Any]:
    return {
        "input": inp,
        "display": {
            "item_id": inp["item_id"],
            "sku": inp["sku"],
            "msku": inp["sku"] + "-M",
            "name": "Synthetic " + inp["sku"],
            "owner": owner,
            "stores": [{"id": store, "name": "S-" + store, "sales30": 0, "available": 0}],
            "seg": {},
            "batches": [],
            "dom_rows": [],
        },
        "expect": {},
    }


def _snapshot() -> dict[str, Any]:
    items = [
        # normal, no stock, no sales
        _item(_inp("100", "SKU-A"), "s1", "Ann"),
        # out of stock: sells, WFS empty, nothing coming
        _item(
            _inp(
                "200",
                "SKU-B",
                daily=3,
                n30=20,
                oos_days=5,
                no_stock_90=False,
                sellout=TODAY,
                suggest=200,
                suggest_raw=200,
            ),
            "s2",
            "Bob",
        ),
        # heavily over-stocked: 10/day, 3000 supply → cover 300 days
        _item(
            _inp(
                "300",
                "SKU-C",
                daily=10,
                n30=30,
                oos_days=0,
                no_stock_90=False,
                supply=3000,
                wm_available=3000,
                sellout="2027-08-29",
            ),
            "s1",
            "Ann",
        ),
    ]
    return {
        "version": 1,
        "source": "synthetic",
        "today": TODAY,
        "src": "synthetic test data",
        "params": {"minQty": 50, "over1": 120, "over2": 150, "safety": 0},
        "expected_kpi": {"items": 3},
        "stores": [{"id": "s1", "name": "S-s1"}, {"id": "s2", "name": "S-s2"}],
        "store_summary": [{"store": "S-s1", "skus": 2}],
        "ops": {"cols": ["sku"], "heads": ["SKU"], "rows": [["SKU-A"]]},
        "warehouses": [
            {
                "name": "WH-CN",
                "class": "国内仓",
                "valid": 5,
                "lock": 1,
                "total": 6,
                "onway": 0,
                "skus": 1,
            },
            {
                "name": "WH-V",
                "class": "WFS 虚拟仓（剔除）",
                "valid": 9,
                "lock": 0,
                "total": 9,
                "onway": 0,
                "skus": 1,
            },
        ],
        "domestic_age": {"WH-CN": {"qty": 6, "avg": 3, "max": 9, "bands": {"0–30 天": 6}}},
        "unattributed_detail": [{"kind": "plan", "why": "SKU 未上架任何在售 ItemID", "qty": 4}],
        "overseas_total": 0,
        "items": items,
    }


@pytest.fixture
def snap_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(_snapshot(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, str(path))
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv(snapshot.DRAFT_MODE_ENV, raising=False)
    snapshot.clear_cache()
    return path


def _app(*permissions: str, scoped: bool = True) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user", permissions=frozenset(permissions)
    )
    application.dependency_overrides[require_source_account_scope] = lambda: (
        frozenset({"synthetic-account"}) if scoped else frozenset()
    )
    return application


def _envelope(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def test_openapi_lists_every_registered_route() -> None:
    paths = create_app().openapi()["paths"]
    for entry in PMC_OVERVIEW_API_REGISTRY.values():
        assert entry.route_path in paths
        op = paths[entry.route_path]["get"]
        assert op["operationId"]
        assert "503" in op["responses"]
    assert all(not p.startswith("/api/pmc/overview") or set(v) == {"get"} for p, v in paths.items())


def test_policy_maps_routes_to_the_page_permission() -> None:
    assert permission_for_request("GET", "/api/pmc/overview/items", "pmc:overview:read") == READ


@pytest.mark.parametrize("route", [e.route_path for e in PMC_OVERVIEW_API_REGISTRY.values()])
def test_routes_fail_closed(route: str, snap_file: Path) -> None:
    path = route.replace("{item_id}", "100")
    _envelope(TestClient(_app()).get(path), 403)
    _envelope(TestClient(_app(READ, scoped=False)).get(path), 403)


def test_missing_snapshot_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(snapshot.SNAPSHOT_ENV, raising=False)
    snapshot.clear_cache()
    body = _envelope(TestClient(_app(READ)).get("/api/pmc/overview/summary"), 503)
    assert body["error"]["code"] == "PMC_OVERVIEW_NOT_READY"


def test_broken_snapshot_is_not_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(snapshot.SNAPSHOT_ENV, str(bad))
    monkeypatch.setenv("APP_ENV", "local")
    snapshot.clear_cache()
    _envelope(TestClient(_app(READ)).get("/api/pmc/overview/items"), 503)


def test_summary_counts_all_items(snap_file: Path) -> None:
    body = _envelope(TestClient(_app(READ)).get("/api/pmc/overview/summary"))
    kpi = body["data"]["kpi"]
    assert kpi["items"] == 3
    assert kpi["oos"] == 1
    assert kpi["over2"] == 1
    assert body["data"]["parity_with_8088"] == {}
    assert body["data"]["unattributed"][0]["qty"] == 4
    meta = body["meta"]
    assert meta["data_date"] == TODAY
    assert meta["source"] == "pmc_overview_snapshot_8088"
    assert meta["draft_mode"] == "replenishment"


def test_items_default_only_issues_sorted_by_priority(snap_file: Path) -> None:
    client = TestClient(_app(READ))
    body = _envelope(client.get("/api/pmc/overview/items"))
    ids = [r["item_id"] for r in body["data"]["items"]]
    assert ids == ["200", "300"]  # 已断货 before 严重过剩; normal row hidden
    assert body["meta"]["total"] == 2
    every = _envelope(client.get("/api/pmc/overview/items", params={"only_issue": "false"}))
    assert every["meta"]["total"] == 3


def test_items_filters(snap_file: Path) -> None:
    client = TestClient(_app(READ))

    def ids(**params: Any) -> list[str]:
        body = _envelope(client.get("/api/pmc/overview/items", params=params))
        return [r["item_id"] for r in body["data"]["items"]]

    assert ids(store_id="s2") == ["200"]
    assert ids(owner="Ann") == ["300"]
    assert ids(cats=["严重过剩"]) == ["300"]
    assert ids(cats=["严重过剩", "已断货"]) == []
    assert ids(keyword="sku-b") == ["200"]
    _envelope(client.get("/api/pmc/overview/items", params={"page_size": 7}), 422)
    _envelope(client.get("/api/pmc/overview/items", params={"sort_by": "sku"}), 422)


def test_items_accept_page_size_from_the_query_string(snap_file: Path) -> None:
    # Regression 2026-11-04: the page always sends page_size; "50" must not be a 422.
    client = TestClient(_app(READ))
    for size in ("50", "100", "200", "500", "1000"):
        url = f"/api/pmc/overview/items?only_issue=true&page=1&page_size={size}"
        body = _envelope(client.get(url))
        assert body["meta"]["page_size"] == int(size)
        assert body["meta"]["total"] == 2


def test_items_sort_whitelist_and_category_counts(snap_file: Path) -> None:
    client = TestClient(_app(READ))
    body = _envelope(client.get("/api/pmc/overview/items", params={"only_issue": "false"}))
    counts = body["data"]["category_counts"]
    assert counts["已断货"] == 1
    assert counts["严重过剩"] == 1
    assert sum(1 for v in counts.values() if v) == len([k for k, v in counts.items() if v])
    narrowed = _envelope(
        client.get("/api/pmc/overview/items", params={"only_issue": "false", "cats": ["已断货"]})
    )
    assert narrowed["data"]["category_counts"] == counts  # cats do not narrow the buttons
    asc = _envelope(
        client.get(
            "/api/pmc/overview/items",
            params={"only_issue": "false", "sort_by": "supply", "sort_order": "asc"},
        )
    )
    desc = _envelope(
        client.get(
            "/api/pmc/overview/items",
            params={"only_issue": "false", "sort_by": "supply", "sort_order": "desc"},
        )
    )
    supply_asc = [r["supply"] for r in asc["data"]["items"]]
    assert supply_asc == sorted(supply_asc)
    assert [r["item_id"] for r in desc["data"]["items"]] == [
        r["item_id"] for r in reversed(asc["data"]["items"])
    ]
    _envelope(client.get("/api/pmc/overview/items", params={"cats": ["nope"]}), 422)


def test_item_detail_and_404(snap_file: Path) -> None:
    client = TestClient(_app(READ))
    body = _envelope(client.get("/api/pmc/overview/items/200"))
    assert body["data"]["main"] == "已断货"
    assert body["data"]["batches"] == []
    _envelope(client.get("/api/pmc/overview/items/999"), 404)


def test_options_warehouses_rules_export(snap_file: Path) -> None:
    client = TestClient(_app(READ))
    opts = _envelope(client.get("/api/pmc/overview/filter-options"))["data"]
    assert opts["owners"] == ["Ann", "Bob"]
    assert len(opts["categories"]) == 13
    wh = _envelope(client.get("/api/pmc/overview/warehouses"))["data"]
    assert [w["name"] for w in wh["warehouses"]] == ["WH-CN"]
    assert wh["warehouses"][0]["age_max"] == 9
    rules = _envelope(client.get("/api/pmc/overview/rules"))["data"]
    assert rules["editable"] is False
    assert {p["key"] for p in rules["params"]} >= {"over1", "over2"}
    exp = _envelope(client.get("/api/pmc/overview/export", params={"only_issue": "false"}))
    assert exp["meta"]["total"] == 3
    assert len(exp["data"]["warehouses"]) == 2
    assert exp["data"]["ops_heads"] == ["SKU"]


def test_cache_reloads_when_file_changes(snap_file: Path) -> None:
    first = snapshot.load_board()
    assert snapshot.load_board() is first
    data = _snapshot()
    data["items"] = data["items"][:1]
    snap_file.write_text(json.dumps(data, ensure_ascii=False) + " ", encoding="utf-8")
    assert snapshot.load_board().kpi["items"] == 1


@pytest.mark.parametrize("env", ["production", "staging", ""])
def test_snapshot_is_refused_outside_local(
    snap_file: Path, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("APP_ENV", env)
    snapshot.clear_cache()
    body = _envelope(TestClient(_app(READ)).get("/api/pmc/overview/summary"), 503)
    assert body["error"]["code"] == "PMC_OVERVIEW_NOT_READY"
