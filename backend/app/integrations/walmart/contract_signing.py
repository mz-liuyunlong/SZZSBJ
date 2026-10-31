"""Protocol v3: signed contracts between the SZZSBJ server and the per-store SCF executor.

The server signs ``{contract hash, request hash, store, time, nonce, approval_ref}`` with
an Ed25519 key that lives only on the main server. The cloud executor verifies the
signature with public keys from its own environment, rebuilds the operation from the
contract and re-validates the request with the same contract code. Per-operation
environment allowlists in the cloud functions are therefore no longer the extension
mechanism; what the cloud still enforces structurally lives in ``cloud_executor`` and
``https_transport`` (host, ``/v3`` paths, methods, no caller headers, size caps).

No secret, token or Walmart credential is handled here.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import secrets
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.integrations.walmart.contracts import (
    ContractError,
    Operation,
    canonical_json,
    operation_from_contract,
    sha256_hex,
)

PROTOCOL_VERSION = 3
MAX_SKEW_SECONDS = 300
_KID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_NONCE = re.compile(r"^[0-9a-f]{32}$")
_APPROVAL = re.compile(r"^[^\x00-\x1f]{1,128}$")
_STORE = re.compile(r"^(?:HK|CN)[0-9]{4}$")
_MAX_PUBLIC_KEYS = 4


def request_sha256(*, method: str, path: str, query: Mapping[str, Any], body: Any) -> str:
    return sha256_hex({"method": method, "path": path, "query": dict(query), "body": body})


def signing_payload(
    *,
    kid: str,
    store_code: str,
    issued_at: int,
    nonce: str,
    contract_sha256: str,
    request_sha256: str,
    approval_ref: str | None,
) -> bytes:
    return canonical_json(
        {
            "v": PROTOCOL_VERSION,
            "kid": kid,
            "store_code": store_code,
            "issued_at": issued_at,
            "nonce": nonce,
            "contract_sha256": contract_sha256,
            "request_sha256": request_sha256,
            "approval_ref": approval_ref,
        }
    )


class ContractSigner:
    """Main-server side. Holds the private key in memory only; never logs or returns it."""

    def __init__(self, private_key: Ed25519PrivateKey, *, kid: str) -> None:
        if not _KID.fullmatch(kid):
            raise ContractError("WALMART_SIGNING_KEY_ID_INVALID")
        self._key = private_key
        self.kid = kid

    def __repr__(self) -> str:
        return f"ContractSigner(kid={self.kid!r})"

    @classmethod
    def generate(cls, *, kid: str) -> ContractSigner:
        return cls(Ed25519PrivateKey.generate(), kid=kid)

    @classmethod
    def from_pem_file(cls, path: str | Path, *, kid: str) -> ContractSigner:
        """Load an unencrypted Ed25519 PEM (PKCS#8) from the owner-managed key file."""
        file = Path(path)
        if not file.is_file() or file.stat().st_size > 16 * 1024:
            raise ContractError("WALMART_SIGNING_KEY_UNAVAILABLE")
        try:
            loaded = serialization.load_pem_private_key(file.read_bytes(), password=None)
        except (ValueError, TypeError):
            raise ContractError("WALMART_SIGNING_KEY_INVALID") from None
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ContractError("WALMART_SIGNING_KEY_INVALID")
        return cls(loaded, kid=kid)

    def private_pem(self) -> bytes:
        """Only for the owner's key-generation command; callers must write it 0600."""
        return self._key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def public_key_b64(self) -> str:
        raw = self._key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return base64.b64encode(raw).decode("ascii")

    def sign(
        self,
        *,
        store_code: str,
        contract: Mapping[str, Any],
        method: str,
        path: str,
        query: Mapping[str, Any],
        body: Any,
        approval_ref: str | None,
        issued_at: int | None = None,
        nonce: str | None = None,
    ) -> dict[str, Any]:
        if not _STORE.fullmatch(store_code):
            raise ContractError("WALMART_STORE_NOT_AUTHORIZED")
        if approval_ref is not None and not _APPROVAL.fullmatch(approval_ref):
            raise ContractError("WALMART_APPROVAL_INVALID")
        issued = int(time.time()) if issued_at is None else issued_at
        use_nonce = secrets.token_hex(16) if nonce is None else nonce
        payload = signing_payload(
            kid=self.kid,
            store_code=store_code,
            issued_at=issued,
            nonce=use_nonce,
            contract_sha256=sha256_hex(contract),
            request_sha256=request_sha256(method=method, path=path, query=query, body=body),
            approval_ref=approval_ref,
        )
        return {
            "kid": self.kid,
            "issued_at": issued,
            "nonce": use_nonce,
            "sig": base64.b64encode(self._key.sign(payload)).decode("ascii"),
        }


class ContractVerifier:
    """Cloud side. Public keys only (kid -> key); ``verify`` returns the rebuilt Operation."""

    def __init__(
        self,
        public_keys: Mapping[str, Ed25519PublicKey],
        *,
        clock: Callable[[], float] = time.time,
        max_skew_seconds: int = MAX_SKEW_SECONDS,
    ) -> None:
        if not public_keys or len(public_keys) > _MAX_PUBLIC_KEYS:
            raise ContractError("WALMART_VERIFY_KEYS_INVALID")
        if any(not _KID.fullmatch(kid) for kid in public_keys):
            raise ContractError("WALMART_VERIFY_KEYS_INVALID")
        self._keys = dict(public_keys)
        self._clock = clock
        self._skew = max_skew_seconds

    @classmethod
    def from_env_json(cls, raw: str, **kwargs: Any) -> ContractVerifier:
        """``{"kid": "<base64 raw 32-byte Ed25519 public key>", ...}``."""
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise ContractError("WALMART_VERIFY_KEYS_INVALID") from None
        if not isinstance(parsed, dict):
            raise ContractError("WALMART_VERIFY_KEYS_INVALID")
        keys: dict[str, Ed25519PublicKey] = {}
        for kid, encoded in parsed.items():
            if not isinstance(kid, str) or not isinstance(encoded, str):
                raise ContractError("WALMART_VERIFY_KEYS_INVALID")
            try:
                raw_key = base64.b64decode(encoded, validate=True)
                keys[kid] = Ed25519PublicKey.from_public_bytes(raw_key)
            except (ValueError, binascii.Error):
                raise ContractError("WALMART_VERIFY_KEYS_INVALID") from None
        return cls(keys, **kwargs)

    def verify(self, event: Mapping[str, Any]) -> tuple[Operation, str]:
        """Check signature, freshness, store and hashes; return (operation, contract_sha256)."""
        auth = event.get("auth")
        if not isinstance(auth, Mapping) or set(auth) != {"kid", "issued_at", "nonce", "sig"}:
            raise ContractError("WALMART_SIGNATURE_INVALID")
        kid, issued_at, nonce, sig = auth["kid"], auth["issued_at"], auth["nonce"], auth["sig"]
        if not isinstance(kid, str) or kid not in self._keys:
            raise ContractError("WALMART_SIGNATURE_KEY_UNKNOWN")
        if type(issued_at) is not int or not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
            raise ContractError("WALMART_SIGNATURE_INVALID")
        if abs(self._clock() - issued_at) > self._skew:
            raise ContractError("WALMART_SIGNATURE_EXPIRED")
        store = event.get("store_code")
        if not isinstance(store, str) or not _STORE.fullmatch(store):
            raise ContractError("WALMART_STORE_NOT_AUTHORIZED")
        approval = event.get("approval_ref")
        if approval is not None and (
            not isinstance(approval, str) or not _APPROVAL.fullmatch(approval)
        ):
            raise ContractError("WALMART_APPROVAL_INVALID")
        contract = event.get("contract")
        operation = operation_from_contract(contract)
        method, path, query, body = (
            event.get("method"),
            event.get("path"),
            event.get("query"),
            event.get("body"),
        )
        if not isinstance(method, str) or not isinstance(path, str):
            raise ContractError("WALMART_EVENT_INVALID")
        if query is None:
            query = {}
        if not isinstance(query, Mapping):
            raise ContractError("WALMART_EVENT_INVALID")
        contract_hash = sha256_hex(contract)
        payload = signing_payload(
            kid=kid,
            store_code=store,
            issued_at=issued_at,
            nonce=nonce,
            contract_sha256=contract_hash,
            request_sha256=request_sha256(method=method, path=path, query=query, body=body),
            approval_ref=approval,
        )
        if not isinstance(sig, str) or len(sig) > 128:
            raise ContractError("WALMART_SIGNATURE_INVALID")
        try:
            self._keys[kid].verify(base64.b64decode(sig, validate=True), payload)
        except (InvalidSignature, ValueError, binascii.Error):
            raise ContractError("WALMART_SIGNATURE_INVALID") from None
        return operation, contract_hash
