"""FR-9 enrollment photo validation with scripted detections."""

import numpy as np
from fakes import FakeDetector, FakeEmbedder, face_at

from app.pipeline.enrollment import EnrollRules, validate_and_embed

RULES = EnrollRules(detector_min_score=0.6, min_face_width_px=112, min_quality=0.5, min_blur_variance=60)


def _textured() -> np.ndarray:
    return np.random.default_rng(7).integers(0, 255, (600, 600, 3), dtype=np.uint8)


def test_fr9_accepts_one_large_sharp_face() -> None:
    embedder = FakeEmbedder()
    outcome = validate_and_embed(_textured(), FakeDetector([face_at(200, 150, 160)]), embedder, RULES)
    assert outcome.accepted and outcome.embedding is not None
    assert outcome.face_width_px == 160 and embedder.calls == 1


def test_fr9_rejects_multiple_faces() -> None:
    outcome = validate_and_embed(
        _textured(), FakeDetector([face_at(10, 10, 150), face_at(300, 300, 150)]), FakeEmbedder(), RULES
    )
    assert outcome.rejection_reason == "multiple_faces" and outcome.face_count == 2


def test_fr9_rejects_small_face_without_embedding() -> None:
    embedder = FakeEmbedder()
    outcome = validate_and_embed(_textured(), FakeDetector([face_at(200, 150, 90)]), embedder, RULES)
    assert outcome.rejection_reason == "face_too_small" and embedder.calls == 0


def test_fr9_rejects_blurred_face() -> None:
    flat = np.full((600, 600, 3), 120, dtype=np.uint8)
    outcome = validate_and_embed(flat, FakeDetector([face_at(200, 150, 160)]), FakeEmbedder(), RULES)
    assert outcome.rejection_reason == "blurred"


def test_fr9_rejects_low_quality_pose() -> None:
    face = face_at(200, 150, 160)
    face.landmarks[2] += np.array([70, 0], dtype=np.float32)  # nose far to one side: strong yaw
    strict = EnrollRules(0.6, 112, min_quality=0.9, min_blur_variance=60)
    outcome = validate_and_embed(_textured(), FakeDetector([face]), FakeEmbedder(), strict)
    assert outcome.rejection_reason == "low_quality"
