"""Payroll push (FR-35) and HR sync (FR-12, FR-24), run at the times set in Settings."""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from celery import shared_task

from app.core.config import get_settings
from app.core.db import transaction
from app.core.pagination import PageParams
from app.core.redis import get_sync_redis
from app.domain.attendance.rules import parse_hhmm
from app.domain.audit import service as audit
from app.domain.integration import hr_sync, payroll
from app.domain.settings import service as settings_service
from app.services import hr_client, metrics_store
from app.worker import runtime

logger = logging.getLogger(__name__)
WATERMARK_KEY = "integration:payroll_watermark"
MAX_ATTEMPTS = 5  # §12: retried 5 times with backoff
HR_LEAVE_WINDOW = (timedelta(days=30), timedelta(days=90))  # past, future


def _settings() -> dict[str, Any]:
    async def handle(db: Any) -> dict[str, Any]:
        return await settings_service.resolved(db)

    return runtime.run_with_session(handle)


def _watermark() -> datetime:
    raw = get_sync_redis().get(WATERMARK_KEY)
    if raw:
        return datetime.fromisoformat(str(raw))
    # First push (or lost Redis state): resend the last three days; receivers upsert.
    return datetime.now(UTC) - timedelta(days=3)


@shared_task(bind=True, name="app.worker.tasks.integration.push_payroll", max_retries=MAX_ATTEMPTS)
def push_payroll(self: Any, work_date: str | None = None) -> dict[str, Any]:
    """Sends finalised days to the payroll webhook, signed with HMAC-SHA256 (§12).

    `work_date` resends one whole date (manual push); otherwise every day changed since the last
    successful delivery is sent.
    """
    values = _settings()
    url = str(values["integration.payroll_webhook_url"])
    secret = get_settings().payroll_webhook_secret.get_secret_value()
    if not url or not secret:
        logger.warning("payroll push skipped: webhook URL or PAYROLL_WEBHOOK_SECRET not configured")
        return {"sent": 0, "skipped": "not configured"}

    async def collect(db: Any) -> list[Any]:
        if work_date:
            days, _ = await payroll.finalised_for_date(
                db, date.fromisoformat(work_date), PageParams(page=1, page_size=100_000, sort=None)
            )
            return days
        return await payroll.changed_since(db, _watermark(), datetime.now(UTC))

    days = runtime.run_with_session(collect)
    if not days:
        return {"sent": 0}
    payload = payroll.build_payload(days, "manual" if work_date else "scheduled")
    body = payroll.encode(payload)
    try:
        response = httpx.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                payroll.SIGNATURE_HEADER: payroll.sign(body, secret),
                payroll.DELIVERY_HEADER: payload["delivery_id"],
            },
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        attempt = self.request.retries + 1
        logger.warning("payroll push failed", extra={"attempt": attempt, "error": type(exc).__name__})
        if self.request.retries >= MAX_ATTEMPTS:
            metrics_store.increment("payroll_push_failures_total")
            from app.worker.tasks.notifications import send_alert  # noqa: PLC0415

            send_alert.delay(
                "Payroll push failed", f"{len(days)} attendance days could not be delivered: {exc}"
            )
            raise
        raise self.retry(exc=exc, countdown=min(3600, 60 * 2**self.request.retries)) from exc

    if not work_date:
        get_sync_redis().set(WATERMARK_KEY, max(day.updated_at for day in days).isoformat())

    async def record(db: Any) -> None:
        async with transaction(db):
            await audit.record(
                db,
                None,
                "payroll.push",
                "integration",
                payload["delivery_id"],
                new={"days": len(days), "work_date": work_date, "status": response.status_code},
            )

    runtime.run_with_session(record)
    metrics_store.set_value("payroll_push_last_success_timestamp", datetime.now(UTC).timestamp())
    return {"sent": len(days), "delivery_id": payload["delivery_id"]}


@shared_task(name="app.worker.tasks.integration.sync_hr")
def sync_hr() -> dict[str, Any]:
    """FR-12 employee master and FR-24 approved leave from the HR system."""
    values = _settings()
    base_url = str(values["integration.hr_base_url"])
    if not base_url:
        logger.warning("HR sync skipped: integration.hr_base_url is not set")
        return {"skipped": "not configured"}
    today = datetime.now(UTC).date()
    window = (today - HR_LEAVE_WINDOW[0], today + HR_LEAVE_WINDOW[1])
    report = hr_sync.SyncReport()
    try:
        employees = hr_client.fetch_employees(base_url)
        leaves = hr_client.fetch_leaves(base_url, *window)
    except hr_client.HrSystemError as exc:
        logger.error("HR sync failed", extra={"error": str(exc)})
        metrics_store.increment("hr_sync_failures_total")
        from app.worker.tasks.notifications import send_alert  # noqa: PLC0415

        send_alert.delay("HR sync failed", str(exc))
        return {"error": str(exc)}

    async def apply(db: Any) -> None:
        await hr_sync.sync_employees(db, employees, report)
        await hr_sync.sync_leaves(db, leaves, window, report)
        await hr_sync.record_run(db, report)

    runtime.run_with_session(apply)
    metrics_store.set_value("hr_sync_last_success_timestamp", datetime.now(UTC).timestamp())
    logger.info("HR sync finished", extra=report.as_dict())
    return report.as_dict()


def due_today(key: str, at: str, timezone: str, now: datetime) -> bool:
    """True once per local day, after the configured HH:MM (Redis remembers it ran)."""
    local = now.astimezone(ZoneInfo(timezone))
    if local.time() < parse_hhmm(at):
        return False
    return bool(get_sync_redis().set(f"ran:{key}:{local.date().isoformat()}", "1", nx=True, ex=3 * 86400))


@shared_task(name="app.worker.tasks.integration.run_due_integrations")
def run_due_integrations() -> list[str]:
    values = _settings()
    now = datetime.now(UTC)
    timezone = str(values["general.timezone"])
    started = []
    if values["integration.payroll_mode"] == "push" and due_today(
        "payroll_push", str(values["integration.payroll_push_time"]), timezone, now
    ):
        push_payroll.delay()
        started.append("payroll_push")
    if values["integration.hr_sync_enabled"] and due_today(
        "hr_sync", str(values["integration.hr_sync_time"]), timezone, now
    ):
        sync_hr.delay()
        started.append("hr_sync")
    return started
