"""Access to the project encryption helper (facetrack_common.crypto) with the configured key."""

from functools import lru_cache

from facetrack_common.crypto import Cipher

from app.core.config import get_settings


@lru_cache
def get_cipher() -> Cipher:
    return Cipher.from_base64(get_settings().encryption_key.get_secret_value())
