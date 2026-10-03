"""Model interfaces (requirements §9, standards/17 §5).

Every model sits behind one of these interfaces so a model can be swapped by configuration.
Implementations run on CPU through OpenVINO or ONNX Runtime only.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

ImageBGR = npt.NDArray[np.uint8]
Embeddings = npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class FaceDetection:
    """A detected face in the coordinates of the image passed to the detector."""

    x: float
    y: float
    width: float
    height: float
    # 5 points (right eye, left eye, nose tip, right mouth corner, left mouth corner), shape (5, 2).
    landmarks: npt.NDArray[np.float32]
    score: float

    def shifted(self, dx: float, dy: float, scale: float = 1.0) -> "FaceDetection":
        """Maps a detection from a cropped/resized image back to the original frame."""
        return FaceDetection(
            x=self.x * scale + dx,
            y=self.y * scale + dy,
            width=self.width * scale,
            height=self.height * scale,
            landmarks=(self.landmarks * scale + np.array([dx, dy], dtype=np.float32)).astype(np.float32),
            score=self.score,
        )


class Detector(Protocol):
    name: str

    def detect(self, image: ImageBGR, score_threshold: float) -> list[FaceDetection]:
        """Returns faces with score >= threshold, in `image` pixel coordinates."""
        ...


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, aligned_faces: Sequence[ImageBGR]) -> Embeddings:
        """Embeds 112x112 aligned BGR faces; returns L2-normalised float32 vectors, shape (n, dim)."""
        ...


class LivenessChecker(Protocol):
    name: str
    input_size: int
    crop_scale: float

    def real_score(self, face_region: ImageBGR) -> float:
        """Probability in [0, 1] that the face is a real person (not a photo or screen)."""
        ...


def l2_normalise(vectors: npt.NDArray[np.float32]) -> Embeddings:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalised: Embeddings = (vectors / np.maximum(norms, 1e-12)).astype(np.float32)
    return normalised
