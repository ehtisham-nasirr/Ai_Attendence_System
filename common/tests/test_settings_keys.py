"""Settings registry tests (FR-38)."""

import pytest
from pydantic import ValidationError

from facetrack_common.settings_keys import SETTINGS, default_settings, resolve_settings


def test_all_defaults_validate() -> None:
    for spec in SETTINGS.values():
        spec.validate(spec.default)


def test_nfr2_recognition_defaults_match_requirements_section_9() -> None:
    defaults = default_settings()
    assert defaults["recognition.match_thresholds"] == {"sface": 0.36, "arcface_r50": 0.45}
    assert defaults["recognition.margin"] == 0.08
    assert defaults["recognition.best_crops"] == 3
    assert defaults["recognition.min_votes"] == 2
    assert defaults["recognition.duplicate_warning_similarity"] == 0.6


def test_resolve_overrides_and_ignores_unknown_keys() -> None:
    resolved = resolve_settings({"recognition.margin": 0.1, "nope": 1})
    assert resolved["recognition.margin"] == 0.1
    assert "nope" not in resolved


def test_validation_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        SETTINGS["attendance.checkin_camera_roles"].validate(["DOOR"])
    with pytest.raises(ValidationError):
        SETTINGS["engine.peak_windows"].validate([{"start": "25:00", "end": "10:00"}])


def test_secret_keys_are_marked() -> None:
    assert SETTINGS["integration.payroll_webhook_url"].secret
    assert SETTINGS["notifications.teams_webhook_url"].secret
    assert not SETTINGS["recognition.margin"].secret
