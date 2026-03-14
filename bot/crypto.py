"""AES encryption for sensitive settings stored in DB."""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from bot.config import settings

_SALT = b"kraken_bot_salt_v1"


def _get_key() -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    key = kdf.derive(settings.dashboard_secret_key.encode())
    return base64.urlsafe_b64encode(key)


def encrypt(plaintext: str) -> str:
    f = Fernet(_get_key())
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    f = Fernet(_get_key())
    return f.decrypt(ciphertext.encode()).decode()
