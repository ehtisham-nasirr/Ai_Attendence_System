"""Encryption helper tests (NFR-8, standards/18)."""

import numpy as np
import pytest

from facetrack_common.constants import CRYPTO_PURPOSE_CAMERA_URL, CRYPTO_PURPOSE_EMBEDDING
from facetrack_common.crypto import Cipher, EncryptionError, generate_key_b64


@pytest.fixture
def cipher() -> Cipher:
    return Cipher.from_base64(generate_key_b64())


def test_nfr8_roundtrip_string(cipher: Cipher) -> None:
    token = cipher.encrypt_str("rtsp://user:pass@10.0.0.5/stream", CRYPTO_PURPOSE_CAMERA_URL)
    assert b"pass" not in token
    assert cipher.decrypt_str(token, CRYPTO_PURPOSE_CAMERA_URL) == "rtsp://user:pass@10.0.0.5/stream"


def test_nfr8_roundtrip_embedding(cipher: Cipher) -> None:
    vector = np.random.default_rng(1).standard_normal(128).astype(np.float32)
    token = cipher.encrypt_embedding(vector, CRYPTO_PURPOSE_EMBEDDING)
    restored = cipher.decrypt_embedding(token, CRYPTO_PURPOSE_EMBEDDING, 128)
    np.testing.assert_array_equal(vector, restored)


def test_nonce_is_random(cipher: Cipher) -> None:
    assert cipher.encrypt(b"same", b"p") != cipher.encrypt(b"same", b"p")


def test_wrong_purpose_is_rejected(cipher: Cipher) -> None:
    token = cipher.encrypt(b"secret", CRYPTO_PURPOSE_EMBEDDING)
    with pytest.raises(EncryptionError):
        cipher.decrypt(token, CRYPTO_PURPOSE_CAMERA_URL)


def test_wrong_key_is_rejected(cipher: Cipher) -> None:
    token = cipher.encrypt(b"secret", b"p")
    other = Cipher.from_base64(generate_key_b64())
    with pytest.raises(EncryptionError):
        other.decrypt(token, b"p")


def test_tampered_ciphertext_is_rejected(cipher: Cipher) -> None:
    token = bytearray(cipher.encrypt(b"secret", b"p"))
    token[-1] ^= 0x01
    with pytest.raises(EncryptionError):
        cipher.decrypt(bytes(token), b"p")


@pytest.mark.parametrize("key", ["", "not-base64!!", "c2hvcnQ="])
def test_invalid_keys_are_rejected(key: str) -> None:
    with pytest.raises(EncryptionError):
        Cipher.from_base64(key)


def test_embedding_dim_mismatch(cipher: Cipher) -> None:
    token = cipher.encrypt_embedding(np.ones(128, dtype=np.float32), b"p")
    with pytest.raises(EncryptionError):
        cipher.decrypt_embedding(token, b"p", 512)


def test_b64_transport_roundtrip(cipher: Cipher) -> None:
    assert cipher.decrypt_from_b64(cipher.encrypt_to_b64(b"abc", b"p"), b"p") == b"abc"
