"""Emails and alerts (FR-32, FR-33, §18). Never includes face images or embeddings."""

import logging
from typing import Any

from celery import shared_task

from app.domain.settings import service as settings_service
from app.services import email, teams
from app.worker import runtime

logger = logging.getLogger(__name__)


def _settings() -> dict[str, Any]:
    async def handle(db: Any) -> dict[str, Any]:
        return await settings_service.resolved(db)

    return runtime.run_with_session(handle)


@shared_task(
    name="app.worker.tasks.notifications.send_password_reset",
    autoretry_for=(OSError,),
    max_retries=3,
    retry_backoff=10,
)
def send_password_reset(recipient: str, link: str) -> bool:
    return email.send_email(
        [recipient],
        "FaceTrack password reset",
        "A password reset was requested for your FaceTrack account.\n\n"
        f"Open this link within 30 minutes:\n{link}\n\n"
        "If you did not request it, ignore this email.",
    )


@shared_task(
    name="app.worker.tasks.notifications.send_alert",
    autoretry_for=(OSError,),
    max_retries=5,
    retry_backoff=10,
)
def send_alert(title: str, text: str) -> dict[str, bool]:
    """Admin alert by email and Teams (camera offline, engine failure)."""
    values = _settings()
    sent_email = email.send_email(list(values["notifications.alert_emails"]), f"[FaceTrack] {title}", text)
    sent_teams = False
    try:
        sent_teams = teams.post_message(str(values["notifications.teams_webhook_url"]), title, text)
    except Exception as exc:  # one channel failing must not block the other
        logger.warning("teams alert failed", extra={"error": type(exc).__name__})
    if not (sent_email or sent_teams):
        logger.warning("alert not delivered: no channel configured", extra={"title": title})
    return {"email": sent_email, "teams": sent_teams}


@shared_task(name="app.worker.tasks.notifications.run_due_notifications")
def run_due_notifications() -> int:
    """Scheduled daily summary and report emails. Nothing is scheduled until the reports module exists."""
    return 0
