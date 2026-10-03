"""Region of interest helpers (FR-5): crop to the ROI before detection, ignore faces outside it."""

from dataclasses import dataclass, field

import cv2
import numpy as np
import numpy.typing as npt


@dataclass
class Roi:
    """A normalised polygon ([[x, y], ...] in [0, 1]); `None` means the whole frame."""

    polygon: list[list[float]] | None = None
    _mask_cache: dict[tuple[int, int], npt.NDArray[np.uint8]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.polygon is not None and len(self.polygon) < 3:
            raise ValueError("an ROI polygon needs at least 3 points")

    def _points(self, width: int, height: int) -> npt.NDArray[np.int32]:
        if self.polygon is None:
            raise ValueError("no polygon")
        scaled = np.array(self.polygon, dtype=np.float64) * np.array([width, height])
        points: npt.NDArray[np.int32] = np.round(scaled).astype(np.int32)
        return points

    def bounding_rect(self, width: int, height: int) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) pixel box around the ROI, clipped to the frame."""
        if self.polygon is None:
            return 0, 0, width, height
        points = self._points(width, height)
        x0, y0 = np.clip(points.min(axis=0), 0, [width, height])
        x1, y1 = np.clip(points.max(axis=0) + 1, 0, [width, height])
        return int(x0), int(y0), int(x1), int(y1)

    def contains(self, x: float, y: float, width: int, height: int) -> bool:
        """True when pixel point (x, y) of a width x height frame is inside the ROI."""
        if self.polygon is None:
            return True
        contour = self._points(width, height).reshape(-1, 1, 2)
        return cv2.pointPolygonTest(contour, (float(x), float(y)), measureDist=False) >= 0

    def mask(self, width: int, height: int) -> npt.NDArray[np.uint8]:
        """255 inside the ROI, 0 outside; cached per frame size."""
        key = (width, height)
        if key not in self._mask_cache:
            mask = np.zeros((height, width), dtype=np.uint8)
            if self.polygon is None:
                mask[:] = 255
            else:
                cv2.fillPoly(mask, [self._points(width, height)], 255)
            self._mask_cache[key] = mask
        return self._mask_cache[key]
