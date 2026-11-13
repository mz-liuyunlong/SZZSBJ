"""WFS 费用报表远端执行器：白名单锁定 + 下单 / 复用 / 下载 / 个人信息 / 令牌。

全部用假的传输层，不发真请求。
"""

from __future__ import annotations

import ast
import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from app.integrations.walmart import wfs_report_engine as E

ENGINE_FILE = Path(E.__file__)
START, END = "2026-10-03T00:00:00.000Z", "2026-10-16T23:59:59.000Z"


def test_whitelist_is_locked_to_two_report_types_and_one_post_path():
    """改这里要 Rocky 批准（2026-11-13）：只能下单做结算报表、仓储费报表。"""
    assert E.REPORT_TYPES == {"SETTLEMENT": "v1", "WFS_STORAGE_FEE": "v1"}
    assert E.ALLOWED_METHODS == ("GET", "POST")
    assert E.POST_PATHS == ("/v3/reports/reportRequests",)
    source = ENGINE_FILE.read_text(encoding="utf-8")
    paths = set(re.findall(r'"(/v3/[A-Za-z0-9/_{}-]*)"', source))
    assert paths == {"/v3/reports/reportRequests", "/v3/reports/downloadReport"}
    for method in ("PUT", "PATCH", "DELETE"):
        assert f'"{method}"' not in source


def test_engine_only_uses_the_standard_library():
    """店铺服务器只有系统 Python（最低 3.6），不能依赖仓库里的包。"""
    tree = ast.parse(ENGINE_FILE.read_text(encoding="utf-8"))
    modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    allowed = {
        "__future__",
        "argparse",
        "csv",
        "hashlib",
        "io",
        "json",
        "os",
        "re",
        "sys",
        "time",
        "urllib",
        "uuid",
        "zipfile",
    }
    assert modules <= allowed


def _zip(name: str, body: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, body)
    return buf.getvalue()


class FakeWalmart:
    name = "mock"

    def __init__(self, *, existing=None, status="READY", file_bytes=None, submit_status=200):
        self.calls: list[tuple[str, str, dict]] = []
        self.existing = existing or []
        self.status = status
        self.file_bytes = (
            file_bytes
            if file_bytes is not None
            else _zip(
                "SettlementReport.csv", b"Transaction Type,Net Payable\nLostInventory,-1.00\n"
            )
        )
        self.submit_status = submit_status

    def send(self, method, url, headers, data):
        self.calls.append((method, url, dict(headers)))
        if url.startswith("https://files.example.test/"):
            assert "WM_SEC.ACCESS_TOKEN" not in headers  # 下载地址不带鉴权头
            return 200, {}, self.file_bytes
        if headers.get("WM_SEC.ACCESS_TOKEN") == "expired":
            return 401, {}, b"{}"
        path = url.split("marketplace.walmartapis.com", 1)[1]
        if method == "GET" and path.startswith("/v3/reports/reportRequests?"):
            return 200, {}, json.dumps({"requests": self.existing}).encode()
        if method == "POST" and path.startswith("/v3/reports/reportRequests?"):
            if self.submit_status != 200:
                return self.submit_status, {"X-Next-Replenishment-Time": "1"}, b"{}"
            return (
                200,
                {},
                json.dumps({"requestId": "req-00000001", "requestStatus": "RECEIVED"}).encode(),
            )
        if method == "GET" and path.startswith("/v3/reports/reportRequests/"):
            return 200, {}, json.dumps({"requestStatus": self.status}).encode()
        if method == "GET" and path.startswith("/v3/reports/downloadReport?"):
            return (
                200,
                {},
                json.dumps({"downloadURL": "https://files.example.test/r.zip?sig=x"}).encode(),
            )
        raise AssertionError(url)


def _run(tmp_path, plan, transport, token="t0k"):
    engine = E.Engine(
        {"store_code": "HK0001", "max_posts": 2, **plan}, str(tmp_path), transport, token
    )
    code = engine.run()
    doc = json.loads((tmp_path / "results.json").read_text())
    return code, doc


def submit(rt="SETTLEMENT", **extra):
    return {
        "op": "submit",
        "key": f"k-{rt}",
        "reportType": rt,
        "dataStartTime": START,
        "dataEndTime": END,
        "post_allowed": True,
        **extra,
    }


def test_submit_posts_once_per_type_and_refuses_other_types(tmp_path):
    t = FakeWalmart()
    code, doc = _run(
        tmp_path,
        {
            "actions": [
                submit("SETTLEMENT"),
                {**submit("SETTLEMENT"), "key": "again"},
                submit("ITEM"),
            ]
        },
        t,
    )
    outcomes = [r["outcome"] for r in doc["results"]]
    assert outcomes == [
        "submitted",
        "deferred_one_post_per_type_per_run",
        "refused_type_not_allowed",
    ]
    assert [c[0] for c in t.calls].count("POST") == 1
    assert code == E.EXIT_OK


def test_existing_request_is_reused_without_posting(tmp_path):
    existing = [
        {
            "requestId": "req-old00001",
            "requestStatus": "READY",
            "payload": {"dataStartTime": START, "dataEndTime": END},
        }
    ]
    t = FakeWalmart(existing=existing)
    _code, doc = _run(tmp_path, {"actions": [submit()]}, t)
    assert (
        doc["results"][0]["outcome"] == "reused"
        and doc["results"][0]["requestId"] == "req-old00001"
    )
    assert all(c[0] == "GET" for c in t.calls)


def test_bad_date_and_rate_window_never_post(tmp_path):
    t = FakeWalmart()
    _code, doc = _run(
        tmp_path,
        {
            "actions": [
                {**submit(), "dataStartTime": "2026-10-03"},
                {**submit("WFS_STORAGE_FEE"), "post_allowed": False},
            ]
        },
        t,
    )
    assert [r["outcome"] for r in doc["results"]] == [
        "refused_bad_date_format",
        "deferred_rate_window",
    ]
    assert all(c[0] == "GET" for c in t.calls)


def test_rate_limited_submit_is_reported(tmp_path):
    _code, doc = _run(tmp_path, {"actions": [submit()]}, FakeWalmart(submit_status=429))
    assert doc["results"][0]["outcome"] == "rate_limited"


def test_fetch_downloads_csv_members_and_writes_checksums(tmp_path):
    action = {"op": "fetch", "key": "k1", "reportType": "SETTLEMENT", "requestId": "req-00000001"}
    _code, doc = _run(tmp_path, {"actions": [action]}, FakeWalmart())
    result = doc["results"][0]
    assert result["outcome"] == "downloaded" and result["download_host"] == "files.example.test"
    assert (
        (tmp_path / "files" / "k1" / "SettlementReport.csv")
        .read_bytes()
        .startswith(b"Transaction Type")
    )
    sums = (tmp_path / "SHA256SUMS").read_text()
    assert "files/k1/SettlementReport.csv" in sums and "results.json" in sums
    assert "sig=x" not in (tmp_path / "results.json").read_text()  # 下载地址不落盘


def test_not_ready_and_pii_reports_are_not_written(tmp_path):
    action = {"op": "fetch", "key": "k1", "reportType": "SETTLEMENT", "requestId": "req-00000001"}
    (tmp_path / "a").mkdir()
    _c, doc = _run(tmp_path / "a", {"actions": [action]}, FakeWalmart(status="INPROGRESS"))
    assert doc["results"][0]["outcome"] == "not_ready"
    pii = _zip("r.csv", b"Customer Name,Net Payable\nSomeone,1\n")
    (tmp_path / "b").mkdir()
    _c, doc = _run(tmp_path / "b", {"actions": [action]}, FakeWalmart(file_bytes=pii))
    assert doc["results"][0]["outcome"] == "pii_blocked"
    assert not (tmp_path / "b" / "files" / "k1").exists()


def test_token_rejected_stops_the_run(tmp_path):
    code, doc = _run(
        tmp_path, {"actions": [submit(), submit("WFS_STORAGE_FEE")]}, FakeWalmart(), token="expired"
    )
    assert code == E.EXIT_TOKEN and doc["exit"] == E.EXIT_TOKEN


def test_request_ids_and_keys_are_validated(tmp_path):
    t = FakeWalmart()
    _code, doc = _run(
        tmp_path,
        {
            "actions": [
                {"op": "fetch", "key": "k1", "reportType": "SETTLEMENT", "requestId": "../../etc"},
                {
                    "op": "fetch",
                    "key": "../x",
                    "reportType": "SETTLEMENT",
                    "requestId": "req-00000001",
                },
                {"op": "rap", "key": "k3"},
            ]
        },
        t,
    )
    assert [r["outcome"] for r in doc["results"]] == [
        "refused_bad_request",
        "refused_bad_key",
        "refused_op_not_allowed",
    ]
    assert t.calls == []


def test_call_layer_refuses_paths_outside_the_whitelist(tmp_path):
    engine = E.Engine({"store_code": "HK0001"}, str(tmp_path), FakeWalmart(), "t")
    with pytest.raises(E.Refused):
        engine._call("POST", "/v3/price")
    with pytest.raises(E.Refused):
        engine._call("POST", "/v3/reports/downloadReport")
    with pytest.raises(E.Refused):
        engine._call("PUT", "/v3/reports/reportRequests")
    with pytest.raises(E.Refused):
        engine._call("GET", None, full_url="http://files.example.test/x")


def test_zip_members_with_the_same_name_are_not_overwritten():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a/report.csv", "x,y\n1,2\n")
        archive.writestr("b/report.csv", "x,y\n3,4\n")
    members = E.Engine._members(buffer.getvalue(), True)
    assert [name for name, _ in members] == ["report.csv", "report_2.csv"]
    assert [data for _, data in members] == [b"x,y\n1,2\n", b"x,y\n3,4\n"]


# ---------------------------------------------------------------- ZIP 解压上限（刘云龙 11-14）


def _zip_many(count, body=b"x,y\n1,2\n"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for i in range(count):
            archive.writestr(f"part{i}.csv", body)
    return buffer.getvalue()


def test_zip_limits_are_set():
    mb = 1024 * 1024
    assert E.MAX_ZIP_MEMBERS == 20 and E.MAX_ZIP_ENTRIES == 1000
    assert E.MAX_DOWNLOAD_BYTES == 64 * mb
    assert E.MAX_MEMBER_BYTES == 64 * mb
    assert E.MAX_UNZIPPED_BYTES == 128 * mb
    assert E.MAX_MEMBER_BYTES <= E.MAX_UNZIPPED_BYTES <= E.MAX_ZIP_MEMBERS * E.MAX_MEMBER_BYTES
    # 下载的和解压后的都在内存里：合计不超过 256MB（复核 P2-1）
    assert E.MAX_DOWNLOAD_BYTES + E.MAX_UNZIPPED_BYTES <= 256 * mb


def test_zip_with_too_many_entries_is_refused_even_if_they_are_not_csv(monkeypatch):
    monkeypatch.setattr(E, "MAX_ZIP_ENTRIES", 3)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("report.csv", "x,y\n1,2\n")
        for i in range(3):
            archive.writestr(f"junk{i}.txt", "")
    with pytest.raises(E.ZipTooLarge, match="too_many_members"):
        E.Engine._members(buffer.getvalue(), True)


def test_pii_scan_reads_rows_without_decoding_the_whole_file():
    clean = [("a.csv", "\ufeffTransaction Type,Net Payable\nSale,1.00\n".encode("utf-8"))]
    assert E.Engine._pii_scan(clean) == {}
    header_hit = [("b.csv", b"Customer Name,Net Payable\nSomeone,1\n")]
    assert E.Engine._pii_scan(header_hit)["b.csv"]["header_columns"] == ["Customer Name"]
    value_hit = [("c.csv", b"Note,Net Payable\nmail someone@example.test,1\n")]
    assert E.Engine._pii_scan(value_hit)["c.csv"]["value_columns"] == ["Note"]
    broken = [("d.csv", b"Transaction Type,Net Payable\nSale,\xff\xfe1\n")]
    assert E.Engine._pii_scan(broken) == {}  # 坏字节不让检查崩


def test_zip_with_too_many_members_is_refused(monkeypatch):
    monkeypatch.setattr(E, "MAX_ZIP_MEMBERS", 3)
    assert len(E.Engine._members(_zip_many(3), True)) == 3
    with pytest.raises(E.ZipTooLarge, match="too_many_members"):
        E.Engine._members(_zip_many(4), True)


def test_zip_member_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(E, "MAX_MEMBER_BYTES", 32)
    assert len(E.Engine._members(_zip_many(1, b"a" * 32), True)) == 1
    with pytest.raises(E.ZipTooLarge, match="member_too_large"):
        E.Engine._members(_zip_many(1, b"a" * 33), True)


def test_zip_total_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(E, "MAX_MEMBER_BYTES", 32)
    monkeypatch.setattr(E, "MAX_UNZIPPED_BYTES", 64)
    assert len(E.Engine._members(_zip_many(2, b"a" * 32), True)) == 2
    with pytest.raises(E.ZipTooLarge, match="total_too_large"):
        E.Engine._members(_zip_many(3, b"a" * 32), True)


def test_zip_header_lying_about_the_size_is_still_refused(monkeypatch):
    # 文件头说很小、实际解压很大：zipfile 按文件头截断后 CRC 对不上（bad_zip），
    # 没截断的话按实际大小再查一遍（zip_too_large）；两种结果都是拒绝，不落盘
    monkeypatch.setattr(E, "MAX_MEMBER_BYTES", 32)
    raw = _zip_many(1, b"a" * 100)
    real_infolist = zipfile.ZipFile.infolist

    def lying(self):
        infos = real_infolist(self)
        for info in infos:
            info.file_size = 1
        return infos

    monkeypatch.setattr(zipfile.ZipFile, "infolist", lying)
    with pytest.raises((E.ZipTooLarge, zipfile.BadZipFile)):
        E.Engine._members(raw, True)


def test_zip_header_lying_report_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "MAX_MEMBER_BYTES", 32)
    real_infolist = zipfile.ZipFile.infolist

    def lying(self):
        infos = real_infolist(self)
        for info in infos:
            info.file_size = 1
        return infos

    monkeypatch.setattr(zipfile.ZipFile, "infolist", lying)
    action = {"op": "fetch", "key": "k1", "reportType": "SETTLEMENT", "requestId": "req-00000001"}
    big = _zip_many(1, b"a" * 100)
    _c, doc = _run(tmp_path, {"actions": [action]}, FakeWalmart(file_bytes=big))
    assert doc["results"][0]["outcome"] in {"bad_zip", "zip_too_large"}
    assert list((tmp_path / "files").iterdir()) == []  # files/ 目录运行时就建好，里面不能有东西


def test_zip_member_bigger_than_its_header_is_refused_by_size(monkeypatch):
    # 直接验第二道保险：文件头通过、读出来超了 → member_too_large
    monkeypatch.setattr(E, "MAX_MEMBER_BYTES", 32)
    raw = _zip_many(1, b"a" * 32)
    real_open = zipfile.ZipFile.open

    class Bigger:
        def __init__(self, fh):
            self.fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.fh.close()

        def read(self, n=-1):
            return self.fh.read(n) + b"b"

    def bigger(self, *a, **k):
        return Bigger(real_open(self, *a, **k))

    monkeypatch.setattr(zipfile.ZipFile, "open", bigger)
    with pytest.raises(E.ZipTooLarge, match="member_too_large"):
        E.Engine._members(raw, True)


def test_oversized_zip_report_is_reported_and_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "MAX_ZIP_MEMBERS", 1)
    action = {"op": "fetch", "key": "k1", "reportType": "SETTLEMENT", "requestId": "req-00000001"}
    _c, doc = _run(tmp_path, {"actions": [action]}, FakeWalmart(file_bytes=_zip_many(2)))
    result = doc["results"][0]
    assert result["outcome"] == "zip_too_large" and result["zip_limit"] == "too_many_members"
    assert not (tmp_path / "files" / "k1").exists()
