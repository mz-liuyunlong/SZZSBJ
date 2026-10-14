from app.modules.iam.security import hash_password, issue_access_token, token_hash, verify_password


def test_bcrypt_password_hash_roundtrip() -> None:
    hashed = hash_password("StrongPass123")
    assert hashed.startswith("$2")
    assert verify_password("StrongPass123", hashed)
    assert not verify_password("WrongPass123", hashed)


def test_legacy_placeholder_password_fails_closed() -> None:
    assert not verify_password("anything", "x")


def test_access_token_hash_is_stable_and_not_raw_token() -> None:
    token, digest, expires_at = issue_access_token()
    assert digest == token_hash(token)
    assert token not in digest
    assert expires_at.tzinfo is not None
