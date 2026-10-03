"""Object storage for snapshots, enrollment photos and report exports (requirements §8, standards/14, 18).

One interface, two backends (ADR-0005):
- `LocalObjectStore`: files under one managed root directory (a mounted volume). Default, because the
  open-source MinIO server is archived and its images/binaries are no longer published.
- `S3ObjectStore`: any S3-compatible server (an existing MinIO install, or a replacement chosen by the
  owner), through the `minio` client library.

Callers pass bytes that are ALREADY encrypted with the project encryption helper; object names are
generated server-side (never client filenames) and validated here against path traversal.
"""

import io
import os
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Protocol

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")


class StorageError(Exception):
    """Raised for invalid object names or backend failures."""


def validate_object_name(name: str) -> str:
    if not _SAFE_NAME.match(name) or ".." in name.split("/") or "//" in name:
        raise StorageError("invalid object name")
    return name


class ObjectStore(Protocol):
    def put(self, name: str, data: bytes) -> None: ...

    def get(self, name: str) -> bytes: ...

    def delete(self, name: str) -> None: ...

    def list_older_than(self, prefix: str, cutoff: datetime) -> Iterator[str]: ...


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        path = (self._root / validate_object_name(name)).resolve()
        if self._root not in path.parents:
            raise StorageError("invalid object name")
        return path

    def put(self, name: str, data: bytes) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp.write_bytes(data)
        os.chmod(temp, 0o640)
        temp.replace(path)

    def get(self, name: str) -> bytes:
        try:
            return self._path(name).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("object not found") from exc

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def list_older_than(self, prefix: str, cutoff: datetime) -> Iterator[str]:
        base = self._path(prefix.rstrip("/")) if prefix else self._root
        if not base.exists():
            return
        threshold = cutoff.timestamp()
        for path in base.rglob("*"):
            if path.is_file() and not path.name.startswith(".") and path.stat().st_mtime < threshold:
                yield path.relative_to(self._root).as_posix()


class S3ObjectStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool, bucket: str) -> None:
        from minio import Minio  # noqa: PLC0415  # optional dependency (extra "s3")

        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket

    def put(self, name: str, data: bytes) -> None:
        self._client.put_object(
            self._bucket,
            validate_object_name(name),
            io.BytesIO(data),
            len(data),
            content_type="application/octet-stream",
        )

    def get(self, name: str) -> bytes:
        response = self._client.get_object(self._bucket, validate_object_name(name))
        try:
            return bytes(response.read())
        finally:
            response.close()
            response.release_conn()

    def delete(self, name: str) -> None:
        self._client.remove_object(self._bucket, validate_object_name(name))

    def list_older_than(self, prefix: str, cutoff: datetime) -> Iterator[str]:
        for item in self._client.list_objects(self._bucket, prefix=prefix, recursive=True):
            if item.last_modified is not None and item.last_modified < cutoff:
                yield str(item.object_name)


def create_object_store(
    backend: str,
    local_root: Path,
    endpoint: str = "",
    access_key: str = "",
    secret_key: str = "",
    secure: bool = True,
    bucket: str = "facetrack",
) -> ObjectStore:
    if backend == "s3":
        return S3ObjectStore(endpoint, access_key, secret_key, secure, bucket)
    if backend == "local":
        return LocalObjectStore(local_root)
    raise StorageError(f"unknown storage backend '{backend}'")
