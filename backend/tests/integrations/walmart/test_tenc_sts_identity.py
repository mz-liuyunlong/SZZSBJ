"""Cross-account STS provider tests: mock HTTP, no network or secrets."""

from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.walmart.tenc_sts_identity import (
    CachedScfAssumeRoleIdentity,
    TencentStsIdentityError,
)

ROLE = "qcs::cam::uin/100013426561:roleName/SZZSBJ-CrossAccount-SCF-Invoker"


class Clock:
    now = 1800000000

    def __call__(self) -> float:
        return float(self.now)


def test_assume_role_is_cached_and_refreshed_before_expiry() -> None:
    clock = Clock()
    calls = {"cvm": 0, "sts": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "metadata.tencentyun.com":
            calls["cvm"] += 1
            assert request.method == "GET"
            assert request.url.path.endswith("/SZZSBJ-CVM-SCF-Invoker")
            return httpx.Response(
                200,
                json={
                    "Code": "Success",
                    "TmpSecretId": "fake-cvm-id",
                    "TmpSecretKey": "fake-cvm-key",
                    "Token": "fake-cvm-token",
                    "ExpiredTime": clock.now + 1800,
                },
            )
        assert request.url.host == "sts.tencentcloudapi.com"
        assert request.method == "POST"
        assert request.headers["X-TC-Action"] == "AssumeRole"
        assert request.headers["X-TC-Token"] == "fake-cvm-token"
        assert json.loads(request.content)["RoleArn"] == ROLE
        calls["sts"] += 1
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Credentials": {
                        "TmpSecretId": "fake-b-id",
                        "TmpSecretKey": "fake-b-key",
                        "Token": "fake-b-token",
                    },
                    "ExpiredTime": clock.now + 1800,
                }
            },
        )

    provider = CachedScfAssumeRoleIdentity(
        cvm_role="SZZSBJ-CVM-SCF-Invoker",
        target_role_arn=ROLE,
        transport=httpx.MockTransport(respond),
        clock=clock,
    )
    first = provider.get_identity()
    assert "fake-b-key" not in repr(first)
    clock.now += 1499
    assert provider.get_identity() is first
    assert calls == {"cvm": 1, "sts": 1}
    clock.now += 2
    assert provider.get_identity() is not first
    assert calls == {"cvm": 2, "sts": 2}


def test_failed_sts_never_exposes_upstream_error() -> None:
    clock = Clock()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "metadata.tencentyun.com":
            return httpx.Response(
                200,
                json={
                    "Code": "Success",
                    "TmpSecretId": "fake-cvm-id",
                    "TmpSecretKey": "fake-cvm-key",
                    "Token": "fake-cvm-token",
                    "ExpiredTime": clock.now + 1800,
                },
            )
        return httpx.Response(
            200,
            json={"Response": {"Error": {"Code": "FAKE_SENSITIVE_PROVIDER_MESSAGE"}}},
        )

    provider = CachedScfAssumeRoleIdentity(
        cvm_role="SZZSBJ-CVM-SCF-Invoker",
        target_role_arn=ROLE,
        transport=httpx.MockTransport(respond),
        clock=clock,
    )
    with pytest.raises(TencentStsIdentityError, match="STS_ASSUME_ROLE_UNAVAILABLE") as error:
        provider.get_identity()
    assert "FAKE_SENSITIVE_PROVIDER_MESSAGE" not in str(error.value)


def test_invalid_config_rejected() -> None:
    with pytest.raises(TencentStsIdentityError, match="STS_CONFIG_INVALID"):
        CachedScfAssumeRoleIdentity(cvm_role="../metadata", target_role_arn=ROLE)
