from goszdrav_bot.services.crypto import FieldCipher


def test_field_cipher_roundtrip() -> None:
    cipher = FieldCipher(secret="unit-test-secret", salt="unit-test-salt")

    encrypted = cipher.encrypt("Иванов Иван Иванович")

    assert encrypted is not None
    assert encrypted != "Иванов Иван Иванович"
    assert cipher.decrypt(encrypted) == "Иванов Иван Иванович"

