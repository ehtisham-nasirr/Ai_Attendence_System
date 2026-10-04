"""Grouping of unknown faces that look like the same person (§13 screen 9, FR-17, FR-27).

The review screen shows one card per person. Embeddings are decrypted in memory only (ADR-0001)
and never leave this module.

Method (docs/open-questions.md Q58): faces are taken oldest first. Each face joins the group whose
centroid (normalised mean of its members) is most similar, if that similarity reaches the model's
match threshold; otherwise it starts a new group. Faces from different models are never compared,
and a face without an embedding is a group of its own.

- A centroid is a steadier picture of a person than any one sighting, so one person stays in one
  group more often than with the old "compare with the first face of each group" rule.
- Risk: once a wrong face joins, the centroid moves between two people and can pull in more of the
  second person. The reviewer sees the thumbnails and the face count before any decision, and a
  group is only a suggestion: nothing is assigned without a person choosing the employee.

The result is deterministic, and a group's id is the id of its oldest face. Newer faces never change
the groups of older ones, so ids stay the same while faces arrive; they can change when older faces
leave the set (reviewed, deleted by retention, or past the `max_faces` limit).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING

from app.core.crypto import get_cipher

# Used when a model has no threshold in the settings (same fallback as before this module).
FALLBACK_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class FaceVector:
    """The parts of an unknown face the grouping needs."""

    id: int
    captured_at: datetime
    model_name: str
    embedding_encrypted: bytes | None
    embedding_dim: int | None


def cluster(vectors: npt.NDArray[np.float32], threshold: float) -> npt.NDArray[np.int64]:
    """Group index of each row. Rows are L2-normalised and in processing order (oldest first).

    Each row is compared with every current centroid in one matrix-vector product; the first best
    group wins a tie, so the result never depends on anything but the input order. The product uses
    `einsum`, which runs on one core: the multi-threaded BLAS call it replaces took every core and,
    under load, 6-16 s instead of about 1 s for 5,000 distinct 512-d faces (Q58).
    """
    count, dim = vectors.shape
    sums = np.zeros((count, dim), dtype=np.float32)
    centroids = np.zeros((count, dim), dtype=np.float32)
    labels = np.empty(count, dtype=np.int64)
    groups = 0
    for row in range(count):
        vector = vectors[row]
        target = -1
        if groups:
            scores = np.einsum("ij,j->i", centroids[:groups], vector)
            best = int(np.argmax(scores))
            if float(scores[best]) >= threshold:
                target = best
        if target < 0:
            target = groups
            groups += 1
        labels[row] = target
        sums[target] += vector
        centroids[target] = sums[target] / max(float(np.linalg.norm(sums[target])), 1e-12)
    return labels


def group_faces(faces: Iterable[FaceVector], thresholds: dict[str, float]) -> dict[int, int]:
    """Maps every face id to its group id (the id of the oldest face in the group)."""
    ordered = sorted(faces, key=lambda f: (f.captured_at, f.id))
    cipher = get_cipher()
    by_model: dict[tuple[str, int], list[tuple[int, npt.NDArray[np.float32]]]] = defaultdict(list)
    groups: dict[int, int] = {}
    for face in ordered:
        if not face.embedding_encrypted or not face.embedding_dim:
            groups[face.id] = face.id
            continue
        vector = cipher.decrypt_embedding(
            face.embedding_encrypted, CRYPTO_PURPOSE_EMBEDDING, face.embedding_dim
        )
        norm = max(float(np.linalg.norm(vector)), 1e-12)
        by_model[(face.model_name, face.embedding_dim)].append((face.id, (vector / norm).astype(np.float32)))
    for (model_name, _), members in by_model.items():
        matrix = np.stack([vector for _, vector in members])
        labels = cluster(matrix, float(thresholds.get(model_name, FALLBACK_THRESHOLD)))
        seed: dict[int, int] = {}
        for (face_id, _), label in zip(members, labels.tolist(), strict=True):
            groups[face_id] = seed.setdefault(label, face_id)
    return groups
