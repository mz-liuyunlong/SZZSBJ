from __future__ import annotations

import socket

import pytest

from app.modules.woocommerce_config import client


def test_probe_accepts_a_minimal_products_list_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_resolve_public_ips", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(client, "_request_one", lambda *_args: (200, b'[{"id": 123}]'))

    assert (
        client.probe_connection("https://store.example.com", "ck_synthetic", "cs_synthetic") == "OK"
    )


def test_probe_reports_connection_failure_when_all_addresses_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "_resolve_public_ips", lambda _host: ["93.184.216.34"])

    def fail(*_args: str) -> tuple[int, bytes]:
        raise OSError("synthetic failure")

    monkeypatch.setattr(client, "_request_one", fail)
    assert (
        client.probe_connection("https://store.example.com", "ck_synthetic", "cs_synthetic")
        == "WOO_CONNECTION_FAILED"
    )


def test_probe_accepts_an_empty_products_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_resolve_public_ips", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(client, "_request_one", lambda *_args: (200, b"[]"))

    assert (
        client.probe_connection("https://store.example.com", "ck_synthetic", "cs_synthetic") == "OK"
    )


def test_probe_blocks_private_dns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )

    assert (
        client.probe_connection("https://store.example.com", "ck_synthetic", "cs_synthetic")
        == "WOO_HOST_NOT_PUBLIC"
    )


def test_probe_maps_authentication_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_resolve_public_ips", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(client, "_request_one", lambda *_args: (401, b""))

    assert (
        client.probe_connection("https://store.example.com", "ck_synthetic", "cs_synthetic")
        == "WOO_AUTH_FAILED"
    )


def test_probe_never_follows_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_resolve_public_ips", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(client, "_request_one", lambda *_args: (302, b""))

    assert (
        client.probe_connection("https://store.example.com", "ck_synthetic", "cs_synthetic")
        == "WOO_REDIRECT_BLOCKED"
    )


def test_probe_rejects_non_products_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_resolve_public_ips", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(
        client,
        "_request_one",
        lambda *_args: (200, b'{"code":"woocommerce_rest_cannot_view"}'),
    )

    assert (
        client.probe_connection("https://store.example.com", "ck_synthetic", "cs_synthetic")
        == "WOO_RESPONSE_INVALID"
    )


def test_probe_does_not_include_credentials_in_failure_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "_resolve_public_ips", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(client, "_request_one", lambda *_args: (403, b"sensitive provider body"))

    result = client.probe_connection(
        "https://store.example.com", "ck_secret_value", "cs_secret_value"
    )
    assert result == "WOO_PERMISSION_DENIED"
    assert "secret_value" not in result
