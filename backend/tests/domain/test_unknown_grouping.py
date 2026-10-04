"""Unknown-face grouping (§13 screen 9, Q58) on synthetic vectors (no real faces)."""

from datetime import UTC, datetime, timedelta

import numpy as np
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING

from app.core.crypto import get_cipher
from app.domain.recognition.grouping import FaceVector, group_faces

T0 = datetime(2026, 10, 5, 4, 0, tzinfo=UTC)
THRESHOLDS = {"sface": 0.36}


def _at_angle(degrees: float, dim: int = 128) -> np.ndarray:
    """A unit vector in the plane of the first two axes."""
    vector = np.zeros(dim, dtype=np.float32)
    vector[0], vector[1] = np.cos(np.radians(degrees)), np.sin(np.radians(degrees))
    return vector


def _face(face_id: int, minute: int, vector: np.ndarray | None, model: str = "sface") -> FaceVector:
    token = get_cipher().encrypt_embedding(vector, CRYPTO_PURPOSE_EMBEDDING) if vector is not None else None
    return FaceVector(
        face_id, T0 + timedelta(minutes=minute), model, token, len(vector) if vector is not None else None
    )


def test_screen9_centroid_keeps_a_drifting_person_together() -> None:
    # 0° -> 60° -> 75°: the third sighting is too far from the first (cos 0.26) but close to the
    # group's centre (30°, cos 0.71). The old first-face rule split it into a second card.
    faces = [_face(1, 0, _at_angle(0)), _face(2, 1, _at_angle(60)), _face(3, 2, _at_angle(75))]
    other = _face(4, 3, _at_angle(200))  # someone else
    groups = group_faces([*faces, other], THRESHOLDS)
    assert groups == {1: 1, 2: 1, 3: 1, 4: 4}


def test_screen9_grouping_is_deterministic_and_ids_are_stable() -> None:
    faces = [_face(i, i, _at_angle(angle)) for i, angle in enumerate((0, 10, 180, 170, 5), start=1)]
    groups = group_faces(faces, THRESHOLDS)
    assert groups == {1: 1, 2: 1, 5: 1, 3: 3, 4: 3}  # group id = id of the oldest face
    assert group_faces(list(reversed(faces)), THRESHOLDS) == groups  # input order does not matter
    # A newer sighting never changes the groups of older faces.
    newer = group_faces([*faces, _face(6, 10, _at_angle(90))], THRESHOLDS)
    assert {k: v for k, v in newer.items() if k != 6} == groups


def test_screen9_models_never_mixed_and_missing_embeddings_stand_alone() -> None:
    same = _at_angle(0)
    groups = group_faces(
        [_face(1, 0, same), _face(2, 1, same, model="arcface_r50"), _face(3, 2, None), _face(4, 3, same)],
        THRESHOLDS,
    )
    assert groups == {1: 1, 2: 2, 3: 3, 4: 1}


def test_nfr2_screen9_threshold_is_the_model_match_threshold() -> None:
    # cos(70°) = 0.34 is below the SFace threshold 0.36: two cards, nothing merged on a weak match.
    groups = group_faces([_face(1, 0, _at_angle(0)), _face(2, 1, _at_angle(70))], THRESHOLDS)
    assert groups == {1: 1, 2: 2}
