import json
from base64 import b64encode
from collections.abc import Mapping
from hashlib import md5
from time import time

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pydantic import JsonValue, SecretStr


class LingxingQuerySignError(RuntimeError):
    """Safe query-sign error that does not expose authentication material."""


def canonical_value(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_canonical_signing_params(
    business_params: Mapping[str, JsonValue],
    *,
    access_token: SecretStr,
    app_id: str,
    timestamp: str,
) -> dict[str, JsonValue]:
    params = {key: value for key, value in business_params.items() if key != "sign"}
    params.update(
        {
            "access_token": access_token.get_secret_value(),
            "app_key": app_id,
            "timestamp": timestamp,
        }
    )
    return params


def build_signing_string(params: Mapping[str, JsonValue]) -> str:
    return "&".join(
        f"{key}={canonical_value(value)}"
        for key, value in sorted(params.items())
        if key != "sign" and value != ""
    )


def md5_uppercase(value: str) -> str:
    return md5(value.encode("utf-8"), usedforsecurity=False).hexdigest().upper()


def aes_ecb_base64(value: str, *, app_id: str) -> str:
    try:
        cipher = Cipher(algorithms.AES(app_id.encode("utf-8")), modes.ECB())
    except ValueError:
        raise LingxingQuerySignError("Lingxing query-sign configuration is invalid") from None
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(value.encode("utf-8")) + padder.finalize()
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return b64encode(encrypted).decode("ascii")


def build_query_auth_params(
    business_params: Mapping[str, JsonValue],
    *,
    access_token: SecretStr,
    app_id: str,
    timestamp: str | None = None,
) -> dict[str, str]:
    request_timestamp = timestamp if timestamp is not None else str(int(time()))
    if not request_timestamp.isdecimal():
        raise LingxingQuerySignError("Lingxing query-sign timestamp is invalid")
    signing_params = build_canonical_signing_params(
        business_params,
        access_token=access_token,
        app_id=app_id,
        timestamp=request_timestamp,
    )
    signature = aes_ecb_base64(
        md5_uppercase(build_signing_string(signing_params)),
        app_id=app_id,
    )
    return {
        "access_token": access_token.get_secret_value(),
        "app_key": app_id,
        "timestamp": request_timestamp,
        "sign": signature,
    }
