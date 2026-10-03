"""Recognition-event contract tests (requirements §10.2, FR-16, FR-17)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from facetrack_common.events import RecognitionEvent


def _event(**overrides: object) -> RecognitionEvent:
    data: dict[str, object] = {
        "event_id": str(uuid.uuid4()),
        "camera_id": 3,
        "employee_code": "ITRC-0142",
        "status": "recognized",
        "confidence": 0.71,
        "liveness_score": 0.97,
        "track_id": 8812,
        "captured_at": "2026-10-03T04:02:11Z",
        "snapshot_path": "snapshots/2026/10/03/x.jpg",
        "model_name": "sface",
        "engine_node": "node-1",
    }
    data.update(overrides)
    return RecognitionEvent.model_validate(data)


def test_fr16_valid_recognized_event_roundtrips_through_stream_fields() -> None:
    event = _event()
    fields = event.to_stream_fields()
    assert RecognitionEvent.from_stream_fields(fields) == event
    encoded = {k.encode(): v.encode() for k, v in fields.items()}
    assert RecognitionEvent.from_stream_fields(encoded) == event


def test_captured_at_is_normalised_to_utc() -> None:
    pkt = timezone(timedelta(hours=5))
    event = _event(captured_at=datetime(2026, 10, 3, 9, 2, 11, tzinfo=pkt))
    assert event.captured_at == datetime(2026, 10, 3, 4, 2, 11, tzinfo=UTC)
    assert event.captured_at.utcoffset() == timedelta(0)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(captured_at="2026-10-03T04:02:11")


def test_recognized_requires_employee_code() -> None:
    with pytest.raises(ValidationError):
        _event(employee_code=None)


def test_fr17_unknown_must_not_carry_employee_code() -> None:
    with pytest.raises(ValidationError):
        _event(status="unknown")
    event = _event(status="unknown", employee_code=None, embedding_encrypted="AAAA")
    assert event.employee_code is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "voided"},
        {"camera_id": 0},
        {"confidence": 1.5},
        {"liveness_score": -0.1},
        {"bbox": (0.1, 0.2, 1.3, 0.4)},
        {"unexpected": "field"},
    ],
)
def test_invalid_events_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _event(**overrides)


def test_missing_payload_field_raises_key_error() -> None:
    with pytest.raises(KeyError):
        RecognitionEvent.from_stream_fields({"other": "{}"})
