"""FaceTracker with the real supervision ByteTrack (requirements §10.1 step 5, FR-4: camera must not crash)."""

import numpy as np

from app.models.base import FaceDetection
from app.pipeline.tracking import FaceTracker


def _face(x: float, score: float = 0.9) -> FaceDetection:
    return FaceDetection(x=x, y=50, width=80, height=80, landmarks=np.zeros((5, 2), np.float32), score=score)


def test_same_face_keeps_its_track_id() -> None:
    tracker = FaceTracker(frame_rate=8, lost_after_s=2.0)
    first = tracker.update([_face(100)])
    second = tracker.update([_face(104)])
    assert len(first) == 1 and len(second) == 1
    assert first[0][0] == second[0][0]
    assert second[0][1].x == 104


def test_frame_without_confirmed_track_returns_nothing_instead_of_crashing() -> None:
    """Regression: a frame where ByteTrack confirms no track used to raise KeyError('index') and kill
    the camera process (seen with a real webcam clip)."""
    tracker = FaceTracker(frame_rate=8, lost_after_s=2.0)
    assert len(tracker.update([_face(100)])) == 1
    assert tracker.update([_face(300, score=0.3)]) == []  # low-score face only
    assert tracker.update([_face(500, score=0.62)]) == []  # new face not yet confirmed
    assert tracker.update([]) == []


def test_tracking_continues_after_an_empty_frame() -> None:
    tracker = FaceTracker(frame_rate=8, lost_after_s=2.0)
    track_id = tracker.update([_face(100)])[0][0]
    assert tracker.update([_face(300, score=0.3)]) == []
    again = tracker.update([_face(104)])
    assert [tid for tid, _ in again] == [track_id]
