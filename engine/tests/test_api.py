"""Internal engine API: token, envelope, /embed validation, health (§12.2, standards/04)."""

import io
from typing import Any

import cv2
import numpy as np
import pytest
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING
from facetrack_common.crypto import Cipher
from facetrack_common.schemas.engine import EngineHealth, GalleryReloadResult
from fastapi.testclient import TestClient

from app.config import EngineSettings
from app.main import create_app
from app.pipeline.enrollment import EnrollOutcome
from app.scheduler.supervisor import EngineUnavailableError


class FakeSupervisor:
    def __init__(self, settings: EngineSettings) -> None:
        self.settings = settings
        self.cipher = Cipher.from_base64(settings.encryption_key.get_secret_value())
        self.outcome: EnrollOutcome | Exception = EnrollOutcome(
            True, None, 1, 140, 0.95, 0.8, 120.0, np.ones(128, dtype=np.float32) / np.sqrt(128)
        )

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def embed_image(self, image: Any) -> EnrollOutcome:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def reload_gallery(self) -> GalleryReloadResult:
        return GalleryReloadResult(model_name="sface", employees=2, embeddings=6, version=3)

    async def health(self) -> EngineHealth:
        return EngineHealth(
            node="node-1",
            status="ok",
            workers_alive=1,
            cameras_running=0,
            gallery_version=3,
            redis_ok=True,
            database_ok=True,
        )


@pytest.fixture
def client(engine_settings: EngineSettings) -> TestClient:
    app = create_app(engine_settings, supervisor_factory=FakeSupervisor)  # type: ignore[arg-type]
    with TestClient(app) as test_client:
        yield test_client  # type: ignore[misc]


def _jpeg() -> bytes:
    ok, data = cv2.imencode(".jpg", np.full((300, 300, 3), 120, dtype=np.uint8))
    assert ok
    return data.tobytes()


AUTH = {"X-Engine-Token": "test-token"}


def test_token_is_required(client: TestClient) -> None:
    response = client.post("/gallery/reload")
    assert response.status_code == 401
    assert response.json() == {"success": False, "message": "Invalid engine token.", "errors": {}}
    assert client.post("/gallery/reload", headers={"X-Engine-Token": "wrong"}).status_code == 401


def test_gallery_reload_envelope(client: TestClient) -> None:
    body = client.post("/gallery/reload", headers=AUTH).json()
    assert body["success"] is True and body["data"]["version"] == 3


def test_fr9_embed_returns_encrypted_embedding(client: TestClient, engine_settings: EngineSettings) -> None:
    response = client.post(
        "/embed", headers=AUTH, files={"image": ("a.jpg", io.BytesIO(_jpeg()), "image/jpeg")}
    )
    data = response.json()["data"]
    assert response.status_code == 200 and data["accepted"] and data["embedding_dim"] == 128
    import base64

    cipher = Cipher.from_base64(engine_settings.encryption_key.get_secret_value())
    vector = cipher.decrypt_embedding(
        base64.b64decode(data["embedding_encrypted"]), CRYPTO_PURPOSE_EMBEDDING, 128
    )
    assert vector.shape == (128,)


def test_embed_rejects_non_images_by_content(client: TestClient) -> None:
    response = client.post(
        "/embed", headers=AUTH, files={"image": ("a.jpg", io.BytesIO(b"GIF89a..."), "image/jpeg")}
    )
    assert response.json()["data"]["rejection_reason"] == "invalid_image"
    huge = b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024 + 1)
    response = client.post("/embed", headers=AUTH, files={"image": ("a.jpg", io.BytesIO(huge), "image/jpeg")})
    assert response.json()["data"]["rejection_reason"] == "invalid_image"


def test_embed_returns_503_when_engine_busy(client: TestClient) -> None:
    client.app.state.supervisor.outcome = EngineUnavailableError("busy")  # type: ignore[attr-defined]
    response = client.post(
        "/embed", headers=AUTH, files={"image": ("a.jpg", io.BytesIO(_jpeg()), "image/jpeg")}
    )
    assert response.status_code == 503 and response.json()["success"] is False


def test_validation_error_uses_envelope(client: TestClient) -> None:
    response = client.post("/cameras/test", headers=AUTH, json={"camera_id": 0})
    assert response.status_code == 422
    assert response.json()["success"] is False and "camera_id" in response.json()["errors"]


def test_health_and_metrics_are_public(client: TestClient) -> None:
    assert client.get("/health").json()["data"]["status"] == "ok"
    assert client.get("/metrics").status_code == 200
