"""Event delivery, disk buffering and replay (FR-16, NFR-7, standards/17 §8)."""

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from facetrack_common.constants import CRYPTO_PURPOSE_IMAGE
from facetrack_common.crypto import Cipher
from facetrack_common.events import RecognitionEvent

from app.publisher.disk_buffer import DiskBuffer
from app.publisher.event_publisher import EventPublisher, snapshot_object_path


class FakeSink:
    def __init__(self) -> None:
        self.up = True
        self.snapshots: dict[str, bytes] = {}
        self.published: list[dict[str, str]] = []

    def put_snapshot(self, object_path: str, data: bytes) -> None:
        if not self.up:
            raise ConnectionError("storage down")
        self.snapshots[object_path] = data

    def publish(self, fields: dict[str, str]) -> None:
        if not self.up:
            raise ConnectionError("redis down")
        self.published.append(fields)


def _event(track_id: int) -> RecognitionEvent:
    event_id = uuid.uuid4()
    captured = datetime(2026, 10, 3, 4, 2, 11, tzinfo=UTC)
    return RecognitionEvent(
        event_id=event_id,
        camera_id=3,
        employee_code="ITRC-0142",
        status="recognized",
        confidence=0.7,
        track_id=track_id,
        captured_at=captured,
        snapshot_path=snapshot_object_path(captured, str(event_id)),
        model_name="sface",
        engine_node="node-1",
    )


def _wait_for(condition, timeout: float = 5.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.02)


def test_snapshot_path_layout() -> None:
    path = snapshot_object_path(datetime(2026, 10, 3, 4, 2, tzinfo=UTC), "abc")
    assert path == "snapshots/2026/10/03/abc.jpg"


def test_fr16_snapshot_is_encrypted_and_event_published(tmp_path: Path, cipher: Cipher) -> None:
    sink = FakeSink()
    publisher = EventPublisher(sink, DiskBuffer(tmp_path, cipher, 100, 10**7), cipher, queue_size=4)
    publisher.start()
    event = _event(1)
    publisher.emit(event, b"jpeg-bytes")
    _wait_for(lambda: len(sink.published) == 1)
    publisher.stop()
    stored = sink.snapshots[event.snapshot_path or ""]
    assert b"jpeg-bytes" not in stored
    assert cipher.decrypt(stored, CRYPTO_PURPOSE_IMAGE) == b"jpeg-bytes"
    assert RecognitionEvent.from_stream_fields(sink.published[0]) == event


def test_nfr7_outage_buffers_to_disk_and_replays_in_order(tmp_path: Path, cipher: Cipher) -> None:
    sink = FakeSink()
    sink.up = False
    publisher = EventPublisher(sink, DiskBuffer(tmp_path, cipher, 100, 10**7), cipher, queue_size=2)
    publisher.start()
    events = [_event(i) for i in range(10)]
    for event in events:
        publisher.emit(event, b"x")
    _wait_for(lambda: publisher.buffered == 10)
    assert not any(p.read_bytes().count(b"ITRC-0142") for p in tmp_path.glob("*.evt"))  # encrypted at rest
    sink.up = True
    _wait_for(lambda: len(sink.published) == 10)
    publisher.stop()
    assert [RecognitionEvent.from_stream_fields(p).track_id for p in sink.published] == list(range(10))
    assert publisher.buffered == 0 and publisher.lost == 0


def test_buffer_survives_restart(tmp_path: Path, cipher: Cipher) -> None:
    buffer = DiskBuffer(tmp_path, cipher, 100, 10**7)
    assert buffer.append({"event": {"n": 1}}, b"blob")
    reopened = DiskBuffer(tmp_path, cipher, 100, 10**7)
    [record] = list(reopened.oldest(10))
    assert record.header == {"event": {"n": 1}} and record.blob == b"blob"
    reopened.remove(record)
    assert len(reopened) == 0 and reopened.size_bytes == 0


def test_buffer_is_bounded_and_refuses_new_records(tmp_path: Path, cipher: Cipher) -> None:
    buffer = DiskBuffer(tmp_path, cipher, max_events=3, max_bytes=10**7)
    assert all(buffer.append({"n": i}, b"") for i in range(3))
    assert not buffer.append({"n": 4}, b"")
    small = DiskBuffer(tmp_path / "b", cipher, max_events=100, max_bytes=50)
    assert not small.append({"n": 1}, b"x" * 100)


def test_tampered_buffer_record_is_quarantined(tmp_path: Path, cipher: Cipher) -> None:
    buffer = DiskBuffer(tmp_path, cipher, 100, 10**7)
    buffer.append({"n": 1}, b"")
    [path] = tmp_path.glob("*.evt")
    path.write_bytes(b"garbage")
    assert list(buffer.oldest(10)) == []
    assert len(buffer) == 0 and list(tmp_path.glob("*.bad"))


@pytest.mark.parametrize("queue_size", [1])
def test_full_handoff_queue_goes_to_disk_not_lost(tmp_path: Path, cipher: Cipher, queue_size: int) -> None:
    sink = FakeSink()
    publisher = EventPublisher(sink, DiskBuffer(tmp_path, cipher, 100, 10**7), cipher, queue_size=queue_size)
    for i in range(5):  # thread not started: the queue fills, the rest must go to disk
        publisher.emit(_event(i), b"")
    assert publisher.buffered == 4
    publisher.start()
    _wait_for(lambda: len(sink.published) == 5)
    publisher.stop()
