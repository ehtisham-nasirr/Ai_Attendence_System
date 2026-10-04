"""PyAV decoding: keyframe-only idle mode, latest-frame buffer, safe errors, reconnects, FR-2 snapshot (§10.4)."""

import base64
import socketserver
import threading
import time
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

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


class _RtspRefusal(socketserver.ThreadingTCPServer):
    """Local RTSP server that answers every request with one status line and counts the connections."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, status: str) -> None:
        super().__init__(("127.0.0.1", 0), _RtspRefusalHandler)
        self.status = status
        self.connections = 0
        self.url = f"rtsp://admin:secret@127.0.0.1:{self.server_address[1]}/cam/realmonitor?channel=1"


class _RtspRefusalHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: _RtspRefusal = self.server  # type: ignore[assignment]
        server.connections += 1
        pending = b""
        while data := self.request.recv(4096):
            pending += data
            while b"\r\n\r\n" in pending:
                head, pending = pending.split(b"\r\n\r\n", 1)
                headers = dict(line.split(b":", 1) for line in head.split(b"\r\n")[1:] if b":" in line)
                reply = [
                    b"RTSP/1.0 " + server.status.encode(),
                    b"CSeq: " + headers.get(b"CSeq", b"1").strip(),
                ]
                if server.status.startswith("401"):
                    reply.append(b'WWW-Authenticate: Digest realm="test", nonce="n1"')
                self.request.sendall(b"\r\n".join(reply) + b"\r\n\r\n")


def _run_against(status: str, settings: DecoderSettings, seconds: float) -> tuple[StreamDecoder, int, float]:
    server = _RtspRefusal(status)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        decoder = StreamDecoder(1, server.url, LatestFrameBuffer(), settings)
        decoder.start()
        time.sleep(seconds)
        stopped_at = time.monotonic()
        decoder.stop()
        decoder.join(timeout=5)
        return decoder, server.connections, time.monotonic() - stopped_at
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("status", "error"),
    [("401 Unauthorized", "HTTPUnauthorizedError"), ("403 Forbidden", "HTTPForbiddenError")],
)
def test_fr4_refused_credentials_wait_auth_retry_before_trying_again(status: str, error: str) -> None:
    """A camera that rejects the login is not retried every few seconds (Q61: Dahua locks the account)."""
    settings = replace(SETTINGS, auth_retry_s=60.0)
    decoder, connections, stop_s = _run_against(status, settings, seconds=2.0)
    assert connections == 1  # with the 0.1-0.2 s network backoff this would be about 10
    assert not decoder.is_alive() and stop_s < 5  # stop() still ends the long wait at once
    assert not decoder.connected and decoder.reconnects == 1
    assert decoder.last_error is not None and decoder.last_error.startswith(error)
    assert "secret" not in decoder.last_error and "admin" not in decoder.last_error


def test_fr4_other_rtsp_errors_keep_the_fast_backoff() -> None:
    settings = replace(SETTINGS, auth_retry_s=60.0)
    decoder, connections, _ = _run_against("404 Not Found", settings, seconds=2.0)
    assert connections >= 4
    assert decoder.last_error is not None and decoder.last_error.startswith("HTTPNotFoundError")


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
