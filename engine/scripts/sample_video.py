"""Writes a synthetic H.264 test clip: textured static scene with moving blocks during set windows.

It contains no faces and no recordings of people, so it can be generated anywhere (standards/18).
Used by the decoder tests, `make dev` (looped by MediaMTX) and `benchmark_cpu.py`.

    uv run python scripts/sample_video.py recordings/sample.mp4 --seconds 60
"""

import argparse
from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def write_sample_video(
    path: Path,
    seconds: float = 20.0,
    fps: int = 25,
    width: int = 1280,
    height: int = 720,
    gop: int = 25,
    motion_windows: tuple[tuple[float, float], ...] = ((4.0, 9.0), (14.0, 18.0)),
) -> Path:
    """Static background with a moving block during each (start_s, end_s) window. GOP = 1 s at 25 fps."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    background = rng.integers(40, 200, size=(height // 8, width // 8, 3), dtype=np.uint8)
    background = np.kron(background, np.ones((8, 8, 1), dtype=np.uint8))  # blocky texture compresses well
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        stream.codec_context.gop_size = gop
        stream.codec_context.options = {
            "preset": "veryfast",
            "tune": "zerolatency",
            "bf": "0",
            "sc_threshold": "0",
        }
        stream.time_base = Fraction(1, fps)
        for index in range(int(seconds * fps)):
            t = index / fps
            frame = background.copy()
            for start, end in motion_windows:
                if start <= t < end:
                    progress = (t - start) / (end - start)
                    x = int(progress * (width - 200))
                    frame[height // 3 : height // 3 + 200, x : x + 160] = (230, 230, 230)
            video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
            video_frame.pts = index
            for packet in stream.encode(video_frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    windows = tuple((float(s), float(s + 6)) for s in range(5, int(args.seconds), 20))
    write_sample_video(
        args.output, args.seconds, width=args.width, height=args.height, motion_windows=windows
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
