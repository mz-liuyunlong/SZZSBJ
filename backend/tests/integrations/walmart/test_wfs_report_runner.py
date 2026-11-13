"""WFS 费用报表远端执行：开关、结果核对、令牌只走标准输入、远端不留东西。不连任何服务器。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.integrations.walmart import wfs_report_engine as engine
from app.integrations.walmart import wfs_report_runner as runner
from app.integrations.walmart.remote_dispatch import DispatchRejected, WorkerRoute

ROUTE = WorkerRoute("HK2612", "store-host.invalid", "/opt/szzsbj/walmart/run_worker.py")
PLAN = {"store_code": "HK2612", "max_posts": 2, "actions": []}


def test_disabled_unless_both_switches_are_on(monkeypatch):
    monkeypatch.setenv("SZZSBJ_WALMART_REMOTE_COLLECTION_ENABLED", "1")
    monkeypatch.delenv("SZZSBJ_WALMART_WFS_REPORTS_ENABLED", raising=False)
    with pytest.raises(DispatchRejected, match="WFS_REPORTS_DISABLED"):
        runner.approved_routes()


def _out(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    (out / "files" / "k1").mkdir(parents=True)
    (out / "files" / "k1" / "report.csv").write_bytes(b"a,b\n1,2\n")
    (out / "results.json").write_text('{"store_code": "HK2612", "results": []}')
    lines = sorted(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(out)}"
        for path in out.rglob("*")
        if path.is_file()
    )
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return out


def test_verify_sums_accepts_exact_set(tmp_path):
    runner._verify_sums(_out(tmp_path))


def test_verify_sums_rejects_changed_extra_or_missing_files(tmp_path):
    out = _out(tmp_path)
    (out / "files" / "k1" / "report.csv").write_bytes(b"changed\n")
    with pytest.raises(DispatchRejected, match="WFS_REPORTS_FILE_HASH_MISMATCH"):
        runner._verify_sums(out)
    out = _out(tmp_path / "second")
    (out / "files" / "extra.csv").write_bytes(b"x")
    with pytest.raises(DispatchRejected, match="WFS_REPORTS_FILES_MISMATCH"):
        runner._verify_sums(out)


def test_plan_must_belong_to_the_route_store(tmp_path):
    with pytest.raises(DispatchRejected, match="WFS_REPORTS_PLAN_STORE_MISMATCH"):
        runner.run_plan(
            route=ROUTE,
            run_id="wfs-synthetic-01",
            plan={**PLAN, "store_code": "HK2613"},
            token_supplier=lambda: "t",
            local_root=tmp_path,
        )


def test_token_only_on_stdin_and_remote_is_cleaned_up(tmp_path, monkeypatch):
    uploaded: dict[str, str] = {}
    calls: list[tuple[list[str], str | None]] = []

    def fake_exec(args, *, data=None, timeout=120):
        if args[0] == "scp" and "-r" not in args:
            local, remote = args[-2], args[-1].split(":", 1)[1]
            uploaded[remote] = hashlib.sha256(Path(local).read_bytes()).hexdigest()
        return 0, ""

    def fake_ssh(host, argv, *, data=None, timeout=120):
        calls.append((argv, data))
        if argv[0] == "sha256sum":
            return 0, uploaded.get(argv[-1], "0" * 64) + "  " + argv[-1]
        if argv[0] == "python3":
            return engine.EXIT_SAFETY, ""
        return 0, ""

    monkeypatch.setattr(runner, "_exec", fake_exec)
    monkeypatch.setattr(runner, "_ssh", fake_ssh)
    with pytest.raises(DispatchRejected, match="WFS_REPORTS_ENGINE_REFUSED"):
        runner.run_plan(
            route=ROUTE,
            run_id="wfs-synthetic-01",
            plan=PLAN,
            token_supplier=lambda: "synthetic-token",
            local_root=tmp_path,
        )
    engine_call = next(item for item in calls if item[0][0] == "python3")
    assert "--token-stdin" in engine_call[0]
    assert all("synthetic-token" not in arg for argv, _ in calls for arg in argv)
    assert engine_call[1] == "synthetic-token\n"
    # 执行器每次重新上传、核对哈希
    assert set(uploaded) == {
        runner.REMOTE_BASE + "/wfs-synthetic-01/wfs_report_engine.py",
        runner.REMOTE_BASE + "/wfs-synthetic-01/plan.json",
    }
    assert calls[-1][0][:3] == ["rm", "-rf", "--"]
    assert runner.REMOTE_BASE + "/.runs/wfs-synthetic-01" in calls[-1][0]


def test_lock_held_by_another_run_is_not_entered(tmp_path, monkeypatch):
    def fake_ssh(host, argv, *, data=None, timeout=120):
        if argv == ["mkdir", runner.REMOTE_BASE + "/.runs/wfs-synthetic-02"]:
            return 1, ""
        return 0, ""

    monkeypatch.setattr(runner, "_ssh", fake_ssh)
    with pytest.raises(DispatchRejected, match="REMOTE_ALREADY_RUNNING"):
        runner.run_plan(
            route=ROUTE,
            run_id="wfs-synthetic-02",
            plan=PLAN,
            token_supplier=lambda: pytest.fail("token must not be requested"),
            local_root=tmp_path,
        )
