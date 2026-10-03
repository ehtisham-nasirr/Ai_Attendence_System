"""Best-crop selection per track (requirements §10.1 steps 6-7, standards/17 §1).

Only the best `capacity` crops of a track are kept in memory, and only those are ever embedded.
A crop that has been embedded stays (its CPU is already spent); unembedded ones are replaced by
better crops as the person walks closer.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import numpy.typing as npt

from app.gallery.index import MatchCandidate
from app.models.base import ImageBGR


@dataclass
class CropCandidate:
    crop_id: int
    quality: float
    aligned: ImageBGR  # 112x112, input to the embedder
    snapshot: ImageBGR  # wider face crop, JPEG-encoded only if this crop becomes the event snapshot
    liveness_region: ImageBGR | None
    captured_at: datetime
    bbox_norm: tuple[float, float, float, float]
    matches: list[MatchCandidate] | None = None
    embedding: npt.NDArray[np.float32] | None = field(default=None, repr=False)

    @property
    def embedded(self) -> bool:
        return self.matches is not None


class BestCrops:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._crops: list[CropCandidate] = []

    def __len__(self) -> int:
        return len(self._crops)

    @property
    def crops(self) -> list[CropCandidate]:
        return sorted(self._crops, key=lambda c: c.quality, reverse=True)

    @property
    def embedded(self) -> list[CropCandidate]:
        return [c for c in self.crops if c.embedded]

    @property
    def unembedded(self) -> list[CropCandidate]:
        return [c for c in self.crops if not c.embedded]

    def best(self) -> CropCandidate | None:
        crops = self.crops
        return crops[0] if crops else None

    def offer(self, candidate: CropCandidate) -> bool:
        """Keeps the candidate if there is room or it beats the worst *unembedded* crop."""
        if len(self._crops) < self.capacity:
            self._crops.append(candidate)
            return True
        replaceable = [c for c in self._crops if not c.embedded]
        if not replaceable:
            return False
        worst = min(replaceable, key=lambda c: c.quality)
        if candidate.quality <= worst.quality:
            return False
        self._crops.remove(worst)
        self._crops.append(candidate)
        return True

    def record_embedding(
        self, crop_id: int, embedding: npt.NDArray[np.float32], matches: list[MatchCandidate]
    ) -> bool:
        for crop in self._crops:
            if crop.crop_id == crop_id:
                crop.embedding = embedding
                crop.matches = matches
                return True
        return False
