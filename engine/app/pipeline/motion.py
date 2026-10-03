"""Motion gate (requirements §10.1 step 2): the cheapest check, run on a 320 px frame inside the ROI."""

import cv2
import numpy as np
import numpy.typing as npt

from app.models.base import ImageBGR
from app.pipeline.roi import Roi

MOTION_FRAME_WIDTH = 320
# Per-pixel intensity change that counts as "moved" and the background adaptation rate. These shape
# the algorithm, not business behaviour; the area threshold that decides motion is configuration.
_PIXEL_DELTA = 25
_BACKGROUND_ALPHA = 0.05


class MotionGate:
    def __init__(self, roi: Roi, min_area_ratio: float) -> None:
        self._roi = roi
        self._min_area_ratio = min_area_ratio
        self._background: npt.NDArray[np.float32] | None = None
        self.last_ratio = 0.0

    def reset(self) -> None:
        self._background = None

    def update(self, frame: ImageBGR) -> bool:
        """Feeds one frame; returns True when enough of the ROI changed since the background."""
        height, width = frame.shape[:2]
        small_h = max(1, round(height * MOTION_FRAME_WIDTH / width))
        small = cv2.resize(frame, (MOTION_FRAME_WIDTH, small_h), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        if self._background is None or self._background.shape != gray.shape:
            self._background = gray.astype(np.float32)
            self.last_ratio = 0.0
            return False
        delta = cv2.absdiff(gray, cv2.convertScaleAbs(self._background))
        mask = self._roi.mask(MOTION_FRAME_WIDTH, small_h)
        moved = cv2.countNonZero(cv2.bitwise_and((delta > _PIXEL_DELTA).astype(np.uint8) * 255, mask))
        roi_area = max(1, cv2.countNonZero(mask))
        cv2.accumulateWeighted(gray.astype(np.float32), self._background, _BACKGROUND_ALPHA)
        self.last_ratio = moved / roi_area
        return self.last_ratio >= self._min_area_ratio
