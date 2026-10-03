"""Face embedders on OpenVINO / ONNX Runtime CPU (requirements §9).

- `SFaceEmbedder`: OpenCV Zoo SFace, 128-d, permissive licence — the default (docs/open-questions.md Q3).
- `ArcFaceEmbedder`: InsightFace ArcFace R50 (`w600k_r50`), 512-d. Its released weights need an
  InsightFace commercial licence before production use; not enabled by default.
"""

from collections.abc import Sequence

import cv2
import numpy as np

from app.models.alignment import ALIGNED_SIZE
from app.models.base import Embeddings, ImageBGR, l2_normalise
from app.models.runtime import InferenceSession


class _OnnxEmbedder:
    name: str
    dim: int

    def __init__(self, session: InferenceSession) -> None:
        self._session = session
        # Fixed batch-1 models are run once per face; dynamic-batch models take the whole batch.
        self._dynamic_batch = session.input_shape[0] == -1

    def _preprocess(self, face: ImageBGR) -> np.ndarray:
        raise NotImplementedError

    def embed(self, aligned_faces: Sequence[ImageBGR]) -> Embeddings:
        if not aligned_faces:
            return np.zeros((0, self.dim), dtype=np.float32)
        for face in aligned_faces:
            if face.shape[:2] != (ALIGNED_SIZE, ALIGNED_SIZE):
                raise ValueError("faces must be aligned 112x112 crops")
        tensors = [self._preprocess(face) for face in aligned_faces]
        if self._dynamic_batch:
            raw = next(iter(self._session.run(np.stack(tensors)).values()))
        else:
            raw = np.concatenate([next(iter(self._session.run(t[np.newaxis]).values())) for t in tensors])
        vectors = raw.reshape(len(aligned_faces), -1).astype(np.float32)
        if vectors.shape[1] != self.dim:
            raise ValueError(f"{self.name} produced {vectors.shape[1]}-d vectors, expected {self.dim}")
        return l2_normalise(vectors)


class SFaceEmbedder(_OnnxEmbedder):
    """Input: RGB, 0-255 float, no mean subtraction (as OpenCV FaceRecognizerSF)."""

    name = "sface"
    dim = 128

    def _preprocess(self, face: ImageBGR) -> np.ndarray:
        rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        return rgb.transpose(2, 0, 1).astype(np.float32)


class ArcFaceEmbedder(_OnnxEmbedder):
    """Input: RGB, (x - 127.5) / 127.5 (InsightFace convention)."""

    name = "arcface_r50"
    dim = 512

    def _preprocess(self, face: ImageBGR) -> np.ndarray:
        rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32)
        return ((rgb - 127.5) / 127.5).transpose(2, 0, 1)
