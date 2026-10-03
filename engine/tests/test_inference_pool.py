"""Inference pool: bounded lanes, priority, micro-batching, worker task execution (standards/17 §4)."""

import multiprocessing as mp
import queue
import time

import numpy as np
import pytest
from conftest import models_available
from fakes import FakeDetector, FakeEmbedder, face_at

from app.config import EngineSettings
from app.gallery.index import GalleryIndex, GallerySnapshot
from app.scheduler.inference_pool import (
    InferencePool,
    InferenceTask,
    PoolClient,
    PoolQueues,
    TaskKind,
    _collect_embed_batch,
    _run,
    parse_cores,
)


def _queues(size: int = 4) -> PoolQueues:
    ctx = mp.get_context("spawn")
    return PoolQueues(
        ctx.Queue(maxsize=size), ctx.Queue(maxsize=size), [ctx.Queue(maxsize=size) for _ in range(3)]
    )


def test_parse_cores() -> None:
    assert parse_cores("2-4, 7") == [2, 3, 4, 7]
    assert parse_cores("") == []


def test_full_lane_rejects_instead_of_growing() -> None:
    client = PoolClient(_queues(size=2), slot=1)
    accepted = [client.submit(InferenceTask(TaskKind.DETECT, i, 1), high_priority=False) for i in range(5)]
    time.sleep(0.1)  # let the queue feeder thread flush
    assert accepted.count(True) == 2
    assert accepted[2:] == [False, False, False]


def test_micro_batch_collects_up_to_eight_crops() -> None:
    queues = _queues(size=10)
    crop = np.zeros((112, 112, 3), dtype=np.uint8)
    for i in range(4):
        queues.low.put(InferenceTask(TaskKind.EMBED, i, 1, crops=[crop, crop, crop]))
    time.sleep(0.1)
    first = queues.low.get(timeout=1)
    stashed: list[InferenceTask] = []
    batch = _collect_embed_batch(first, queues.low, queues.high, 8, 0.05, stashed)
    assert sum(len(t.crops or []) for t in batch) <= 8
    assert len(batch) == 2 and len(stashed) == 1  # third task would exceed 8 crops: stashed, not lost


def test_micro_batch_does_not_hold_high_priority_work() -> None:
    queues = _queues(size=10)
    queues.high.put(InferenceTask(TaskKind.DETECT, 99, 1))
    time.sleep(0.1)
    started = time.monotonic()
    first = InferenceTask(TaskKind.EMBED, 1, 1, crops=[np.zeros((112, 112, 3), dtype=np.uint8)])
    batch = _collect_embed_batch(first, queues.low, queues.high, 8, 0.05, [])
    assert batch == [first] and time.monotonic() - started < 0.04


def test_run_embed_batch_splits_results_per_task() -> None:
    gallery = GalleryIndex(GallerySnapshot("sface", 1, ["A"], np.array([[1, 0, 0, 0]], dtype=np.float32)))
    crop = np.zeros((112, 112, 3), dtype=np.uint8)
    tasks = [
        InferenceTask(TaskKind.EMBED, 1, 1, crops=[crop]),
        InferenceTask(TaskKind.EMBED, 2, 2, crops=[crop] * 2),
    ]
    results = _run(tasks, FakeDetector([]), FakeEmbedder(), None, gallery)
    assert [0 if r.embeddings is None else len(r.embeddings) for r in results] == [1, 2]
    assert results[1].matches is not None and results[1].matches[0][0].employee_code == "A"


def test_run_detect_and_missing_liveness_model() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    [detect] = _run(
        [InferenceTask(TaskKind.DETECT, 1, 1, image=image)],
        FakeDetector([face_at(5, 5, 50)]),
        FakeEmbedder(),
        None,
        None,
    )
    assert detect.ok and len(detect.detections or []) == 1
    [liveness] = _run(
        [InferenceTask(TaskKind.LIVENESS, 2, 1, image=image)], FakeDetector([]), FakeEmbedder(), None, None
    )
    assert not liveness.ok and liveness.error == "liveness_unavailable"


@pytest.mark.skipif(not models_available(), reason="model files not downloaded")
def test_real_worker_process_round_trip_and_restart(engine_settings: EngineSettings) -> None:
    pool = InferencePool(engine_settings)
    pool.start()
    try:
        pool.publish_gallery(GallerySnapshot("sface", 1, ["A"], np.eye(1, 128, dtype=np.float32)))
        client = pool.client(1)
        image = np.full((360, 640, 3), 128, dtype=np.uint8)
        crop = np.zeros((112, 112, 3), dtype=np.uint8)
        assert client.submit(InferenceTask(TaskKind.DETECT, 1, 1, image=image), high_priority=True)
        assert client.submit(InferenceTask(TaskKind.EMBED, 2, 1, crops=[crop, crop]), high_priority=False)
        results = {}
        deadline = time.monotonic() + 60
        while len(results) < 2 and time.monotonic() < deadline:
            result = client.wait(timeout=1)
            if result is not None:
                results[result.request_id] = result
        assert results[1].ok and results[1].detections == []
        assert results[2].ok and results[2].embeddings is not None and results[2].embeddings.shape == (2, 128)
        assert results[2].matches is not None and results[2].matches[0][0].employee_code == "A"
        # Kill the worker: supervise() must bring a new one up.
        [stats] = pool.worker_stats()
        import os
        import signal

        os.kill(stats["pid"], signal.SIGKILL)
        time.sleep(0.5)
        pool.supervise()
        assert pool.restarts == 1
        deadline = time.monotonic() + 60
        client.submit(InferenceTask(TaskKind.DETECT, 3, 1, image=image), high_priority=True)
        reply = None
        while reply is None and time.monotonic() < deadline:
            reply = client.wait(timeout=1)
        assert reply is not None and reply.request_id == 3
    finally:
        pool.stop()
    with pytest.raises(queue.Empty):
        pool.queues.replies[1].get_nowait()
