"""Celery worker package. `celery -A app.worker worker` / `celery -A app.worker beat` (requirements §18)."""

from app.worker.celery_app import celery

__all__ = ["celery"]
