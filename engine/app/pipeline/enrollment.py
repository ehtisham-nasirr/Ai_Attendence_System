"""Enrollment photo validation for `POST /embed` (FR-9, standards/14).

Exactly one face, face width >= minimum, quality above threshold, not blurred. The engine only
reports the outcome; whether a photo is stored is decided by the backend's enrollment service.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from facetrack_common.schemas.engine import EnrollmentRejection

from app.models.alignment import align_face
from app.models.base import Detector, Embedder, ImageBGR
from app.pipeline.quality import assess_quality, crop_box


@dataclass(frozen=True, slots=True)
class EnrollRules:
    detector_min_score: float
    min_face_width_px: int
    min_quality: float
    min_blur_variance: float


@dataclass(frozen=True, slots=True)
class EnrollOutcome:
    accepted: bool
    rejection_reason: EnrollmentRejection | None
    face_count: int
    face_width_px: int | None = None
    detector_score: float | None = None
    quality_score: float | None = None
    blur_variance: float | None = None
    embedding: npt.NDArray[np.float32] | None = None


def validate_and_embed(
    image: ImageBGR, detector: Detector, embedder: Embedder, rules: EnrollRules
) -> EnrollOutcome:
    faces = detector.detect(image, rules.detector_min_score)
    if not faces:
        return EnrollOutcome(False, "no_face", 0)
    if len(faces) > 1:
        return EnrollOutcome(False, "multiple_faces", len(faces))
    face = faces[0]
    width = round(face.width)
    quality = assess_quality(
        crop_box(image, face),
        face,
        min_face_width=rules.min_face_width_px,
        min_quality=rules.min_quality,
        min_blur_variance=rules.min_blur_variance,
    )

    def outcome(
        reason: EnrollmentRejection | None, embedding: npt.NDArray[np.float32] | None = None
    ) -> EnrollOutcome:
        return EnrollOutcome(
            accepted=reason is None,
            rejection_reason=reason,
            face_count=1,
            face_width_px=width,
            detector_score=face.score,
            quality_score=round(quality.score, 4),
            blur_variance=round(quality.blur_variance, 2),
            embedding=embedding,
        )

    if face.width < rules.min_face_width_px:
        return outcome("face_too_small")
    if quality.blur_variance < rules.min_blur_variance:
        return outcome("blurred")
    if quality.score < rules.min_quality:
        return outcome("low_quality")
    return outcome(None, embedder.embed([align_face(image, face.landmarks)])[0])
