"""Builds the configured models (swapping a model is a config change, standards/17 §5)."""

from app.config import EngineSettings
from app.models.base import Detector, Embedder, LivenessChecker
from app.models.embedders import ArcFaceEmbedder, SFaceEmbedder
from app.models.liveness import MiniFASNetLiveness
from app.models.runtime import create_session
from app.models.yunet import YuNetDetector

EMBEDDER_DIMS = {"sface": SFaceEmbedder.dim, "arcface_r50": ArcFaceEmbedder.dim}


def build_detector(settings: EngineSettings, threads: int) -> Detector:
    session = create_session(
        settings.detector_model_path, settings.runtime, threads, settings.openvino_precision
    )
    return YuNetDetector(session)


def build_embedder(settings: EngineSettings, threads: int) -> Embedder:
    session = create_session(
        settings.embedder_model_path, settings.runtime, threads, settings.openvino_precision
    )
    if settings.embedder == "arcface_r50":
        return ArcFaceEmbedder(session)
    return SFaceEmbedder(session)


def build_liveness(settings: EngineSettings, threads: int) -> LivenessChecker | None:
    if settings.liveness_model_path is None:
        return None
    session = create_session(
        settings.liveness_model_path, settings.runtime, threads, settings.openvino_precision
    )
    return MiniFASNetLiveness(
        session,
        input_size=settings.liveness_input_size,
        crop_scale=settings.liveness_crop_scale,
        real_class_index=settings.liveness_real_class_index,
    )
