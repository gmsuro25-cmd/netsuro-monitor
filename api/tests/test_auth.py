from app.auth import hash_password, verify_password


def test_password_hash_does_not_store_plaintext():
    encoded = hash_password("a-very-long-password")
    assert "a-very-long-password" not in encoded
    assert verify_password("a-very-long-password", encoded)


def test_wrong_password_is_rejected():
    encoded = hash_password("a-very-long-password")
    assert not verify_password("wrong-password", encoded)
