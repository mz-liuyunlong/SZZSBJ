#!/usr/bin/env python3
"""WFS 费用报表远端执行器（店铺路由服务器上运行；生产服务器每次上传、核对 sha256、跑完删除）。

从 features/tools/walmart_remote_pull/reports/wfs_reports_engine_v7.py（2026-10 实拉验证过）
抽出，只保留财务 WFS 费用明细要用的 4 个动作，其余功能一律不带
（Rocky 2026-11-13 批准的白名单）：

  list    GET  /v3/reports/reportRequests?reportType=…    查近 30 天已有请求（复用，少占下单额度）
  submit  POST /v3/reports/reportRequests?reportType=&reportVersion=
               下单做报表（只建报表请求，不改任何店铺数据）
  fetch   GET  /v3/reports/reportRequests/{requestId}             查状态；READY 时
          GET  /v3/reports/downloadReport?requestId=              取预签名下载地址，再
          GET  <https 下载地址>     下载（不带沃尔玛鉴权头；地址不落盘，只记主机名）

白名单写死：报表类型只有 SETTLEMENT、WFS_STORAGE_FEE；HTTP 方法只有 GET、POST；
POST 只发往
/v3/reports/reportRequests。
测试（tests/integrations/walmart/test_wfs_report_engine.py）锁住这些常量和
文件里出现的全部接口路径，要加别的类型或接口必须改代码、走审核、Rocky 批准。

额度：同一店同一报表类型每小时只能下单 1 次（格式错误的下单也扣额度）
→ 每次运行每类型最多 1 次 POST；
近 30 天有同类型、同日期范围、未失败的请求直接复用，不再下单。日期必须 YYYY-MM-DDTHH:MM:SS.000Z。

令牌只从标准输入第一行读（--token-stdin），不进命令行 / 日志 / 文件；401 直接停（不刷新）。
个人信息：下载后先在内存里检查表头和内容，疑似个人信息 → 不落盘，记 pii_blocked。
兼容 Python 3.6（有的店铺服务器是 3.6.8，f-string 可用），只用标准库。

用法：python3 wfs_report_engine.py --plan plan.json --out <目录> --token-stdin
plan.json：{"store_code": "…", "max_posts": 2,
            "actions": [{"op": "submit", "key": "…", "reportType": "SETTLEMENT",
                          "dataStartTime": "…000Z", "dataEndTime": "…000Z", "post_allowed": true},
                         {"op": "fetch", "key": "…", "reportType": "…", "requestId": "…"}]}
输出：<out>/results.json、<out>/files/<key>/<文件>、<out>/SHA256SUMS
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

ENGINE_VERSION = "wfs-fees-1.0.0"
BASE = "https://marketplace.walmartapis.com"
SVC_NAME = "Walmart Marketplace"
TIMEOUT = 120
MIN_INTERVAL = 1.25
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
MAX_ACTIONS = 20

# ---- 白名单（测试锁住，改动要 Rocky 批准）
REPORT_TYPES = {"SETTLEMENT": "v1", "WFS_STORAGE_FEE": "v1"}
ALLOWED_METHODS = ("GET", "POST")
REPORTS_PATH = "/v3/reports/reportRequests"
DOWNLOAD_PATH = "/v3/reports/downloadReport"
POST_PATHS = (REPORTS_PATH,)

WFS_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.000Z$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,80}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
STORE_RE = re.compile(r"^(HK|CN)[0-9]{4}$")
EMAIL_VALUE_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_VALUE_RE = re.compile(r"^(\+?1[ .-])?(\(\d{3}\) ?|\d{3}[ -])\d{3}[ -]\d{4}$")
PII_HEADER_RE = re.compile(
    r"(customer|buyer|recipient|shipping|ship to|consumer|shopper)[ _]*"
    r"(name|email|phone|address|city|zip|postal)"
    r"|^name$|first ?name|last ?name|full ?name|e-?mail|phone|street|address|postal|zip ?code",
    re.I,
)
KEEP_RESP_HEADERS = ("wm_qos.correlation_id", "x-current-token-count", "x-next-replenishment-time")
EXIT_OK, EXIT_PARTIAL, EXIT_SAFETY, EXIT_TOKEN = 0, 1, 2, 4


class TokenRejected(Exception):
    pass


class Refused(Exception):
    pass


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class RealTransport:
    name = "real"

    def send(self, method, url, headers, data):
        if method not in ALLOWED_METHODS:
            raise Refused("method_not_allowed")
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            try:
                return resp.status, dict(resp.headers), resp.read(MAX_DOWNLOAD_BYTES + 1)
            finally:
                resp.close()
        except urllib.error.HTTPError as e:
            try:
                raw = e.read()
            except Exception:  # noqa
                raw = b""
            return e.code, dict(e.headers or {}), raw
        except Exception as e:  # noqa  URLError / timeout / ssl
            return None, {}, f"transport_error:{e.__class__.__name__}".encode()


class Engine:
    def __init__(self, plan, out_dir, transport, token, interval=MIN_INTERVAL):
        self.plan = plan
        self.out = out_dir
        self.t = transport
        self.token = token
        self.interval = interval
        self.last = 0.0
        self.results = []
        self.listed = {}
        self.posted_types = set()
        self.counts = {"list": 0, "submit_post": 0, "status": 0, "download_url": 0, "file_get": 0}
        if not os.path.isdir(os.path.join(out_dir, "files")):
            os.makedirs(os.path.join(out_dir, "files"))

    def _pace(self):
        if self.t.name == "mock":
            return
        wait = self.interval - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)

    def _call(self, method, path, query=None, body=None, full_url=None):
        """全部 HTTP 都从这里出：方法、路径、POST 目标都按白名单再查一遍。"""
        if method not in ALLOWED_METHODS:
            raise Refused("method_not_allowed")
        if full_url is None:
            allowed = path in (REPORTS_PATH, DOWNLOAD_PATH) or (
                path.startswith(REPORTS_PATH + "/")
                and REQUEST_ID_RE.match(path[len(REPORTS_PATH) + 1 :])
            )
            if not allowed or (method == "POST" and path not in POST_PATHS):
                raise Refused("path_not_allowed")
        elif method != "GET" or urllib.parse.urlsplit(full_url).scheme != "https":
            raise Refused("download_not_allowed")
        self._pace()
        if full_url:
            url = full_url
            headers = {"Accept": "*/*"}
        else:
            url = BASE + path + ("?" + urllib.parse.urlencode(query) if query else "")
            headers = {
                "Accept": "application/json",
                "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
                "WM_SVC.NAME": SVC_NAME,
                "WM_SEC.ACCESS_TOKEN": self.token,
            }
        data = None
        if method == "POST":
            data = json.dumps(body if body is not None else {}).encode()
            headers["Content-Type"] = "application/json"
        status, rh, raw = self.t.send(method, url, headers, data)
        self.last = time.time()
        keep = {}
        for k, v in (rh or {}).items():
            if k.lower() in KEEP_RESP_HEADERS:
                keep[k.lower()] = str(v)
        parsed = None
        if raw and not full_url:
            try:
                parsed = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                parsed = None
        if status == 401 and not full_url:
            raise TokenRejected()
        return status, keep, raw, parsed

    # ---------------------------------------------------------------- 动作
    def op_list(self, report_type):
        if report_type in self.listed:
            return
        st, _rh, _raw, p = self._call("GET", REPORTS_PATH, {"reportType": report_type})
        self.counts["list"] += 1
        self.listed[report_type] = ((p or {}).get("requests") or []) if st == 200 else []

    def _reusable(self, report_type, start, end):
        for r in self.listed.get(report_type) or []:
            pl = r.get("payload") or {}
            if (
                pl.get("dataStartTime") == start
                and pl.get("dataEndTime") == end
                and r.get("requestStatus") in ("RECEIVED", "INPROGRESS", "READY")
            ):
                return r
        return None

    def op_submit(self, a):
        rt, key = a.get("reportType"), a.get("key")
        version = REPORT_TYPES.get(rt)
        if not version:
            self.results.append({"op": "submit", "key": key, "outcome": "refused_type_not_allowed"})
            return
        start, end = a.get("dataStartTime", ""), a.get("dataEndTime", "")
        if not (WFS_DATE_RE.match(start or "") and WFS_DATE_RE.match(end or "")):
            self.results.append({"op": "submit", "key": key, "outcome": "refused_bad_date_format"})
            return
        self.op_list(rt)
        reused = self._reusable(rt, start, end)
        if reused:
            self.results.append(
                {
                    "op": "submit",
                    "key": key,
                    "outcome": "reused",
                    "requestId": reused.get("requestId"),
                    "requestStatus": reused.get("requestStatus"),
                }
            )
            return
        if not a.get("post_allowed", False):
            self.results.append({"op": "submit", "key": key, "outcome": "deferred_rate_window"})
            return
        if rt in self.posted_types:
            self.results.append(
                {"op": "submit", "key": key, "outcome": "deferred_one_post_per_type_per_run"}
            )
            return
        if self.counts["submit_post"] >= int(self.plan.get("max_posts", 0)):
            self.results.append({"op": "submit", "key": key, "outcome": "deferred_post_budget"})
            return
        self.posted_types.add(rt)
        st, rh, _raw, p = self._call(
            "POST",
            REPORTS_PATH,
            {"reportType": rt, "reportVersion": version},
            {"dataStartTime": start, "dataEndTime": end},
        )
        self.counts["submit_post"] += 1
        res = {"op": "submit", "key": key, "http": st, "submitted_at": now_iso()}
        if st == 200 and p and p.get("requestId"):
            res.update(
                outcome="submitted",
                requestId=p.get("requestId"),
                requestStatus=p.get("requestStatus"),
            )
        elif st == 429:
            res.update(
                outcome="rate_limited", next_replenishment=rh.get("x-next-replenishment-time", "")
            )
        else:
            res.update(outcome="submit_failed")
        self.results.append(res)

    def op_fetch(self, a):
        key, rid, rt = a.get("key"), a.get("requestId") or "", a.get("reportType")
        if rt not in REPORT_TYPES or not REQUEST_ID_RE.match(rid):
            self.results.append({"op": "fetch", "key": key, "outcome": "refused_bad_request"})
            return
        st, _rh, _raw, p = self._call("GET", REPORTS_PATH + "/" + rid)
        self.counts["status"] += 1
        state = (p or {}).get("requestStatus") if st == 200 else None
        res = {"op": "fetch", "key": key, "requestId": rid, "http": st, "requestStatus": state}
        if state != "READY":
            res["outcome"] = (
                "error_state"
                if state == "ERROR"
                else ("not_ready" if st == 200 else "status_failed")
            )
            self.results.append(res)
            return
        st2, _rh2, _raw2, p2 = self._call("GET", DOWNLOAD_PATH, {"requestId": rid})
        self.counts["download_url"] += 1
        url = (p2 or {}).get("downloadURL") if st2 == 200 else None
        if not url or urllib.parse.urlsplit(url).scheme != "https":
            res.update(outcome="download_url_failed")
            self.results.append(res)
            return
        st3, _rh3, raw3, _ = self._call("GET", None, full_url=url)
        self.counts["file_get"] += 1
        res["download_host"] = urllib.parse.urlsplit(url).hostname
        if st3 != 200 or not raw3:
            res.update(outcome="file_get_failed", http_file=st3)
            self.results.append(res)
            return
        if len(raw3) > MAX_DOWNLOAD_BYTES:
            res.update(outcome="file_too_large")
            self.results.append(res)
            return
        is_zip = raw3[:2] == b"PK"
        try:
            members = self._members(raw3, is_zip)
        except zipfile.BadZipFile:
            res.update(outcome="bad_zip")
            self.results.append(res)
            return
        pii = self._pii_scan(members)
        if pii:
            res.update(outcome="pii_blocked", pii=pii)
            self.results.append(res)
            return
        d = os.path.join(self.out, "files", key)
        if not os.path.isdir(d):
            os.makedirs(d)
        names = []
        for base, data in members:
            with open(os.path.join(d, base), "wb") as f:
                f.write(data)
            names.append({"name": base, "bytes": len(data), "sha256": sha256_bytes(data)})
        res.update(outcome="downloaded", files=names)
        self.results.append(res)

    @staticmethod
    def _members(raw, is_zip):
        if not is_zip:
            return [("report.csv", raw)]
        z = zipfile.ZipFile(io.BytesIO(raw))
        out = []
        for n in z.namelist():
            base = os.path.basename(n)
            if n.endswith("/") or not base or base.startswith(".") or n.startswith("__MACOSX/"):
                continue
            if not base.lower().endswith(".csv"):
                continue
            out.append((re.sub(r"[^A-Za-z0-9_.-]", "_", base), z.read(n)))
        return out

    @staticmethod
    def _pii_scan(members):
        """内存检查：表头像个人信息列，或内容出现邮箱 / 带分隔符的电话。

        返回命中的列名（不含值）。
        """
        hits = {}
        for base, data in members:
            rdr = csv.reader(io.StringIO(data.decode("utf-8-sig", "replace"), newline=""))
            header = next(rdr, [])
            cols = [h for h in header if PII_HEADER_RE.search(h or "")]
            vals = set()
            for i, row in enumerate(rdr):
                for j, c in enumerate(row):
                    c = c.strip()
                    if c and (EMAIL_VALUE_RE.search(c) or PHONE_VALUE_RE.match(c)):
                        vals.add(header[j] if j < len(header) else f"col{j}")
                if i > 200000:
                    break
            if cols or vals:
                hits[base] = {"header_columns": cols, "value_columns": sorted(vals)}
        return hits

    def run(self):
        actions = self.plan.get("actions") or []
        if len(actions) > MAX_ACTIONS:
            raise Refused("too_many_actions")
        code = EXIT_OK
        try:
            for a in actions:
                if not KEY_RE.match(str(a.get("key") or "")):
                    self.results.append({"op": a.get("op"), "outcome": "refused_bad_key"})
                    continue
                if a.get("op") == "submit":
                    self.op_submit(a)
                elif a.get("op") == "fetch":
                    self.op_fetch(a)
                else:
                    self.results.append(
                        {
                            "op": a.get("op"),
                            "key": a.get("key"),
                            "outcome": "refused_op_not_allowed",
                        }
                    )
        except TokenRejected:
            code = EXIT_TOKEN
        return self.finish(code)

    def finish(self, code):
        doc = {
            "engine": ENGINE_VERSION,
            "store_code": self.plan.get("store_code"),
            "finished_at": now_iso(),
            "exit": code,
            "counts": self.counts,
            "results": self.results,
        }
        with open(os.path.join(self.out, "results.json"), "w") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=True)
        lines = []
        for root, _dirs, files in os.walk(self.out):
            for name in sorted(files):
                if name == "SHA256SUMS":
                    continue
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    digest = sha256_bytes(f.read())
                lines.append(f"{digest}  {os.path.relpath(path, self.out)}")
        with open(os.path.join(self.out, "SHA256SUMS"), "w") as f:
            f.write("\n".join(sorted(lines)) + "\n")
        return code


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--token-stdin", action="store_true", required=True)
    args = parser.parse_args(argv)
    with open(args.plan) as f:
        plan = json.load(f)
    if not STORE_RE.match(str(plan.get("store_code") or "")):
        return EXIT_SAFETY
    token = sys.stdin.readline().strip()
    if not token or len(token) > 8192:
        return EXIT_TOKEN
    try:
        return Engine(plan, args.out, RealTransport(), token).run()
    except Refused:
        return EXIT_SAFETY


if __name__ == "__main__":
    sys.exit(main())
