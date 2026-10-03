"""Model layer checked against OpenCV's reference implementations, on synthetic images only.

The YuNet post-processing, 5-point alignment and SFace preprocessing are re-implemented for
OpenVINO/ONNX Runtime; these tests prove they match OpenCV's `FaceDetectorYN` / `FaceRecognizerSF`.
"""

import cv2
import numpy as np
import pytest
from conftest import SFACE, YUNET, models_available

from app.models.alignment import TEMPLATE_112, align_face, similarity_transform
from app.models.embedders import SFaceEmbedder
from app.models.runtime import create_session
from app.models.yunet import YuNetDetector
from app.pipeline.enrollment import EnrollRules, validate_and_embed

pytestmark = pytest.mark.skipif(not models_available(), reason="model files not downloaded")
RUNTIMES = ["onnxruntime", "openvino"]


def _noise_image() -> np.ndarray:
    rng = np.random.default_rng(0)
    return cv2.GaussianBlur((rng.random((640, 640, 3)) * 255).astype(np.uint8), (0, 0), 3)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_yunet_decoding_matches_opencv_reference(runtime: str) -> None:
    image = _noise_image()
    reference = cv2.FaceDetectorYN.create(str(YUNET), "", (640, 640), 0.05, 0.3, 50)
    _, faces = reference.detect(image)
    ours = YuNetDetector(create_session(YUNET, runtime, 1)).detect(image, 0.05)  # type: ignore[arg-type]
    assert faces is not None and len(ours) == len(faces) > 0
    for mine, ref in zip(
        sorted(ours, key=lambda d: -d.score), sorted(faces, key=lambda f: -f[14]), strict=True
    ):
        assert mine.score == pytest.approx(float(ref[14]), abs=1e-3)
        np.testing.assert_allclose(mine.landmarks.reshape(-1), ref[4:14], atol=0.05)


def test_alignment_matches_opencv_align_crop() -> None:
    image = _noise_image()
    row = np.array(
        [200, 150, 120, 140, 230, 200, 290, 198, 262, 235, 240, 265, 285, 263, 0.9], dtype=np.float32
    )
    reference = cv2.FaceRecognizerSF.create(str(SFACE), "").alignCrop(image, row)
    ours = align_face(image, row[4:14].reshape(5, 2))
    assert np.abs(reference.astype(int) - ours.astype(int)).max() <= 1


def test_similarity_transform_recovers_known_transform() -> None:
    angle, scale = np.deg2rad(12), 1.7
    rotation = scale * np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    source = (TEMPLATE_112 - 20) @ rotation.T + np.array([5.0, -3.0])
    matrix = similarity_transform(source, TEMPLATE_112)
    mapped = source @ matrix[:, :2].T + matrix[:, 2]
    np.testing.assert_allclose(mapped, TEMPLATE_112, atol=1e-6)


@pytest.mark.parametrize("runtime", RUNTIMES)
def test_sface_embedding_matches_opencv_reference(runtime: str) -> None:
    rng = np.random.default_rng(1)
    face = rng.integers(0, 255, (112, 112, 3), dtype=np.uint8)
    reference = cv2.FaceRecognizerSF.create(str(SFACE), "").feature(face).reshape(-1)
    reference /= np.linalg.norm(reference)
    embedder = SFaceEmbedder(create_session(SFACE, runtime, 1))  # type: ignore[arg-type]
    [ours] = embedder.embed([face, face])[:1]
    assert float(ours @ reference) == pytest.approx(1.0, abs=1e-4)
    assert np.linalg.norm(ours) == pytest.approx(1.0, abs=1e-5)


def test_fr9_photo_without_a_face_is_rejected() -> None:
    detector = YuNetDetector(create_session(YUNET, "onnxruntime", 1))
    embedder = SFaceEmbedder(create_session(SFACE, "onnxruntime", 1))
    rules = EnrollRules(detector_min_score=0.6, min_face_width_px=112, min_quality=0.5, min_blur_variance=60)
    outcome = validate_and_embed(np.full((480, 640, 3), 128, dtype=np.uint8), detector, embedder, rules)
    assert not outcome.accepted and outcome.rejection_reason == "no_face" and outcome.embedding is None


def test_missing_model_file_has_a_clear_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(FileNotFoundError, match="download_models"):
        create_session(tmp_path / "nope.onnx", "onnxruntime", 1)
