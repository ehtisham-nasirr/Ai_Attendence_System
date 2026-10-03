"""PyAV decoding: keyframe-only idle mode, latest-frame buffer, safe errors, FR-2 snapshot (§10.4)."""

import base64
import time
from pathlib import Path

import cv2
import numpy as np

from app.capture.decoder import DecoderSettings, StreamDecoder, is_file_source, safe_error
from app.capture.frame_buffer import LatestFrameBuffer
from app.capture.snapshot import grab_snapshot

SETTINGS = DecoderSettings(
    open_timeout_s=5,
    read_timeout_s=5,
    threads=1,
    reconnect_min_s=0.1,
    reconnect_max_s=0.2,
    allow_file_sources=True,
)


def _run_decoder(clip: Path, keyframes_only: bool, seconds: float) -> LatestFrameBuffer:
    buffer = LatestFrameBuffer()
    decoder = StreamDecoder(1, f"file://{clip}", buffer, SETTINGS)
    decoder.set_keyframes_only(keyframes_only)
    decoder.start()
    time.sleep(seconds)
    decoder.stop()
    decoder.join(timeout=5)
    return buffer


def test_keyframe_only_mode_decodes_about_one_frame_per_second(sample_clip: Path) -> None:
    idle = _run_decoder(sample_clip, keyframes_only=True, seconds=3.0)
    active = _run_decoder(sample_clip, keyframes_only=False, seconds=3.0)
    # GOP = 25 frames at 25 fps: ~3 keyframes vs ~75 frames in 3 s of real-time playback.
    assert 2 <= idle.frames_written <= 5
    assert active.frames_written >= 60
    assert active.frames_written > 10 * idle.frames_written


def test_file_sources_are_paced_in_real_time(sample_clip: Path) -> None:
    buffer = _run_decoder(sample_clip, keyframes_only=False, seconds=1.0)
    assert buffer.frames_written <= 35  # ~25 fps, not "as fast as possible"


def test_latest_frame_is_a_bgr_image(sample_clip: Path) -> None:
    buffer = _run_decoder(sample_clip, keyframes_only=True, seconds=1.5)
    item = buffer.take_latest()
    assert item is not None
    image = item.to_bgr()
    assert image.shape == (360, 640, 3) and image.dtype == np.uint8


def test_fr4_unreachable_stream_reconnects_with_backoff(tmp_path: Path) -> None:
    buffer = LatestFrameBuffer()
    decoder = StreamDecoder(1, f"file://{tmp_path}/missing.mp4", buffer, SETTINGS)
    decoder.start()
    time.sleep(1.0)
    decoder.stop()
    decoder.join(timeout=5)
    assert decoder.reconnects >= 2
    assert not decoder.connected
    assert decoder.last_error is not None and decoder.last_error.startswith("FileNotFoundError")


def test_file_sources_refused_outside_development(sample_clip: Path) -> None:
    production = DecoderSettings(5, 5, 1, 0.1, 0.2, allow_file_sources=False)
    result = grab_snapshot(f"file://{sample_clip}", production)
    assert not result.ok


def test_safe_error_never_leaks_credentials() -> None:
    message = safe_error(OSError("Connection refused: rtsp://admin:secret@10.0.0.5:554/stream1"))
    assert "secret" not in message and "admin" not in message
    assert is_file_source("/videos/a.mp4") and is_file_source("file:///a.mp4")
    assert not is_file_source("rtsp://cam/1")


def test_fr2_snapshot_from_stream(sample_clip: Path) -> None:
    result = grab_snapshot(f"file://{sample_clip}", SETTINGS)
    assert result.ok and result.width == 640 and result.height == 360 and result.codec == "h264"
    jpeg = base64.b64decode(result.snapshot_jpeg_b64 or "")
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (360, 640, 3)
