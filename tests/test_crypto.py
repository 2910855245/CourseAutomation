"""Tests for api/crypto.py — AES-256-GCM 加密模块"""
import base64
import os


class TestEncryptDecrypt:
    """加解密一致性测试"""

    def test_roundtrip(self):
        from api.crypto import decrypt_password, encrypt_password

        plain = "my_secret_password_123"
        encrypted = encrypt_password(plain)
        assert encrypted.startswith("ENC2:")
        assert decrypt_password(encrypted) == plain

    def test_roundtrip_chinese(self):
        from api.crypto import decrypt_password, encrypt_password

        plain = "密码测试中文"
        encrypted = encrypt_password(plain)
        assert decrypt_password(encrypted) == plain

    def test_roundtrip_special_chars(self):
        from api.crypto import decrypt_password, encrypt_password

        plain = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        encrypted = encrypt_password(plain)
        assert decrypt_password(encrypted) == plain

    def test_empty_string(self):
        from api.crypto import encrypt_password

        assert encrypt_password("") == ""

    def test_decrypt_empty(self):
        from api.crypto import decrypt_password

        assert decrypt_password("") == ""

    def test_decrypt_plain_text_passthrough(self):
        from api.crypto import decrypt_password

        # 未加密的纯文本直接返回
        assert decrypt_password("plain_text") == "plain_text"

    def test_different_encryptions_differ(self):
        from api.crypto import encrypt_password

        plain = "same_password"
        enc1 = encrypt_password(plain)
        enc2 = encrypt_password(plain)
        # nonce 随机，两次加密结果应不同
        assert enc1 != enc2
        # 但都能解密回原值
        from api.crypto import decrypt_password
        assert decrypt_password(enc1) == plain
        assert decrypt_password(enc2) == plain


class TestLegacyXor:
    """旧 XOR 格式兼容测试"""

    def test_decrypt_legacy_xor(self):
        import api.crypto

        # 手动构造一个 XOR 加密的值
        plain = "test_password"
        key = "test-encryption-key-32chars!!!!!"
        derived = __import__("hashlib").sha256(key.encode()).digest()
        raw = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(plain.encode("utf-8")))
        stored = api.crypto._PREFIX_OLD + base64.b64encode(raw).decode("ascii")

        old_key = api.crypto.settings.password_encryption_key
        api.crypto.settings.password_encryption_key = key
        try:
            assert api.crypto.decrypt_password(stored) == plain
        finally:
            api.crypto.settings.password_encryption_key = old_key
