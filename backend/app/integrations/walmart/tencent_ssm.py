"""Tencent SSM secret lookup, isolated to the cloud execution runtime.

Reads only owner-approved, store-scoped secret names. The result is never
serialized in SDK/SCF responses, task payloads, RAW, or application logs.
"""
from __future__ import annotations

import json
import re

from app.integrations.walmart.https_transport import ClientCredentials
from app.integrations.walmart.tencent_api import TencentApiClient, TencentApiRejected

_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class SsmRejected(RuntimeError):
    """Non-secret error code."""


class TencentSsmResolver:
    def __init__(
        self,
        client: TencentApiClient,
        *,
        approved_stores: frozenset[str],
        version: str,
    ) -> None:
        if not _VERSION.fullmatch(version):
            raise SsmRejected("SSM_VERSION_INVALID")
        self._client = client
        self._stores = approved_stores
        self._version = version

    def get_store_credentials(self, store_code: str) -> ClientCredentials:
        if store_code not in self._stores:
            raise SsmRejected("SSM_STORE_FORBIDDEN")
        if not re.fullmatch(r"(?:HK|CN)[0-9]{4}", store_code):
            raise SsmRejected("SSM_STORE_INVALID")
        try:
            result = self._client.request(
                "ssm",
                {"SecretName": "walmart-" + store_code, "VersionId": self._version},
            )
            raw = result.get("SecretString")
            if not isinstance(raw, str) or len(raw) > 16384:
                raise SsmRejected("SSM_VALUE_UNAVAILABLE")
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise SsmRejected("SSM_SCHEMA_INVALID")
            client_id = record.get("WALMART_CLIENT_ID")
            client_secret = record.get("WALMART_CLIENT_SECRET")
            market = record.get("WALMART_MARKET")
            if (
                not isinstance(client_id, str)
                or not isinstance(client_secret, str)
                or not client_id.strip()
                or not client_secret.strip()
                or str(market).upper() != "US"
            ):
                raise SsmRejected("SSM_SCHEMA_INVALID")
            return ClientCredentials(client_id.strip(), client_secret.strip())
        except SsmRejected:
            raise
        except (TencentApiRejected, ValueError, TypeError):
            raise SsmRejected("SSM_READ_FAILED") from None
