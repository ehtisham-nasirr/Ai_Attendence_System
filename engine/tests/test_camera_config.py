"""Runtime config resolution from camera rows + settings (§9 thresholds per camera, FR-18)."""

from typing import Any

import pytest
from facetrack_common.constants import CRYPTO_PURPOSE_CAMERA_URL, CameraRole
from facetrack_common.crypto import Cipher
from facetrack_common.models import Camera
from facetrack_common.settings_keys import default_settings

from app.scheduler.camera_config import CameraConfigError, build_runtime_config


def _camera(cipher: Cipher, **overrides: Any) -> Camera:
    camera = Camera(
        id=7,
        name="Lobby",
        role=CameraRole.ENTRY,
        engine_node="node-1",
        location_id=1,
        rtsp_url_encrypted=cipher.encrypt_str("rtsp://u:p@cam/main", CRYPTO_PURPOSE_CAMERA_URL),
        substream_url_encrypted=None,
        roi_polygon=None,
        fps=None,
        match_threshold=None,
        liveness_enabled=False,
        operating_hours=None,
    )
    for key, value in overrides.items():
        setattr(camera, key, value)
    return camera


def test_threshold_defaults_per_model_and_camera_override(cipher: Cipher) -> None:
    settings = default_settings()
    config = build_runtime_config(_camera(cipher), "Asia/Karachi", settings, cipher, "sface", False)
    assert config.match_threshold == 0.36 and config.margin == 0.08 and config.best_crops == 3
    assert config.main_url == "rtsp://u:p@cam/main"
    stricter = build_runtime_config(
        _camera(cipher, match_threshold=0.5), "UTC", settings, cipher, "sface", False
    )
    assert stricter.match_threshold == 0.5


def test_nfr2_unconfigured_model_has_no_silent_default(cipher: Cipher) -> None:
    with pytest.raises(CameraConfigError):
        build_runtime_config(_camera(cipher), "UTC", default_settings(), cipher, "other_model", False)


def test_fr18_liveness_without_model_refuses_to_run(cipher: Cipher) -> None:
    camera = _camera(cipher, liveness_enabled=True)
    with pytest.raises(CameraConfigError):
        build_runtime_config(camera, "UTC", default_settings(), cipher, "sface", liveness_available=False)
    general = _camera(cipher, liveness_enabled=True, role=CameraRole.GENERAL)
    config = build_runtime_config(
        general, "UTC", default_settings(), cipher, "sface", liveness_available=False
    )
    assert not config.liveness_required  # liveness applies to entrance cameras only


def test_fingerprint_changes_with_config(cipher: Cipher) -> None:
    settings = default_settings()
    a = build_runtime_config(_camera(cipher), "UTC", settings, cipher, "sface", False)
    b = build_runtime_config(_camera(cipher, fps=2.0), "UTC", settings, cipher, "sface", False)
    assert a.fingerprint() != b.fingerprint()
    assert (
        a.fingerprint()
        == build_runtime_config(_camera(cipher), "UTC", settings, cipher, "sface", False).fingerprint()
    )
