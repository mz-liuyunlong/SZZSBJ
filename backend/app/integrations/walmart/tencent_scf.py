"""Main-server SCF Invoke adapter.

Only Invoke is allowed; the main server has no SSM permissions and never
receives Walmart credentials. Cloud authorization still executes independently.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from app.integrations.walmart.tencent_api import TencentApiClient, TencentApiRejected


class ScfInvokeRejected(RuntimeError):
    """Stable status without cloud response contents."""


class TencentScfInvoker:
    def __init__(
        self,
        client: TencentApiClient,
        *,
        function_name: str,
        namespace: str = "default",
        qualifier: str = "stable",
    ) -> None:
        allowed = r"^[A-Za-z0-9_.-]{1,128}$"
        if not (
            re.fullmatch(allowed, function_name)
            and re.fullmatch(allowed, namespace)
            and re.fullmatch(allowed, qualifier)
        ):
            raise ScfInvokeRejected("SCF_TARGET_INVALID")
        self._client = client
        self._name = function_name
        self._namespace = namespace
        self._qualifier = qualifier

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            context = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            if len(context.encode()) > 65536:
                raise ScfInvokeRejected("SCF_INPUT_TOO_LARGE")
            response = self._client.request(
                "scf",
                {
                    "FunctionName": self._name,
                    "Namespace": self._namespace,
                    "Qualifier": self._qualifier,
                    "InvocationType": "RequestResponse",
                    "LogType": "None",
                    "ClientContext": context,
                },
            )
            result = response.get("Result")
            if not isinstance(result, dict) or result.get("InvokeResult") != 0:
                raise ScfInvokeRejected("SCF_INVOKE_FAILED")
            ret = result.get("RetMsg")
            if not isinstance(ret, str) or len(ret) > 1024 * 1024:
                raise ScfInvokeRejected("SCF_RESULT_INVALID")
            parsed = json.loads(ret)
            if not isinstance(parsed, dict):
                raise ScfInvokeRejected("SCF_RESULT_INVALID")
            return parsed
        except ScfInvokeRejected:
            raise
        except (TencentApiRejected, ValueError, TypeError):
            raise ScfInvokeRejected("SCF_INVOKE_UNAVAILABLE") from None
