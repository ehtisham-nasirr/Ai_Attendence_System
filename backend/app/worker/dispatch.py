"""Thin helpers the API uses to enqueue Celery tasks (keeps routers free of Celery details)."""

from typing import Any


def _send(task_name: str, *args: Any, **kwargs: Any) -> None:
    from app.worker.celery_app import celery  # noqa: PLC0415  # avoid importing Celery at API import time

    celery.send_task(task_name, args=args, kwargs=kwargs)


def send_password_reset_email(email: str, link: str) -> None:
    _send("app.worker.tasks.notifications.send_password_reset", email, link)


def start_employee_import(job_id: str, sheet_path: str, zip_path: str | None, actor_id: int) -> None:
    _send("app.worker.tasks.employees.import_employees", job_id, sheet_path, zip_path, actor_id)


def start_report_export(
    job_id: str, report_type: str, params: dict[str, Any], fmt: str, actor_id: int
) -> None:
    _send("app.worker.tasks.reports.export_report", job_id, report_type, params, fmt, actor_id)
