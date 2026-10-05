"""One camera's processing loop, run in its own process (requirements §10.1, §10.4, standards/17).

Each tick: collect inference replies -> decide what this camera may do now (mode x ladder x hours) ->
take the latest frame only -> motion gate -> (ACTIVE/COOLDOWN) submit detection on the ROI crop at the
planned rate -> track, quality-gate and keep best crops -> embed/vote/liveness through the shared
pool -> emit one event per decided track. A failure in this process never affects other cameras.
"""

import base64
import logging
import math
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING, CameraMode, LoadLevel
from facetrack_common.crypto import Cipher
from facetrack_common.events import RecognitionEvent

from app.capture.frame_buffer import FrameItem, LatestFrameBuffer
from app.config import EngineSettings
from app.models.alignment import align_face
from app.models.base import FaceDetection, ImageBGR
from app.pipeline.best_crops import CropCandidate
from app.pipeline.motion import MotionGate
from app.pipeline.quality import assess_quality, crop_box
from app.pipeline.roi import Roi
from app.pipeline.track_manager import (
    Action,
    EmbedRequest,
    EmitEvent,
    LivenessRequest,
    TrackManager,
    TrackRules,
    UnconfirmedKnownTrack,
)
from app.pipeline.tracking import FaceTracker
from app.pipeline.voting import VotingRules
from app.publisher.event_publisher import snapshot_object_path
from app.scheduler.camera_config import CameraRuntimeConfig
from app.scheduler.inference_pool import InferenceResult, InferenceTask, PoolClient, TaskKind
from app.scheduler.modes import CameraModeMachine, ModeTimings
from app.scheduler.operating_hours import within_operating_hours, within_peak
from app.scheduler.rates import ProcessingPlan, RateSettings, plan_processing

logger = logging.getLogger(__name__)

# Bounded per-step timing samples sent with each status report (metrics, never logs).
_MAX_TIMING_SAMPLES = 64
# Snapshot crop size relative to the face box (a little context around the face).
_SNAPSHOT_SCALE = 1.6


class FrameSource(Protocol):
    connected: bool
    last_error: str | None
    reconnects: int

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def set_keyframes_only(self, value: bool) -> None: ...
    def switch_source(self, url: str) -> None: ...
    def request_restart(self) -> None: ...


class EventEmitter(Protocol):
    @property
    def buffered(self) -> int: ...

    lost: int

    def emit(self, event: RecognitionEvent, snapshot_jpeg: bytes) -> None: ...


@dataclass
class CameraStatusReport:
    camera_id: int
    name: str
    role: str
    mode: CameraMode
    connected: bool
    fps_target: float
    fps_actual: float
    last_frame_at: datetime | None
    lag_seconds: float
    faces_today: int
    reconnects: int
    last_error: str | None
    deferred_embeddings: int
    buffered_events: int
    lost_events: int
    mode_changed: bool
    counters: dict[str, int] = field(default_factory=dict)
    timings_ms: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class _PendingDetect:
    request_id: int
    sent_at: float
    frame: FrameItem
    image: ImageBGR
    offset: tuple[int, int]
    scale: float


@dataclass
class _PendingTrackRequest:
    kind: TaskKind
    track_id: int
    sent_at: float
    crop_ids: list[int]


def _failure_kind(pending: "_PendingTrackRequest") -> Literal["embed", "liveness"]:
    return "embed" if pending.kind == TaskKind.EMBED else "liveness"


class CameraWorker:
    def __init__(
        self,
        config: CameraRuntimeConfig,
        settings: EngineSettings,
        client: PoolClient,
        frame_buffer: LatestFrameBuffer,
        source: FrameSource,
        emitter: EventEmitter,
        level_reader: Callable[[], int],
        status_sink: Callable[[CameraStatusReport], None],
        cipher: Cipher,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._settings = settings
        self._client = client
        self._buffer = frame_buffer
        self._source = source
        self._emitter = emitter
        self._level_reader = level_reader
        self._status_sink = status_sink
        self._cipher = cipher
        self._clock = clock
        self._tz = ZoneInfo(config.timezone)
        now = clock()

        self._roi = Roi(config.roi_polygon)
        self._motion = MotionGate(self._roi, config.motion_min_area_ratio)
        self._modes = CameraModeMachine(ModeTimings(config.cooldown_enter_s, config.cooldown_idle_s), now)
        self._rates = RateSettings(config.entrance_fps, config.general_fps, config.cooldown_fps)
        self._tracker = FaceTracker(config.camera_fps or config.entrance_fps, config.track_lost_s)
        self.tracks = TrackManager(
            TrackRules(
                voting=VotingRules(
                    config.match_threshold,
                    config.margin,
                    config.min_votes,
                    config.best_crops,
                    config.conflict_gap,
                ),
                embed_after_s=config.embed_after_s,
                track_lost_s=config.track_lost_s,
                liveness_required=config.liveness_required,
                liveness_spoof_threshold=config.liveness_spoof_threshold,
            )
        )
        self._pending_detect: _PendingDetect | None = None
        self._pending: dict[int, _PendingTrackRequest] = {}
        self._deferred: deque[EmbedRequest] = deque()
        self._last_process = -math.inf
        self._last_status = -math.inf
        self._last_watchdog = now
        self._face_seen = False
        self._lag = 0.0
        self._last_frame_wall: datetime | None = None
        self._detect_times: deque[float] = deque(maxlen=64)
        self._faces_today = 0
        self._faces_date: date | None = None
        self._tracks_started = 0
        self._counters: dict[str, int] = {}
        self._timings: dict[str, list[float]] = {}
        self._mode_changed = False
        self.plan = ProcessingPlan(0.0, True, False, False, False)

    # ------------------------------------------------------------------ main loop

    def run(self, should_stop: Callable[[], bool]) -> None:
        self._source.start()
        try:
            while not should_stop():
                sleep_s = self.tick()
                time.sleep(sleep_s)
        finally:
            self._source.stop()

    def tick(self) -> float:
        """One iteration; returns how long to sleep before the next one."""
        now = self._clock()
        for result in self._client.poll():
            self._handle_result(result, now)
        self._expire_requests(now)

        level = LoadLevel(self._level_reader())
        now_local = datetime.now(self._tz)
        outside_hours = not within_operating_hours(self.config.operating_hours, now_local)
        shed = not self.config.is_entrance and level >= LoadLevel.GENERAL_PAUSED  # ladder step 3
        if outside_hours or shed:
            self._update_mode(now, motion=False, face=False, paused=True)
        elif self._modes.mode == CameraMode.PAUSED:
            self._update_mode(now, motion=False, face=False, paused=False)
        in_peak = within_peak(self.config.peak_windows, now_local)
        self.plan = plan_processing(
            self.config.role, self._modes.mode, level, self.config.camera_fps, self._rates, in_peak
        )
        self._source.set_keyframes_only(self.plan.keyframes_only)
        self._select_stream()
        if not self.plan.paused:
            self._watchdog(now)

        frame = self._buffer.take_latest()
        if frame is not None and not self.plan.paused and self._due(now):
            self._process_frame(frame, now)

        if not self.plan.defer_embedding:
            while self._deferred:
                self._submit_embed(self._deferred.popleft(), now)
        self._handle_actions(self.tracks.step(now), now)

        if self._mode_changed or now - self._last_status >= self._settings.status_interval_s:
            self._report_status(now)
        return 0.005 if self.plan.detect_fps >= 2 else 0.02

    def _due(self, now: float) -> bool:
        rate = self.plan.detect_fps
        if rate <= 0:
            # IDLE: motion checks only, no faster than the role's detection rate (keyframes are ~1/s).
            rate = max(self._rates.entrance_fps if self.config.is_entrance else self._rates.general_fps, 1.0)
        return now - self._last_process >= 1.0 / rate

    def _select_stream(self) -> None:
        """Sub-stream for general cameras and for idle entrance cameras; main stream when ACTIVE (§10.4)."""
        if not self.config.substream_url:
            return
        use_main = self.config.is_entrance and self._modes.mode == CameraMode.ACTIVE
        self._source.switch_source(self.config.main_url if use_main else self.config.substream_url)

    def _watchdog(self, now: float) -> None:
        # Only a connected-but-silent stream needs a restart; while disconnected, the decoder is already
        # reconnecting with its own backoff (restarting it then would only add a warning every few seconds).
        if not self._source.connected:
            return
        last = self._buffer.last_write_monotonic
        reference = last if last is not None else self._last_watchdog
        if now - reference > self._settings.watchdog_no_frame_s and now - self._last_watchdog > (
            self._settings.watchdog_no_frame_s
        ):
            logger.warning(
                "no frame received; restarting decoder", extra={"camera_id": self.config.camera_id}
            )
            self._count("watchdog_restarts")
            self._source.request_restart()
            self._last_watchdog = now

    # ------------------------------------------------------------------ frames

    def _process_frame(self, frame: FrameItem, now: float) -> None:
        self._last_process = now
        self._last_frame_wall = frame.wall_time
        started = self._clock()
        image = frame.to_bgr()
        motion = self._motion.update(image)
        self._timing("motion", started)
        self._count("frames_processed")
        mode = self._update_mode(now, motion=motion, face=self._face_seen, paused=False)
        self._face_seen = False
        if mode in (CameraMode.ACTIVE, CameraMode.COOLDOWN) and self._pending_detect is None:
            self._submit_detect(frame, image, now)

    def _update_mode(self, now: float, *, motion: bool, face: bool, paused: bool) -> CameraMode:
        previous = self._modes.mode
        mode = self._modes.update(now, motion=motion, face=face, paused=paused)
        if mode != previous:
            self._mode_changed = True
            if previous == CameraMode.IDLE:
                self._motion.reset()
            logger.info(
                "camera mode changed",
                extra={"camera_id": self.config.camera_id, "from": previous.value, "to": mode.value},
            )
        return mode

    def _submit_detect(self, frame: FrameItem, image: ImageBGR, now: float) -> None:
        height, width = image.shape[:2]
        x0, y0, x1, y1 = self._roi.bounding_rect(width, height)
        roi_image: ImageBGR = image[y0:y1, x0:x1]
        limit = self._settings.detector_input_size
        scale = min(1.0, limit / max(roi_image.shape[:2]))
        if scale < 1.0:
            roi_image = np.asarray(
                cv2.resize(roi_image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), dtype=np.uint8
            )
        request_id = self._client.new_request_id()
        task = InferenceTask(
            TaskKind.DETECT,
            request_id,
            self._client.slot,
            image=np.ascontiguousarray(roi_image),
            score_threshold=self.config.detector_min_score,
        )
        if self._client.submit(task, high_priority=self.config.is_entrance):
            self._pending_detect = _PendingDetect(request_id, now, frame, image, (x0, y0), scale)
        else:
            self._count("detect_dropped")  # lane full: skip this frame, the next one is newer anyway

    def _on_detections(self, pending: _PendingDetect, detections: list[FaceDetection], now: float) -> None:
        image = pending.image
        height, width = image.shape[:2]
        self._lag = now - pending.frame.decoded_at
        self._detect_times.append(now)
        faces = []
        for detection in detections:
            mapped = detection.shifted(pending.offset[0], pending.offset[1], 1.0 / pending.scale)
            cx, cy = mapped.x + mapped.width / 2, mapped.y + mapped.height / 2
            if mapped.width < self.config.min_face_width_px or not self._roi.contains(cx, cy, width, height):
                continue
            faces.append(mapped)
        self._face_seen = bool(faces)
        self._count("faces_detected", len(faces))
        started = self._clock()
        tracked = self._tracker.update(faces)
        before = self.tracks.tracks_started
        for track_id, face in tracked:
            if not self.tracks.wants_crops(track_id):
                self.tracks.touch(track_id, now)
                continue
            candidate = self._make_candidate(image, face, pending.frame.wall_time, width, height)
            if candidate is None:
                self.tracks.touch(track_id, now)
            else:
                self.tracks.add_crop(track_id, candidate, now)
        self._add_faces_today(self.tracks.tracks_started - before)
        self._timing("track_quality", started)

    def _make_candidate(
        self, image: ImageBGR, face: FaceDetection, captured_at: datetime, width: int, height: int
    ) -> CropCandidate | None:
        quality = assess_quality(
            crop_box(image, face),
            face,
            min_face_width=self.config.min_face_width_px,
            min_quality=self.config.min_crop_quality,
            min_blur_variance=self.config.min_blur_variance,
        )
        if not quality.passed:
            self._count("crops_rejected_quality")
            return None
        liveness_region = None
        if self.config.liveness_required:
            liveness_region = crop_box(image, face, scale=self._settings.liveness_crop_scale, square=True)
        return CropCandidate(
            crop_id=self.tracks.next_crop_id(),
            quality=quality.score,
            aligned=align_face(image, face.landmarks),
            snapshot=crop_box(image, face, scale=_SNAPSHOT_SCALE, square=True),
            liveness_region=liveness_region,
            captured_at=captured_at,
            bbox_norm=(
                min(1.0, max(0.0, face.x / width)),
                min(1.0, max(0.0, face.y / height)),
                min(1.0, face.width / width),
                min(1.0, face.height / height),
            ),
        )

    # ------------------------------------------------------------------ inference results

    def _handle_result(self, result: InferenceResult, now: float) -> None:
        if result.kind == TaskKind.DETECT:
            pending_detect = self._pending_detect
            if pending_detect is None or pending_detect.request_id != result.request_id:
                return  # late reply for a request that already timed out
            self._pending_detect = None
            self._timings.setdefault("detect_roundtrip", []).append((now - pending_detect.sent_at) * 1000)
            if result.ok and result.detections is not None:
                self._on_detections(pending_detect, result.detections, now)
            return
        pending = self._pending.pop(result.request_id, None)
        if pending is None:
            return
        if not result.ok:
            self._count(f"{pending.kind.value}_failed")
            self._handle_actions(self.tracks.on_request_failed(pending.track_id, _failure_kind(pending)), now)
            return
        if pending.kind == TaskKind.EMBED and result.embeddings is not None and result.matches is not None:
            self._count("embeddings", len(pending.crop_ids))
            self._timings.setdefault("embed_roundtrip", []).append((now - pending.sent_at) * 1000)
            results = {
                crop_id: (result.embeddings[i], result.matches[i])
                for i, crop_id in enumerate(pending.crop_ids)
            }
            self._handle_actions(self.tracks.on_embeddings(pending.track_id, results), now)
        elif pending.kind == TaskKind.LIVENESS and result.real_score is not None:
            self._count("liveness_checks")
            self._handle_actions(self.tracks.on_liveness(pending.track_id, result.real_score), now)

    def _expire_requests(self, now: float) -> None:
        timeout = self._settings.request_timeout_s
        if self._pending_detect is not None and now - self._pending_detect.sent_at > timeout:
            self._pending_detect = None
            self._count("detect_timeouts")
        for request_id, pending in list(self._pending.items()):
            if now - pending.sent_at > timeout:
                del self._pending[request_id]
                self._count(f"{pending.kind.value}_timeouts")
                actions = self.tracks.on_request_failed(pending.track_id, _failure_kind(pending))
                self._handle_actions(actions, now)

    # ------------------------------------------------------------------ actions

    def _handle_actions(self, actions: list[Action], now: float) -> None:
        for action in actions:
            if isinstance(action, EmbedRequest):
                if self.plan.defer_embedding:
                    if len(self._deferred) < self._settings.deferred_embed_max:
                        self._deferred.append(action)  # ladder step 5: run when load drops
                    else:
                        self._count("deferred_embed_dropped")
                        self.tracks.cancel_in_flight(action.track_id)
                else:
                    self._submit_embed(action, now)
            elif isinstance(action, LivenessRequest):
                self._submit_liveness(action, now)
            elif isinstance(action, EmitEvent):
                self._emit(action)
            elif isinstance(action, UnconfirmedKnownTrack):
                # FR-17: a known person seen too briefly to confirm is not an Unknown face. No event and
                # no snapshot; ids and counts only in the log (standards/18).
                self._count("unconfirmed_known_tracks")
                logger.info(
                    "unconfirmed track matched one enrolled employee; not logged as unknown",
                    extra={
                        "camera_id": self.config.camera_id,
                        "track_id": action.track_id,
                        "embedded_crops": action.embedded_crops,
                    },
                )

    def _submit_embed(self, request: EmbedRequest, now: float) -> None:
        request_id = self._client.new_request_id()
        task = InferenceTask(
            TaskKind.EMBED, request_id, self._client.slot, crops=[c.aligned for c in request.crops]
        )
        if self._client.submit(task, high_priority=self.config.is_entrance):
            self._pending[request_id] = _PendingTrackRequest(
                TaskKind.EMBED, request.track_id, now, [c.crop_id for c in request.crops]
            )
        else:
            self._count("embed_dropped")
            self.tracks.cancel_in_flight(request.track_id)  # try again on a later tick

    def _submit_liveness(self, request: LivenessRequest, now: float) -> None:
        region = request.crop.liveness_region
        if region is None:
            self._handle_actions(self.tracks.on_request_failed(request.track_id, "liveness"), now)
            return
        request_id = self._client.new_request_id()
        task = InferenceTask(TaskKind.LIVENESS, request_id, self._client.slot, image=region)
        high = self.config.is_entrance and not self.plan.liveness_low_priority  # ladder step 4
        if self._client.submit(task, high_priority=high):
            self._pending[request_id] = _PendingTrackRequest(TaskKind.LIVENESS, request.track_id, now, [])
        else:
            self._handle_actions(self.tracks.on_request_failed(request.track_id, "liveness"), now)

    def _emit(self, action: EmitEvent) -> None:
        event_id = uuid.uuid4()
        captured_at = action.crop.captured_at
        embedding_b64 = None
        if action.status == "unknown" and action.embedding is not None:
            token = self._cipher.encrypt_embedding(action.embedding, CRYPTO_PURPOSE_EMBEDDING)
            embedding_b64 = base64.b64encode(token).decode("ascii")
        ok, jpeg = cv2.imencode(
            ".jpg", action.crop.snapshot, [cv2.IMWRITE_JPEG_QUALITY, self._settings.snapshot_jpeg_quality]
        )
        event = RecognitionEvent(
            event_id=event_id,
            camera_id=self.config.camera_id,
            employee_code=action.employee_code,
            status=action.status,
            confidence=max(-1.0, min(1.0, action.confidence)),
            liveness_score=action.liveness_score,
            track_id=action.track_id,
            captured_at=captured_at,
            snapshot_path=snapshot_object_path(captured_at, str(event_id)) if ok else None,
            model_name=self.config.model_name,
            engine_node=self._settings.node_name,
            embedding_encrypted=embedding_b64,
            bbox=action.crop.bbox_norm,
        )
        self._emitter.emit(event, jpeg.tobytes() if ok else b"")
        self._count(f"events_{action.status}")
        if action.status == "unknown" and action.liveness_score is not None:
            self._count("liveness_rejections")

    # ------------------------------------------------------------------ status

    def _add_faces_today(self, count: int) -> None:
        today = datetime.now(self._tz).date()
        if self._faces_date != today:
            self._faces_date, self._faces_today = today, 0
        self._faces_today += count

    def _count(self, name: str, value: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def _timing(self, name: str, started: float) -> None:
        samples = self._timings.setdefault(name, [])
        if len(samples) < _MAX_TIMING_SAMPLES:
            samples.append((self._clock() - started) * 1000)

    def _report_status(self, now: float) -> None:
        window = [t for t in self._detect_times if now - t <= 5.0]
        report = CameraStatusReport(
            camera_id=self.config.camera_id,
            name=self.config.name,
            role=self.config.role.value,
            mode=self._modes.mode,
            connected=self._source.connected,
            fps_target=self.plan.detect_fps,
            fps_actual=round(len(window) / 5.0, 2),
            last_frame_at=self._last_frame_wall,
            lag_seconds=round(self._lag, 3) if self._modes.mode == CameraMode.ACTIVE else 0.0,
            faces_today=self._faces_today,
            reconnects=self._source.reconnects,
            last_error=self._source.last_error,
            deferred_embeddings=len(self._deferred),
            buffered_events=self._emitter.buffered,
            lost_events=self._emitter.lost,
            mode_changed=self._mode_changed,
            counters=self._counters,
            timings_ms={k: v[:_MAX_TIMING_SAMPLES] for k, v in self._timings.items()},
        )
        self._counters, self._timings = {}, {}
        self._mode_changed = False
        self._last_status = now
        self._status_sink(report)


# ---------------------------------------------------------------------- process entry point


def run_camera_process(
    config: CameraRuntimeConfig,
    settings: EngineSettings,
    client: PoolClient,
    level: Any,
    status_queue: Any,
    stop_event: Any,
) -> None:
    """Entry point of the per-camera process (spawned by the supervisor)."""
    import contextlib  # noqa: PLC0415
    import queue  # noqa: PLC0415

    from facetrack_common.jsonlog import configure_logging  # noqa: PLC0415
    from facetrack_common.storage import create_object_store  # noqa: PLC0415

    from app.capture.decoder import DecoderSettings, StreamDecoder  # noqa: PLC0415
    from app.publisher.disk_buffer import DiskBuffer  # noqa: PLC0415
    from app.publisher.event_publisher import EventPublisher, RedisStoreSink  # noqa: PLC0415

    configure_logging("engine-camera", settings.log_level)
    cv2.setNumThreads(1)  # decoding + light per-frame work only; inference runs in the pool
    cipher = Cipher.from_base64(settings.encryption_key.get_secret_value())
    frame_buffer = LatestFrameBuffer()
    decoder = StreamDecoder(
        config.camera_id,
        config.substream_url or config.main_url,
        frame_buffer,
        DecoderSettings(
            open_timeout_s=settings.stream_open_timeout_s,
            read_timeout_s=settings.stream_read_timeout_s,
            threads=settings.decoder_threads,
            reconnect_min_s=settings.reconnect_min_s,
            reconnect_max_s=settings.reconnect_max_s,
            allow_file_sources=settings.allow_file_sources,
            auth_retry_s=settings.auth_retry_s,
        ),
    )
    store = create_object_store(
        settings.storage_backend,
        settings.media_root,
        settings.s3_endpoint,
        settings.s3_access_key.get_secret_value(),
        settings.s3_secret_key.get_secret_value(),
        settings.s3_secure,
        settings.s3_bucket,
    )
    sink = RedisStoreSink(settings.redis_url.get_secret_value(), store)
    buffer = DiskBuffer(
        settings.buffer_dir / str(config.camera_id),
        cipher,
        settings.buffer_max_events,
        settings.buffer_max_mb * 1024 * 1024,
    )
    publisher = EventPublisher(sink, buffer, cipher, settings.publish_queue_size)
    publisher.start()

    def send_status(report: CameraStatusReport) -> None:
        # If the supervisor is behind, drop this report; the next one supersedes it.
        with contextlib.suppress(queue.Full):
            status_queue.put_nowait(report)

    worker = CameraWorker(
        config,
        settings,
        client,
        frame_buffer,
        decoder,
        publisher,
        level_reader=lambda: int(level.value),
        status_sink=send_status,
        cipher=cipher,
    )
    try:
        worker.run(stop_event.is_set)
    finally:
        publisher.stop()
