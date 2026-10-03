"""One-off snapshot grab for the FR-2 camera connection test."""

import base64

import av
import cv2
import numpy as np
from facetrack_common.schemas.engine import CameraTestResult

from app.capture.decoder import DecoderSettings, is_file_source, safe_error

_MAX_PACKETS = 600  # give up if no decodable keyframe arrives in this many packets


def grab_snapshot(url: str, settings: DecoderSettings, jpeg_quality: int = 85) -> CameraTestResult:
    """Opens the stream, decodes the first keyframe and returns it as a JPEG. Blocking: run in a thread."""
    if is_file_source(url) and not settings.allow_file_sources:
        return CameraTestResult(ok=False, error="file sources are only allowed in development")
    timeout = (settings.open_timeout_s, settings.read_timeout_s)
    options = None if is_file_source(url) else {"rtsp_transport": "tcp"}
    try:
        with av.open(url.removeprefix("file://"), options=options, timeout=timeout) as container:
            stream = container.streams.video[0]
            for count, packet in enumerate(container.demux(stream)):
                if count > _MAX_PACKETS:
                    break
                if not packet.is_keyframe:
                    continue
                for frame in packet.decode():
                    image = np.ascontiguousarray(frame.to_ndarray(format="bgr24"), dtype=np.uint8)
                    ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                    if not ok:
                        continue
                    return CameraTestResult(
                        ok=True,
                        width=image.shape[1],
                        height=image.shape[0],
                        codec=stream.codec_context.name,
                        snapshot_jpeg_b64=base64.b64encode(jpeg.tobytes()).decode("ascii"),
                    )
        return CameraTestResult(ok=False, error="no decodable keyframe received")
    except (av.FFmpegError, OSError, ValueError) as exc:
        return CameraTestResult(ok=False, error=safe_error(exc))
