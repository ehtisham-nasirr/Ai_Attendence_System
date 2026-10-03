"""Base classes and shared field types for API schemas."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, PlainSerializer


def to_utc_z(value: datetime) -> str:
    """ISO 8601 in UTC with `Z` (standards/04)."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


# Every timestamp in a response is UTC with `Z`; the frontend converts to Asia/Karachi for display.
UtcDateTime = Annotated[datetime, PlainSerializer(to_utc_z, return_type=str, when_used="json")]
# Timestamps in requests must carry a timezone.
AwareInput = AwareDatetime


class ApiModel(BaseModel):
    """Output schema, buildable from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    """Request body: unknown fields are rejected, strings stripped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
