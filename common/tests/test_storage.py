"""Object storage tests (standards/14: server-side names, no path traversal; ADR-0005)."""

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from facetrack_common.storage import LocalObjectStore, StorageError, create_object_store


def test_put_get_delete_roundtrip(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    store.put("snapshots/2026/10/03/abc.jpg", b"ciphertext")
    assert store.get("snapshots/2026/10/03/abc.jpg") == b"ciphertext"
    store.delete("snapshots/2026/10/03/abc.jpg")
    with pytest.raises(StorageError):
        store.get("snapshots/2026/10/03/abc.jpg")
    store.delete("snapshots/2026/10/03/abc.jpg")  # idempotent


@pytest.mark.parametrize(
    "name", ["../etc/passwd", "/abs/path", "a/../../b", "a//b", "", "a b.jpg", ".hidden"]
)
def test_path_traversal_and_bad_names_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(StorageError):
        LocalObjectStore(tmp_path / "root").put(name, b"x")


def test_list_older_than_for_retention(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    store.put("snapshots/old.jpg", b"1")
    store.put("snapshots/new.jpg", b"2")
    store.put("enroll/old.jpg", b"3")
    past = time.time() - 100 * 86400
    os.utime(tmp_path / "snapshots/old.jpg", (past, past))
    cutoff = datetime.now(UTC) - timedelta(days=90)
    assert list(store.list_older_than("snapshots/", cutoff)) == ["snapshots/old.jpg"]
    assert list(store.list_older_than("missing/", cutoff)) == []


def test_factory_rejects_unknown_backend(tmp_path: Path) -> None:
    assert isinstance(create_object_store("local", tmp_path), LocalObjectStore)
    with pytest.raises(StorageError):
        create_object_store("ftp", tmp_path)
