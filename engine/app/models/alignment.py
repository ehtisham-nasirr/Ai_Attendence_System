"""5-point similarity alignment to a 112x112 crop (requirements §9 "Alignment")."""

import cv2
import numpy as np
import numpy.typing as npt

from app.models.base import ImageBGR

ALIGNED_SIZE = 112

# Canonical ArcFace/SFace landmark positions in a 112x112 crop
# (right eye, left eye, nose tip, right mouth corner, left mouth corner).
TEMPLATE_112 = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float64,
)


def similarity_transform(
    src: npt.NDArray[np.float64], dst: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Least-squares similarity transform (Umeyama 1991) mapping `src` points onto `dst`; returns 2x3."""
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_c = src - src_mean
    dst_c = dst - dst_mean
    covariance = dst_c.T @ src_c / len(src)
    u, singular, vt = np.linalg.svd(covariance)
    reflection = np.eye(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        reflection[1, 1] = -1.0
    rotation = u @ reflection @ vt
    src_var = (src_c**2).sum() / len(src)
    scale = float((singular * np.diag(reflection)).sum() / src_var) if src_var > 0 else 1.0
    translation = dst_mean - scale * rotation @ src_mean
    matrix = np.zeros((2, 3), dtype=np.float64)
    matrix[:, :2] = scale * rotation
    matrix[:, 2] = translation
    return matrix


def align_face(image: ImageBGR, landmarks: npt.NDArray[np.float32]) -> ImageBGR:
    """Warps the face so its landmarks land on the canonical template; returns a 112x112 BGR crop."""
    matrix = similarity_transform(landmarks.astype(np.float64), TEMPLATE_112)
    aligned = cv2.warpAffine(image, matrix, (ALIGNED_SIZE, ALIGNED_SIZE), borderValue=(0, 0, 0))
    return np.ascontiguousarray(aligned, dtype=np.uint8)
