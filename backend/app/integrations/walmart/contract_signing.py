"""Protocol v3: signed contracts between the SZZSBJ server and the per-store SCF executor.

The server signs one request at a time with an Ed25519 key that lives only on the main
server. The signature covers (handover chapter 76.3, reviewer requirement 1):

    protocol version, key id, target store, target cloud function, operation key,
    HTTP method, resolved path, params SHA-256, body SHA-256, contract SHA-256,
    response kind, risk level, actor kind + uid, request_id, issued_at, expires_at,
    approval_ref.

The cloud executor verifies the signature with public keys from its own environment,
checks freshness and replay, rebuilds the operation from the contract and re-validates
the request with the same contract code. Per-operation environment allowlists in the
cloud functions are therefore no longer the extension mechanism; what the cloud still
enforces structurally lives in ``cloud_executor`` and ``https_transport`` (host, HTTPS,
``/v3`` paths, methods, no caller headers, no redirects, size caps).

Canonical JSON (both sides use ``contracts.canonical_json``): UTF-8, keys sorted,
separators ``,`` and ``:`` without spaces, non-ASCII kept as is, NaN/Infinity refused,
numbers rendered by Python's ``json`` (ints exact; floats by ``repr``). Both ends run
this same module, so a request hashes identically on the server and in the cloud.

A signer only signs contracts that belong to the registry it was built with (reviewer
requirement 2): business code cannot construct an ad-hoc method/path/schema and get it
signed. No secret, token or Walmart credential is handled here.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.integrations.walmart.contracts import (
    ContractError,
    ContractRegistry,
    Operation,
    canonical_json,
    operation_from_contract,
    sha256_hex,
)

PROTOCOL_VERSION = 3
# A signature is valid for at most this long; the server asks for less (default 120 s).
MAX_TTL_SECONDS = 300
DEFAULT_TTL_SECONDS = 120
# Tolerated clock lead of the server relative to the cloud (issued_at in the future).
MAX_FUTURE_SKEW_SECONDS = 60
_KID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")
_APPROVAL = re.compile(r"^[^\x00-\x1f]{1,128}$")
_STORE = re.compile(r"^(?:HK|CN)[0-9]{4}$")
_FUNCTION = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ACTOR_KINDS = frozenset({"user", "system"})
_ACTOR_UID = re.compile(r"^[^\x00-\x1f]{1,128}$")
_MAX_PUBLIC_KEYS = 4
RISK_READ = "read"
RISK_WRITE = "write"

# Reviewer requirement 3: a non-GET is a write unless the operation was explicitly
# reviewed as read-semantic. This set is cloud-side code, not configuration, and is
# empty on purpose (WFS inbound-preview is a POST and is treated as a write).
READ_SEMANTIC_NON_GET_KEYS: frozenset[str] = frozenset()


def risk_for(method: str, operation_key: str) -> str:
    """Risk level both sides agree on: method decides, with the reviewed-key exception."""
    if method == "GET":
        return RISK_READ
    if operation_key in READ_SEMANTIC_NON_GET_KEYS:
        return RISK_READ
    return RISK_WRITE


def signing_payload(
    *,
    kid: str,
    store_code: str,
    function_name: str,
    operation_key: str,
    method: str,
    path: str,
    params_sha256: str,
    body_sha256: str,
    contract_sha256: str,
    response_kind: str,
    risk: str,
    actor_kind: str,
    actor_uid: str,
    request_id: str,
    issued_at: int,
    expires_at: int,
    approval_ref: str | None,
) -> bytes:
    return canonical_json(
        {
            "v": PROTOCOL_VERSION,
            "kid": kid,
            "store_code": store_code,
            "function_name": function_name,
            "operation_key": operation_key,
            "method": method,
            "path": path,
            "params_sha256": params_sha256,
            "body_sha256": body_sha256,
            "contract_sha256": contract_sha256,
            "response_kind": response_kind,
            "risk": risk,
            "actor_kind": actor_kind,
            "actor_uid": actor_uid,
            "request_id": request_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "approval_ref": approval_ref,
        }
    )


def validate_actor(actor: Any) -> tuple[str, str]:
    """``{"kind": "user"|"system", "uid": str}`` — the only shape both sides accept."""
    if (
        not isinstance(actor, Mapping)
        or set(actor) != {"kind", "uid"}
        or actor["kind"] not in _ACTOR_KINDS
        or not isinstance(actor["uid"], str)
        or not _ACTOR_UID.fullmatch(actor["uid"])
    ):
        raise ContractError("WALMART_ACTOR_INVALID")
    return str(actor["kind"]), str(actor["uid"])


class ContractSigner:
    """Main-server side. Holds the private key in memory only; never logs or returns it.

    ``registry`` is the set of contracts this signer is allowed to sign (the reviewed
    registry in production). Anything else is refused with ``WALMART_CONTRACT_NOT_REGISTERED``.
    """

    def __init__(
        self, private_key: Ed25519PrivateKey, *, kid: str, registry: ContractRegistry
    ) -> None:
        if not _KID.fullmatch(kid):
            raise ContractError("WALMART_SIGNING_KEY_ID_INVALID")
        self._key = private_key
        self.kid = kid
        self._allowed = {sha256_hex(registry.contract_for(key)): key for key in registry.keys()}

    def __repr__(self) -> str:
        return f"ContractSigner(kid={self.kid!r}, contracts={len(self._allowed)})"

    @classmethod
    def generate(cls, *, kid: str, registry: ContractRegistry) -> ContractSigner:
        return cls(Ed25519PrivateKey.generate(), kid=kid, registry=registry)

    @classmethod
    def from_pem_file(
        cls, path: str | Path, *, kid: str, registry: ContractRegistry
    ) -> ContractSigner:
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
        return cls(loaded, kid=kid, registry=registry)

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
        function_name: str,
        contract: Mapping[str, Any],
        method: str,
        path: str,
        params: Mapping[str, Any],
        body: Any,
        response_kind: str,
        actor: Mapping[str, str],
        approval_ref: str | None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        issued_at: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        actor_kind, actor_uid = validate_actor(actor)
        if not _STORE.fullmatch(store_code):
            raise ContractError("WALMART_STORE_NOT_AUTHORIZED")
        if not _FUNCTION.fullmatch(function_name):
            raise ContractError("WALMART_FUNCTION_INVALID")
        if approval_ref is not None and not _APPROVAL.fullmatch(approval_ref):
            raise ContractError("WALMART_APPROVAL_INVALID")
        if not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ContractError("WALMART_SIGNATURE_TTL_INVALID")
        contract_hash = sha256_hex(contract)
        operation_key = self._allowed.get(contract_hash)
        if operation_key is None or operation_key != contract.get("key"):
            raise ContractError("WALMART_CONTRACT_NOT_REGISTERED")
        issued = int(time.time()) if issued_at is None else issued_at
        expires = issued + ttl_seconds
        rid = uuid4().hex if request_id is None else request_id
        if not _REQUEST_ID.fullmatch(rid):
            raise ContractError("WALMART_REQUEST_ID_INVALID")
        payload = signing_payload(
            kid=self.kid,
            store_code=store_code,
            function_name=function_name,
            operation_key=operation_key,
            method=method,
            path=path,
            params_sha256=sha256_hex(dict(params)),
            body_sha256=sha256_hex(body),
            contract_sha256=contract_hash,
            response_kind=response_kind,
            risk=risk_for(method, operation_key),
            actor_kind=actor_kind,
            actor_uid=actor_uid,
            request_id=rid,
            issued_at=issued,
            expires_at=expires,
            approval_ref=approval_ref,
        )
        return {
            "kid": self.kid,
            "request_id": rid,
            "issued_at": issued,
            "expires_at": expires,
            "sig": base64.b64encode(self._key.sign(payload)).decode("ascii"),
        }


class ReplayStore(Protocol):
    """Atomic first-use claim of a (kid, request_id) until ``expires_at``.

    ``claim`` returns True exactly once per key across every holder of the same store.
    ``shared`` says whether the store is visible to other cloud-function instances; a
    write is only executed when it is (reviewer requirement: cross-instance replay).
    """

    shared: bool

    def claim(self, kid: str, request_id: str, expires_at: int, now: float) -> bool: ...


class MemoryReplayStore:
    """Per-process memory (one warm instance). Enough for reads; never for writes."""

    shared = False

    def __init__(self, *, max_entries: int = 20_000) -> None:
        self._seen: dict[tuple[str, str], int] = {}
        self._max = max_entries

    def claim(self, kid: str, request_id: str, expires_at: int, now: float) -> bool:
        if len(self._seen) >= self._max or len(self._seen) % 512 == 0:
            self._seen = {k: exp for k, exp in self._seen.items() if exp >= now}
        if len(self._seen) >= self._max:
            raise ContractError("WALMART_REPLAY_CACHE_FULL")
        key = (kid, request_id)
        if key in self._seen:
            return False
        self._seen[key] = expires_at
        return True


class FileReplayStore:
    """Shared-filesystem claim (Tencent CFS mounted into every instance of a function).

    ``open(..., O_CREAT | O_EXCL)`` is atomic on a POSIX / NFS mount, so two instances
    racing on the same request_id get exactly one winner. Marker files older than their
    ``expires_at`` are swept opportunistically; the signature itself is already invalid
    by then, so a late sweep cannot re-open a replay window.
    """

    shared = True

    def __init__(self, directory: str | Path, *, sweep_every: int = 256) -> None:
        self._dir = Path(directory)
        if not self._dir.is_dir():
            raise ContractError("WALMART_REPLAY_STORE_UNAVAILABLE")
        self._sweep_every = sweep_every
        self._claims = 0

    def _path(self, kid: str, request_id: str) -> Path:
        if not _KID.fullmatch(kid) or not _REQUEST_ID.fullmatch(request_id):
            raise ContractError("WALMART_SIGNATURE_INVALID")
        return self._dir / f"{kid}.{request_id}.claim"

    def claim(self, kid: str, request_id: str, expires_at: int, now: float) -> bool:
        self._claims += 1
        if self._claims % self._sweep_every == 0:
            self._sweep(now)
        path = self._path(kid, request_id)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        except OSError:
            raise ContractError("WALMART_REPLAY_STORE_UNAVAILABLE") from None
        try:
            os.write(fd, str(expires_at).encode("ascii"))
        finally:
            os.close(fd)
        return True

    def _sweep(self, now: float) -> None:
        try:
            for marker in self._dir.glob("*.claim"):
                try:
                    expires_at = int(marker.read_text(encoding="ascii") or "0")
                except (OSError, ValueError):
                    continue
                if expires_at < now - MAX_TTL_SECONDS:
                    marker.unlink(missing_ok=True)
        except OSError:
            return


class RedisReplayStore:
    """Shared claim on Redis (``SET key 1 NX PX ttl``). The client is injected so this
    module stays dependency-free; the runtime builds it from ``SZZSBJ_WALMART_REPLAY_REDIS_URL``.
    """

    shared = True

    def __init__(self, client: Any, *, prefix: str = "szzsbj:walmart:replay:") -> None:
        self._client = client
        self._prefix = prefix

    def claim(self, kid: str, request_id: str, expires_at: int, now: float) -> bool:
        ttl_ms = max(1000, int((expires_at - now + MAX_TTL_SECONDS) * 1000))
        try:
            result = self._client.set(f"{self._prefix}{kid}:{request_id}", "1", nx=True, px=ttl_ms)
        except Exception:
            raise ContractError("WALMART_REPLAY_STORE_UNAVAILABLE") from None
        return bool(result)


# Backwards-compatible name used by the first v3 iteration.
ReplayCache = MemoryReplayStore


@dataclass(frozen=True, slots=True)
class VerifiedCall:
    operation: Operation
    contract_sha256: str
    risk: str
    request_id: str
    kid: str
    actor_kind: str
    actor_uid: str


class ContractVerifier:
    """Cloud side. Public keys only (kid -> key); bound to one store and one function."""

    def __init__(
        self,
        public_keys: Mapping[str, Ed25519PublicKey],
        *,
        bound_store: str,
        bound_function: str,
        clock: Callable[[], float] = time.time,
        replay: ReplayStore | None = None,
    ) -> None:
        if not public_keys or len(public_keys) > _MAX_PUBLIC_KEYS:
            raise ContractError("WALMART_VERIFY_KEYS_INVALID")
        if any(not _KID.fullmatch(kid) for kid in public_keys):
            raise ContractError("WALMART_VERIFY_KEYS_INVALID")
        if not _STORE.fullmatch(bound_store) or not _FUNCTION.fullmatch(bound_function):
            raise ContractError("WALMART_STORE_BINDING_MISSING")
        self._keys = dict(public_keys)
        self._store = bound_store
        self._function = bound_function
        self._clock = clock
        self._replay: ReplayStore = replay or MemoryReplayStore()

    @property
    def shared_replay(self) -> bool:
        """True when replays are refused across instances, not only within this one."""
        return bool(self._replay.shared)

    @classmethod
    def from_env_json(cls, raw: str, **kwargs: Any) -> ContractVerifier:
        """``{"kid": "<base64 raw 32-byte Ed25519 public key>", ...}`` (<= 4 keys for rotation)."""
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

    def verify(self, event: Mapping[str, Any]) -> VerifiedCall:
        """Signature, key, freshness, replay, binding, contract shape, hashes and risk."""
        auth = event.get("auth")
        expected = {"kid", "request_id", "issued_at", "expires_at", "sig"}
        if not isinstance(auth, Mapping) or set(auth) != expected:
            raise ContractError("WALMART_SIGNATURE_INVALID")
        kid, request_id = auth["kid"], auth["request_id"]
        issued_at, expires_at, sig = auth["issued_at"], auth["expires_at"], auth["sig"]
        if not isinstance(kid, str) or kid not in self._keys:
            raise ContractError("WALMART_SIGNATURE_KEY_UNKNOWN")
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ContractError("WALMART_SIGNATURE_INVALID")
        if type(issued_at) is not int or type(expires_at) is not int:
            raise ContractError("WALMART_SIGNATURE_INVALID")
        if not 1 <= expires_at - issued_at <= MAX_TTL_SECONDS:
            raise ContractError("WALMART_SIGNATURE_TTL_INVALID")
        now = self._clock()
        if now > expires_at or issued_at > now + MAX_FUTURE_SKEW_SECONDS:
            raise ContractError("WALMART_SIGNATURE_EXPIRED")
        store, function_name = event.get("store_code"), event.get("function_name")
        if store != self._store:
            raise ContractError("WALMART_STORE_NOT_AUTHORIZED")
        if function_name != self._function:
            raise ContractError("WALMART_FUNCTION_MISMATCH")
        approval = event.get("approval_ref")
        if approval is not None and (
            not isinstance(approval, str) or not _APPROVAL.fullmatch(approval)
        ):
            raise ContractError("WALMART_APPROVAL_INVALID")
        actor_kind, actor_uid = validate_actor(event.get("actor"))
        contract = event.get("contract")
        operation = operation_from_contract(contract)
        method, path, params, body = (
            event.get("method"),
            event.get("path"),
            event.get("params"),
            event.get("body"),
        )
        response_kind, declared_risk = event.get("accept"), event.get("risk")
        if not isinstance(method, str) or not isinstance(path, str):
            raise ContractError("WALMART_EVENT_INVALID")
        if params is None:
            params = {}
        if not isinstance(params, Mapping) or response_kind not in ("json", "pdf"):
            raise ContractError("WALMART_EVENT_INVALID")
        # The cloud decides the risk from the method; the server's declaration must agree.
        risk = risk_for(method, operation.key)
        if declared_risk != risk:
            raise ContractError("WALMART_RISK_MISMATCH")
        contract_hash = sha256_hex(contract)
        payload = signing_payload(
            kid=kid,
            store_code=store,
            function_name=function_name,
            operation_key=operation.key,
            method=method,
            path=path,
            params_sha256=sha256_hex(dict(params)),
            body_sha256=sha256_hex(body),
            contract_sha256=contract_hash,
            response_kind=response_kind,
            risk=risk,
            actor_kind=actor_kind,
            actor_uid=actor_uid,
            request_id=request_id,
            issued_at=issued_at,
            expires_at=expires_at,
            approval_ref=approval,
        )
        if not isinstance(sig, str) or len(sig) > 128:
            raise ContractError("WALMART_SIGNATURE_INVALID")
        try:
            self._keys[kid].verify(base64.b64decode(sig, validate=True), payload)
        except (InvalidSignature, ValueError, binascii.Error):
            raise ContractError("WALMART_SIGNATURE_INVALID") from None
        # Only a request that verified is claimed; a forged one must not fill the store.
        if not self._replay.claim(kid, request_id, expires_at, now):
            raise ContractError("WALMART_SIGNATURE_REPLAYED")
        return VerifiedCall(
            operation=operation,
            contract_sha256=contract_hash,
            risk=risk,
            request_id=request_id,
            kid=kid,
            actor_kind=actor_kind,
            actor_uid=actor_uid,
        )
