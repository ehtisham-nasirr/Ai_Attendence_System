"""Engine configuration from the environment (pydantic-settings, standards/06).

Node-level, environment-specific values live here. Recognition thresholds, FPS rates, cooldowns and
ladder limits are business configuration and come from the `settings` table instead
(`facetrack_common.settings_keys`).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENGINE_", env_file=".env", extra="ignore")

    environment: Literal["development", "staging", "production"] = "development"
    node_name: str = Field(default="node-1", min_length=1, max_length=64)
    log_level: str = "INFO"

    # Shared secret the backend sends in `X-Engine-Token`; the API is also kept on the internal network.
    api_token: SecretStr
    database_url: SecretStr
    redis_url: SecretStr
    # Base64 AES-256 key, shared with the backend (NFR-8).
    encryption_key: SecretStr

    # Object storage for snapshots (ADR-0005): "local" = a mounted volume shared with the backend,
    # "s3" = any S3-compatible server.
    storage_backend: Literal["local", "s3"] = "local"
    media_root: Path = Path("/srv/media")
    s3_endpoint: str = ""
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    s3_secure: bool = True
    s3_bucket: str = "facetrack"

    # --- models (standards/17 §5): swapping a model is a config change ---
    runtime: Literal["openvino", "onnxruntime"] = "openvino"
    # f32 unless bf16 has passed scripts/evaluate.py on the reference set (accuracy first, NFR-2).
    openvino_precision: Literal["f32", "bf16"] = "f32"
    detector: Literal["yunet"] = "yunet"
    detector_model_path: Path = Path("models/face_detection_yunet_2023mar.onnx")
    detector_input_size: int = 640
    embedder: Literal["sface", "arcface_r50"] = "sface"
    embedder_model_path: Path = Path("models/face_recognition_sface_2021dec.onnx")
    # MiniFASNet ONNX; None disables liveness, and cameras with liveness enabled then refuse to start.
    liveness_model_path: Path | None = None
    liveness_input_size: int = 80
    liveness_crop_scale: float = 2.7
    liveness_real_class_index: int = 1

    # --- CPU budget (standards/17 §4) ---
    inference_workers: int = Field(default=2, ge=1, le=64)
    threads_per_worker: int = Field(default=2, ge=1, le=16)
    # Cores reserved for inference workers, e.g. "2-7" or "2,3,4,5"; empty = no pinning.
    inference_cores: str = ""
    decoder_threads: int = Field(default=1, ge=1, le=4)

    # --- bounded queues (standards/17 §3: no unbounded queue anywhere) ---
    max_cameras: int = Field(default=32, ge=1, le=256)
    high_queue_size: int = 32
    low_queue_size: int = 64
    response_queue_size: int = 32
    embed_batch_max: int = Field(default=8, ge=1, le=8)
    embed_batch_wait_ms: int = Field(default=50, ge=0, le=50)
    request_timeout_s: float = 3.0
    deferred_embed_max: int = 64
    publish_queue_size: int = 64
    status_queue_size: int = 512

    # --- resilience (standards/17 §8, FR-4, NFR-7) ---
    watchdog_no_frame_s: float = 10.0
    reconnect_min_s: float = 2.0
    reconnect_max_s: float = 60.0
    stream_open_timeout_s: float = 10.0
    stream_read_timeout_s: float = 10.0
    worker_memory_limit_mb: int = 1500
    buffer_dir: Path = Path("buffer")
    buffer_max_events: int = 10_000
    buffer_max_mb: int = 2048

    status_interval_s: float = 1.0
    snapshot_jpeg_quality: int = Field(default=85, ge=50, le=95)
    # Dev only: lets a camera URL be a local video file (looped in real time).
    allow_file_sources: bool = False


@lru_cache
def get_settings() -> EngineSettings:
    return EngineSettings()  # required values come from the environment
