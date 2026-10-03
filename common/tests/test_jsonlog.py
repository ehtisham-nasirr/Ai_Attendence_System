"""Structured logging tests (standards/09, NFR-13)."""

import json
import logging

from facetrack_common.jsonlog import JsonFormatter


def _format(**extra: object) -> dict[str, object]:
    record = logging.LogRecord("facetrack.test", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter("engine").format(record))  # type: ignore[no-any-return]


def test_json_line_has_service_and_extras() -> None:
    entry = _format(camera_id=3)
    assert entry["service"] == "engine"
    assert entry["message"] == "hello x"
    assert entry["camera_id"] == 3
    assert str(entry["ts"]).endswith("Z")


def test_sensitive_keys_are_redacted() -> None:
    entry = _format(password="p", rtsp_url="rtsp://u:p@h", embedding=[1, 2])
    assert entry["password"] == entry["rtsp_url"] == entry["embedding"] == "[redacted]"
