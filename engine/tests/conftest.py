"""Shared fixtures. Tests use synthetic images/video only — never real faces (standards/18)."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from facetrack_common.crypto import Cipher, generate_key_b64
from pydantic import SecretStr

from app.config import EngineSettings
from app.gallery.index import MatchCandidate
from app.pipeline.best_crops import CropCandidate

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
YUNET = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE = MODELS_DIR / "face_recognition_sface_2021dec.onnx"


def models_available() -> bool:
    return YUNET.is_file() and SFACE.is_file()


@pytest.fixture
def key_b64() -> str:
    return generate_key_b64()


@pytest.fixture
def cipher(key_b64: str) -> Cipher:
    return Cipher.from_base64(key_b64)


@pytest.fixture
def engine_settings(key_b64: str, tmp_path: Path) -> EngineSettings:
    return EngineSettings(
        api_token=SecretStr("test-token"),
        database_url=SecretStr("postgresql+asyncpg://unused/unused"),
        redis_url=SecretStr("redis://localhost:6379/15"),
        encryption_key=SecretStr(key_b64),
        media_root=tmp_path / "media",
        detector_model_path=YUNET,
        embedder_model_path=SFACE,
        buffer_dir=tmp_path / "buffer",
        allow_file_sources=True,
        inference_workers=1,
        threads_per_worker=1,
    )


def make_crop(crop_id: int, quality: float = 0.8, value: int = 100) -> CropCandidate:
    return CropCandidate(
        crop_id=crop_id,
        quality=quality,
        aligned=np.full((112, 112, 3), value, dtype=np.uint8),
        snapshot=np.full((64, 64, 3), value, dtype=np.uint8),
        liveness_region=np.full((80, 80, 3), value, dtype=np.uint8),
        captured_at=datetime(2026, 10, 3, 4, 2, 11, tzinfo=UTC),
        bbox_norm=(0.1, 0.1, 0.2, 0.3),
    )


def matches(*pairs: tuple[str, float]) -> list[MatchCandidate]:
    return [MatchCandidate(code, score) for code, score in pairs]


@pytest.fixture(scope="session")
def sample_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from sample_video import write_sample_video

    path = tmp_path_factory.mktemp("clips") / "sample.mp4"
    return write_sample_video(path, seconds=6.0, width=640, height=360, motion_windows=((2.0, 4.0),))
