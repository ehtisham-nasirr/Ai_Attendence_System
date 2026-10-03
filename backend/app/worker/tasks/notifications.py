"""Emails and alerts (FR-32, FR-33, §18). Never includes face images or embeddings."""

import logging
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from celery import shared_task
from facetrack_common.models import Employee
from facetrack_common.settings_keys import ReportSchedule

from app.core.redis import get_sync_redis
from app.core.security import DataScope
from app.domain.notifications import service as notification_service
from app.domain.settings import service as settings_service
from app.schemas.report import ReportFilters
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


@shared_task(
    name="app.worker.tasks.notifications.confirm_checkin",
    autoretry_for=(OSError,),
    max_retries=3,
    retry_backoff=10,
)
def confirm_checkin(employee_id: int, work_date: str, checkin_text: str) -> bool:
    """FR-33: "You checked in at 09:05 at Main entrance", once per employee per work day."""
    values = _settings()
    if not values["notifications.checkin_confirmation"]:
        return False
    if not get_sync_redis().set(f"checkin_notice:{employee_id}:{work_date}", "1", nx=True, ex=2 * 86400):
        return False

    async def recipient(db: Any) -> tuple[str | None, str]:
        employee = await db.get(Employee, employee_id)
        return (employee.email, employee.full_name) if employee else (None, "")

    address, name = runtime.run_with_session(recipient)
    if not address:
        return False
    return email.send_email(
        [address],
        "FaceTrack check-in recorded",
        f"Hello {name},\n\nYour check-in was recorded at {checkin_text}.\n\n"
        "If this is wrong, request a correction in the FaceTrack portal (My attendance).",
    )


@shared_task(
    name="app.worker.tasks.notifications.send_scheduled_report",
    autoretry_for=(OSError,),
    max_retries=3,
    retry_backoff=30,
)
def send_scheduled_report(schedule: dict[str, Any], date_from: str, date_to: str) -> bool:
    """FR-32 scheduled report email with the Excel/PDF attached (whole organisation, or one department)."""
    from app.worker.tasks.reports import CONTENT_TYPES, file_name, render_report  # noqa: PLC0415

    spec = ReportSchedule.model_validate(schedule)
    filters = ReportFilters(
        date_from=date.fromisoformat(date_from),
        date_to=date.fromisoformat(date_to),
        department_id=spec.department_id,
    )

    async def build(db: Any) -> tuple[Any, bytes]:
        return await render_report(
            db, spec.report_type, filters, spec.format, DataScope(all_employees=True), "FaceTrack schedule"
        )

    report, data = runtime.run_with_session(build)
    return email.send_email(
        list(spec.recipients),
        f"FaceTrack {report.title} {filters.date_from:%d %b %Y}"
        + ("" if filters.date_from == filters.date_to else f" to {filters.date_to:%d %b %Y}"),
        f"{report.title}: {report.total_rows} rows. The {spec.format.upper()} file is attached.",
        [(file_name(spec.report_type, filters, spec.format), data, CONTENT_TYPES[spec.format])],
    )


@shared_task(name="app.worker.tasks.notifications.send_daily_summary")
def send_daily_summary() -> int:
    values = _settings()

    async def build(db: Any) -> list[notification_service.Email]:
        return await notification_service.daily_summary_emails(db, list(values["notifications.hr_emails"]))

    sent = 0
    for message in runtime.run_with_session(build):
        sent += int(email.send_email(message.recipients, message.subject, message.text))
    return sent


@shared_task(name="app.worker.tasks.notifications.run_due_notifications")
def run_due_notifications() -> list[str]:
    """Every 5 minutes: queues the daily summary and scheduled reports that are due (once each)."""
    from app.worker.tasks.integration import due_today  # noqa: PLC0415

    values = _settings()
    now = datetime.now(UTC)
    timezone = str(values["general.timezone"])
    queued: list[str] = []
    if values["notifications.daily_summary_enabled"] and due_today(
        "daily_summary", str(values["notifications.daily_summary_time"]), timezone, now
    ):
        send_daily_summary.delay()
        queued.append("daily_summary")
    local_now = now.astimezone(ZoneInfo(timezone))
    for raw in values["notifications.report_schedules"]:
        schedule = ReportSchedule.model_validate(raw)
        if not notification_service.schedulable(schedule):
            logger.warning("scheduled report skipped: employee history needs an employee")
            continue
        period = notification_service.due_period(schedule, local_now)
        if period is None:
            continue
        if get_sync_redis().set(f"ran:report:{period.key}", "1", nx=True, ex=40 * 86400):
            send_scheduled_report.delay(
                schedule.model_dump(mode="json"), period.date_from.isoformat(), period.date_to.isoformat()
            )
            queued.append(period.key)
    return queued
