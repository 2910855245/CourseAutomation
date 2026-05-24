"""密码加密模块 — AES-256-GCM（兼容旧 XOR 格式解密）"""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import settings

_PREFIX_NEW = "ENC2:"
_PREFIX_OLD = "ENC:"


def _derive_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()


def encrypt_password(plain: str) -> str:
    if not plain:
        return ""
    key = _derive_key(settings.password_encryption_key)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plain.encode("utf-8"), None)
    return _PREFIX_NEW + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_password(stored: str) -> str:
    if not stored:
        return stored
    if stored.startswith(_PREFIX_NEW):
        try:
            raw = base64.b64decode(stored[len(_PREFIX_NEW):])
            nonce, ct = raw[:12], raw[12:]
            key = _derive_key(settings.password_encryption_key)
            return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
        except Exception:
            return stored
    if stored.startswith(_PREFIX_OLD):
        try:
            raw = base64.b64decode(stored[len(_PREFIX_OLD):])
            derived = _derive_key(settings.password_encryption_key)
            return bytes(b ^ derived[i % len(derived)] for i, b in enumerate(raw)).decode("utf-8")
        except Exception:
            return stored
    return stored
