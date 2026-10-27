"""Explicit, output-redacted server-side Walmart read-only preflight.

Do not pass Walmart credentials as CLI arguments. Main-server invocations use
short-lived Tencent identity and per-store SCF; SSM remains cloud-side.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.integrations.walmart.routed_scf import create_scoped_client
from app.integrations.walmart.tencent_api import TemporaryTencentIdentity, TencentApiClient
from app.integrations.walmart.unified_api import (
    WalmartReadAPI,
    capability_summary,
    load_unified_registry,
)


def _params(path: str | None) -> dict[str, Any]:
    if path is None:
        return {}
    file = Path(path)
    if not file.is_file() or file.stat().st_size > 16_384:
        raise ValueError("WALMART_PARAMS_FILE_INVALID")
    value = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WALMART_PARAMS_FILE_INVALID")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walmart read-only gateway preflight")
    parser.add_argument("--store", help="One store code; required for prepare/live")
    parser.add_argument("--operation", help="Reviewed operation key; required for prepare/live")
    parser.add_argument("--params-file", help="Local JSON file; values never printed")
    parser.add_argument("--live", action="store_true", help="Explicit opt-in to SCF invocation")
    args = parser.parse_args(argv)
    try:
        approved = frozenset(
            key.strip() for key in
            os.getenv("SZZSBJ_WALMART_APPROVED_READ_KEYS", "").split(",") if key.strip()
        )
        registry = load_unified_registry(
            approved,
            contract_file=os.getenv("SZZSBJ_WALMART_CONTRACT_FILE") or None,
            contract_sha256=os.getenv("SZZSBJ_WALMART_CONTRACT_SHA256") or None,
        )
        if not args.store and not args.operation and not args.live:
            print(json.dumps(capability_summary(registry), sort_keys=True))
            return 0
        if not args.store or not args.operation:
            raise ValueError("WALMART_PROBE_ARGUMENTS_REQUIRED")
        params = _params(args.params_file)
        if not args.live:
            from app.integrations.walmart.client import WalmartClient

            client = WalmartClient(
                registry,
                allowed_stores=frozenset({args.store}),
                configured_stores=frozenset({args.store}),
            )
            planned = WalmartReadAPI(client).prepare(
                args.store, args.operation, params=params
            )
            print(json.dumps({
                "mode": "offline", "status": "PREPARED_NO_NETWORK",
                "store": args.store, "operation": planned.key,
                "method": planned.method, "path": planned.path,
                "query_keys": sorted(planned.query),
            }, sort_keys=True))
            return 0
        if (
            os.getenv("SZZSBJ_WALMART_LIVE_MODE") != "owner-approved-read-only"
            or os.getenv("SZZSBJ_WALMART_ALLOW_PROBE") != "1"
            or os.getenv("SZZSBJ_WALMART_TEST_STORE") != args.store
        ):
            raise ValueError("WALMART_LIVE_PROBE_DISABLED")
        functions = json.loads(os.getenv("SZZSBJ_WALMART_SCF_FUNCTION_BY_STORE", "{}"))
        if not isinstance(functions, dict) or set(functions) != {args.store}:
            raise ValueError("WALMART_STORE_GATEWAY_UNAVAILABLE")
        client = create_scoped_client(
            registry,
            allowed_stores=frozenset({args.store}),
            function_by_store=functions,
            cloud_api=TencentApiClient(TemporaryTencentIdentity.from_environment()),
        )
        result = WalmartReadAPI(client).call(
            args.store, args.operation, params=params
        )
        # Deliberately never print response body, provider errors or credentials.
        print(json.dumps({
            "mode": "live", "status": "HTTP_SUCCESS",
            "operation": args.operation, "store": args.store,
            "http_status": result.status_code,
        }, sort_keys=True))
        return 0
    except Exception:
        print("WALMART_PROBE_REJECTED: check approvals, contracts and isolated gateway", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
