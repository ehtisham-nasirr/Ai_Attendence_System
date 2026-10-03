"""`process_event`: one recognition event -> stored event + attendance (FR-16, FR-20). Idempotent."""

import logging
from typing import Any

from celery import shared_task
from facetrack_common.crypto import EncryptionError
from facetrack_common.events import RecognitionEvent
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError

from app.domain.recognition import service
from app.services import live, metrics_store
from app.worker import runtime
from app.worker.consumer import ack, dead_letter

logger = logging.getLogger(__name__)


@shared_task(
    name="app.worker.tasks.events.process_event",
    autoretry_for=(OperationalError, DBAPIError, ConnectionError),
    retry_backoff=2,
    retry_backoff_max=60,
    max_retries=5,
)
def process_event(message_id: str, fields: dict[str, Any]) -> str:
    try:
        event = RecognitionEvent.from_stream_fields(fields)
    except (ValidationError, KeyError, ValueError) as exc:
        dead_letter(message_id, fields, f"invalid event: {type(exc).__name__}")
        logger.error("invalid recognition event dead-lettered", extra={"message_id": message_id})
        return "dead-lettered"

    async def handle(db: Any) -> service.ProcessOutcome:
        return await service.process_event(db, event)

    try:
        outcome = runtime.run_with_session(handle)
    except (service.InvalidEvent, EncryptionError) as exc:
        dead_letter(message_id, fields, str(exc) or type(exc).__name__)
        logger.error(
            "recognition event rejected", extra={"event_uuid": str(event.event_id), "error": str(exc)}
        )
        return "dead-lettered"
    # Acknowledge only after the transaction committed (a crash before this line means redelivery).
    ack(message_id)
    if outcome.stored:
        metrics_store.increment("events_processed_total")
        for message_type, data in service.live_messages(event, outcome):
            live.publish_sync(message_type, data)
        if outcome.checkin_text and outcome.employee is not None and outcome.attendance is not None:
            from app.worker.tasks.notifications import confirm_checkin  # noqa: PLC0415

            confirm_checkin.delay(
                outcome.employee.id, outcome.attendance.work_date.isoformat(), outcome.checkin_text
            )
    return "stored" if outcome.stored else "duplicate"
