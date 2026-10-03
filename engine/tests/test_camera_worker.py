"""End-to-end camera pipeline with scripted models (§10.1 steps 1-11, FR-14..FR-17, NFR-15)."""

import base64
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING, CameraMode, CameraRole, LoadLevel
from facetrack_common.crypto import Cipher
from facetrack_common.events import RecognitionEvent
from fakes import FakeDetector, FakeEmbedder, InProcessClient, face_at

from app.capture.frame_buffer import LatestFrameBuffer
from app.config import EngineSettings
from app.gallery.index import GalleryIndex, GallerySnapshot
from app.pipeline.camera_worker import CameraStatusReport, CameraWorker
from app.scheduler.camera_config import CameraRuntimeConfig
from app.scheduler.inference_pool import TaskKind


class FakeSource:
    def __init__(self) -> None:
        self.connected = True
        self.last_error: str | None = None
        self.reconnects = 0
        self.keyframes_only: list[bool] = []
        self.restarts = 0
        self.urls: list[str] = []

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def set_keyframes_only(self, value: bool) -> None:
        self.keyframes_only.append(value)

    def switch_source(self, url: str) -> None:
        self.urls.append(url)

    def request_restart(self) -> None:
        self.restarts += 1


class FakeEmitter:
    buffered = 0
    lost = 0

    def __init__(self) -> None:
        self.events: list[tuple[RecognitionEvent, bytes]] = []

    def emit(self, event: RecognitionEvent, snapshot_jpeg: bytes) -> None:
        self.events.append((event, snapshot_jpeg))


def _config(**overrides: Any) -> CameraRuntimeConfig:
    values: dict[str, Any] = {
        "camera_id": 3,
        "name": "Main entrance",
        "role": CameraRole.ENTRY,
        "timezone": "Asia/Karachi",
        "main_url": "rtsp://main",
        "substream_url": None,
        "roi_polygon": None,
        "camera_fps": None,
        "operating_hours": None,
        "model_name": "sface",
        "match_threshold": 0.36,
        "margin": 0.08,
        "min_votes": 2,
        "best_crops": 3,
        "detector_min_score": 0.6,
        "min_face_width_px": 60,
        "min_crop_quality": 0.35,
        "min_blur_variance": 40.0,
        "embed_after_s": 2.0,
        "track_lost_s": 2.0,
        "liveness_required": False,
        "liveness_spoof_threshold": 0.5,
        "entrance_fps": 4.0,
        "general_fps": 1.0,
        "cooldown_fps": 1.0,
        "cooldown_enter_s": 3.0,
        "cooldown_idle_s": 10.0,
        "motion_min_area_ratio": 0.01,
        "peak_windows": [],
    }
    values.update(overrides)
    return CameraRuntimeConfig(**values)


def _scene(block: bool) -> np.ndarray:
    rng = np.random.default_rng(3)
    frame = np.kron(rng.integers(40, 200, (45, 80, 3), dtype=np.uint8), np.ones((8, 8, 1), dtype=np.uint8))
    if block:
        frame[100:300, 400:560] = 250
    return frame


class Harness:
    def __init__(
        self, settings: EngineSettings, cipher: Cipher, gallery_codes: list[str], **config: Any
    ) -> None:
        self.clock = 0.0
        self.level = int(LoadLevel.NORMAL)
        self.buffer = LatestFrameBuffer(clock=lambda: self.clock)
        self.source = FakeSource()
        self.emitter = FakeEmitter()
        self.embedder = FakeEmbedder()
        vectors = (
            np.eye(len(gallery_codes), 4, dtype=np.float32) if gallery_codes else np.zeros((0, 4), np.float32)
        )
        gallery = GalleryIndex(GallerySnapshot("sface", 1, gallery_codes, vectors))
        self.client = InProcessClient(FakeDetector([face_at(200, 100, 160)]), self.embedder, gallery)
        self.reports: list[CameraStatusReport] = []
        self.worker = CameraWorker(
            _config(**config),
            settings,
            self.client,
            self.buffer,
            self.source,
            self.emitter,  # type: ignore[arg-type]
            level_reader=lambda: self.level,
            status_sink=self.reports.append,
            cipher=cipher,
            clock=lambda: self.clock,
        )

    def run(self, frames: int, block: bool = True, step: float = 0.3, detector_faces: bool = True) -> None:
        if not detector_faces:
            self.client._detector.faces = []
        for _ in range(frames):
            self.clock += step
            self.buffer.put(False, datetime.now(UTC), lambda b=block: _scene(b))
            self.worker.tick()


def test_fr16_person_walking_in_is_recognized_once(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A", "B"])
    h.run(1, block=False)
    assert h.worker._modes.mode == CameraMode.IDLE
    h.run(8)
    assert h.worker._modes.mode == CameraMode.ACTIVE
    assert len(h.emitter.events) == 1
    event, jpeg = h.emitter.events[0]
    assert event.status == "recognized" and event.employee_code == "A"
    assert event.camera_id == 3 and event.model_name == "sface" and event.embedding_encrypted is None
    assert event.snapshot_path and event.snapshot_path.startswith("snapshots/")
    assert jpeg[:2] == b"\xff\xd8" and event.bbox is not None
    assert h.embedder.calls == 3  # only the best 3 crops are ever embedded
    h.run(10)
    assert h.embedder.calls == 3 and len(h.emitter.events) == 1  # locked track: no more work, no repeat


def test_fr17_unknown_person_logged_once_with_encrypted_embedding(
    engine_settings: EngineSettings, cipher: Cipher
) -> None:
    h = Harness(engine_settings, cipher, [])
    h.run(1, block=False)
    h.run(6)
    assert h.emitter.events == []
    h.run(12, detector_faces=False)  # person leaves: track ends after 2 s
    [(event, _)] = h.emitter.events
    assert event.status == "unknown" and event.employee_code is None
    token = base64.b64decode(event.embedding_encrypted or "")
    vector = cipher.decrypt_embedding(token, CRYPTO_PURPOSE_EMBEDDING, 4)
    assert vector.shape == (4,)


def test_idle_camera_sends_no_detection_work(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A"])
    h.run(10, block=False)
    assert h.client.kinds() == []
    assert h.source.keyframes_only[-1] is True


def test_outside_operating_hours_camera_is_paused(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A"], operating_hours=[{"start": "00:00", "end": "00:00"}])
    h.run(6)
    assert h.worker._modes.mode == CameraMode.PAUSED
    assert h.client.kinds() == []


def test_nfr15_general_camera_shed_at_ladder_step_3(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A"], role=CameraRole.GENERAL)
    h.level = int(LoadLevel.GENERAL_PAUSED)
    h.run(6)
    assert h.worker._modes.mode == CameraMode.PAUSED and h.client.kinds() == []


def test_nfr15_step5_defers_embedding_until_load_drops(
    engine_settings: EngineSettings, cipher: Cipher
) -> None:
    h = Harness(engine_settings, cipher, ["A"])
    h.level = int(LoadLevel.EMBEDDING_DEFERRED)
    h.run(1, block=False)
    h.run(8)
    assert TaskKind.DETECT in h.client.kinds()  # detection and tracking continue
    assert TaskKind.EMBED not in h.client.kinds()
    assert h.emitter.events == []
    h.level = int(LoadLevel.NORMAL)
    h.run(2)
    assert TaskKind.EMBED in h.client.kinds()
    assert len(h.emitter.events) == 1  # delayed, not lost


def test_fr18_liveness_runs_once_on_entrance_camera(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A"], liveness_required=True)
    h.run(1, block=False)
    h.run(8)
    assert h.client.kinds().count(TaskKind.LIVENESS) == 1
    [(event, _)] = h.emitter.events
    assert event.status == "recognized" and event.liveness_score == pytest.approx(0.95)


def test_full_lane_drops_frames_instead_of_queueing(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A"])
    h.client.accept = False
    h.run(1, block=False)
    h.run(5)
    h.worker._report_status(h.clock)
    assert sum(r.counters.get("detect_dropped", 0) for r in h.reports) >= 1


def test_fr4_watchdog_restarts_a_silent_decoder(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A"])
    h.run(1, block=False)
    for _ in range(3):
        h.clock += 6.0
        h.worker.tick()
    assert h.source.restarts == 1


def test_watchdog_leaves_a_disconnected_decoder_to_its_backoff(
    engine_settings: EngineSettings, cipher: Cipher
) -> None:
    h = Harness(engine_settings, cipher, ["A"])
    h.run(1, block=False)
    h.source.connected = False  # camera offline: the decoder is reconnecting by itself
    for _ in range(5):
        h.clock += 6.0
        h.worker.tick()
    assert h.source.restarts == 0


def test_status_report_contents(engine_settings: EngineSettings, cipher: Cipher) -> None:
    h = Harness(engine_settings, cipher, ["A"])
    h.run(1, block=False)
    h.run(8)
    report = h.reports[-1]
    assert report.camera_id == 3 and report.connected
    assert any(r.mode_changed for r in h.reports)
    assert "motion" in {k for r in h.reports for k in r.timings_ms}


def test_substream_used_when_idle_main_stream_when_active(
    engine_settings: EngineSettings, cipher: Cipher
) -> None:
    h = Harness(engine_settings, cipher, ["A"], substream_url="rtsp://sub")
    h.run(1, block=False)
    assert h.source.urls[-1] == "rtsp://sub"
    h.run(3)
    assert h.source.urls[-1] == "rtsp://main"
