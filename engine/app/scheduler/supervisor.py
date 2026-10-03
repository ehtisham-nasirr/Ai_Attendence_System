"""Engine supervisor (main process): camera processes, inference pool, load monitor, gallery, watchdogs.

No frame processing happens here. Background threads only move small status messages, sample
CPU, and restart crashed or hung children (standards/17 §4, §8).
"""

import asyncio
import json
import logging
import multiprocessing as mp
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from multiprocessing.queues import Queue as MPQueue
from typing import Any

import psutil
from facetrack_common.constants import (
    CRYPTO_PURPOSE_CAMERA_URL,
    ENGINE_CONTROL_CHANNEL,
    LIVE_UPDATES_CHANNEL,
    CameraMode,
    CameraRole,
    LoadLevel,
    WsMessageType,
)
from facetrack_common.crypto import Cipher
from facetrack_common.models import Camera
from facetrack_common.schemas.engine import (
    CameraRuntimeStatus,
    CameraSyncResult,
    CameraTestResult,
    EngineHealth,
    GalleryReloadResult,
    LoadStatus,
    WorkerLoad,
)
from facetrack_common.settings_keys import default_settings
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app import metrics
from app.capture.decoder import DecoderSettings
from app.capture.snapshot import grab_snapshot
from app.config import EngineSettings
from app.db import create_session_factory
from app.gallery.loader import load_gallery
from app.models.factory import EMBEDDER_DIMS
from app.pipeline.camera_worker import CameraStatusReport, run_camera_process
from app.pipeline.enrollment import EnrollOutcome, EnrollRules
from app.scheduler.camera_config import CameraRuntimeConfig, load_camera_configs, load_settings
from app.scheduler.inference_pool import API_REPLY_SLOT, InferencePool, InferenceTask, TaskKind
from app.scheduler.ladder import DegradationLadder, LadderLimits

logger = logging.getLogger(__name__)

# A camera process that sends no status for this long is considered hung and restarted.
_HUNG_AFTER_S = 30.0
_CAMERA_RESTART_BACKOFF_MAX_S = 60.0


class EngineUnavailableError(Exception):
    """The inference pool did not answer in time."""


@dataclass
class _CameraHandle:
    config: CameraRuntimeConfig
    fingerprint: str
    slot: int
    process: mp.process.BaseProcess
    stop_event: Any
    started_at: float
    restarts: int = 0
    next_restart_at: float = 0.0
    last_report_at: float = field(default_factory=time.monotonic)
    report: CameraStatusReport | None = None


class _ApiGateway:
    """Lets async API handlers wait for pool replies on the API reply slot without blocking the loop."""

    def __init__(self, pool: InferencePool) -> None:
        self._client = pool.client(API_REPLY_SLOT)
        self._futures: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Future[Any]]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, name="api-replies", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _pump(self) -> None:
        while not self._stop.is_set():
            result = self._client.wait(timeout=0.5)
            if result is None:
                continue
            with self._lock:
                entry = self._futures.pop(result.request_id, None)
            if entry is not None:
                loop, future = entry
                loop.call_soon_threadsafe(_resolve, future, result)

    async def run(self, task: InferenceTask, wait_s: float) -> Any:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        with self._lock:
            task.request_id = self._client.new_request_id()
            self._futures[task.request_id] = (loop, future)
        if not self._client.submit(task, high_priority=True):
            with self._lock:
                self._futures.pop(task.request_id, None)
            raise EngineUnavailableError("inference queue is full")
        try:
            return await asyncio.wait_for(future, wait_s)
        except TimeoutError as exc:
            with self._lock:
                self._futures.pop(task.request_id, None)
            raise EngineUnavailableError("inference timed out") from exc


def _resolve(future: "asyncio.Future[Any]", result: Any) -> None:
    if not future.done():
        future.set_result(result)


class EngineSupervisor:
    def __init__(self, settings: EngineSettings) -> None:
        self.settings = settings
        self.cipher = Cipher.from_base64(settings.encryption_key.get_secret_value())
        self._db_engine: AsyncEngine
        self._sessions: async_sessionmaker[AsyncSession]
        self._db_engine, self._sessions = create_session_factory(settings.database_url.get_secret_value())
        self._ctx = mp.get_context("spawn")
        self.pool = InferencePool(settings)
        self._gateway = _ApiGateway(self.pool)
        self._level = self._ctx.Value("i", int(LoadLevel.NORMAL))
        self._status_queue: MPQueue[CameraStatusReport] = self._ctx.Queue(maxsize=settings.status_queue_size)
        self._cameras: dict[int, _CameraHandle] = {}
        self._refused: dict[int, str] = {}
        self._free_slots = list(range(settings.max_cameras, 0, -1))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._cpu_percent = 0.0
        self.gallery_version = 0
        self.gallery_counts = (0, 0)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis: Any = None
        self._settings_cache: dict[str, Any] = default_settings()
        self._started_monotonic = time.monotonic()
        self._ladder = DegradationLadder(self._ladder_limits(), time.monotonic())

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        import redis  # noqa: PLC0415

        self._loop = asyncio.get_running_loop()
        self._redis = redis.Redis.from_url(
            self.settings.redis_url.get_secret_value(), socket_timeout=3, socket_connect_timeout=3
        )
        self.pool.start()
        self._gateway.start()
        self._settings_cache = await load_settings(self._sessions)
        self._ladder.limits = self._ladder_limits()
        await self.reload_gallery()
        await self.sync_cameras()
        for target, name in (
            (self._collect_status, "status-collector"),
            (self._monitor_load, "load-monitor"),
            (self._watch_children, "watchdog"),
            (self._listen_control, "control-listener"),
        ):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        logger.info("engine started", extra={"node": self.settings.node_name})

    async def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for camera_id in list(self._cameras):
                self._stop_camera(camera_id)
        self._gateway.stop()
        self.pool.stop()
        await self._db_engine.dispose()

    def _ladder_limits(self) -> LadderLimits:
        s = self._settings_cache
        return LadderLimits(
            cpu_high_pct=float(s["engine.ladder_cpu_high_pct"]),
            cpu_high_s=float(s["engine.ladder_cpu_high_s"]),
            lag_high_s=float(s["engine.ladder_lag_high_s"]),
            cpu_low_pct=float(s["engine.ladder_cpu_low_pct"]),
            cpu_low_s=float(s["engine.ladder_cpu_low_s"]),
        )

    # ------------------------------------------------------------------ gallery (FR-19)

    async def reload_gallery(self) -> GalleryReloadResult:
        model = self.settings.embedder
        self.gallery_version += 1
        snapshot = await load_gallery(
            self._sessions, self.cipher, model, EMBEDDER_DIMS[model], self.gallery_version
        )
        await asyncio.to_thread(self.pool.publish_gallery, snapshot)
        self.gallery_counts = (snapshot.employee_count, len(snapshot.employee_codes))
        metrics.GALLERY_EMPLOYEES.set(snapshot.employee_count)
        metrics.GALLERY_SIZE.set(len(snapshot.employee_codes))
        logger.info(
            "gallery reloaded",
            extra={"version": snapshot.version, "employees": snapshot.employee_count, "model": model},
        )
        return GalleryReloadResult(
            model_name=model,
            employees=snapshot.employee_count,
            embeddings=len(snapshot.employee_codes),
            version=snapshot.version,
        )

    # ------------------------------------------------------------------ cameras

    async def sync_cameras(self) -> CameraSyncResult:
        self._settings_cache = await load_settings(self._sessions)
        self._ladder.limits = self._ladder_limits()
        configs, refused = await load_camera_configs(
            self._sessions,
            self.cipher,
            self.settings.node_name,
            self.settings.embedder,
            liveness_available=self.settings.liveness_model_path is not None,
        )
        wanted = {c.camera_id: c for c in configs}
        result = CameraSyncResult(started=[], stopped=[], restarted=[], unchanged=[])
        with self._lock:
            self._refused = refused
            for camera_id in list(self._cameras):
                if camera_id not in wanted:
                    self._stop_camera(camera_id)
                    result.stopped.append(camera_id)
            for camera_id, config in wanted.items():
                handle = self._cameras.get(camera_id)
                if handle is None:
                    if self._start_camera(config):
                        result.started.append(camera_id)
                elif handle.fingerprint != config.fingerprint():
                    self._stop_camera(camera_id)
                    self._start_camera(config)
                    result.restarted.append(camera_id)
                else:
                    result.unchanged.append(camera_id)
        logger.info("cameras synced", extra=result.model_dump())
        return result

    def _start_camera(self, config: CameraRuntimeConfig, restarts: int = 0) -> bool:
        if not self._free_slots:
            logger.error("max cameras reached on this node", extra={"camera_id": config.camera_id})
            self._refused[config.camera_id] = "node camera limit reached"
            return False
        slot = self._free_slots.pop()
        stop_event = self._ctx.Event()
        process = self._ctx.Process(
            target=run_camera_process,
            name=f"camera-{config.camera_id}",
            args=(config, self.settings, self.pool.client(slot), self._level, self._status_queue, stop_event),
            daemon=True,
        )
        process.start()
        self._cameras[config.camera_id] = _CameraHandle(
            config, config.fingerprint(), slot, process, stop_event, time.monotonic(), restarts
        )
        return True

    def _stop_camera(self, camera_id: int) -> None:
        handle = self._cameras.pop(camera_id, None)
        if handle is None:
            return
        handle.stop_event.set()
        handle.process.join(timeout=8)
        if handle.process.is_alive():
            handle.process.kill()
            handle.process.join(timeout=2)
        self._drain_reply_slot(handle.slot)
        self._free_slots.append(handle.slot)
        for mode in CameraMode:
            metrics.CAMERA_MODE.labels(str(camera_id), mode.value).set(0)

    def _drain_reply_slot(self, slot: int) -> None:
        self.pool.client(slot).poll(max_items=1_000)

    def camera_statuses(self) -> list[CameraRuntimeStatus]:
        statuses = []
        with self._lock:
            for camera_id, handle in sorted(self._cameras.items()):
                report = handle.report
                alive = handle.process.is_alive()
                statuses.append(
                    CameraRuntimeStatus(
                        camera_id=camera_id,
                        name=handle.config.name,
                        role=handle.config.role,
                        mode=report.mode if report else CameraMode.IDLE,
                        connected=bool(report and report.connected and alive),
                        fps_target=report.fps_target if report else 0.0,
                        fps_actual=report.fps_actual if report else 0.0,
                        last_frame_at=report.last_frame_at if report else None,
                        lag_seconds=report.lag_seconds if report else 0.0,
                        faces_today=report.faces_today if report else 0,
                        restarts=handle.restarts + (report.reconnects if report else 0),
                        last_error=report.last_error if report else None,
                        process_alive=alive,
                    )
                )
            for camera_id, error in sorted(self._refused.items()):
                if camera_id not in self._cameras:
                    statuses.append(
                        CameraRuntimeStatus(
                            camera_id=camera_id,
                            name="",
                            role=CameraRole.GENERAL,
                            mode=CameraMode.PAUSED,
                            connected=False,
                            fps_target=0.0,
                            fps_actual=0.0,
                            lag_seconds=0.0,
                            faces_today=0,
                            restarts=0,
                            last_error=error,
                            process_alive=False,
                        )
                    )
        return statuses

    async def test_camera(self, camera_id: int, use_substream: bool) -> CameraTestResult:
        async with self._sessions() as session:
            camera = (await session.scalars(select(Camera).where(Camera.id == camera_id))).first()
        if camera is None:
            return CameraTestResult(ok=False, error="camera not found")
        token = camera.substream_url_encrypted if use_substream else camera.rtsp_url_encrypted
        if token is None:
            return CameraTestResult(ok=False, error="camera has no sub-stream configured")
        url = self.cipher.decrypt_str(token, CRYPTO_PURPOSE_CAMERA_URL)
        decoder_settings = DecoderSettings(
            open_timeout_s=self.settings.stream_open_timeout_s,
            read_timeout_s=self.settings.stream_read_timeout_s,
            threads=1,
            reconnect_min_s=self.settings.reconnect_min_s,
            reconnect_max_s=self.settings.reconnect_max_s,
            allow_file_sources=self.settings.allow_file_sources,
        )
        # Decoding is blocking work: run it in a thread, never on the event loop.
        return await asyncio.to_thread(
            grab_snapshot, url, decoder_settings, self.settings.snapshot_jpeg_quality
        )

    # ------------------------------------------------------------------ enrollment (FR-9)

    async def embed_image(self, image: Any, wait_s: float = 15.0) -> EnrollOutcome:
        s = self._settings_cache
        rules = EnrollRules(
            detector_min_score=float(s["recognition.detector_min_score"]),
            min_face_width_px=int(s["enrollment.min_face_width_px"]),
            min_quality=float(s["enrollment.min_quality"]),
            min_blur_variance=float(s["enrollment.min_blur_variance"]),
        )
        task = InferenceTask(TaskKind.ENROLL, 0, API_REPLY_SLOT, image=image, enroll_rules=rules)
        result = await self._gateway.run(task, wait_s)
        if not result.ok or result.enroll is None:
            raise EngineUnavailableError(result.error or "enrollment failed")
        outcome: EnrollOutcome = result.enroll
        return outcome

    # ------------------------------------------------------------------ load and health

    def load_status(self) -> LoadStatus:
        high, low = self.pool.queue_depths()
        uptime = max(time.monotonic() - self._started_monotonic, 1.0)
        with self._lock:
            reports = [h.report for h in self._cameras.values() if h.report]
        return LoadStatus(
            node=self.settings.node_name,
            cpu_percent=self._cpu_percent,
            level=self._ladder.level,
            level_since=datetime.now(UTC) - timedelta(seconds=time.monotonic() - self._ladder.since),
            max_lag_seconds=max((r.lag_seconds for r in reports), default=0.0),
            high_queue_depth=high,
            low_queue_depth=low,
            deferred_embeddings=sum(r.deferred_embeddings for r in reports),
            workers=[
                WorkerLoad(
                    worker_id=w["worker_id"],
                    pid=w["pid"],
                    alive=w["alive"],
                    tasks_done=w["tasks_done"],
                    busy_ratio=round(min(1.0, w["busy_seconds"] / uptime), 3),
                    rss_mb=w["rss_mb"],
                )
                for w in self.pool.worker_stats()
            ],
        )

    async def health(self) -> EngineHealth:
        database_ok = redis_ok = True
        try:
            async with self._sessions() as session:
                await session.execute(text("SELECT 1"))
        except Exception:  # health must report, not raise
            database_ok = False
        try:
            await asyncio.to_thread(self._redis.ping)
        except Exception:
            redis_ok = False
        workers_alive = sum(1 for w in self.pool.worker_stats() if w["alive"])
        with self._lock:
            running = sum(1 for h in self._cameras.values() if h.process.is_alive())
        ok = workers_alive == self.settings.inference_workers and database_ok and redis_ok
        return EngineHealth(
            node=self.settings.node_name,
            status="ok" if ok else "degraded",
            workers_alive=workers_alive,
            cameras_running=running,
            gallery_version=self.gallery_version,
            redis_ok=redis_ok,
            database_ok=database_ok,
        )

    # ------------------------------------------------------------------ background threads

    def _collect_status(self) -> None:
        while not self._stop.is_set():
            try:
                report = self._status_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._lock:
                handle = self._cameras.get(report.camera_id)
                if handle is None:
                    continue
                previous = handle.report
                handle.report = report
                handle.last_report_at = time.monotonic()
            self._export_metrics(report)
            changed = (
                previous is None or previous.mode != report.mode or previous.connected != report.connected
            )
            if changed:
                self._publish_live(
                    WsMessageType.CAMERA_STATUS_CHANGED,
                    {
                        "camera_id": report.camera_id,
                        "mode": report.mode.value,
                        "connected": report.connected,
                        "fps_actual": report.fps_actual,
                        "engine_node": self.settings.node_name,
                    },
                )

    def _export_metrics(self, report: CameraStatusReport) -> None:
        camera = str(report.camera_id)
        for mode in CameraMode:
            metrics.CAMERA_MODE.labels(camera, mode.value).set(1 if mode == report.mode else 0)
        metrics.CAMERA_CONNECTED.labels(camera).set(1 if report.connected else 0)
        metrics.CAMERA_FPS.labels(camera).set(report.fps_actual)
        metrics.CAMERA_FPS_TARGET.labels(camera).set(report.fps_target)
        metrics.CAMERA_LAG.labels(camera).set(report.lag_seconds)
        metrics.CAMERA_BUFFERED.labels(camera).set(report.buffered_events)
        metrics.CAMERA_DEFERRED.labels(camera).set(report.deferred_embeddings)
        metrics.CAMERA_LOST.labels(camera).set(report.lost_events)
        if report.last_frame_at is not None:
            age = (datetime.now(UTC) - report.last_frame_at).total_seconds()
            metrics.CAMERA_FRAME_AGE.labels(camera).set(max(0.0, age))
        for name, value in report.counters.items():
            metrics.CAMERA_COUNTS.labels(camera, name).inc(value)
        for step, samples in report.timings_ms.items():
            for sample in samples:
                metrics.STEP_MS.labels(step).observe(sample)

    def _monitor_load(self) -> None:
        psutil.cpu_percent(interval=None)  # prime the counter
        while not self._stop.wait(float(self._settings_cache.get("engine.ladder_sample_s", 5.0))):
            self._cpu_percent = psutil.cpu_percent(interval=None)
            with self._lock:
                lags = [h.report.lag_seconds for h in self._cameras.values() if h.report]
            max_lag = max(lags, default=0.0)
            previous = self._ladder.level
            level = self._ladder.update(time.monotonic(), self._cpu_percent, max_lag)
            self._level.value = int(level)
            metrics.CPU_PERCENT.set(self._cpu_percent)
            metrics.LOAD_LEVEL.set(int(level))
            metrics.MAX_LAG.set(max_lag)
            high, low = self.pool.queue_depths()
            metrics.QUEUE_DEPTH.labels("high").set(high)
            metrics.QUEUE_DEPTH.labels("low").set(low)
            if level != previous:
                metrics.LADDER_CHANGES.inc()
                logger.warning(
                    "degradation level changed",
                    extra={"from": int(previous), "to": int(level), "cpu": self._cpu_percent, "lag": max_lag},
                )
                self._publish_live(
                    WsMessageType.LOAD_LEVEL_CHANGED,
                    {
                        "engine_node": self.settings.node_name,
                        "level": int(level),
                        "cpu_percent": self._cpu_percent,
                    },
                )

    def _watch_children(self) -> None:
        while not self._stop.wait(2.0):
            before = self.pool.restarts
            self.pool.supervise()
            if self.pool.restarts > before:
                metrics.WORKER_RESTARTS.inc(self.pool.restarts - before)
            now = time.monotonic()
            with self._lock:
                for camera_id, handle in list(self._cameras.items()):
                    dead = not handle.process.is_alive()
                    hung = now - handle.last_report_at > _HUNG_AFTER_S
                    if not (dead or hung) or now < handle.next_restart_at:
                        continue
                    logger.error(
                        "camera process failed; restarting",
                        extra={"camera_id": camera_id, "dead": dead, "hung": hung},
                    )
                    metrics.CAMERA_RESTARTS.labels(str(camera_id)).inc()
                    config, restarts = handle.config, handle.restarts + 1
                    self._stop_camera(camera_id)
                    if self._start_camera(config, restarts):
                        new_handle = self._cameras[camera_id]
                        backoff = min(2.0 ** min(restarts, 6), _CAMERA_RESTART_BACKOFF_MAX_S)
                        new_handle.next_restart_at = now + backoff

    def _listen_control(self) -> None:
        """Gallery reload / camera sync notifications from the backend (standards/17 §9)."""
        while not self._stop.is_set():
            try:
                pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(ENGINE_CONTROL_CHANNEL)
                while not self._stop.is_set():
                    message = pubsub.get_message(timeout=1.0)
                    if message is None:
                        continue
                    self._handle_control(message.get("data"))
            except Exception as exc:  # Redis down: retry, never crash the engine
                logger.warning("control channel unavailable", extra={"error": type(exc).__name__})
                self._stop.wait(5.0)

    def _handle_control(self, data: Any) -> None:
        try:
            command = json.loads(data)["type"]
        except (TypeError, ValueError, KeyError):
            return
        coroutine = {"gallery_reload": self.reload_gallery, "cameras_sync": self.sync_cameras}.get(command)
        if coroutine is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(coroutine(), self._loop)

    def _publish_live(self, message_type: WsMessageType, data: dict[str, Any]) -> None:
        message = {"type": message_type.value, "data": data, "sent_at": datetime.now(UTC).isoformat()}
        try:
            self._redis.publish(LIVE_UPDATES_CHANNEL, json.dumps(message))
        except Exception as exc:  # live updates are best-effort; the API stays authoritative
            logger.warning("live update not published", extra={"error": type(exc).__name__})
