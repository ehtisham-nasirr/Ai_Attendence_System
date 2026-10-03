"""Bounded local disk buffer for events that could not be delivered (NFR-7, standards/17 §8).

Records are AES-256-GCM encrypted (they contain a face snapshot) and replayed oldest-first.
Overflow policy: when the buffer is full a new record is refused (`append` returns False); the
caller logs it at CRITICAL and counts it. Ordering of everything already buffered is preserved.
"""

import json
import logging
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from facetrack_common.crypto import Cipher, EncryptionError

logger = logging.getLogger(__name__)

_PURPOSE = b"facetrack:engine-buffer"
_SUFFIX = ".evt"


@dataclass(frozen=True)
class BufferedRecord:
    path: Path
    header: dict[str, Any]
    blob: bytes


class DiskBuffer:
    def __init__(self, directory: Path, cipher: Cipher, max_events: int, max_bytes: int) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cipher = cipher
        self._max_events = max_events
        self._max_bytes = max_bytes
        files = self._files()
        self._count = len(files)
        self._bytes = sum(f.stat().st_size for f in files)
        self._seq = int(files[-1].stem) if files else 0

    def _files(self) -> list[Path]:
        return sorted(self._dir.glob(f"*{_SUFFIX}"))

    def __len__(self) -> int:
        return self._count

    @property
    def size_bytes(self) -> int:
        return self._bytes

    @property
    def last_seq(self) -> int:
        return self._seq

    def append(self, header: dict[str, Any], blob: bytes, seq: int | None = None) -> bool:
        """Stores a record; `seq` (emission order) names the file so replay order is emission order."""
        header_bytes = json.dumps(header).encode()
        plaintext = struct.pack(">I", len(header_bytes)) + header_bytes + blob
        token = self._cipher.encrypt(plaintext, _PURPOSE)
        if self._count >= self._max_events or self._bytes + len(token) > self._max_bytes:
            return False
        seq = seq if seq is not None else self._seq + 1
        self._seq = max(self._seq, seq)
        final = self._dir / f"{seq:016d}{_SUFFIX}"
        temp = final.with_suffix(".tmp")
        temp.write_bytes(token)
        temp.replace(final)  # atomic: a crash never leaves a half-written record
        self._count += 1
        self._bytes += len(token)
        return True

    def oldest(self, limit: int) -> Iterator[BufferedRecord]:
        for path in self._files()[:limit]:
            try:
                plaintext = self._cipher.decrypt(path.read_bytes(), _PURPOSE)
            except (OSError, EncryptionError):
                logger.error("unreadable buffered event; quarantining", extra={"file": path.name})
                self._bytes -= path.stat().st_size
                path.rename(path.with_suffix(".bad"))
                self._count -= 1
                continue
            (header_len,) = struct.unpack(">I", plaintext[:4])
            header = json.loads(plaintext[4 : 4 + header_len])
            yield BufferedRecord(path, header, plaintext[4 + header_len :])

    def remove(self, record: BufferedRecord) -> None:
        size = record.path.stat().st_size
        record.path.unlink()
        self._count -= 1
        self._bytes -= size
