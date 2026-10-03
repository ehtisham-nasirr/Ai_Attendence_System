"""Celery application (Redis broker) and the recognition-event consumer bootstep."""

from celery import Celery, bootsteps

from app.core.config import get_settings
from app.worker.schedule import beat_schedule

_settings = get_settings()
celery = Celery("facetrack", broker=_settings.redis_url.get_secret_value(), backend=None)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=4,
    broker_connection_retry_on_startup=True,
    beat_schedule=beat_schedule(),
    imports=(
        "app.worker.tasks.events",
        "app.worker.tasks.attendance",
        "app.worker.tasks.maintenance",
        "app.worker.tasks.cameras",
        "app.worker.tasks.employees",
        "app.worker.tasks.notifications",
        "app.worker.tasks.reports",
        "app.worker.tasks.integration",
    ),
)


class EventConsumerStep(bootsteps.StartStopStep):
    """Runs the Redis-stream consumer inside each worker node (one consumer per node)."""

    requires = ("celery.worker.components:Pool",)

    def __init__(self, worker: object, **kwargs: object) -> None:
        super().__init__(worker, **kwargs)
        self._consumer: object | None = None

    def start(self, worker: object) -> None:
        from app.worker.consumer import EventStreamConsumer  # noqa: PLC0415

        consumer = EventStreamConsumer()
        consumer.start()
        self._consumer = consumer

    def stop(self, worker: object) -> None:
        if self._consumer is not None:
            self._consumer.stop()  # type: ignore[attr-defined]


celery.steps["worker"].add(EventConsumerStep)
