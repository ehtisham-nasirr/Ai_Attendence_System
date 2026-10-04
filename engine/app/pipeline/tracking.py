"""Face tracking with ByteTrack from `supervision` (requirements §10.1 step 5)."""

import numpy as np
import supervision as sv

# supervision >= 0.26 keeps ByteTrack only as a deprecated top-level alias; import it from its module.
from supervision.tracker.byte_tracker.core import ByteTrack

from app.models.base import FaceDetection


class FaceTracker:
    """Assigns a stable track id to each face across processed frames of one camera."""

    def __init__(self, frame_rate: float, lost_after_s: float) -> None:
        # ByteTrack drops a lost track after (frame_rate / 30) * lost_track_buffer frames.
        lost_track_buffer = max(1, round(lost_after_s * 30))
        self._tracker = ByteTrack(
            track_activation_threshold=0.5,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=0.8,
            frame_rate=max(frame_rate, 0.5),
            minimum_consecutive_frames=1,
        )

    def update(self, detections: list[FaceDetection]) -> list[tuple[int, FaceDetection]]:
        """Returns (track_id, detection) for every detection the tracker kept."""
        if not detections:
            self._tracker.update_with_detections(sv.Detections.empty())
            return []
        xyxy = np.array([[d.x, d.y, d.x + d.width, d.y + d.height] for d in detections], dtype=np.float32)
        tracked = self._tracker.update_with_detections(
            sv.Detections(
                xyxy=xyxy,
                confidence=np.array([d.score for d in detections], dtype=np.float32),
                class_id=np.zeros(len(detections), dtype=int),
                data={"index": np.arange(len(detections))},
            )
        )
        # ByteTrack returns an empty Detections without our "index" data when no track is confirmed
        # in this frame (e.g. a new face below the activation score); that is "no faces", not an error.
        if tracked.tracker_id is None or len(tracked) == 0 or "index" not in tracked.data:
            return []
        return [
            (int(track_id), detections[int(index)])
            for track_id, index in zip(tracked.tracker_id, tracked.data["index"], strict=True)
        ]
