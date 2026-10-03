"""Face quality gate (requirements §9 "Face quality", §10.1 step 6, FR-9).

Quality combines face size, sharpness, pose and detector confidence. Only crops that pass the
gate are kept as candidates for embedding, so blurred or turned-away frames can never vote (NFR-2).
"""

from dataclasses import dataclass

import cv2
import numpy as np

from app.models.alignment import TEMPLATE_112
from app.models.base import FaceDetection, ImageBGR

# Width at which size stops improving the score (the FR-9 ideal face width).
IDEAL_FACE_WIDTH_PX = 112.0
# Laplacian variance treated as "fully sharp" for a 112 px face.
SHARP_VARIANCE = 200.0
# Where a frontal nose sits between the eye line and the mouth line (from the canonical template).
FRONTAL_NOSE_RATIO = float(
    (TEMPLATE_112[2, 1] - TEMPLATE_112[:2, 1].mean())
    / (TEMPLATE_112[3:, 1].mean() - TEMPLATE_112[:2, 1].mean())
)
# Relative weights of the quality components; they sum to 1.
_WEIGHTS = {"size": 0.3, "sharpness": 0.25, "pose": 0.25, "detector": 0.2}


@dataclass(frozen=True, slots=True)
class QualityResult:
    score: float
    blur_variance: float
    size_score: float
    pose_score: float
    passed: bool


def blur_variance(face: ImageBGR) -> float:
    """Variance of the Laplacian on a 112 px-wide grayscale face; low means blurred."""
    height, width = face.shape[:2]
    if width == 0 or height == 0:
        return 0.0
    resized = cv2.resize(face, (112, max(1, round(height * 112 / width))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def pose_score(detection: FaceDetection) -> float:
    """1.0 for a frontal face, falling towards 0 as yaw/pitch grow (estimated from landmarks)."""
    right_eye, left_eye, nose, right_mouth, left_mouth = detection.landmarks.astype(np.float64)
    eye_distance = float(np.linalg.norm(left_eye - right_eye))
    if eye_distance < 1e-6:
        return 0.0
    eye_mid = (right_eye + left_eye) / 2
    mouth_mid = (right_mouth + left_mouth) / 2
    yaw = abs(float(nose[0] - eye_mid[0])) / eye_distance
    face_height = float(np.linalg.norm(mouth_mid - eye_mid))
    pitch = 0.0
    if face_height > 1e-6:
        pitch = abs(float(np.linalg.norm(nose - eye_mid)) / face_height - FRONTAL_NOSE_RATIO)
    return float(np.clip(1.0 - yaw * 1.6 - pitch * 1.5, 0.0, 1.0))


def assess_quality(
    face: ImageBGR,
    detection: FaceDetection,
    min_face_width: float,
    min_quality: float,
    min_blur_variance: float,
) -> QualityResult:
    """Scores one face crop and applies the gate."""
    variance = blur_variance(face)
    span = max(IDEAL_FACE_WIDTH_PX - min_face_width, 1.0)
    size = float(np.clip((detection.width - min_face_width) / span, 0.0, 1.0))
    sharpness = float(np.clip(variance / SHARP_VARIANCE, 0.0, 1.0))
    pose = pose_score(detection)
    score = (
        _WEIGHTS["size"] * size
        + _WEIGHTS["sharpness"] * sharpness
        + _WEIGHTS["pose"] * pose
        + _WEIGHTS["detector"] * float(np.clip(detection.score, 0.0, 1.0))
    )
    passed = detection.width >= min_face_width and variance >= min_blur_variance and score >= min_quality
    return QualityResult(score=score, blur_variance=variance, size_score=size, pose_score=pose, passed=passed)


def crop_box(frame: ImageBGR, detection: FaceDetection, scale: float = 1.0, square: bool = False) -> ImageBGR:
    """Crops the face box enlarged by `scale` around its centre, clipped to the frame."""
    height, width = frame.shape[:2]
    cx = detection.x + detection.width / 2
    cy = detection.y + detection.height / 2
    w = detection.width * scale
    h = detection.height * scale
    if square:
        w = h = max(w, h)
    x0, y0 = max(0, int(cx - w / 2)), max(0, int(cy - h / 2))
    x1, y1 = min(width, int(cx + w / 2)), min(height, int(cy + h / 2))
    return np.ascontiguousarray(frame[y0:y1, x0:x1])
