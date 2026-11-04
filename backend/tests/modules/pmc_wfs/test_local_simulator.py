"""本机模拟通道只在 APP_ENV=local + 本机库 + WFS_CREATION_MODE 未设时生效；别处误设一律报错，
不会退回真实 Walmart 通道，也不会悄悄当成关闭。"""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url

from app.core import config
from app.core.api import ApiError
from app.modules.pmc_wfs import creation_task, gateway, local_simulator
from app.modules.pmc_wfs.gateway import DisabledGateway
from app.modules.pmc_wfs.local_simulator import (
    LocalSimulatorGateway,
    SimulatorRefused,
    label_pdf,
)

LOCAL_DB = "postgresql+psycopg://dev@127.0.0.1:55432/szzsbj_dev"


def fake_settings(monkeypatch, env, url=LOCAL_DB):
    settings = SimpleNamespace(
        app_env=SimpleNamespace(value=env), sqlalchemy_url=lambda: make_url(url)
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)


@pytest.fixture
def state(tmp_path, monkeypatch):
    path = tmp_path / "sim.json"
    monkeypatch.setenv(local_simulator.STATE_ENV, str(path))
    monkeypatch.delenv("WFS_CREATION_MODE", raising=False)
    return path


@pytest.fixture
def local(monkeypatch, state):
    monkeypatch.setenv(local_simulator.ENV, "1")
    fake_settings(monkeypatch, "local")


def test_switch_unset_changes_nothing(monkeypatch, state):
    monkeypatch.delenv(local_simulator.ENV, raising=False)
    fake_settings(monkeypatch, "production", "postgresql+psycopg://app@10.0.0.5:5432/prod")
    assert local_simulator.simulator_active() is False
    local_simulator.startup_check()
    assert isinstance(gateway.get_creation_gateway(), DisabledGateway)
    assert creation_task.simulator_pull(None, None, "u") == []


@pytest.mark.parametrize(
    ("env", "url", "mode", "words"),
    [
        ("production", "postgresql+psycopg://app@10.0.0.5:5432/szzsbj", None, "APP_ENV=local"),
        ("staging", LOCAL_DB, None, "APP_ENV=local"),
        ("test", LOCAL_DB, None, "APP_ENV=local"),
        ("local", "postgresql+psycopg://dev@10.0.0.5:55432/szzsbj_dev", None, "本机库"),
        ("local", "postgresql+psycopg://dev@127.0.0.1:5432/szzsbj_dev", None, "本机库"),
        ("local", "postgresql+psycopg://dev@127.0.0.1:55432/szzsbj", None, "szzsbj_dev"),
        ("local", LOCAL_DB, "single", "WFS_CREATION_MODE"),
        ("local", LOCAL_DB, "probe", "WFS_CREATION_MODE"),
    ],
)
def test_misplaced_switch_raises_everywhere(monkeypatch, state, env, url, mode, words):
    monkeypatch.setenv(local_simulator.ENV, "1")
    if mode:
        monkeypatch.setenv("WFS_CREATION_MODE", mode)
    fake_settings(monkeypatch, env, url)
    for call in (
        local_simulator.startup_check,
        local_simulator.simulator_active,
        gateway.get_creation_gateway,  # raises: never DisabledGateway, never the Walmart adapter
        LocalSimulatorGateway,
        lambda: creation_task.simulator_pull(None, None, "u"),
    ):
        with pytest.raises(SimulatorRefused, match=words):
            call()


def test_unreadable_settings_refuse(monkeypatch, state):
    monkeypatch.setenv(local_simulator.ENV, "yes")

    def broken():
        raise config.SettingsError("missing")

    monkeypatch.setattr(config, "get_settings", broken)
    with pytest.raises(SimulatorRefused):
        local_simulator.startup_check()


@pytest.mark.parametrize("env", ["test", "production"])
def test_real_settings_object_refuses_outside_local(monkeypatch, state, env):
    """Real Settings (not a stub) pointing at the local database: still refused, because
    APP_ENV is not local. Production settings that do not validate are refused as well."""
    monkeypatch.setenv(local_simulator.ENV, "1")
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("DATABASE_URL", LOCAL_DB)
    monkeypatch.setenv("TEST_DATABASE_URL", LOCAL_DB)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(SimulatorRefused):
            local_simulator.startup_check()
        with pytest.raises(SimulatorRefused):
            gateway.get_creation_gateway()
    finally:
        config.get_settings.cache_clear()


def test_router_import_fails_in_production(monkeypatch, state):
    from app.modules.pmc_wfs import creation_router

    monkeypatch.setenv(local_simulator.ENV, "1")
    fake_settings(monkeypatch, "production", "postgresql+psycopg://app@10.0.0.5:5432/szzsbj")
    with pytest.raises(SimulatorRefused):
        importlib.reload(creation_router)
    monkeypatch.delenv(local_simulator.ENV)
    importlib.reload(creation_router)  # leave the module as the rest of the suite expects


def test_pull_endpoint_is_404_outside_simulator(monkeypatch, state):
    from app.modules.pmc_wfs.creation_router import simulator_pull_now

    monkeypatch.delenv(local_simulator.ENV, raising=False)
    with pytest.raises(ApiError) as caught:
        simulator_pull_now(request=None, base=None, actor=None)
    assert caught.value.status_code == 404


def test_local_simulator_behaves_like_8088(local, state):
    from app.modules.pmc_wfs.walmart_gateway import DefinitiveRejection, ResultUnknown

    sim = gateway.get_creation_gateway()
    assert isinstance(sim, LocalSimulatorGateway) and sim.simulator and sim.mode == "simulator"
    order = "PMC-HK2614-20261104-01"
    snap = {"order": {"store_name": "HK2614-测试"}, "return_address": {"postal_code": "91710"}}
    assert sim.store_code(snap) == "HK2614"
    assert sim.reconcile(order, snap) is None  # 先查：查无此单
    sids = sim.create(order, snap, {})
    assert sids and sids[0].startswith("SIM") and not isinstance(sids[0], dict)  # 不带 FC
    back = sim.reconcile(order, snap)
    assert back[0]["shipment_id"] == sids[0] and back[0]["fc"] == "LAX2T"
    assert b"SIMULATED" in sim.label(sids[0], snap, 4)

    rejected = {**snap, "return_address": {"postal_code": "00000"}}
    with pytest.raises(DefinitiveRejection):
        sim.create("PMC-HK2614-20261104-02", rejected, {})
    assert sim.reconcile("PMC-HK2614-20261104-02", rejected) is None

    unknown = {**snap, "return_address": {"postal_code": "99999"}}
    with pytest.raises(ResultUnknown):
        sim.create("PMC-HK2614-20261104-03", unknown, {})
    assert sim.reconcile("PMC-HK2614-20261104-03", unknown)[0]["fc"] == "LAX2T"
    assert state.exists()


def test_label_pdf_is_a_pdf():
    pdf = label_pdf("SIM0000001", 3)
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert b"SIMULATED WFS LABEL SIM0000001 CARTONS 3" in pdf


def test_simulator_module_makes_no_network_calls():
    source = importlib.util.find_spec("app.modules.pmc_wfs.local_simulator").origin
    text = open(source, encoding="utf-8").read()
    for word in (
        "httpx",
        "requests",
        "urllib",
        "socket",
        "walmart_scf",
        "build_production_gateway",
    ):
        assert word not in text


def test_seed_script_refuses_outside_local(monkeypatch):
    import runpy

    fake_settings(monkeypatch, "production", "postgresql+psycopg://app@10.0.0.5:5432/szzsbj")
    script = Path(__file__).parents[3] / "scripts" / "seed_pmc_wfs_local_demo.py"
    module = runpy.run_path(str(script))
    for command in (["seed"], ["clear"]):
        assert module["main"](command) == 2
