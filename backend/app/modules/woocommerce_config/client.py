from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit

_API_PATH = "/wp-json/wc/v3/products?per_page=1&_fields=id"
_MAX_RESPONSE_BYTES = 65536
_TIMEOUT_SECONDS = 6
_MAX_ADDRESSES = 2


class ProbeFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned_ip: str) -> None:
        super().__init__(
            host=host,
            port=443,
            timeout=_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _resolve_public_ips(host: str) -> list[str]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ProbeFailure("WOO_DNS_FAILED") from None

    addresses: list[str] = []
    for record in records:
        raw_ip = str(record[4][0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_ip)
        except ValueError:
            raise ProbeFailure("WOO_DNS_INVALID") from None
        if not address.is_global:
            raise ProbeFailure("WOO_HOST_NOT_PUBLIC")
        normalized = str(address)
        if normalized not in addresses:
            addresses.append(normalized)

    if not addresses:
        raise ProbeFailure("WOO_DNS_FAILED")
    return addresses


def _request_one(host: str, pinned_ip: str, authorization: str) -> tuple[int, bytes]:
    connection = _PinnedHTTPSConnection(host, pinned_ip)
    try:
        connection.request(
            "GET",
            _API_PATH,
            headers={
                "Authorization": authorization,
                "Accept": "application/json",
                "User-Agent": "SZZSBJ-WooCommerce-Connector/1.0",
            },
        )
        response = connection.getresponse()
        body = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ProbeFailure("WOO_RESPONSE_TOO_LARGE")
        return response.status, body
    finally:
        connection.close()


def _status_code(status: int) -> str:
    if 300 <= status < 400:
        return "WOO_REDIRECT_BLOCKED"
    if status == 401:
        return "WOO_AUTH_FAILED"
    if status == 403:
        return "WOO_PERMISSION_DENIED"
    if status == 404:
        return "WOO_API_NOT_FOUND"
    if status == 429:
        return "WOO_RATE_LIMITED"
    if status >= 500:
        return "WOO_UPSTREAM_ERROR"
    return "WOO_HTTP_ERROR"


def probe_connection(store_url: str, consumer_key: str, consumer_secret: str) -> str:
    host = urlsplit(store_url).hostname
    if not host:
        return "WOO_STORE_URL_INVALID"

    try:
        addresses = _resolve_public_ips(host)
    except ProbeFailure as exc:
        return exc.code

    credential = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode("ascii")
    authorization = f"Basic {credential}"

    for address in addresses[:_MAX_ADDRESSES]:
        try:
            status, body = _request_one(host, address, authorization)
        except ProbeFailure as exc:
            return exc.code
        except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException):
            continue

        if status != 200:
            return _status_code(status)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "WOO_RESPONSE_INVALID"
        if not isinstance(payload, list):
            return "WOO_RESPONSE_INVALID"
        if any(not isinstance(item, dict) or "id" not in item for item in payload):
            return "WOO_RESPONSE_INVALID"
        return "OK"

    return "WOO_CONNECTION_FAILED"
