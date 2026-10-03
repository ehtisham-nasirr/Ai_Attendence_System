"""MiniFASNet passive liveness (Silent-Face-Anti-Spoofing, Apache-2.0) on CPU (FR-18).

Runs once on the best crop of a confirmed track on entrance cameras (standards/17 §6). The model
file must be converted from the official weights and pinned by SHA-256 (docs/open-questions.md Q4).
"""

import cv2
import numpy as np

from app.models.base import ImageBGR
from app.models.runtime import InferenceSession


class MiniFASNetLiveness:
    name = "minifasnet"

    def __init__(
        self, session: InferenceSession, input_size: int, crop_scale: float, real_class_index: int
    ) -> None:
        self._session = session
        self.input_size = input_size
        self.crop_scale = crop_scale
        self._real_index = real_class_index

    def real_score(self, face_region: ImageBGR) -> float:
        resized = cv2.resize(face_region, (self.input_size, self.input_size))
        tensor = resized.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
        logits = next(iter(self._session.run(tensor).values())).reshape(-1).astype(np.float64)
        exp = np.exp(logits - logits.max())
        probabilities = exp / exp.sum()
        return float(probabilities[self._real_index])
