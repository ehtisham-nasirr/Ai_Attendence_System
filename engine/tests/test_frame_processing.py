"""Motion gate, ROI, quality gate and latest-frame buffer (§10.1 steps 1-2, 6; §10.4)."""

from datetime import UTC, datetime

import cv2
import numpy as np
import pytest

from app.capture.frame_buffer import LatestFrameBuffer
from app.models.alignment import TEMPLATE_112
from app.models.base import FaceDetection
from app.pipeline.motion import MotionGate
from app.pipeline.quality import assess_quality, blur_variance, crop_box, pose_score
from app.pipeline.roi import Roi


def _scene(block_x: int | None = None) -> np.ndarray:
    rng = np.random.default_rng(3)
    frame = np.kron(rng.integers(40, 200, (90, 160, 3), dtype=np.uint8), np.ones((8, 8, 1), dtype=np.uint8))
    if block_x is not None:
        frame[300:500, block_x : block_x + 160] = 250
    return frame


def test_motion_detected_inside_roi_only() -> None:
    left_half = Roi([[0, 0], [0.5, 0], [0.5, 1], [0, 1]])
    gate = MotionGate(left_half, min_area_ratio=0.01)
    assert not gate.update(_scene())  # first frame primes the background
    assert not gate.update(_scene())  # static scene
    assert gate.update(_scene(block_x=100))  # block in the left half
    gate_right = MotionGate(left_half, min_area_ratio=0.01)
    gate_right.update(_scene())
    assert not gate_right.update(_scene(block_x=1000))  # block outside the ROI


def test_roi_bounding_rect_and_contains() -> None:
    roi = Roi([[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]])
    assert roi.bounding_rect(400, 200) == (100, 50, 301, 151)
    assert roi.contains(200, 100, 400, 200)
    assert not roi.contains(10, 10, 400, 200)
    assert Roi(None).bounding_rect(400, 200) == (0, 0, 400, 200)
    with pytest.raises(ValueError):
        Roi([[0, 0], [1, 1]])


def _frontal(width: float = 100.0) -> FaceDetection:
    landmarks = (TEMPLATE_112 * width / 112 + 100).astype(np.float32)
    return FaceDetection(100, 100, width, width * 1.2, landmarks, 0.9)


def test_blur_variance_separates_sharp_from_blurred() -> None:
    rng = np.random.default_rng(4)
    sharp = rng.integers(0, 255, (112, 112, 3), dtype=np.uint8)
    blurred = cv2.GaussianBlur(sharp, (0, 0), 4)
    assert blur_variance(sharp) > 10 * blur_variance(blurred)


def test_pose_score_prefers_frontal_faces() -> None:
    frontal = _frontal()
    turned = FaceDetection(
        100,
        100,
        100,
        120,
        frontal.landmarks + np.array([[0, 0], [0, 0], [30, 0], [0, 0], [0, 0]], dtype=np.float32),
        0.9,
    )
    assert pose_score(frontal) > 0.9
    assert pose_score(turned) < 0.3


def test_quality_gate_rejects_small_or_blurred_faces() -> None:
    rng = np.random.default_rng(5)
    sharp = rng.integers(0, 255, (120, 100, 3), dtype=np.uint8)
    good = assess_quality(sharp, _frontal(112), min_face_width=60, min_quality=0.35, min_blur_variance=40)
    assert good.passed and good.score > 0.8
    small = assess_quality(sharp, _frontal(50), min_face_width=60, min_quality=0.35, min_blur_variance=40)
    assert not small.passed
    blurred = cv2.GaussianBlur(sharp, (0, 0), 6)
    soft = assess_quality(blurred, _frontal(112), min_face_width=60, min_quality=0.35, min_blur_variance=40)
    assert not soft.passed


def test_crop_box_is_clipped_to_frame() -> None:
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    face = FaceDetection(150, 150, 60, 60, np.zeros((5, 2), dtype=np.float32), 0.9)
    # centre (180, 180), 120 px box -> x/y 120..240, clipped to 200: 80 x 80
    assert crop_box(frame, face, scale=2.0).shape[:2] == (80, 80)


def test_nfr15_latest_frame_buffer_overwrites_and_never_queues() -> None:
    buffer = LatestFrameBuffer()
    now = datetime.now(UTC)
    for value in range(5):
        buffer.put(False, now, lambda v=value: np.full((2, 2, 3), v, dtype=np.uint8))
    item = buffer.take_latest()
    assert item is not None and int(item.to_bgr()[0, 0, 0]) == 4
    assert buffer.frames_dropped == 4
    assert buffer.take_latest() is None  # nothing new
    buffer.put(True, now, lambda: np.zeros((2, 2, 3), dtype=np.uint8))
    assert buffer.take_latest() is not None
