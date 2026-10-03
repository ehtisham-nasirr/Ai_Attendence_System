"""The recognition-event contract (requirements §10.2) — the ONLY definition.

The engine publishes one event per decided track to the Redis stream `recognition.events`
(see `constants.RECOGNITION_EVENTS_STREAM`); the backend validates every message against
`RecognitionEvent` and dead-letters anything invalid.

Fields beyond §10.2 (`schema_version`, `model_name`, `engine_node`, `embedding_encrypted`, `bbox`)
are additive and optional for consumers (docs/open-questions.md Q8). Never remove or rename a field.
"""

from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

EVENT_SCHEMA_VERSION = 1
STREAM_PAYLOAD_FIELD = "payload"

EngineEventStatus = Literal["recognized", "unknown"]


class RecognitionEvent(BaseModel):
    """One decided face track from one camera."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    event_id: UUID
    camera_id: int = Field(gt=0)
    employee_code: str | None = Field(default=None, min_length=1, max_length=64)
    status: EngineEventStatus
    # Cosine similarity of the decision (mean over the winning votes, or best score for unknowns).
    confidence: float = Field(ge=-1.0, le=1.0)
    liveness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    track_id: int = Field(ge=0)
    captured_at: AwareDatetime
    snapshot_path: str | None = Field(default=None, max_length=512)
    model_name: str = Field(min_length=1, max_length=64)
    engine_node: str = Field(min_length=1, max_length=64)
    # AES-256-GCM ciphertext (base64) of the best crop's embedding; only sent for unknown faces (FR-17).
    embedding_encrypted: str | None = Field(default=None, max_length=8192)
    # Face box of the best crop, normalised to the full frame: (x, y, width, height) in [0, 1].
    bbox: tuple[float, float, float, float] | None = None

    @field_validator("captured_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("bbox")
    @classmethod
    def _bbox_normalised(
        cls, value: tuple[float, float, float, float] | None
    ) -> tuple[float, float, float, float] | None:
        if value is not None and not all(0.0 <= v <= 1.0 for v in value):
            raise ValueError("bbox values must be normalised to [0, 1]")
        return value

    @model_validator(mode="after")
    def _check_status_fields(self) -> Self:
        if self.status == "recognized" and self.employee_code is None:
            raise ValueError("a recognized event must carry employee_code")
        if self.status == "unknown" and self.employee_code is not None:
            raise ValueError("an unknown event must not carry employee_code")
        return self

    def to_stream_fields(self) -> dict[str, str]:
        """Serialises the event for `XADD recognition.events * payload <json>`."""
        return {STREAM_PAYLOAD_FIELD: self.model_dump_json()}

    @classmethod
    def from_stream_fields(cls, fields: dict[str, str] | dict[bytes, bytes]) -> "RecognitionEvent":
        """Parses a stream entry; raises `pydantic.ValidationError` or `KeyError` if invalid."""
        decoded = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in fields.items()
        }
        return cls.model_validate_json(decoded[STREAM_PAYLOAD_FIELD])
