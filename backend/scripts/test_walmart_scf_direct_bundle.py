"""Verify the *built ZIP*, isolated from repo packages, using Python 3.10.

No credentials, cloud accounts, network requests or production writes are used.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import zipfile

SMOKE = r"""
import json
import os
import time
from uuid import uuid4

import httpx

from index import main_handler
from app.integrations.walmart import scf_runtime
from app.integrations.walmart.contract_signing import ContractSigner, risk_for
from app.integrations.walmart.contracts import ContractRegistry
from app.integrations.walmart.wfs_catalog import wfs_registry

STORE = "HK2613"
FUNCTION = "szzsbj-walmart-hk2613-executor"
os.environ.update({
    "SZZSBJ_WALMART_BOUND_STORE": STORE,
    "SZZSBJ_WALMART_FUNCTION_NAME": FUNCTION,
    "SZZSBJ_WALMART_LIVE_MODE": "owner-approved-read-only",
    "SZZSBJ_WALMART_APPROVED_READ_KEYS": "wfs_inventory",
    "SZZSBJ_WALMART_EGRESS_MODE": "direct-public-readonly",
    "SZZSBJ_WALMART_DIRECT_PUBLIC_APPROVED": "1",
    "SZZSBJ_WALMART_MAX_RISK": "read",
    "SZZSBJ_WALMART_SECRET_VERSION": "v1",
})
assert main_handler({"operation": "health"}, None)["success"] is True

class FakeTencentApi:
    def __init__(self, identity):
        pass
    def request(self, service, payload):
        assert service == "ssm"
        assert payload["SecretName"] == "walmart-" + STORE
        return {"SecretString": json.dumps({
            "WALMART_CLIENT_ID": "test-only",
            "WALMART_CLIENT_SECRET": "test-only",
            "WALMART_MARKET": "US"
        })}

scf_runtime.TencentApiClient = FakeTencentApi
scf_runtime.TemporaryTencentIdentity.from_environment = classmethod(lambda cls: object())

requests = []
original_client = httpx.Client
def fake_http(request):
    requests.append((request.method, request.url.host, request.url.path))
    assert request.url.host == "marketplace.walmartapis.com"
    if request.url.path == "/v3/token":
        return httpx.Response(200, json={"access_token": "test-token"})
    assert request.method == "GET"
    return httpx.Response(200, json={"items": [{"test": True}]})
def fake_client(**kwargs):
    assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
    assert "proxy" not in kwargs
    return original_client(transport=httpx.MockTransport(fake_http), **kwargs)
httpx.Client = fake_client

# Original v1 inventory contract is still allowed by its original allowlist.
v1 = {
    "version": 1, "operation": "marketplace_call", "store_code": STORE,
    "api_key": "wfs_inventory", "method": "GET", "path": "/v3/wfs/inventory",
    "query": {"limit": 1}, "body": None, "approval_ref": None,
}
assert main_handler(v1, None)["success"] is True
v1_bad = dict(v1, api_key="inbound_shipments")
assert main_handler(v1_bad, None)["success"] is False  # v1 keeps its own allowlist
assert len(requests) == 2

# Signed v3 calls all four reviewed read contracts without cloud allowlist changes.
keys = frozenset({"wfs_inventory", "inbound_shipments", "inbound_shipment_items", "inventory_log"})
registry = wfs_registry(approved_keys=keys)
signer = ContractSigner.generate(kid="scf-smoke", registry=registry)
os.environ["SZZSBJ_WALMART_CONTRACT_PUBLIC_KEYS"] = json.dumps({
    signer.kid: signer.public_key_b64()
})

def event_for(key, params):
    req = registry.prepare(key, params=params, allow_writes=True)
    auth = signer.sign(
        store_code=STORE, function_name=FUNCTION, contract=req.contract,
        method=req.method, path=req.path, params=req.params or {},
        body=req.body, response_kind=req.response_kind,
        actor={"kind": "system", "uid": "scf-ci"},
        approval_ref=None, ttl_seconds=120,
        issued_at=int(time.time()), request_id=uuid4().hex,
    )
    return {
        "version": 3, "operation": "marketplace_call", "store_code": STORE,
        "function_name": FUNCTION, "contract": dict(req.contract),
        "method": req.method, "path": req.path, "params": dict(req.params or {}),
        "body": req.body, "accept": req.response_kind,
        "risk": risk_for(req.method, key), "approval_ref": None,
        "actor": {"kind": "system", "uid": "scf-ci"}, "auth": auth,
    }

samples = {
    "wfs_inventory": {"limit": 1},
    "inbound_shipments": {"fromCreatedDate": 1761000000, "toCreatedDate": 1762000000},
    "inbound_shipment_items": {"shipmentId": "sample-shipment"},
    "inventory_log": {"gtin": "12345678901234", "fromDate": "2026-10-01", "toDate": "2026-10-31"},
}
for key, params in samples.items():
    signed = event_for(key, params)
    result = main_handler(signed, None)
    assert result.get("success") is True, (key, result)
    assert result["protocol"] == 3
    assert result["api_key"] == key
    assert main_handler(signed, None)["status"] == "WALMART_SIGNATURE_REPLAYED"
    modified = dict(signed, store_code="CN2603")
    assert main_handler(modified, None)["success"] is False

# A write-shaped signed request cannot be executed in read-only direct mode.
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS, wfs_write_registry
for op in wfs_write_registry(approved_keys=WFS_WRITE_KEYS).values():
    if op.method == "GET":
        continue
    assert scf_runtime._max_risk_from_env(False) == "read"
    break
assert len([p for p in requests if p[0] == "GET"]) == 5  # v1 + four v3
print("SCF_PY310_ZIP_SMOKE_OK: v1 + v3 four reads, signature replay/store checks, no writes")
'''

def main() -> None:
    if sys.version_info[:2] != (3, 10):
        raise SystemExit("SCF_TEST_PYTHON310_REQUIRED")
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_walmart_scf_direct_bundle.py <zip>")
    archive = pathlib.Path(sys.argv[1]).resolve()
    if not archive.is_file():
        raise SystemExit("SCF_ZIP_NOT_FOUND")
    with tempfile.TemporaryDirectory(prefix="szzsbj-scf-py310-") as temp:
        work = pathlib.Path(temp)
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)) or any(
                pathlib.PurePosixPath(name).is_absolute()
                or ".." in pathlib.PurePosixPath(name).parts
                for name in names
            ):
                raise SystemExit("SCF_ZIP_UNSAFE")
            if "index.py" not in names or "app/integrations/walmart/scf_runtime.py" not in names:
                raise SystemExit("SCF_ENTRYPOINT_MISSING")
            bundle.extractall(work)
        # Isolated mode prevents an accidentally installed backend app from hiding
        # missing modules in this zip. It also disables user site packages and PYTHONPATH.
        bootstrap = "import sys; sys.path.insert(0, " + repr(str(work)) + ");\n" + SMOKE
        subprocess.run([sys.executable, "-I", "-c", bootstrap], cwd=work, check=True, timeout=90)


if __name__ == "__main__":
    main()
