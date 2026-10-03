"""The project's single encryption helper: AES-256-GCM for data at rest (NFR-8, standards/18).

Used for embeddings, camera RTSP URLs, snapshots/enrollment photos and secret settings.
Token layout: 1-byte format version | 12-byte random nonce | ciphertext + 16-byte GCM tag.
The `purpose` is bound as associated data, so a ciphertext made for one purpose
(e.g. an embedding) fails to decrypt as another (e.g. a camera URL).
"""

import base64
import binascii
import os

import numpy as np
import numpy.typing as npt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_FORMAT_V1 = b"\x01"
_NONCE_BYTES = 12
_KEY_BYTES = 32  # AES-256


class EncryptionError(Exception):
    """Raised when a key is invalid or a ciphertext cannot be decrypted."""


class Cipher:
    """AES-256-GCM encryptor bound to one key."""

    def __init__(self, key: bytes) -> None:
        if len(key) != _KEY_BYTES:
            raise EncryptionError("Encryption key must be exactly 32 bytes (AES-256).")
        self._aead = AESGCM(key)

    @classmethod
    def from_base64(cls, key_b64: str) -> "Cipher":
        """Builds a cipher from the base64 `ENCRYPTION_KEY` environment value."""
        try:
            key = base64.b64decode(key_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise EncryptionError("Encryption key is not valid base64.") from exc
        return cls(key)

    def encrypt(self, plaintext: bytes, purpose: bytes) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return _FORMAT_V1 + nonce + self._aead.encrypt(nonce, plaintext, purpose)

    def decrypt(self, token: bytes, purpose: bytes) -> bytes:
        if len(token) < 1 + _NONCE_BYTES + 16 or token[:1] != _FORMAT_V1:
            raise EncryptionError("Ciphertext has an unknown format.")
        nonce = token[1 : 1 + _NONCE_BYTES]
        try:
            return self._aead.decrypt(nonce, token[1 + _NONCE_BYTES :], purpose)
        except InvalidTag as exc:
            raise EncryptionError("Ciphertext could not be decrypted (wrong key or purpose).") from exc

    def encrypt_str(self, value: str, purpose: bytes) -> bytes:
        return self.encrypt(value.encode("utf-8"), purpose)

    def decrypt_str(self, token: bytes, purpose: bytes) -> str:
        return self.decrypt(token, purpose).decode("utf-8")

    def encrypt_embedding(self, vector: npt.NDArray[np.float32], purpose: bytes) -> bytes:
        """Encrypts a 1-D embedding as little-endian float32."""
        if vector.ndim != 1:
            raise EncryptionError("Embedding must be a 1-D vector.")
        return self.encrypt(vector.astype("<f4").tobytes(), purpose)

    def decrypt_embedding(self, token: bytes, purpose: bytes, dim: int) -> npt.NDArray[np.float32]:
        raw = self.decrypt(token, purpose)
        if len(raw) != dim * 4:
            raise EncryptionError("Decrypted embedding has an unexpected length.")
        return np.frombuffer(raw, dtype="<f4").astype(np.float32)

    def encrypt_to_b64(self, plaintext: bytes, purpose: bytes) -> str:
        """Encrypts and base64-encodes, for transport inside JSON (events, engine API)."""
        return base64.b64encode(self.encrypt(plaintext, purpose)).decode("ascii")

    def decrypt_from_b64(self, token_b64: str, purpose: bytes) -> bytes:
        try:
            token = base64.b64decode(token_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise EncryptionError("Ciphertext is not valid base64.") from exc
        return self.decrypt(token, purpose)


def generate_key_b64() -> str:
    """Returns a new random AES-256 key, base64-encoded, for `ENCRYPTION_KEY`."""
    return base64.b64encode(os.urandom(_KEY_BYTES)).decode("ascii")
