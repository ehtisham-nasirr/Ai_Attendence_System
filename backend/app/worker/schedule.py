"""Celery Beat schedule — the only place scheduled jobs are defined (standards/02).

Jobs run often and decide inside the domain whether anything is due, so business times (day close,
payroll push, HR sync, daily summary) stay in the `settings` table and take effect without restarts.
"""

from typing import Any

from celery.schedules import crontab


def beat_schedule() -> dict[str, dict[str, Any]]:
    return {
        "close-due-days": {
            "task": "app.worker.tasks.attendance.close_due_days",
            "schedule": crontab(minute="*/10"),
        },
        "sync-camera-status": {"task": "app.worker.tasks.cameras.sync_camera_status", "schedule": 30.0},
        "ensure-event-partitions": {
            "task": "app.worker.tasks.maintenance.ensure_event_partitions",
            "schedule": crontab(minute=7, hour="*/6"),
        },
        "trim-event-stream": {
            "task": "app.worker.tasks.maintenance.trim_event_stream",
            "schedule": crontab(minute=17),
        },
        "retention": {
            "task": "app.worker.tasks.maintenance.apply_retention",
            "schedule": crontab(minute=37, hour="*"),
        },
        "cleanup-temp-imports": {
            "task": "app.worker.tasks.maintenance.cleanup_temp_files",
            "schedule": crontab(minute=47, hour="*/3"),
        },
        "scheduled-integrations": {
            "task": "app.worker.tasks.integration.run_due_integrations",
            "schedule": crontab(minute="*/5"),
        },
        "scheduled-notifications": {
            "task": "app.worker.tasks.notifications.run_due_notifications",
            "schedule": crontab(minute="*/5"),
        },
    }
