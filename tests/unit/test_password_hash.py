from app.security.password_hash import hash_password, verify_password


def test_password_hash_verifies_without_storing_plaintext() -> None:
    password = "SecurePass123"
    encoded = hash_password(password)

    assert encoded != password
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password(password, encoded)
    assert not verify_password("incorrect123", encoded)
    assert not verify_password(password, None)
