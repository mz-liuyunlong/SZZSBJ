from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

ALLOWED_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)


class MediaDownloadError(RuntimeError):
    """Safe external-image error carrying only a stable code."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class DownloadedImage:
    data: bytes
    mime_type: str


def resolve_host_addresses(host: str) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise MediaDownloadError("SOURCE_DNS_FAILED", retryable=True) from None
    addresses_list: list[str] = []
    for record in records:
        address = record[4][0]
        if isinstance(address, str) and address not in addresses_list:
            addresses_list.append(address)

    addresses = tuple(addresses_list)
    if not addresses:
        raise MediaDownloadError("SOURCE_DNS_FAILED", retryable=True)
    return addresses


def validate_source_url(
    source_url: str,
    allowed_hosts: frozenset[str],
    *,
    resolver: Callable[[str], Sequence[str]] = resolve_host_addresses,
) -> str:
    try:
        parsed = urlsplit(source_url)
        port = parsed.port
    except ValueError:
        raise MediaDownloadError("SOURCE_URL_INVALID", retryable=False) from None

    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not host
        or not host.isascii()
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or host not in allowed_hosts
    ):
        raise MediaDownloadError("SOURCE_URL_NOT_ALLOWED", retryable=False)

    addresses = resolver(host)
    for raw_address in addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            raise MediaDownloadError("SOURCE_DNS_INVALID", retryable=False) from None
        if not address.is_global:
            raise MediaDownloadError("SOURCE_HOST_NOT_PUBLIC", retryable=False)
    return host


class MediaSourceDownloader:
    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        timeout_ms: int,
        max_source_bytes: int,
        transport: httpx.BaseTransport | None = None,
        resolver: Callable[[str], Sequence[str]] = resolve_host_addresses,
    ) -> None:
        self.allowed_hosts = allowed_hosts
        self.timeout_seconds = timeout_ms / 1000
        self.max_source_bytes = max_source_bytes
        self.transport = transport
        self.resolver = resolver

    def download(self, source_url: str) -> DownloadedImage:
        validate_source_url(
            source_url,
            self.allowed_hosts,
            resolver=self.resolver,
        )
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
                headers={
                    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                    "User-Agent": "SZZSBJ-MediaCache/1.0",
                },
            ) as client:
                with client.stream("GET", source_url) as response:
                    self._validate_response(response)
                    content_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_source_bytes:
                            raise MediaDownloadError(
                                "SOURCE_TOO_LARGE",
                                retryable=False,
                            )
                        chunks.append(chunk)
        except MediaDownloadError:
            raise
        except httpx.TimeoutException:
            raise MediaDownloadError("SOURCE_TIMEOUT", retryable=True) from None
        except httpx.TransportError:
            raise MediaDownloadError("SOURCE_NETWORK_ERROR", retryable=True) from None

        data = b"".join(chunks)
        if not data:
            raise MediaDownloadError("SOURCE_EMPTY", retryable=False)
        return DownloadedImage(data=data, mime_type=content_type)

    def _validate_response(self, response: httpx.Response) -> None:
        if response.status_code in {301, 302, 303, 307, 308}:
            raise MediaDownloadError("SOURCE_REDIRECT_NOT_ALLOWED", retryable=False)
        if response.status_code == 403:
            raise MediaDownloadError("SOURCE_FORBIDDEN", retryable=False)
        if response.status_code == 404:
            raise MediaDownloadError("SOURCE_NOT_FOUND", retryable=False)
        if response.status_code == 429:
            raise MediaDownloadError("SOURCE_RATE_LIMITED", retryable=True)
        if 500 <= response.status_code <= 599:
            raise MediaDownloadError("SOURCE_UNAVAILABLE", retryable=True)
        if response.status_code < 200 or response.status_code >= 300:
            raise MediaDownloadError("SOURCE_HTTP_ERROR", retryable=False)

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise MediaDownloadError("SOURCE_CONTENT_TYPE_UNSUPPORTED", retryable=False)

        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                raise MediaDownloadError("SOURCE_CONTENT_LENGTH_INVALID", retryable=False) from None
            if declared_size < 0 or declared_size > self.max_source_bytes:
                raise MediaDownloadError("SOURCE_TOO_LARGE", retryable=False)
