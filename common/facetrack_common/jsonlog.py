"""The project's structured JSON log formatter (standards/09, NFR-13).

Every line carries the service name; callers add tracing fields through `extra=`, e.g.
`logger.info("camera mode changed", extra={"camera_id": 3, "mode": "ACTIVE"})`.
Never pass passwords, tokens, RTSP URLs with credentials, embeddings or images in `extra`.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else on the record came from `extra=`.
_STANDARD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys() | {"message", "asctime", "taskName"}
)

# Keys that must never be logged even if a caller passes them by mistake.
_REDACTED_KEYS = frozenset(
    {"password", "token", "secret", "api_key", "rtsp_url", "embedding", "authorization", "cookie"}
)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            entry[key] = "[redacted]" if key.lower() in _REDACTED_KEYS else value
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(service: str, level: str = "INFO") -> None:
    """Routes all logging to stdout as JSON. Safe to call more than once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
