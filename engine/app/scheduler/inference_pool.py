"""Shared CPU inference worker pool (requirements §10.4, standards/17 §4).

- Separate worker processes (no GIL contention), each with a fixed thread budget and optional core pinning.
- Two bounded request lanes: HIGH (entrance cameras, enrollment) is always served before LOW (general).
- Every queue has a fixed `maxsize`. Overflow policy: a full request lane rejects the new request
  (`submit` returns False and the caller skips that frame or retries the embedding later); a full
  reply queue drops the result (the caller's request times out). Nothing queues without a limit.
- Embedding requests are micro-batched (<= 8 crops, <= 50 ms wait while no HIGH work is waiting).
- Each worker holds the FAISS gallery and matches right after embedding.
"""

import logging
import multiprocessing as mp
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from multiprocessing.queues import Queue as MPQueue
from multiprocessing.sharedctypes import SynchronizedArray
from typing import Any

import numpy as np
import numpy.typing as npt
import psutil

from app.config import EngineSettings
from app.gallery.index import GalleryIndex, GallerySnapshot, MatchCandidate
from app.models.base import FaceDetection, ImageBGR
from app.pipeline.enrollment import EnrollOutcome, EnrollRules, validate_and_embed

logger = logging.getLogger(__name__)

API_REPLY_SLOT = 0  # reply queue of the engine API process; camera slots start at 1
_STATS_FIELDS = 3  # tasks_done, busy_seconds, heartbeat (monotonic)


class TaskKind(StrEnum):
    DETECT = "detect"
    EMBED = "embed"
    LIVENESS = "liveness"
    ENROLL = "enroll"


@dataclass
class InferenceTask:
    kind: TaskKind
    request_id: int
    reply_slot: int
    submitted_at: float = field(default_factory=time.monotonic)
    image: ImageBGR | None = None
    crops: list[ImageBGR] | None = None
    score_threshold: float = 0.6
    enroll_rules: EnrollRules | None = None


@dataclass
class InferenceResult:
    kind: TaskKind
    request_id: int
    ok: bool
    error: str | None = None
    detections: list[FaceDetection] | None = None
    embeddings: npt.NDArray[np.float32] | None = None
    matches: list[list[MatchCandidate]] | None = None
    real_score: float | None = None
    enroll: EnrollOutcome | None = None
    model_name: str | None = None
    queue_ms: float = 0.0
    run_ms: float = 0.0


@dataclass
class PoolQueues:
    """The queues shared with child processes. They must be created before the children start."""

    high: "MPQueue[InferenceTask]"
    low: "MPQueue[InferenceTask]"
    replies: "list[MPQueue[InferenceResult]]"


class PoolClient:
    """Submits tasks to the pool and collects replies for one reply slot (one camera or the API)."""

    def __init__(self, queues: PoolQueues, slot: int) -> None:
        self._queues = queues
        self.slot = slot
        self._next_id = 1

    def new_request_id(self) -> int:
        request_id = self._next_id
        self._next_id += 1
        return request_id

    def submit(self, task: InferenceTask, high_priority: bool) -> bool:
        """Non-blocking. Returns False when the lane is full (the request is dropped by design)."""
        lane = self._queues.high if high_priority else self._queues.low
        try:
            lane.put_nowait(task)
        except queue.Full:
            return False
        return True

    def poll(self, max_items: int = 64) -> list[InferenceResult]:
        results = []
        reply_queue = self._queues.replies[self.slot]
        for _ in range(max_items):
            try:
                results.append(reply_queue.get_nowait())
            except queue.Empty:
                break
        return results

    def wait(self, timeout: float) -> InferenceResult | None:
        try:
            return self._queues.replies[self.slot].get(timeout=timeout)
        except queue.Empty:
            return None


# --------------------------------------------------------------------------------------------
# Worker process
# --------------------------------------------------------------------------------------------


def _next_task(queues: PoolQueues, stashed: list[InferenceTask]) -> tuple[InferenceTask | None, bool]:
    if stashed:
        return stashed.pop(), True
    try:
        return queues.high.get_nowait(), True
    except queue.Empty:
        pass
    try:
        # Short wait on the LOW lane, so HIGH work never waits more than ~10 ms.
        return queues.low.get(timeout=0.01), False
    except queue.Empty:
        return None, False


def _collect_embed_batch(
    first: InferenceTask,
    lane: "MPQueue[InferenceTask]",
    other_lane: "MPQueue[InferenceTask]",
    max_crops: int,
    wait_s: float,
    stashed: list[InferenceTask],
) -> list[InferenceTask]:
    batch = [first]
    count = len(first.crops or [])
    deadline = time.monotonic() + wait_s
    while count < max_crops and time.monotonic() < deadline:
        try:
            task = lane.get_nowait()
        except queue.Empty:
            if not other_lane.empty():
                break  # don't hold other work to fill a batch
            time.sleep(0.002)
            continue
        if task.kind != TaskKind.EMBED or count + len(task.crops or []) > max_crops:
            stashed.append(task)
            break
        batch.append(task)
        count += len(task.crops or [])
    return batch


def worker_main(
    worker_id: int,
    settings: EngineSettings,
    cores: list[int] | None,
    queues: PoolQueues,
    control: "MPQueue[tuple[str, Any]]",
    stats: SynchronizedArray,  # type: ignore[type-arg]
) -> None:
    """Entry point of one inference worker process."""
    from facetrack_common.jsonlog import configure_logging  # noqa: PLC0415

    configure_logging("engine-worker", settings.log_level)
    if cores:
        os.sched_setaffinity(0, cores)
    import cv2  # noqa: PLC0415

    cv2.setNumThreads(settings.threads_per_worker)

    from app.models.factory import build_detector, build_embedder, build_liveness  # noqa: PLC0415

    detector = build_detector(settings, settings.threads_per_worker)
    embedder = build_embedder(settings, settings.threads_per_worker)
    liveness = build_liveness(settings, settings.threads_per_worker)
    gallery: GalleryIndex | None = None
    stashed: list[InferenceTask] = []
    logger.info("inference worker ready", extra={"worker_id": worker_id, "cores": cores})

    while True:
        stats[worker_id * _STATS_FIELDS + 2] = time.monotonic()
        try:
            command, payload = control.get_nowait()
            if command == "stop":
                return
            if command == "gallery":
                snapshot: GallerySnapshot = payload
                if snapshot.model_name != embedder.name:
                    logger.error(
                        "gallery model mismatch; ignoring", extra={"gallery_model": snapshot.model_name}
                    )
                else:
                    gallery = GalleryIndex(snapshot)
        except queue.Empty:
            pass

        task, from_high = _next_task(queues, stashed)
        if task is None:
            continue
        started = time.monotonic()
        tasks = [task]
        if task.kind == TaskKind.EMBED:
            lane, other = (queues.high, queues.low) if from_high else (queues.low, queues.high)
            tasks = _collect_embed_batch(
                task, lane, other, settings.embed_batch_max, settings.embed_batch_wait_ms / 1000, stashed
            )
        try:
            results = _run(tasks, detector, embedder, liveness, gallery)
        except Exception as exc:  # one bad task must never kill the worker
            logger.exception("inference task failed", extra={"worker_id": worker_id, "kind": task.kind})
            results = [
                InferenceResult(t.kind, t.request_id, ok=False, error=type(exc).__name__) for t in tasks
            ]
        run_ms = (time.monotonic() - started) * 1000
        for item, result in zip(tasks, results, strict=True):
            result.queue_ms = (started - item.submitted_at) * 1000
            result.run_ms = run_ms
            try:
                queues.replies[item.reply_slot].put_nowait(result)
            except queue.Full:
                logger.warning("reply queue full; result dropped", extra={"slot": item.reply_slot})
        stats[worker_id * _STATS_FIELDS] += len(tasks)
        stats[worker_id * _STATS_FIELDS + 1] += run_ms / 1000


def _run(
    tasks: list[InferenceTask],
    detector: Any,
    embedder: Any,
    liveness: Any,
    gallery: GalleryIndex | None,
) -> list[InferenceResult]:
    first = tasks[0]
    if first.kind == TaskKind.DETECT:
        detections = detector.detect(_require(first.image), first.score_threshold)
        return [InferenceResult(first.kind, first.request_id, ok=True, detections=detections)]
    if first.kind == TaskKind.LIVENESS:
        if liveness is None:
            return [InferenceResult(first.kind, first.request_id, ok=False, error="liveness_unavailable")]
        score = liveness.real_score(_require(first.image))
        return [InferenceResult(first.kind, first.request_id, ok=True, real_score=score)]
    if first.kind == TaskKind.ENROLL:
        outcome = validate_and_embed(_require(first.image), detector, embedder, _require(first.enroll_rules))
        return [
            InferenceResult(first.kind, first.request_id, ok=True, enroll=outcome, model_name=embedder.name)
        ]

    # EMBED: one forward pass over all crops of the micro-batch, then FAISS matching.
    crops = [crop for task in tasks for crop in (task.crops or [])]
    embeddings = embedder.embed(crops)
    matches = gallery.search(embeddings) if gallery is not None else [[] for _ in crops]
    results, offset = [], 0
    for task in tasks:
        size = len(task.crops or [])
        results.append(
            InferenceResult(
                task.kind,
                task.request_id,
                ok=True,
                embeddings=embeddings[offset : offset + size],
                matches=matches[offset : offset + size],
                model_name=embedder.name,
            )
        )
        offset += size
    return results


def _require[T](value: T | None) -> T:
    if value is None:
        raise ValueError("task is missing a required field")
    return value


# --------------------------------------------------------------------------------------------
# Pool manager (engine main process)
# --------------------------------------------------------------------------------------------


def parse_cores(spec: str) -> list[int]:
    """'2-5,8' -> [2, 3, 4, 5, 8]."""
    cores: list[int] = []
    for part in filter(None, (p.strip() for p in spec.split(","))):
        if "-" in part:
            start, end = part.split("-")
            cores.extend(range(int(start), int(end) + 1))
        else:
            cores.append(int(part))
    return cores


class InferencePool:
    def __init__(self, settings: EngineSettings) -> None:
        self._settings = settings
        self._ctx = mp.get_context("spawn")
        self.queues = PoolQueues(
            high=self._ctx.Queue(maxsize=settings.high_queue_size),
            low=self._ctx.Queue(maxsize=settings.low_queue_size),
            replies=[
                self._ctx.Queue(maxsize=settings.response_queue_size) for _ in range(settings.max_cameras + 1)
            ],
        )
        self._stats = self._ctx.Array("d", settings.inference_workers * _STATS_FIELDS)
        self._workers: list[mp.process.BaseProcess | None] = [None] * settings.inference_workers
        self._controls: list[MPQueue[tuple[str, Any]]] = []
        self._gallery: GallerySnapshot | None = None
        self._lock = threading.Lock()
        self.restarts = 0
        all_cores = parse_cores(settings.inference_cores)
        per_worker = settings.threads_per_worker
        self._core_sets: list[list[int] | None] = [
            all_cores[i * per_worker : (i + 1) * per_worker] or None if all_cores else None
            for i in range(settings.inference_workers)
        ]

    def start(self) -> None:
        for worker_id in range(self._settings.inference_workers):
            self._controls.append(self._ctx.Queue(maxsize=4))
            self._start_worker(worker_id)

    def _start_worker(self, worker_id: int) -> None:
        process = self._ctx.Process(
            target=worker_main,
            name=f"inference-{worker_id}",
            args=(
                worker_id,
                self._settings,
                self._core_sets[worker_id],
                self.queues,
                self._controls[worker_id],
                self._stats,
            ),
            daemon=True,
        )
        process.start()
        self._workers[worker_id] = process
        if self._gallery is not None:
            self._send(worker_id, ("gallery", self._gallery))

    def _send(self, worker_id: int, message: tuple[str, Any]) -> None:
        try:
            self._controls[worker_id].put(message, timeout=5)
        except queue.Full:
            logger.error("worker control queue full", extra={"worker_id": worker_id})

    def publish_gallery(self, snapshot: GallerySnapshot) -> None:
        with self._lock:
            self._gallery = snapshot
            for worker_id in range(len(self._workers)):
                self._send(worker_id, ("gallery", snapshot))

    def client(self, slot: int) -> PoolClient:
        return PoolClient(self.queues, slot)

    def supervise(self) -> None:
        """Restarts dead workers and workers over their memory limit (standards/17 §8)."""
        limit = self._settings.worker_memory_limit_mb * 1024 * 1024
        with self._lock:
            for worker_id, process in enumerate(self._workers):
                if process is None:
                    continue
                restart = not process.is_alive()
                if not restart and process.pid is not None:
                    try:
                        restart = psutil.Process(process.pid).memory_info().rss > limit
                    except psutil.NoSuchProcess:
                        restart = True
                    if restart:
                        logger.warning("worker over memory limit; restarting", extra={"worker_id": worker_id})
                        process.terminate()
                        process.join(timeout=5)
                if restart:
                    self.restarts += 1
                    logger.error("restarting inference worker", extra={"worker_id": worker_id})
                    self._start_worker(worker_id)

    def worker_stats(self) -> list[dict[str, Any]]:
        stats = []
        for worker_id, process in enumerate(self._workers):
            rss = 0.0
            if process is not None and process.pid is not None and process.is_alive():
                try:
                    rss = psutil.Process(process.pid).memory_info().rss / 1024 / 1024
                except psutil.NoSuchProcess:
                    rss = 0.0
            base = worker_id * _STATS_FIELDS
            stats.append(
                {
                    "worker_id": worker_id,
                    "pid": process.pid if process else None,
                    "alive": bool(process and process.is_alive()),
                    "tasks_done": int(self._stats[base]),
                    "busy_seconds": float(self._stats[base + 1]),
                    "rss_mb": round(rss, 1),
                }
            )
        return stats

    def queue_depths(self) -> tuple[int, int]:
        return self.queues.high.qsize(), self.queues.low.qsize()

    def stop(self) -> None:
        for worker_id in range(len(self._workers)):
            self._send(worker_id, ("stop", None))
        for process in self._workers:
            if process is not None:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
