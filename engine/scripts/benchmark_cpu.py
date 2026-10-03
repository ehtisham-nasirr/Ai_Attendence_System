"""CPU benchmark of the recognition pipeline (standards/17 §10, commands/engine-change.md step 2/6).

Measures, on THIS machine:
  - per-step milliseconds: decode (full / keyframe-only), BGR conversion, motion gate, detection,
    alignment, quality, embedding, FAISS matching (5,000 employees x 10 photos);
  - CPU % of one core for one camera in IDLE (keyframe-only decode + motion) and ACTIVE
    (full decode + motion + detection at the entrance rate), played back in real time.
Cameras-per-node figures printed at the end are DERIVED from those measurements, not measured.

The clip is synthetic (scripts/sample_video.py), so it contains no faces: embedding/matching are
timed on synthetic crops, and recognition latency cannot be measured with it.

    uv run python scripts/benchmark_cpu.py --runtime openvino --out benchmark.json
"""

import argparse
import json
import platform
import statistics
import threading
import time
from pathlib import Path
from typing import Any

import av
import numpy as np
import psutil

from app.models.alignment import align_face
from app.models.base import FaceDetection
from app.pipeline.motion import MotionGate
from app.pipeline.quality import assess_quality, crop_box
from app.pipeline.roi import Roi


def _stats(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "mean_ms": round(statistics.fmean(ordered), 3),
        "p50_ms": round(ordered[len(ordered) // 2], 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "n": len(ordered),
    }


def _time(fn: Any, repeat: int) -> list[float]:
    fn()
    samples = []
    for _ in range(repeat):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def bench_decode(clip: Path) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for mode in ("full", "keyframes"):
        samples, convert = [], []
        with av.open(str(clip)) as container:
            stream = container.streams.video[0]
            stream.codec_context.thread_count = 1
            for packet in container.demux(stream):
                if packet.size == 0 or (mode == "keyframes" and not packet.is_keyframe):
                    continue
                started = time.perf_counter()
                frames = packet.decode()
                samples.append((time.perf_counter() - started) * 1000)
                for frame in frames:
                    started = time.perf_counter()
                    frame.to_ndarray(format="bgr24")
                    convert.append((time.perf_counter() - started) * 1000)
        results[f"decode_{mode}"] = _stats(samples)
        results[f"bgr_convert_{mode}"] = _stats(convert)
    return results


def _first_frame(clip: Path) -> np.ndarray:
    with av.open(str(clip)) as container:
        for frame in container.decode(video=0):
            return np.ascontiguousarray(frame.to_ndarray(format="bgr24"))
    raise RuntimeError("empty clip")


def _frontal_face(x: float, y: float, width: float) -> FaceDetection:
    from app.models.alignment import TEMPLATE_112

    return FaceDetection(
        x, y, width, width * 1.2, (TEMPLATE_112 * width / 112 + [x, y]).astype(np.float32), 0.9
    )


def bench_models(
    frame: np.ndarray, runtime: str, threads: int, detector_path: Path, embedder_path: Path
) -> dict[str, Any]:
    from app.gallery.index import GalleryIndex, GallerySnapshot
    from app.models.base import l2_normalise
    from app.models.embedders import SFaceEmbedder
    from app.models.runtime import create_session
    from app.models.yunet import YuNetDetector

    detector = YuNetDetector(create_session(detector_path, runtime, threads))  # type: ignore[arg-type]
    embedder = SFaceEmbedder(create_session(embedder_path, runtime, threads))  # type: ignore[arg-type]
    roi = frame[: frame.shape[0] // 2, : frame.shape[1] // 2]  # a typical entrance ROI crop
    face = _frontal_face(400, 200, 140)
    aligned = align_face(frame, face.landmarks)
    rng = np.random.default_rng(0)
    results: dict[str, Any] = {
        "detect_roi_quarter_frame": _stats(_time(lambda: detector.detect(roi, 0.6), 40)),
        "detect_full_frame": _stats(_time(lambda: detector.detect(frame, 0.6), 40)),
        "align": _stats(_time(lambda: align_face(frame, face.landmarks), 200)),
        "quality": _stats(_time(lambda: assess_quality(crop_box(frame, face), face, 60, 0.35, 40), 200)),
        "embed_1_crop": _stats(_time(lambda: embedder.embed([aligned]), 60)),
        "embed_3_crops": _stats(_time(lambda: embedder.embed([aligned] * 3), 30)),
    }
    for dim in (128, 512):
        codes = [f"E{i // 10:05d}" for i in range(50_000)]
        index = GalleryIndex(
            GallerySnapshot(
                "bench", 1, codes, l2_normalise(rng.standard_normal((50_000, dim)).astype(np.float32))
            )
        )
        query = l2_normalise(rng.standard_normal((1, dim)).astype(np.float32))
        results[f"match_5000x10_{dim}d"] = _stats(_time(lambda q=query, i=index: i.search(q), 100))
    return results


def bench_camera_cpu(
    clip: Path, mode: str, seconds: float, detector_path: Path, runtime: str
) -> dict[str, float]:
    """Runs one camera's decode+motion (+detection at 4 FPS when ACTIVE) in real time; returns CPU %."""
    from app.capture.decoder import DecoderSettings, StreamDecoder
    from app.capture.frame_buffer import LatestFrameBuffer
    from app.models.runtime import create_session
    from app.models.yunet import YuNetDetector

    detector = YuNetDetector(create_session(detector_path, runtime, 1)) if mode == "ACTIVE" else None  # type: ignore[arg-type]
    buffer = LatestFrameBuffer()
    decoder = StreamDecoder(
        1, f"file://{clip}", buffer, DecoderSettings(5, 5, 1, 1, 2, allow_file_sources=True)
    )
    decoder.set_keyframes_only(mode == "IDLE")
    gate = MotionGate(Roi(None), 0.01)
    process = psutil.Process()
    stop = threading.Event()
    processed = 0

    def loop() -> None:
        nonlocal processed
        last = 0.0
        while not stop.is_set():
            item = buffer.take_latest()
            interval = 0.25 if mode == "ACTIVE" else 0.0
            if item is None or time.monotonic() - last < interval:
                time.sleep(0.005)
                continue
            last = time.monotonic()
            image = item.to_bgr()
            gate.update(image)
            if detector is not None:
                detector.detect(image[: image.shape[0] // 2, : image.shape[1] // 2], 0.6)
            processed += 1

    worker = threading.Thread(target=loop, daemon=True)
    decoder.start()
    worker.start()
    time.sleep(2.0)  # warm-up
    cpu_before, wall_before, processed_before = sum(process.cpu_times()[:2]), time.monotonic(), processed
    time.sleep(seconds)
    cpu = sum(process.cpu_times()[:2]) - cpu_before
    wall = time.monotonic() - wall_before
    frames = processed - processed_before
    stop.set()
    decoder.stop()
    decoder.join(timeout=5)
    return {"cpu_percent_of_one_core": round(100 * cpu / wall, 1), "processed_fps": round(frames / wall, 2)}


def main() -> None:
    from sample_video import write_sample_video

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--runtime", choices=["openvino", "onnxruntime"], default="openvino")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--clip", type=Path, default=Path("recordings/bench_1080p.mp4"))
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--detector", type=Path, default=Path("models/face_detection_yunet_2023mar.onnx"))
    parser.add_argument("--embedder", type=Path, default=Path("models/face_recognition_sface_2021dec.onnx"))
    parser.add_argument("--out", type=Path, default=Path("benchmark.json"))
    args = parser.parse_args()

    if not args.clip.is_file():
        write_sample_video(args.clip, seconds=40, width=1920, height=1080, motion_windows=((0.0, 40.0),))
    frame = _first_frame(args.clip)
    report: dict[str, Any] = {
        "machine": {
            "cpu": platform.processor() or platform.machine(),
            "logical_cpus": psutil.cpu_count(),
            "physical_cpus": psutil.cpu_count(logical=False),
            "note": "measured on the machine that ran this script, not necessarily the reference server",
        },
        "runtime": args.runtime,
        "threads_per_model": args.threads,
        "clip": "synthetic 1080p H.264, 25 fps, GOP 25",
        "steps": {
            **bench_decode(args.clip),
            **bench_models(frame, args.runtime, args.threads, args.detector, args.embedder),
        },
    }
    motion_gate = MotionGate(Roi(None), 0.01)
    report["steps"]["motion_gate_1080p"] = _stats(_time(lambda: motion_gate.update(frame), 100))
    report["camera_cpu"] = {
        "IDLE": bench_camera_cpu(args.clip, "IDLE", args.seconds, args.detector, args.runtime),
        "ACTIVE": bench_camera_cpu(args.clip, "ACTIVE", args.seconds, args.detector, args.runtime),
    }
    idle = report["camera_cpu"]["IDLE"]["cpu_percent_of_one_core"]
    active = report["camera_cpu"]["ACTIVE"]["cpu_percent_of_one_core"]
    budget = 16 * 100 * 0.70  # NFR-4: 16 cores, average CPU <= 70 %
    report["derived_not_measured"] = {
        "note": "arithmetic on the measurements above; confirm with a multi-camera soak on the reference server",
        "all_cameras_active_at_once_on_16_cores": int(budget // max(active, 0.1)),
        "all_cameras_idle_on_16_cores": int(budget // max(idle, 0.1)),
    }
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
