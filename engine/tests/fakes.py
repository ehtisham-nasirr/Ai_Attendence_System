"""Scripted test doubles for detector, embedder and the pool client."""

from collections.abc import Sequence

import numpy as np

from app.gallery.index import GalleryIndex
from app.models.base import FaceDetection, ImageBGR
from app.scheduler.inference_pool import InferenceResult, InferenceTask, TaskKind


def face_at(x: float, y: float, width: float, score: float = 0.9) -> FaceDetection:
    s = width / 100
    landmarks = np.array([[35, 45], [65, 45], [50, 60], [38, 78], [62, 78]], dtype=np.float32) * s
    landmarks += np.array([x, y], dtype=np.float32)
    return FaceDetection(x, y, width, width * 1.2, landmarks, score)


class FakeDetector:
    name = "fake"

    def __init__(self, faces: list[FaceDetection]) -> None:
        self.faces = faces

    def detect(self, image: ImageBGR, score_threshold: float) -> list[FaceDetection]:
        return [f for f in self.faces if f.score >= score_threshold]


class FakeEmbedder:
    name = "sface"
    dim = 4

    def __init__(self, vector: Sequence[float] = (1.0, 0.0, 0.0, 0.0)) -> None:
        self.vector = np.array(vector, dtype=np.float32)
        self.calls = 0

    def embed(self, aligned_faces: Sequence[ImageBGR]) -> np.ndarray:
        self.calls += len(aligned_faces)
        return np.tile(self.vector, (len(aligned_faces), 1))


class InProcessClient:
    """Runs tasks synchronously with fake models, like a pool that is never busy."""

    def __init__(self, detector: FakeDetector, embedder: FakeEmbedder, gallery: GalleryIndex | None) -> None:
        self.slot = 1
        self._detector = detector
        self._embedder = embedder
        self._gallery = gallery
        self._next = 1
        self._replies: list[InferenceResult] = []
        self.submitted: list[InferenceTask] = []
        self.real_score = 0.95
        self.accept = True

    def new_request_id(self) -> int:
        self._next += 1
        return self._next

    def submit(self, task: InferenceTask, high_priority: bool) -> bool:
        if not self.accept:
            return False
        self.submitted.append(task)
        if task.kind == TaskKind.DETECT:
            assert task.image is not None
            result = InferenceResult(
                task.kind,
                task.request_id,
                True,
                detections=self._detector.detect(task.image, task.score_threshold),
            )
        elif task.kind == TaskKind.EMBED:
            embeddings = self._embedder.embed(task.crops or [])
            matches = self._gallery.search(embeddings) if self._gallery else [[] for _ in embeddings]
            result = InferenceResult(task.kind, task.request_id, True, embeddings=embeddings, matches=matches)
        else:
            result = InferenceResult(task.kind, task.request_id, True, real_score=self.real_score)
        self._replies.append(result)
        return True

    def poll(self, max_items: int = 64) -> list[InferenceResult]:
        replies, self._replies = self._replies, []
        return replies

    def kinds(self) -> list[TaskKind]:
        return [t.kind for t in self.submitted]
