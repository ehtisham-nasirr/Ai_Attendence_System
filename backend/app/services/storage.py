"""Object storage for enrollment photos, snapshots and exports (standards/14, 18; ADR-0005).

Everything stored is encrypted first with the project encryption helper; names are generated here,
never taken from the client.
"""

import secrets
from datetime import UTC, datetime
from functools import lru_cache

from facetrack_common.constants import CRYPTO_PURPOSE_IMAGE
from facetrack_common.storage import ObjectStore, StorageError, create_object_store

from app.core.config import get_settings
from app.core.crypto import get_cipher


@lru_cache
def get_store() -> ObjectStore:
    s = get_settings()
    return create_object_store(
        s.storage_backend,
        s.media_root,
        s.s3_endpoint,
        s.s3_access_key.get_secret_value(),
        s.s3_secret_key.get_secret_value(),
        s.s3_secure,
        s.s3_bucket,
    )


def new_object_name(prefix: str, extension: str) -> str:
    """`<prefix>/YYYY/MM/<random>.<ext>` — non-guessable, never the client filename."""
    now = datetime.now(UTC)
    return f"{prefix}/{now:%Y/%m}/{secrets.token_hex(16)}.{extension}"


def put_encrypted(name: str, data: bytes) -> None:
    get_store().put(name, get_cipher().encrypt(data, CRYPTO_PURPOSE_IMAGE))


def get_decrypted(name: str) -> bytes:
    return get_cipher().decrypt(get_store().get(name), CRYPTO_PURPOSE_IMAGE)


def delete_quietly(names: list[str]) -> int:
    """Hard-deletes objects; a missing object is not an error (erasure is idempotent)."""
    deleted = 0
    for name in names:
        try:
            get_store().delete(name)
            deleted += 1
        except StorageError:
            continue
    return deleted
