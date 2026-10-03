"""System settings (FR-38): validated per key, secrets encrypted at rest and masked in responses."""

import base64
from datetime import time
from typing import Any

from facetrack_common.constants import CRYPTO_PURPOSE_SETTING, CameraRole
from facetrack_common.models import User
from facetrack_common.settings_keys import SETTINGS, default_settings
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_cipher
from app.core.db import transaction
from app.core.exceptions import ValidationFailed
from app.domain.attendance.rules import RuleSettings, parse_hhmm
from app.domain.audit import service as audit
from app.repositories import system_repo
from app.schemas.system import SettingItem
from app.services import engine_client

SECRET_MASK = "********"  # noqa: S105  # display mask, not a secret
_ENCRYPTED_KEY = "enc"
# Changing any of these changes what the engine does, so engines re-sync their cameras.
_ENGINE_GROUPS = {"recognition", "engine"}


def _decrypt_if_secret(key: str, value: Any) -> Any:
    if SETTINGS[key].secret and isinstance(value, dict) and _ENCRYPTED_KEY in value:
        return get_cipher().decrypt_str(base64.b64decode(value[_ENCRYPTED_KEY]), CRYPTO_PURPOSE_SETTING)
    return value


async def resolved(db: AsyncSession) -> dict[str, Any]:
    """All settings with defaults filled in and secrets decrypted (internal use only)."""
    values = default_settings()
    for key, value in (await system_repo.all_settings(db)).items():
        if key in SETTINGS:
            values[key] = _decrypt_if_secret(key, value)
    return values


async def list_items(db: AsyncSession) -> list[SettingItem]:
    stored = await system_repo.all_settings(db)
    items = []
    for key, spec in SETTINGS.items():
        value = stored.get(key, spec.default)
        is_set = key in stored and value not in ("", None)
        items.append(
            SettingItem(
                key=key,
                group=spec.group,
                value=(SECRET_MASK if is_set else "") if spec.secret else value,
                default="" if spec.secret else spec.default,
                description=spec.description,
                secret=spec.secret,
                is_set=is_set,
            )
        )
    return items


async def update(db: AsyncSession, values: dict[str, Any], actor: User) -> list[SettingItem]:
    errors: dict[str, Any] = {}
    validated: dict[str, Any] = {}
    for key, value in values.items():
        spec = SETTINGS.get(key)
        if spec is None:
            errors[key] = ["Unknown setting."]
            continue
        if spec.secret and value == SECRET_MASK:
            continue  # unchanged secret
        try:
            validated[key] = spec.adapter.dump_python(spec.validate(value), mode="json")
        except ValueError as exc:
            errors[key] = [str(exc).splitlines()[0]]
    for hhmm_key in [k for k in validated if k.endswith("_time")]:
        try:
            parse_hhmm(str(validated[hhmm_key]))
        except ValueError:
            errors[hhmm_key] = ["Use HH:MM."]
    if errors:
        raise ValidationFailed(errors=errors)

    async with transaction(db):
        current = await resolved(db)
        for key, value in validated.items():
            stored = value
            if SETTINGS[key].secret and value:
                token = get_cipher().encrypt_str(str(value), CRYPTO_PURPOSE_SETTING)
                stored = {_ENCRYPTED_KEY: base64.b64encode(token).decode("ascii")}
            await system_repo.upsert_setting(db, key, stored)
        await audit.record(
            db,
            actor,
            "settings.update",
            "settings",
            None,
            old={k: (SECRET_MASK if SETTINGS[k].secret else current.get(k)) for k in validated},
            new={k: (SECRET_MASK if SETTINGS[k].secret else v) for k, v in validated.items()},
        )
    if any(SETTINGS[k].group in _ENGINE_GROUPS for k in validated):
        await engine_client.notify_engines("cameras_sync")
    return await list_items(db)


def rule_settings(values: dict[str, Any]) -> RuleSettings:
    """The attendance-rule view of the settings (requirements §10.3)."""
    return RuleSettings(
        day_close_time=parse_hhmm(str(values["attendance.day_close_time"])),
        night_shift_close_offset_min=int(values["attendance.night_shift_close_offset_min"]),
        duplicate_cooldown_min=int(values["attendance.duplicate_cooldown_min"]),
        checkin_roles=frozenset(CameraRole(r) for r in values["attendance.checkin_camera_roles"]),
        checkout_roles=frozenset(CameraRole(r) for r in values["attendance.checkout_camera_roles"]),
        overtime_enabled=bool(values["attendance.overtime_enabled"]),
        overtime_threshold_min=int(values["attendance.overtime_threshold_min"]),
    )


def local_time(values: dict[str, Any], key: str) -> time:
    return parse_hhmm(str(values[key]))
